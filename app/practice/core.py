"""Manual quote adapter around the existing network-free Paper execution functions."""
from copy import deepcopy
from decimal import Decimal as D
import re
from types import SimpleNamespace
from app.automated.engine import (initial,validate,open_virtual,close_virtual,mark,dec,DemoError,POLICY)
from app.lab.models import digest,money,text,precise

SCOPE='PAPER_PRACTICE_V1'
SOURCE='Binance · Spot / data-api.binance.vision public trades'


def seed(now):
    s=initial(now);s.update(epoch='PRACTICE_'+s['epoch'],mode='ON',practice_scope=SCOPE,last_quote=None)
    return s


def checked(s):
    validate(s)
    if s.get('practice_scope')!=SCOPE or not s['epoch'].startswith('PRACTICE_') or s['mode']!='ON' or s['pending'] is not None:raise DemoError('PRACTICE_SCOPE_MISMATCH')
    p=s['position']
    if p and (not p['id'].startswith(s['epoch']+':manual:') or p.get('timeframe')!='QUOTE' or p.get('execution_context')!='MANUAL_FRESH_QUOTE' or dec(p['notional'])>D(POLICY['max_notional']) or dec(p['size'])<=0):raise DemoError('PRACTICE_SCOPE_MISMATCH')
    if p and dec(s['balance'])-dec(p['notional'])<0:raise DemoError('INSUFFICIENT_BALANCE')
    return s


def number(v):
    if not isinstance(v,str) or not re.fullmatch(r'[0-9]{1,12}(?:\.[0-9]{1,12})?',v) or not D(v)>0:raise DemoError('INVALID_AMOUNT')
    return D(v)


def quote_checked(q,now):
    if type(q) is not dict or q.get('source')!=SOURCE or type(q.get('time_ms')) is not int or type(q.get('trade_id')) is not int or q['trade_id']<0:raise DemoError('INVALID_QUOTE')
    number(q['price'])
    if not -2000<=now*1000-q['time_ms']<=10000:raise DemoError('STALE_QUOTE')
    return q


@precise
def transition(old,q,now,kind,command):
    s=deepcopy(old);checked(s);quote_checked(q,now)
    previous=s['last_quote']
    if previous and (q['time_ms']<previous['time_ms'] or q['trade_id']<previous['trade_id'] or (q['trade_id']==previous['trade_id'] and q!=previous)):raise DemoError('QUOTE_REGRESSION')
    price=number(q['price']);p=s['position'];outcome=None
    # Tick-only snapshot, not OHLC/history: never apply pre-entry candle extremes.
    point=SimpleNamespace(open=price,close=price,time=q['time_ms']//1000)
    if p:
        long=p['direction']=='LONG'
        if price<=dec(p['stop_loss']) if long else price>=dec(p['stop_loss']):outcome=close_virtual(s,price,now,'STOP_LOSS_QUOTE')
        elif price>=dec(p['take_profit']) if long else price<=dec(p['take_profit']):outcome=close_virtual(s,price,now,'TAKE_PROFIT_QUOTE')
    if kind=='OPEN':
        if p:raise DemoError('POSITION_LIMIT')
        expected=number(command['expected_price'])
        if abs(price-expected)/expected>D('.002'):raise DemoError('PRICE_MOVED_REFRESH_REQUIRED')
        stop=number(command['stop_loss']);target=number(command['take_profit'])
        if not (stop<price<target if command['direction']=='LONG' else target<price<stop):raise DemoError('INVALID_STOPS_FOR_CURRENT_QUOTE')
        mark(s,point,now)
        outcome=open_virtual(s,dict(direction=command['direction'],stop_loss=command['stop_loss'],take_profit=command['take_profit'],signal_at=now,reason='MANUAL_PRACTICE_NOT_STRATEGY_SIGNAL',source=SOURCE),point,now)
        s['position']['id']=s['epoch']+':manual:'+command['request_id']
        s['position'].update(timeframe='QUOTE',execution_context='MANUAL_FRESH_QUOTE')
        outcome['payload'].update(s['position'])
    elif kind=='CLOSE':
        if not p or p['id']!=command['position_id']:raise DemoError('POSITION_CHANGED')
        if outcome is None:outcome=close_virtual(s,price,now,'MANUAL_PRACTICE_CLOSE')
    elif kind!='UPDATE':raise DemoError('INVALID_ACTION')
    mark(s,point,now);s['last_quote']=q
    checked(s)
    if outcome is None:
        body=dict(position=s['position'],equity=s['equity'],quote=q);event_kind='UPDATE'
    else:body=outcome['payload'];event_kind=outcome['kind']
    body=dict(body,practice_scope=SCOPE,execution_mode='PAPER_ONLY',real_money_execution='DISABLED',strategy_version='MANUAL_PRACTICE_NOT_AURA_SIGNAL')
    return s,dict(kind=event_kind,epoch=s['epoch'],created_at=now,payload=body)
