import json
from collections import deque
from xml.etree.ElementTree import (Element, SubElement)
import xml.etree.ElementTree as ET
from ODLConnector import ODLConnector
from time import sleep


class FlowModifier:
    fl = None

    @staticmethod
    def get_flow_modifier():
        if FlowModifier.fl is None:
            FlowModifier.fl = FlowModifier({}, ODLConnector("http://172.16.0.120:8181"))
        return FlowModifier.fl

    PROXY_TO_MULTI = 1
    FORWARD = 2
    CONVERT_TO_UNI = 3
    CLIENT_TO_MULTI = 4
    streams = {}
    odl = None
    parent_id = "host:10:10:10:10:10:10"
    gateway_mac = ""

    def __init__(self, streams, odl):
        self.streams = streams
        self.odl = odl

    def upsert_stream(self, stream):
        self.streams[stream.stream_id] = stream

    def remove_stream(self, stream_id):
        del self.streams[stream_id]
        a, b, switches, c = self.get_topology()

        for key, switch in switches.items():
            self.odl.delete_request("opendaylight-inventory:nodes/node/" + switch.id + "/table/0/flow/" + str(stream_id))
            self.odl.delete_request("opendaylight-inventory:nodes/node/" + switch.id + "/table/0/flow/" + str(stream_id + 50))
            self.odl.delete_request("opendaylight-inventory:nodes/node/" + switch.id + "/flow-node-inventory:group/" + str(stream_id))
            self.odl.delete_request("opendaylight-inventory:nodes/node/" + switch.id + "/flow-node-inventory:group/" + str(stream_id + 50))

    def get_topology(self):
        response = self.odl.get_request("network-topology:network-topology")

        nodes = {}
        ip_addresses = {}
        switches = {}

        class Node:
            def __init__(self):
                self.id = ""
                self.ip = ""
                self.parent = None
                self.mac = ""

        class Switch:
            def __init__(self):
                self.id = ""
                self.links = {}
                self.outlinks = {}
                self.parent = None
                self.actions = {}
                self.active_flows = []

            def add_action(self, stream_id, action):
                if stream_id not in self.actions.keys():
                    self.actions[stream_id] = []
                self.actions[stream_id].append(action)


        top_switch = None
        # build graph
        for node in response["network-topology"]["topology"][0]["node"]:
            if "host" in node["node-id"]:
                n = Node()
                n.id = node["node-id"]
                n.ip = node["host-tracker-service:addresses"][0]["ip"]
                n.mac = node["host-tracker-service:addresses"][0]["mac"]
                nodes[n.id] = n
                ip_addresses[n.ip] = n
            elif "openflow" in node["node-id"]:
                s = Switch()
                s.id = node["node-id"]
                switches[s.id] = s
        for link in response["network-topology"]["topology"][0]["link"]:
            source = switches[link["source"]["source-node"]] if link["source"]["source-node"] in switches else None
            source = nodes[link["source"]["source-node"]] if link["source"]["source-node"] in nodes else source
            if source is None:
                raise "Could not find source"
            if "openflow" in link["source"]["source-node"]:
                if "host" in link["destination"]["dest-node"]:
                    source.links[link["source"]["source-tp"]] = nodes[link["destination"]["dest-node"]]
                elif "openflow" in link["destination"]["dest-node"]:
                    source.links[link["source"]["source-tp"]] = switches[link["destination"]["dest-node"]]
                source.outlinks[link["destination"]["dest-node"]] = link["source"]["source-tp"]
            elif "host" in link["source"]["source-node"]:
                nodes[link["source"]["source-node"]].parent = switches[link["destination"]["dest-node"]]
                if link["source"]["source-node"] == self.parent_id:
                    top_switch = switches[link["destination"]["dest-node"]]

        queue = deque([top_switch])
        while len(queue) is not 0:
            node = queue.popleft()
            if type(node) is Switch:
                for key, child in node.links.items():
                    if child.parent is None:
                        child.parent = node
                        queue.append(child)
        top_switch.parent = None

        return nodes, ip_addresses, switches, top_switch

    def update_flows(self):
        nodes, ip_addresses, switches, top_switch = self.get_topology()

        class Action:
            def __init__(self, type, src_ip=None, dst_ip=None, src_mac=None, dst_mac=None,
                         src_port=None, dst_port=None, switch_port=None):
                self.type = type
                self.switch_port = switch_port
                self.src_ip = src_ip
                self.dst_ip = dst_ip
                self.src_mac = src_mac
                self.dst_mac = dst_mac
                self.src_port = src_port
                self.dst_port = dst_port

        for key, stream in self.streams.items():
            stream.fake_dst_mac = ip_addresses[stream.fake_dst_ip].mac
            stream.fake_src_mac = ip_addresses[stream.fake_src_ip].mac

            for ip in stream.ip_addresses:
                node = ip_addresses[ip]
                switch = node.parent
                # Convert back to uni
                a = Action(self.CONVERT_TO_UNI, dst_ip=node.ip, dst_mac=node.mac, src_port=stream.fake_dst_port,
                           dst_port=stream.ip_addresses[node.ip][0], switch_port=node.parent.outlinks[node.id],
                           src_mac=stream.fake_dst_mac, src_ip=stream.fake_dst_ip)
                switch.add_action(stream.stream_id, a)
                a = Action(self.CLIENT_TO_MULTI, switch_port=switch.outlinks[switch.parent.id], dst_ip=stream.fake_dst_ip,
                           dst_port=stream.fake_dst_port, src_port=stream.ip_addresses[node.ip][0])
                switch.add_action(stream.stream_id + 50, a)
                last_switch = switch
                if switch.parent is not None:
                    switch = switch.parent
                while switch is not top_switch:
                    # forward along
                    a = Action(self.FORWARD, switch_port=switch.outlinks[last_switch.id])
                    switch.add_action(stream.stream_id, a)
                    a = Action(self.FORWARD, switch_port=switch.outlinks[switch.parent.id])
                    switch.add_action(stream.stream_id + 50, a)
                    last_switch = switch
                    switch = switch.parent
                # Convert to multi
                a = Action(self.PROXY_TO_MULTI, switch_port=switch.outlinks[last_switch.id], dst_ip=stream.fake_src_ip,
                           dst_port=stream.fake_src_port)
                switch.add_action(stream.stream_id, a) # for proxy
                a = Action(self.CONVERT_TO_UNI, switch_port=switch.outlinks[self.parent_id], src_ip=stream.fake_src_ip,
                           src_mac=stream.fake_src_mac, src_port=stream.fake_src_port,
                           dst_ip=nodes[self.parent_id].ip, dst_port=80, dst_mac=nodes[self.parent_id].mac)
                switch.add_action(stream.stream_id + 50, a)

        for key, switch in switches.items():
            self.push_group(switch)
            self.push_flow(switch)

        sleep(.25)

    def push_flow(self, switch):
        table = {}
        table["id"] = 0
        table["flow"] = []
        flows = table["flow"]
        full = {"table":[table]}
        counter = 5

        for stream_id in switch.actions:
            counter = counter + 1
            flow = dict()
            flow["id"] = stream_id
            flow["table_id"] = 0
            flow["installHw"] = True
            flow["priority"] = 101
            flow["idle-timeout"] = 10
            flow["hard-timeout"] = 60
            flow["cookie"] = stream_id*100
            flow["flow-name"] = "stream" + str(stream_id)
            flow["match"] = {}
            flow["instructions"] = {"instruction": [
                {
                    "apply-actions": {
                        "action": [
                            {
                                "group-action": {"group-id": stream_id},
                                "order": 0
                            }
                        ]
                    },
                    "order": 0
                }
            ]}
            instructions = flow["instructions"]["instruction"]
            inst_counter = 0
            for action in switch.actions[stream_id]:
                if action.type is self.PROXY_TO_MULTI:
                    flow["match"] = {"ipv4-destination": action.dst_ip + "/32",
                                     "tcp-destination-port": action.dst_port,
                                     "ethernet-match": {"ethernet-type": {"type": "2048"}},
                                     "ip-match": {"ip-protocol": "6"}
                                     }
                elif action.type is self.CLIENT_TO_MULTI:
                    flow["match"] = {"ipv4-destination": action.dst_ip + "/32", "tcp-destination-port": action.dst_port,
                                     "tcp-source-port": action.src_port,
                                     "ethernet-match": {"ethernet-type": {"type": "2048"}},
                                     "ip-match": {"ip-protocol": "6"}
                                     }
                elif action.type is self.FORWARD:
                    flow["match"] = {"protocol-match-fields": {"mpls-label": stream_id},
                                     "ethernet-match": {"ethernet-type": {"type": "34887"}}}
                elif action.type is self.CONVERT_TO_UNI:
                    flow["match"] = {"protocol-match-fields": {"mpls-label": stream_id},
                                     "ethernet-match": {"ethernet-type": {"type": "34887"}}}

            #flows.append(flow)
            print("Sending this data to " + switch.id  + " flow " + str(stream_id))
            print(flow)
            data = json.dumps({"flow":[flow]}).encode('utf8')
            self.odl.post_request("opendaylight-inventory:nodes/node/" + switch.id + "/table/0/flow/" + str(stream_id), data)
        #data = json.dumps(full).encode('utf8')
        #self.odl.post_request("opendaylight-inventory:nodes/node/" + switch.id + "/table/1", data)

    def push_group(self, switch):
        for stream_id in switch.actions:
            inst_counter = 0
            group = dict()
            group["group-type"] = "group-all"
            group["group-id"] = stream_id
            group["group-name"] = "stream" + str(stream_id)
            group["buckets"] = {"bucket": []}
            group["barrier"] = True
            buckets = group["buckets"]["bucket"]
            for action in switch.actions[stream_id]:
                if action.type is self.PROXY_TO_MULTI:
                    bucket = {
                        "bucket-id": inst_counter,
                        "action": [
                            {
                                "push-mpls-action": {"ethernet-type": "34887"},
                                "order": 1
                            }, {
                                "set-field": {
                                    "protocol-match-fields": {"mpls-label": stream_id}
                                },
                                "order": 2
                            }, {
                                "output-action": {"output-node-connector": action.switch_port},
                                "order": 3
                            }
                        ]
                    }
                    inst_counter += 1
                    buckets.append(bucket)
                elif action.type is self.CLIENT_TO_MULTI:
                    bucket = {
                        "bucket-id": inst_counter,
                        "action": [
                            {
                                "push-mpls-action": {"ethernet-type": "34887"},
                                "order": 1
                            }, {
                                "set-field": {
                                    "protocol-match-fields": {"mpls-label": stream_id}
                                },
                                "order": 2
                            }, {
                                "output-action": {"output-node-connector": action.switch_port},
                                "order": 3
                            }
                        ]
                    }
                    inst_counter += 1
                    buckets.append(bucket)
                elif action.type is self.FORWARD:
                    bucket = {
                        "bucket-id": inst_counter,
                        "action": [
                            {
                                "output-action": {"output-node-connector": action.switch_port},
                                "order": 1
                            }
                        ]
                    }
                    inst_counter += 1
                    buckets.append(bucket)
                elif action.type is self.CONVERT_TO_UNI:
                    bucket = {
                        "bucket-id": inst_counter,
                        "action": [
                            {
                                "pop-mpls-action": {"ethernet-type": "34887"},
                                "order": 1
                            }, {
                                "set-field": {
                                    "ipv4-destination": action.dst_ip + "/32",
                                    "ipv4-source": action.src_ip + "/32",
                                    "tcp-source-port": action.src_port,
                                    "tcp-destination-port": action.dst_port,
                                    "ethernet-match": {
                                        "ethernet-source": {"address": action.src_mac},
                                        "ethernet-destination": {"address": action.dst_mac}
                                    }
                                },
                                "order": 2
                            }, {
                                "output-action": {"output-node-connector": action.switch_port},
                                "order": 3
                            }
                        ]
                    }
                    inst_counter += 1
                    buckets.append(bucket)
            print("Sending this data to " + switch.id  + " group " + str(stream_id))
            print({"group": [group]})
            data = json.dumps({"group": [group]}).encode('utf8')
            self.odl.post_request("opendaylight-inventory:nodes/node/" + switch.id + "/flow-node-inventory:group/" + str(stream_id), data)


class VideoStream:
    active_ids=[]
    current_id = 5

    def __init__(self, fake_src_ip="", fake_src_mac="", fake_src_port="",
                 fake_dst_ip="", fake_dst_mac="", fake_dst_port="", ips={}):
        self.stream_id = VideoStream.__get_id__()
        self.ip_addresses = ips
        # src is the client
        # dst is the video server
        self.fake_src_ip = fake_src_ip
        self.fake_src_mac = fake_src_mac
        self.fake_src_port = fake_src_port
        self.fake_dst_ip = fake_dst_ip
        self.fake_dst_mac = fake_dst_mac
        self.fake_dst_port = fake_dst_port

    @staticmethod
    def __get_id__():
        VideoStream.current_id = (((VideoStream.current_id - 5) + 1) % 50) + 5
        while VideoStream.current_id in VideoStream.active_ids:
            VideoStream.current_id = (((VideoStream.current_id - 5) + 1) % 50) + 5
        VideoStream.active_ids.append(VideoStream.current_id)
        print("Handing out stream id " + str(VideoStream.current_id))
        return VideoStream.current_id

    def remove_stream(self):
        VideoStream.active_ids.remove(self.stream_id)

    def add_ip(self, ip, client_port, dest_port):
        self.ip_addresses[ip] = (client_port, dest_port)

    def remove_ip(self, ip):
        if ip in self.ip_addresses.keys():
            del self.ip_addresses[ip]
        else:
            raise "IP not found in this stream"
