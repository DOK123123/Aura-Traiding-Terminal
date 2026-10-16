"""Test tooling only: real start_web/lifespan, isolated env, loopback-only I/O."""
import asyncio
import ipaddress
import json
import os
from pathlib import Path
import resource
import runpy
import socket
import sys


def allowed(host):
    try:return ipaddress.ip_address(host).is_loopback
    except ValueError:return host == 'localhost'


def main():
    checkout=Path(sys.argv[1]).resolve()
    if os.getenv('AURA_STAGING_SANDBOX') != str(checkout.parent):raise SystemExit('STAGING_GUARD_REQUIRED')
    cap=int(os.getenv('AURA_STAGING_AS_MIB','1536'))
    if not 512<=cap<=4096:raise SystemExit('INVALID_STAGING_MEMORY_CAP')
    resource.setrlimit(resource.RLIMIT_AS,(cap*1024**2,)*2)
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    connect=socket.socket.connect; connect_ex=socket.socket.connect_ex; lookup=socket.getaddrinfo
    def safe_connect(s,address):
        if s.family in (socket.AF_INET,socket.AF_INET6) and not allowed(address[0]):raise OSError('STAGING_EXTERNAL_NETWORK_DENIED')
        return connect(s,address)
    def safe_ex(s,address):
        if s.family in (socket.AF_INET,socket.AF_INET6) and not allowed(address[0]):raise OSError('STAGING_EXTERNAL_NETWORK_DENIED')
        return connect_ex(s,address)
    def safe_lookup(host,*args,**kwargs):
        if host is not None and not allowed(host):raise OSError('STAGING_EXTERNAL_NETWORK_DENIED')
        return lookup(host,*args,**kwargs)
    socket.socket.connect=safe_connect;socket.socket.connect_ex=safe_ex;socket.getaddrinfo=safe_lookup
    if os.getenv('AURA_STAGING_SANDBOX_POLL')=='true':
        class PollLoop(asyncio.SelectorEventLoop):
            def _run_once(self):self.call_later(.01,lambda:None);super()._run_once()
        class Policy(asyncio.DefaultEventLoopPolicy):
            def new_event_loop(self):return PollLoop()
        asyncio.set_event_loop_policy(Policy())
    os.chdir(checkout);sys.path.insert(0,str(checkout))
    import uvicorn
    real_run=uvicorn.run
    def isolated_run(*args,**kwargs):
        kwargs.update(host='127.0.0.1',loop='asyncio',access_log=False)
        return real_run(*args,**kwargs)
    uvicorn.run=isolated_run
    # Imported real app, original startup/shutdown and background tasks.
    runpy.run_path(str(checkout/'start_web.py'),run_name='__main__')

if __name__=='__main__':main()
