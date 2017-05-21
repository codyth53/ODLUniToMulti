import ProxyServer
import sys
sys.path.append('/home/cody/odl/pycharm-debug-py3k.egg')
import pydevd

if __name__ == '__main__':
    pydevd.settrace('172.16.0.101', port=7890, stdoutToServer=True, stderrToServer=True)
    p = ProxyServer.ProxyServer()