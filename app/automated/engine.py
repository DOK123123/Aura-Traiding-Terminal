"""Network-free Decimal transitions for a separate, virtual-only portfolio."""
from copy import deepcopy
from decimal import Decimal as D
import uuid
from app.lab.models import money, quantity, text, precise, digest,Bar,LabError
from app.lab.execution import fee, fill

VERSION = 'AURA_AUTO_PAPER_4.2.0'
POLICY = dict(starting_balance='10000',risk_pct='0.5',max_positions=1,
    max_notional='2000',daily_loss_pct='2',drawdown_pct='10',
    commission_pct='0.10',slippage_pct='0.05',symbol='BTCUSDT',timeframe='15m',
    execution='CLOSED_SIGNAL_NEXT_OPEN',classification='EXPERIMENTAL / NO_EDGE_FOUND')
RATE=D('.001');SLIP=D('.0005');STEP=900


class DemoError(Exception):
    def __init__(self,code):self.code=code;super().__init__(code)


def dec(value):
    if not isinstance(value,str) or len(value)>100:raise DemoError('CORRUPT_PORTFOLIO')
    try:n=D(value)
    except Exception:raise DemoError('CORRUPT_PORTFOLIO') from None
    if not n.is_finite():raise DemoError('CORRUPT_PORTFOLIO')
    return n


def initial(now,epoch=None):
    return dict(version=VERSION,policy_hash=digest(POLICY),epoch=epoch or uuid.uuid4().hex,
        mode='OFF',emergency=False,balance='10000',equity='10000',peak='10000',
        max_drawdown_pct='0',day=now//86400,day_start_equity='10000',day_low_equity='10000',
        position=None,pending=None,watermark=None,last_bar_hash=None,last_mark_at=None,
        last_run_at=None,last_success_at=None,last_decision='NOT_STARTED',last_error=None,
        missed_candles=0,missed_runs=0,trades=0,wins=0,losses=0,realized_pnl='0',gross_profit='0',
        gross_loss='0',fees='0',slippage='0',created_at=now)


@precise
def _validate(s):
    if s.get('version')!=VERSION or s.get('policy_hash')!=digest(POLICY):raise DemoError('MODEL_CHANGED_RESET_REQUIRED')
    if s.get('mode') not in ('OFF','ON','PAUSED','ERROR','EMERGENCY'):raise DemoError('CORRUPT_PORTFOLIO')
    for k in ('balance','equity','peak','max_drawdown_pct','day_start_equity','day_low_equity',
              'realized_pnl','gross_profit','gross_loss','fees','slippage'):dec(s[k])
    if dec(s['peak'])<=0:raise DemoError('CORRUPT_PORTFOLIO')
    for k in ('day','missed_candles','missed_runs','trades','wins','losses'):
        if type(s.get(k)) is not int or s[k]<0:raise DemoError('CORRUPT_PORTFOLIO')
    for k in ('watermark','last_mark_at','last_run_at','last_success_at'):
        if s[k] is not None and (type(s[k]) is not int or s[k]<0):raise DemoError('CORRUPT_PORTFOLIO')
    p=s['position']
    if p:
        for k in ('entry_price','size','stop_loss','take_profit','entry_fee','notional'):dec(p[k])
        if p['direction'] not in ('LONG','SHORT') or min(dec(p[k]) for k in ('entry_price','size','stop_loss','take_profit'))<=0:raise DemoError('CORRUPT_PORTFOLIO')
        long=p['direction']=='LONG'
        if not (dec(p['stop_loss'])<dec(p['entry_price'])<dec(p['take_profit']) if long else dec(p['take_profit'])<dec(p['entry_price'])<dec(p['stop_loss'])):raise DemoError('CORRUPT_PORTFOLIO')
    if type(s['emergency']) is not bool or not isinstance(s.get('epoch'),str):raise DemoError('CORRUPT_PORTFOLIO')
    if s['wins']+s['losses']>s['trades']:raise DemoError('CORRUPT_PORTFOLIO')
    if any(dec(s[k])<0 for k in ('gross_profit','gross_loss','fees','slippage','max_drawdown_pct')):raise DemoError('CORRUPT_PORTFOLIO')
    expected=money(D(POLICY['starting_balance'])+dec(s['realized_pnl'])-(dec(p['entry_fee']) if p else 0))
    if dec(s['balance'])!=expected:raise DemoError('ACCOUNTING_ERROR')
    pending=s['pending']
    if pending is not None:
        if pending.get('direction') not in ('LONG','SHORT') or type(pending.get('signal_at')) is not int or pending['signal_at']!=s['watermark'] or min(dec(pending[k]) for k in ('stop_loss','take_profit'))<=0:raise DemoError('CORRUPT_PORTFOLIO')
    if p and pending:raise DemoError('CORRUPT_PORTFOLIO')


def validate(s):
    try:
        if not isinstance(s,dict):raise DemoError('CORRUPT_PORTFOLIO')
        _validate(s)
    except (KeyError,TypeError,ValueError,ArithmeticError):raise DemoError('CORRUPT_PORTFOLIO') from None


def validate_bars(bars,now):
    if not bars or len(bars)>4175:raise DemoError('INVALID_MARKET_DATA')
    try:
        for b in bars:
            if not isinstance(b,Bar):raise DemoError('INVALID_MARKET_DATA')
            b.validate(STEP,now)
        if any(b.time<=a.time for a,b in zip(bars,bars[1:])):raise DemoError('DUPLICATE_OR_UNORDERED')
    except LabError:raise DemoError('INVALID_MARKET_DATA') from None


@precise
def liquidation_equity(s,raw):
    p=s['position'];balance=dec(s['balance'])
    if p is None:return balance
    px=fill(raw,p['direction'],False,SLIP);q=dec(p['size']);sign=1 if p['direction']=='LONG' else -1
    return money(balance+money(sign*(px-dec(p['entry_price']))*q)-fee(px,q,RATE))


def event(s,kind,key,now,body):
    return dict(id=s['epoch']+':'+kind+':'+str(key),kind=kind,epoch=s['epoch'],created_at=now,
        payload=dict(body,execution_mode='PAPER_ONLY',real_money_execution='DISABLED',strategy_version=VERSION))


def roll_day(s,at):
    day=at//86400
    if day!=s['day']:
        # Carry the last known liquidation equity; no invented midnight quotation.
        s.update(day=day,day_start_equity=s['equity'],day_low_equity=s['equity'])


@precise
def mark(s,bar,at):
    roll_day(s,at)
    eq=liquidation_equity(s,bar.close);peak=max(dec(s['peak']),eq)
    s.update(equity=text(eq),peak=text(peak),last_mark_at=at,
        day_low_equity=text(min(dec(s['day_low_equity']),eq)),
        max_drawdown_pct=text(max(dec(s['max_drawdown_pct']),money((peak-eq)/peak*100))))


@precise
def risk_reason(s):
    if s['emergency']:return 'EMERGENCY_STOP'
    if dec(s['day_start_equity'])<=0 or dec(s['day_low_equity'])<=dec(s['day_start_equity'])*D('.98'):return 'DAILY_LOSS_LIMIT'
    if dec(s['max_drawdown_pct'])>=10:return 'DRAWDOWN_LIMIT'
    if dec(s['balance'])<=0:return 'INSUFFICIENT_BALANCE'
    return None


@precise
def open_virtual(s,plan,bar,at):
    if s['position']:raise DemoError('POSITION_LIMIT')
    if s['mode']!='ON':raise DemoError('AUTO_OFF')
    reason=risk_reason(s)
    if reason:raise DemoError(reason)
    side=plan.get('direction')
    if side not in ('LONG','SHORT'):raise DemoError('INVALID_SIGNAL')
    stop=dec(plan['stop_loss']);target=dec(plan['take_profit']);entry=fill(bar.open,side,True,SLIP)
    long=side=='LONG';sign=1 if long else -1
    if min(entry,stop,target)<=0 or not (stop<entry<target if long else target<entry<stop):raise DemoError('INVALID_STOPS_AT_NEXT_OPEN')
    stop_fill=fill(stop,side,False,SLIP);target_fill=fill(target,side,False,SLIP)
    budget=dec(s['equity'])*D('.005');balance=dec(s['balance'])
    unit=abs(entry-stop_fill)+RATE*(entry+stop_fill)
    q=quantity(min((budget-D('.00000003'))/unit,D(POLICY['max_notional'])/entry,(balance-D('.00000002'))/(entry*(1+RATE))))
    if q<=0:raise DemoError('INSUFFICIENT_BALANCE')
    cost=money(entry*q,ceil=True);entry_fee=fee(entry,q,RATE)
    risk=money(abs(entry-stop_fill)*q,ceil=True)+entry_fee+fee(stop_fill,q,RATE)
    reward=money(sign*(target_fill-entry)*q)-entry_fee-fee(target_fill,q,RATE)
    if risk>budget:raise DemoError('RISK_LIMIT')
    if reward<=0:raise DemoError('TARGET_AFTER_COSTS')
    if cost>D(POLICY['max_notional']) or cost+entry_fee>balance:raise DemoError('INSUFFICIENT_BALANCE')
    p=dict(id=s['epoch']+':position:'+str(plan['signal_at']),direction=side,symbol='BTCUSDT',timeframe='15m',
        signal_at=plan['signal_at'],entry_time=bar.time,entry_raw_price=text(bar.open),entry_price=text(entry),
        size=text(q),notional=text(cost),stop_loss=text(stop),take_profit=text(target),entry_fee=text(entry_fee),
        risk_usdt=text(risk),risk_budget_usdt=text(money(budget)),reason=plan['reason'],source=plan['source'],status='OPEN')
    s.update(position=p,balance=text(money(balance-entry_fee)),fees=text(dec(s['fees'])+entry_fee))
    s['slippage']=text(money(dec(s['slippage'])+abs(entry-bar.open)*q))
    return event(s,'OPEN',plan['signal_at'],at,p)


@precise
def close_virtual(s,raw,at,reason):
    p=deepcopy(s['position']);q=dec(p['size']);side=p['direction'];sign=1 if side=='LONG' else -1
    px=fill(raw,side,False,SLIP);exit_fee=fee(px,q,RATE);gross=money(sign*(px-dec(p['entry_price']))*q)
    net=money(gross-dec(p['entry_fee'])-exit_fee)
    s.update(position=None,balance=text(money(dec(s['balance'])+gross-exit_fee)),
        realized_pnl=text(money(dec(s['realized_pnl'])+net)),fees=text(dec(s['fees'])+exit_fee),
        slippage=text(money(dec(s['slippage'])+abs(px-raw)*q)),trades=s['trades']+1,
        wins=s['wins']+(net>0),losses=s['losses']+(net<0),
        gross_profit=text(dec(s['gross_profit'])+max(net,D(0))),gross_loss=text(dec(s['gross_loss'])+max(-net,D(0))))
    p.update(exit_time=at,exit_price=text(px),exit_raw_price=text(raw),exit_reason=reason,
        exit_fee=text(exit_fee),fees=text(dec(p['entry_fee'])+exit_fee),gross_price_pnl=text(gross),
        realized_pnl=text(net),pnl_pct=text(money(net/dec(p['notional'])*100)),status='CLOSED')
    return event(s,'CLOSE',p['signal_at'],at,p)


def protective(s,b,now):
    p=s['position']
    if not p:return None
    long=p['direction']=='LONG';stop=dec(p['stop_loss']);target=dec(p['take_profit'])
    if (b.open<=stop if long else b.open>=stop):return close_virtual(s,b.open,b.time,'STOP_GAP')
    if (b.open>=target if long else b.open<=target):return close_virtual(s,target,b.time,'TAKE_PROFIT_GAP_CONSERVATIVE')
    sl=b.low<=stop if long else b.high>=stop;tp=b.high>=target if long else b.low<=target
    if sl:return close_virtual(s,stop,b.time+STEP,'STOP_LOSS_AMBIGUOUS' if tp else 'STOP_LOSS')
    if tp:return close_virtual(s,target,b.time+STEP,'TAKE_PROFIT')
    return None


@precise
def advance(old,bars,decision,now):
    """Already committed signal only; never build signals from catch-up candles."""
    s=deepcopy(old);validate(s);events=[];latest=now//STEP*STEP
    validate_bars(bars,now)
    if bars[-1].time+STEP!=latest:raise DemoError('STALE_DATA')
    watermark=s['watermark']
    if watermark is None:
        s.update(watermark=latest,last_bar_hash=digest(bars[-1].data()),pending=None,last_decision='ACTIVATION_BASELINE')
        mark(s,bars[-1],latest)
        return s,[event(s,'BASELINE',latest,now,dict(reason='ACTIVATION_BASELINE'))]
    prior=next((b for b in bars if b.time+STEP==watermark),None)
    if prior is None or digest(prior.data())!=s['last_bar_hash']:raise DemoError('SOURCE_CORRECTION_OR_HISTORY_MISSING')
    if latest==watermark:return s,[]
    future=[b for b in bars if b.time>=watermark]
    if not future or future[0].time!=watermark or any(b.time-a.time!=STEP for a,b in zip(future,future[1:])):raise DemoError('MISSING_CANDLES')
    if len(future)>32:raise DemoError('CATCHUP_LIMIT')
    if len(future)>1:
        s['missed_candles']+=len(future)-1;s['pending']=None
        events.append(event(s,'MISSED',latest,now,dict(count=len(future)-1,reason='MISSED_RUN_NO_RETROACTIVE_ENTRIES')))
    for b in future:
        roll_day(s,b.time)
        pending=s['pending'];s['pending']=None
        # Apply adverse opening mark before sizing another position.
        eq=liquidation_equity(s,b.open);s['equity']=text(eq);s['day_low_equity']=text(min(dec(s['day_low_equity']),eq))
        s['max_drawdown_pct']=text(max(dec(s['max_drawdown_pct']),money((dec(s['peak'])-eq)/dec(s['peak'])*100)))
        if pending and s['mode']=='ON' and not risk_reason(s) and pending['signal_at']==b.time:
            try:events.append(open_virtual(s,pending,b,now))
            except DemoError as exc:events.append(event(s,'REJECT',b.time,now,dict(reason=exc.code)))
        exit_event=protective(s,b,now)
        if exit_event:events.append(exit_event)
        mark(s,b,b.time+STEP)
        reason=risk_reason(s)
        if reason:
            if not s['emergency']:s['mode']='PAUSED'
            s['pending']=None;s['last_decision']=reason
    s.update(watermark=latest,last_bar_hash=digest(bars[-1].data()))
    reason=risk_reason(s)
    if s['mode']!='ON':reason=reason or 'AUTO_OFF'
    elif s['position']:reason='POSITION_ALREADY_OPEN'
    else:reason=reason or decision['reason']
    if reason==decision['reason'] and decision.get('direction') and s['mode']=='ON' and not s['position'] and not risk_reason(s):
        s['pending']=dict(decision,signal_at=latest,created_at=now);reason='SIGNAL_QUEUED_NEXT_OPEN'
    s['last_decision']=reason
    events.append(event(s,'DECISION',latest,now,dict(reason=reason,signal=decision,mode=s['mode'],closed_at=latest,
        balance=s['balance'],equity=s['equity'])))
    validate(s)
    return s,events
