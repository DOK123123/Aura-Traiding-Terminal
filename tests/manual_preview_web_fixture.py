"""Loopback-only restart fixture: dummy quotes and disposable local SQLite."""
import os,time
from decimal import Decimal
import uvicorn
from app.manual_preview import main
from app.manual_paper.store import ManualStore
from app.manual_paper.service import Service

if os.getenv('RENDER') or os.getenv('MANUAL_PREVIEW_TEST_ONLY')!='1':raise ValueError('LOCAL_TEST_ONLY')
class Store(ManualStore):
    def __init__(self,config):super().__init__(os.environ['MANUAL_PREVIEW_TEST_DB'])
    def verify_scope(self):return True  # SQL scope is verified in the separate real PG harness.
    def close(self):pass
class DummyService(Service):
    async def quote(self):
        bid=Decimal(os.getenv('MANUAL_PREVIEW_TEST_BID','80000'))
        return dict(source='Bitget USDT-M Futures',symbol='BTCUSDT',product='USDT-FUTURES',time=int(time.time()*1000)-20,bid=bid,ask=bid+1,price=bid,bid_size=Decimal('1'),ask_size=Decimal('1'))
main.PreviewStore=Store;main.Service=DummyService
async def _offline_probe(client):pass
main._preview_probe_history=_offline_probe
async def _offline_ws_probe(app):pass
main._preview_probe_ws=_offline_ws_probe
if __name__=='__main__':uvicorn.run(main.app,host='127.0.0.1',port=int(os.environ['MANUAL_PREVIEW_TEST_PORT']),log_level='error')
