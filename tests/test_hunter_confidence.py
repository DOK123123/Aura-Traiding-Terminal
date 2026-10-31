"""No live accounts or exchange POST: descriptive research scores only."""
import math
import tempfile
import unittest
from pathlib import Path

from app.hunter.confidence import VERSION, score_at, technical_scores
from app.hunter.engine import Prepared
from app.hunter.market import SOURCE
from app.hunter.store import Store


def history(direction=1, n=320, step=300):
    rows=[]
    for i in range(n):
        price=50000+direction*3*i+math.sin(i/5)*5
        rows.append([i*step, price-0.4*direction, price+20, price-20, price, 20+(i%5)])
    return rows


def quote(at,price):
    return {'bid':price-.1,'ask':price+.1,'last':price,
            'time':at,'received_at':at,'source':SOURCE}


class ConfidenceTests(unittest.TestCase):
    def test_both_sides_and_score_not_probability(self):
        rows=history();prepared=Prepared(rows[-260:],'5m')
        now=rows[-1][0]+301
        result=technical_scores(prepared,quote(now,rows[-1][4]),now)
        self.assertEqual({r['direction'] for r in result},{'LONG','SHORT'})
        self.assertTrue(all(0<=r['score']<=100 for r in result))
        self.assertTrue(all(sum(r['score_groups'].values())==r['score'] for r in result))
        self.assertTrue(all(r['probability_tp_before_sl'] is None for r in result))
        self.assertTrue(all(r['statistical_status']=='UNVALIDATED' and not r['exchange_execution'] for r in result))
        self.assertGreater(result[0]['score'],result[1]['score'])
        self.assertEqual(result[0]['score_version'],VERSION)

    def test_stale_future_and_foreign_quotes_fail_closed(self):
        rows=history();p=Prepared(rows[-260:],'5m');now=rows[-1][0]+301
        q=quote(now,rows[-1][4])
        for altered in ({**q,'time':now-6},{**q,'source':'BYBIT'},
                        {**q,'ask':q['bid']-.5},{**q,'time':now+1}):
            self.assertEqual(technical_scores(p,altered,now),[])
        self.assertEqual(technical_scores(p,q,now+300),[])

    def test_future_candles_cannot_change_past_score(self):
        rows=history(n=380);earlier=Prepared(rows[:320],'5m')
        at=319
        first=score_at(earlier,at)
        mutated=history(n=380)
        for row in mutated[320:]:row[1:5]=[100000,100020,99980,100000]
        self.assertEqual(first,score_at(Prepared(mutated,'5m'),at))
        self.assertEqual(first,score_at(Prepared(rows,'5m'),at))
        # Historical replay and live 260-bar seeding must produce identical scores.
        self.assertEqual(first,score_at(Prepared(rows[at-259:at+1],'5m'),259))

    def test_store_snapshot_exposes_only_quote_fresh_scores(self):
        rows=history()[-260:];now=rows[-1][0]+301
        q=quote(now,rows[-1][4]);snap={'source':SOURCE,'frame':'5m','step':300,'bars':rows,'quote':q}
        with tempfile.TemporaryDirectory() as directory:
            store=Store(Path(directory)/'observations.sqlite')
            store.observe(snap,[],now,{'approved':[]})
            data=store.snapshot(now,{'5m':q})
            self.assertEqual(len(data['confidence_candidates']),2)
            expected={c['id'] for c in data['confidence_candidates']
                      if c['score']>=50 and c['risk_gates_passed']}
            self.assertEqual({c['id'] for c in data['confidence_history']},expected)
            self.assertTrue(all(x['outcome']=='PENDING' for x in data['confidence_history']))
            self.assertTrue(all(c['input_sha256'] for c in data['confidence_candidates']))
            self.assertTrue(all(c['probability_tp_before_sl'] is None for c in data['confidence_candidates']))
            self.assertEqual(data['alerts'],[])
            newer=quote(now+1,rows[-1][4]+.5)
            store.observe({**snap,'quote':newer},[],now+1,{'approved':[]})
            self.assertEqual(len(store.snapshot(now+1,{'5m':newer})['confidence_candidates']),2)
            self.assertEqual({c['id'] for c in store.snapshot(now+1,{'5m':newer})['confidence_history']},expected)
            self.assertEqual(store.snapshot(now+1,{'5m':q})['confidence_candidates'],[])
            self.assertEqual(store.snapshot(now+6,{'5m':q})['confidence_candidates'],[])
            self.assertEqual(store.snapshot(now,{'5m':q},'OBSERVER_STOPPED')['confidence_candidates'],[])
            self.assertEqual(store.snapshot(now,{'5m':{**q,'time':now-1}})['confidence_candidates'],[])


if __name__=='__main__':unittest.main()
