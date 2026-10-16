"""AUDITOR: independent ledger arithmetic; cannot access trading services or LLM."""
from decimal import Decimal as D,localcontext,ROUND_HALF_EVEN,ROUND_CEILING
from fractions import Fraction as F
import math
import statistics
from scripts.audit_lab_v2_accounting import verify_exit,verify_equity_timeline


def require(condition,label):
    if not condition:raise ValueError('AUDIT_'+label)


def audit_run(run:dict,bars) -> dict:
    if not __debug__:raise ValueError('AUDIT_REQUIRES_ASSERTIONS')
    def rounded(n,up=False):return n.quantize(D('.00000001'),rounding=ROUND_CEILING if up else ROUND_HALF_EVEN)
    def round_fraction(x,up=False):
        q,r=divmod(x.numerator*10**8,x.denominator)
        if (up and r) or (not up and (r*2>x.denominator or r*2==x.denominator and q%2)):q+=1
        return F(q,10**8)
    pnl=F(0);fees=F(0);wins=[];losses=[];last=run['start'];candles={b.time:b for b in bars}
    for t in run['trades']:
        require(run['start']<t['original_signal_at']<=t['signal_at']==t['entry_time']<run['end_exclusive'],'ENTRY_BOUNDARY')
        require(t['entry_time']>=last and t['exit_time']<=run['end_exclusive'],'NO_OVERLAP');last=t['exit_time']
        require(F(t['entry_raw_price'])==F(candles[t['entry_time']].open),'NEXT_OPEN')
        sign=1 if t['direction']=='LONG' else -1;q=F(t['size']);entry=F(t['entry_raw_price'])*(1+sign*F(5,10000));exit=F(t['exit_raw_price'])*(1-sign*F(5,10000))
        ef=round_fraction(entry*q/1000,True);xf=round_fraction(exit*q/1000,True);net=round_fraction(round_fraction(sign*(exit-entry)*q)-ef-xf)
        require(F(t['entry_price'])==entry and F(t['exit_price'])==exit,'FILLS')
        require(F(t['entry_fee'])==ef and F(t['exit_fee'])==xf and F(t['fees'])==ef+xf,'FEES')
        require(F(t['realized_pnl'])==net,'PNL')
        stop=F(t['stop_loss'])*(1-sign*F(5,10000));risk=round_fraction(abs(entry-stop)*q,True)+ef+round_fraction(stop*q/1000,True)
        require(F(t['risk_usdt'])==risk and risk<=round_fraction((10000+pnl)/200) and F(t['notional'])<=2000,'RISK')
        with localcontext() as ctx:ctx.prec=64;verify_exit(t,candles)
        pnl+=net;fees+=ef+xf
        if net>0:wins.append(net)
        elif net<0:losses.append(-net)
    m=run['metrics'];opened=run['open_position'];unfinished=F(opened['entry_fee']) if opened else F(0)
    require(F(m['final_balance'])==10000+pnl-unfinished and F(m['realized_net_pnl'])==pnl,'BALANCE')
    require(F(m['fees'])==fees+unfinished and m['trades']==len(run['trades']),'TOTALS')
    require(F(m['net_profit'])==F(m['final_equity'])-10000 and F(m['return_pct'])==round_fraction((F(m['final_equity'])-10000)/100),'RETURN')
    loss=sum(losses,F(0));profit=sum(wins,F(0));n=len(run['trades'])
    require((m['profit_factor'] is None if not loss else F(m['profit_factor'])==round_fraction(profit/loss)),'PF')
    require((m['expectancy'] is None if not n else F(m['expectancy'])==round_fraction(pnl/n)),'EXPECTANCY')
    require((m['win_rate'] is None if not n else F(m['win_rate'])==round_fraction(F(len(wins)*100,n))),'WIN_RATE')
    with localcontext() as ctx:ctx.prec=64;verify_equity_timeline(run,bars,rounded)
    daily=run['daily_equity'];returns=[float(F(b['equity'])/F(a['equity'])-1) for a,b in zip(daily,daily[1:]) if b['time']-a['time']==86400 and F(a['equity'])>0]
    if n<20 or len(returns)<30 or statistics.stdev(returns)==0:require(m['sharpe'] is None,'SHARPE_UNDEFINED')
    else:require(abs(m['sharpe']-statistics.mean(returns)/statistics.stdev(returns)*math.sqrt(365))<1e-10,'SHARPE')
    return dict(status='PASS',closed_trades_checked=n,independent_math='EXACT_FRACTION_FILLS_FEES_PNL_RISK_PF_WR_EXPECTANCY',
        reused_oracles=['PR5 verify_exit: every raw OHLC first touch','PR5 verify_equity_timeline: all opening/closing marks and exact MaxDD'],proves_profitability=False)


def conclusion(runs:list) -> dict:
    base={r['split']:r for r in runs if r['scale']=='1'}
    validation=base['validation']['metrics'];test=base['test']['metrics']
    negative=D(validation['net_profit'])<=0 or D(test['net_profit'])<=0
    insufficient=validation['trades']<30 or test['trades']<30
    stable=all(D(r['metrics']['net_profit'])>0 for r in runs if r['split'] in ('train','validation'))
    return dict(status='REJECTED' if negative else 'NEEDS_VALIDATION',
        reasons=(['Validation or reused-test result is nonpositive after costs.'] if negative else [])+
        (['Fewer than30 closed trades in validation or reused test.'] if insufficient else [])+
        ([] if stable else ['Frozen train/validation stop-distance sensitivities are not uniformly positive.'])+
        ['Test period was previously examined; no fresh independent evidence.','CANDIDATE_FOR_PAPER is disabled in v1; no activation capability.'],
        parameter_stability=stable,sample_sufficient_for_claim=False,independent_test=False,
        trials_reported=len(runs),selection_uses_test=False,promotion_allowed=False)
