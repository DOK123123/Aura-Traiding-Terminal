"""Loopback integration server. Dummy quotes only, never imported by production."""
import os
import time
from decimal import Decimal
import uvicorn
import app.main as main
from app.manual_paper.service import configured


def manual_fixture(client):
    svc=configured(client)
    async def quote():
        bid=Decimal(os.environ.get('MANUAL_TEST_BID','80000'))
        return dict(source='Bitget USDT-M Futures',symbol='BTCUSDT',product='USDT-FUTURES',
                    time=int(time.time()*1000)-50,bid=bid,ask=bid+1,price=bid,
                    bid_size=Decimal('1'),ask_size=Decimal('1'))
    svc.quote=quote
    return svc


main.configured_manual_paper=manual_fixture
if __name__=='__main__':
    uvicorn.run(main.app,host='127.0.0.1',port=int(os.environ['MANUAL_TEST_PORT']),log_level='error')
