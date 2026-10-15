"""Standard-library scheduler client with mocked HTTP; no real ticks."""
import io,json,socket,unittest,urllib.error
from scripts.auto42_scheduler import configuration,run,HOST,PATH,TIMEOUT,SchedulerError

TOKEN='dummy-scheduler-token-tests-only-00000000'
ENV={'AURA_AUTO42_TICK_URL':'https://'+HOST+PATH,'AURA_AUTO42_SCHEDULER_SECRET':TOKEN}


def result(**values):
    return dict(status='COMPLETED',paper_only=True,exchange_execution=False,state_saved=True,processed_this_run=False,
        tick_outcome='HEARTBEAT_OFF',mode='OFF',last_processed_closed_at=None,decision='AUTO_OFF',opened_positions=0,closed_positions=0,**values)


class Response:
    status=200
    def __init__(self,body):self.raw=json.dumps(body).encode()
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def read(self,limit):return self.raw[:limit]


class Client:
    def __init__(self,values):self.values=iter(values);self.calls=[]
    def open(self,request,timeout):
        self.calls.append((request,timeout));v=next(self.values)
        if isinstance(v,Exception):raise v
        return Response(v)


class SchedulerTests(unittest.TestCase):
    def test_actual_host_allowed_and_old_wrong_host_rejected(self):
        self.assertEqual(configuration(ENV),tuple(ENV.values()))
        with self.assertRaisesRegex(SchedulerError,'CONFIG_URL_HOST'):configuration(dict(ENV,AURA_AUTO42_TICK_URL='https://terminal.onrender.com'+PATH))
    def test_config_errors_are_specific_without_echoing_values(self):
        for changes,code in [({'AURA_AUTO42_TICK_URL':''},'URL_MISSING'),({'AURA_AUTO42_TICK_URL':'http://'+HOST+PATH},'URL_SCHEME'),
            ({'AURA_AUTO42_TICK_URL':'https://'+HOST+PATH+'?token='+TOKEN},'URL_PATH'),({'AURA_AUTO42_SCHEDULER_SECRET':''},'TOKEN_MISSING'),
            ({'AURA_AUTO42_SCHEDULER_SECRET':'bad\n'+TOKEN},'TOKEN_FORMAT')]:
            lines=[];self.assertEqual(run(dict(ENV,**changes),emit=lines.append),1);self.assertIn(code,' '.join(lines));self.assertNotIn(TOKEN,' '.join(lines))
    def test_off_heartbeat_is_explicitly_not_processed_candle(self):
        lines=[];c=Client([result()]);self.assertEqual(run(ENV,c,emit=lines.append),0)
        self.assertIn('HEARTBEAT_OFF',' '.join(lines));self.assertIn('processed=False',' '.join(lines));self.assertEqual(c.calls[0][1],120)
        self.assertEqual(c.calls[0][0].get_method(),'POST');self.assertNotIn(TOKEN,' '.join(lines))
    def test_http_200_without_processing_contract_is_not_success(self):
        lines=[];self.assertEqual(run(ENV,Client([{'status':'COMPLETED','paper_only':True,'exchange_execution':False}]),emit=lines.append),1)
        self.assertIn('API_CONTRACT_MISMATCH',' '.join(lines))
    def test_valid_wait_is_successful_analysis_not_forced_trade(self):
        body=result();body.update(mode='ON',tick_outcome='CANDLE_PROCESSED',processed_this_run=True,last_processed_closed_at=1800,decision='NO_CONFIRMED_SETUP')
        lines=[];self.assertEqual(run(ENV,Client([body]),emit=lines.append),0);self.assertIn('opened=0',' '.join(lines));self.assertIn('NO_CONFIRMED_SETUP',' '.join(lines))
    def test_render_cold_start_timeout_then_success_is_bounded(self):
        lines=[];delays=[];c=Client([socket.timeout(TOKEN),result()]);self.assertEqual(run(ENV,c,sleep=delays.append,emit=lines.append),0)
        self.assertEqual(delays,[2]);self.assertEqual(len(c.calls),2);self.assertNotIn(TOKEN,' '.join(lines));self.assertIn('RENDER_OR_BACKEND_TIMEOUT',' '.join(lines))
    def test_repeated_timeouts_stop_after_three_attempts(self):
        lines=[];delays=[];c=Client([TimeoutError(TOKEN)]*3);self.assertEqual(run(ENV,c,sleep=delays.append,emit=lines.append),1)
        self.assertEqual(len(c.calls),3);self.assertEqual(delays,[2,4]);self.assertNotIn(TOKEN,' '.join(lines))
    def test_http_auth_and_schema_errors_do_not_retry_or_disclose_response(self):
        for status,body in [(401,{'detail':'SCHEDULER_AUTH_REQUIRED'}),(503,{'code':'STORAGE_SCHEMA_MISSING','message':TOKEN}),(404,{'message':TOKEN})]:
            e=urllib.error.HTTPError(ENV['AURA_AUTO42_TICK_URL'],status,TOKEN,{},io.BytesIO(json.dumps(body).encode()))
            c=Client([e]);lines=[];self.assertEqual(run(ENV,c,emit=lines.append),1);self.assertEqual(len(c.calls),1)
            self.assertIn('http='+str(status),' '.join(lines));self.assertNotIn(TOKEN,' '.join(lines))
    def test_risk_blocked_candle_is_verified_without_claiming_entry(self):
        body=result();body.update(mode='PAUSED',tick_outcome='RISK_BLOCKED',processed_this_run=True,last_processed_closed_at=1800,decision='DAILY_LOSS_LIMIT')
        lines=[];self.assertEqual(run(ENV,Client([body]),emit=lines.append),0)
        self.assertIn('RISK_BLOCKED',' '.join(lines));self.assertIn('opened=0',' '.join(lines));self.assertIn('DAILY_LOSS_LIMIT',' '.join(lines))
    def test_duplicate_response_does_not_claim_second_processing(self):
        body=result();body.update(tick_outcome='NO_NEW_WORK',duplicate=True)
        lines=[];self.assertEqual(run(ENV,Client([body]),emit=lines.append),0);self.assertIn('NO_NEW_WORK',' '.join(lines));self.assertIn('opened=0',' '.join(lines))
