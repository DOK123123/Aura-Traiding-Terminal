"""Explicit bounded local public probe; never assumes results apply to Render."""
import asyncio
import json
import httpx
from app.exchange_diagnostics.probes import exchange_probe

async def main():
    async with httpx.AsyncClient(timeout=5,follow_redirects=False) as client:
        async def one(name):
            try:
                async with asyncio.timeout(58):return await exchange_probe(name,client)
            except TimeoutError:return {'status':'TIMEOUT','code':'TOTAL_BUDGET_EXCEEDED'}
        values=await asyncio.gather(one('BINGX'),one('BITGET'))
    print(json.dumps(dict(environment='LOCAL_CODEX_NOT_RENDER',read_only=True,trading_enabled=False,exchanges=dict(zip(('BINGX','BITGET'),values))),indent=2))

if __name__=='__main__':asyncio.run(main())
