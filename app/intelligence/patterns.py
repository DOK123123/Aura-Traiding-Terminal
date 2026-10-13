"""Deterministic closed-candle detectors and extensible, honest model catalogue."""
from dataclasses import dataclass
from decimal import Decimal as D
from app.lab.indicators import ema,rsi,atr,adx

@dataclass(frozen=True)
class Pattern:
    id:str
    ru:str
    category:str
    status:str='IMPLEMENTED'
    version:str='1.0'
    limitation:str='Deterministic research definition; recognition is not a trading edge.'

NAMES=[('hammer','Молот'),('hanging_man','Повешенный'),('inverted_hammer','Перевёрнутый молот'),('shooting_star','Падающая звезда'),('doji','Доджи'),('long_legged_doji','Длинноногий доджи'),('dragonfly_doji','Доджи стрекоза'),('gravestone_doji','Доджи надгробие'),('bullish_engulfing','Бычье поглощение'),('bearish_engulfing','Медвежье поглощение'),('bullish_harami','Бычье харами'),('bearish_harami','Медвежье харами'),('harami_cross','Крест харами'),('morning_star','Утренняя звезда'),('evening_star','Вечерняя звезда'),('morning_doji_star','Утренняя звезда доджи'),('evening_doji_star','Вечерняя звезда доджи'),('marubozu','Марубозу'),('spinning_top','Волчок'),('inside_bar','Внутренний бар'),('outside_bar','Внешний бар')]
REGISTRY={k:Pattern(k,v,'Candlestick') for k,v in NAMES}
EXTENSIONS={}

def register(pattern,detector):
    """Code-owned pure detector extension; no runtime loading/hooks/network."""
    if pattern.id in REGISTRY or not callable(detector):raise ValueError('Duplicate or invalid detector')
    REGISTRY[pattern.id]=pattern;EXTENSIONS[pattern.id]=detector
for k,v,c in [('ema_alignment','Согласование EMA','Indicators'),('adx_strength','Сила ADX','Indicators'),('volume_spike','Всплеск объёма','Volume'),('atr_compression','Сжатие ATR','Volatility'),('atr_expansion','Расширение ATR','Volatility'),('breakout','Пробой диапазона','Price Action'),('swing_high','Подтверждённый максимум','Market Structure'),('swing_low','Подтверждённый минимум','Market Structure'),('fvg','Разрыв справедливой стоимости','SMC')]:
    REGISTRY[k]=Pattern(k,v,c,'EXPERIMENTAL',limitation='Fixed causal definition; SMC/structure terminology is ambiguous; no profitability claim.')
for k in ['three_white_soldiers','three_black_crows','three_inside_up','three_inside_down','three_outside_up','three_outside_down','piercing_line','dark_cloud_cover','tweezer_top','tweezer_bottom','bullish_kicker','bearish_kicker','rising_three_methods','falling_three_methods','double_top','double_bottom','head_shoulders','inverse_head_shoulders','triple_top','triple_bottom','ascending_triangle','descending_triangle','symmetrical_triangle','rectangle','flag','pennant','rising_wedge','falling_wedge','channel','cup_handle','breakout_retest','false_breakout','range_rejection','trend_pullback','higher_high_low','lower_high_low','bos','choch','liquidity_sweep','equal_high_low','order_block','rsi_divergence','macd_divergence']:
    cat='Chart Patterns' if k in ['double_top','double_bottom','head_shoulders','inverse_head_shoulders','triple_top','triple_bottom','ascending_triangle','descending_triangle','symmetrical_triangle','rectangle','flag','pennant','rising_wedge','falling_wedge','channel','cup_handle'] else 'SMC' if k in ['bos','choch','liquidity_sweep','equal_high_low','order_block'] else 'Indicators' if 'divergence' in k else 'Price Action'
    REGISTRY[k]=Pattern(k,k.replace('_',' ').title(),cat,'PLANNED',limitation='Not detected: confirmed-pivot tolerances, trend/context and independent regression fixtures still required.')

TRANSLATIONS={'three_white_soldiers':'Три белых солдата','three_black_crows':'Три чёрных вороны','three_inside_up':'Три внутри вверх','three_inside_down':'Три внутри вниз','three_outside_up':'Три снаружи вверх','three_outside_down':'Три снаружи вниз','piercing_line':'Просвет в облаках','dark_cloud_cover':'Завеса тёмных облаков','tweezer_top':'Пинцет вершина','tweezer_bottom':'Пинцет дно','bullish_kicker':'Бычий кикер','bearish_kicker':'Медвежий кикер','rising_three_methods':'Три метода роста','falling_three_methods':'Три метода падения','double_top':'Двойная вершина','double_bottom':'Двойное дно','head_shoulders':'Голова и плечи','inverse_head_shoulders':'Перевёрнутая голова и плечи','triple_top':'Тройная вершина','triple_bottom':'Тройное дно','ascending_triangle':'Восходящий треугольник','descending_triangle':'Нисходящий треугольник','symmetrical_triangle':'Симметричный треугольник','rectangle':'Прямоугольник','flag':'Флаг','pennant':'Вымпел','rising_wedge':'Восходящий клин','falling_wedge':'Нисходящий клин','channel':'Канал','cup_handle':'Чашка с ручкой','breakout_retest':'Ретест пробоя','false_breakout':'Ложный пробой','range_rejection':'Отбой от диапазона','trend_pullback':'Откат по тренду','higher_high_low':'Повышающиеся экстремумы','lower_high_low':'Понижающиеся экстремумы','bos':'Слом структуры','choch':'Смена характера структуры','liquidity_sweep':'Снятие ликвидности','equal_high_low':'Равные максимумы и минимумы','order_block':'Ордер-блок','rsi_divergence':'Дивергенция RSI','macd_divergence':'Дивергенция MACD'}
for k,ru in TRANSLATIONS.items():
    from dataclasses import replace
    REGISTRY[k]=replace(REGISTRY[k],ru=ru,category='Candlestick' if k in list(TRANSLATIONS)[:14] else REGISTRY[k].category)


def features(bars):
    if len(bars)<200:raise ValueError('INSUFFICIENT_DATA')
    c=[float(b.close) for b in bars];a=atr(bars)[-1];ax=adx(bars)[0][-1]
    if a is None or a<=0 or ax is None:raise ValueError('INSUFFICIENT_DATA')
    f,s=ema(c,20)[-1],ema(c,50)[-1];strength=rsi(c)[-1]
    av=sum(float(b.volume) for b in bars[-21:-1])/20
    relative=float(bars[-1].volume)/av if av>0 else None
    v=[(f-s)/a,ax/100,strength/100,a/c[-1]*100,min(relative or 0,5)/5,(c[-1]-min(float(b.low) for b in bars[-51:-1]))/a/10]
    direction='LONG' if f>s else 'SHORT' if f<s else None
    prior=[x/float(b.close) for b,x in zip(bars[-65:-1],atr(bars)[-65:-1]) if x is not None]
    from statistics import median
    vol=(a/c[-1])/median(prior) if prior and median(prior)>0 else 1
    regime='VOLATILITY_EXPANSION' if vol>=1.5 else 'VOLATILITY_COMPRESSION' if vol<=.65 else 'TREND_UP' if ax>=25 and direction=='LONG' else 'TREND_DOWN' if ax>=25 and direction=='SHORT' else 'RANGE' if ax<=20 else 'UNKNOWN'
    return dict(vector=v,direction=direction,regime=regime,adx=ax,rsi=strength,atr=a,relative_volume=relative,volatility_ratio=vol)


def detect(bars,symbol='BTCUSDT',timeframe='15m',cutoff=None):
    step={'15m':900,'1h':3600,'4h':14400}[timeframe]
    if not bars or len(bars)>500:raise ValueError('INVALID_DATA')
    through=bars[-1].time+step if cutoff is None else cutoff
    for b in bars:b.validate(step,through)
    if any(b.time-a.time!=step for a,b in zip(bars,bars[1:])):raise ValueError('DATA_GAP')
    b=bars[-1];span=b.high-b.low
    if span<=0:return []
    body=abs(b.close-b.open);up=b.high-max(b.open,b.close);down=min(b.open,b.close)-b.low;ratio=body/span
    trend=0
    if len(bars)>=6:
        trend=1 if bars[-2].close>bars[-6].close else -1 if bars[-2].close<bars[-6].close else 0
    found=[]
    def add(k,side=None,evidence=None):
        p=REGISTRY[k];found.append(dict(timestamp=b.time+step,symbol=symbol,timeframe=timeframe,pattern_id=k,direction=side,version=p.version,parameters=dict(body_fraction=float(ratio)),confirmations=evidence or [],limitations=[p.limitation],status=p.status))
    if ratio<=D('.1'):
        add('doji')
        if up/span>=D('.3') and down/span>=D('.3'):add('long_legged_doji')
        if down/span>=D('.6') and up/span<=D('.1'):add('dragonfly_doji','LONG')
        if up/span>=D('.6') and down/span<=D('.1'):add('gravestone_doji','SHORT')
    if D('.1')<ratio<=D('.3') and up>=body and down>=body:add('spinning_top')
    if ratio>=D('.9'):add('marubozu','LONG' if b.close>b.open else 'SHORT')
    if D('.1')<ratio<=D('.35'):
        if down>=body*2 and up<=body*D('.5') and trend:
            add('hammer' if trend<0 else 'hanging_man','LONG' if trend<0 else 'SHORT',['prior4_close_trend'])
        if up>=body*2 and down<=body*D('.5') and trend:
            add('inverted_hammer' if trend<0 else 'shooting_star','LONG' if trend<0 else 'SHORT',['prior4_close_trend'])
    if len(bars)>=2:
        a=bars[-2];ab=abs(a.close-a.open)
        if b.high<a.high and b.low>a.low:add('inside_bar')
        if b.high>a.high and b.low<a.low:add('outside_bar')
        if trend<0 and b.close>b.open and a.close<a.open and b.open<=a.close and b.close>=a.open:add('bullish_engulfing','LONG',['prior_downtrend'])
        if trend>0 and b.close<b.open and a.close>a.open and b.open>=a.close and b.close<=a.open:add('bearish_engulfing','SHORT',['prior_uptrend'])
        inside=max(b.open,b.close)<max(a.open,a.close) and min(b.open,b.close)>min(a.open,a.close) and body<ab*D('.6')
        if inside:
            if ratio<=D('.1') and trend:add('harami_cross','LONG' if trend<0 else 'SHORT')
            elif trend<0 and b.close>b.open and a.close<a.open:add('bullish_harami','LONG')
            elif trend>0 and b.close<b.open and a.close>a.open:add('bearish_harami','SHORT')
    if len(bars)>=7:
        a,m=bars[-3:-1];mid=(a.open+a.close)/2;oldtrend=1 if bars[-4].close>bars[-7].close else -1 if bars[-4].close<bars[-7].close else 0
        small=abs(m.close-m.open)<abs(a.close-a.open)*D('.35')
        if small and a.close<a.open and b.close>b.open and b.close>mid and oldtrend<0:
            add('morning_star','LONG',['three_bars','prior_downtrend'])
            if abs(m.close-m.open)<= (m.high-m.low)*D('.1'):add('morning_doji_star','LONG')
        if small and a.close>a.open and b.close<b.open and b.close<mid and oldtrend>0:
            add('evening_star','SHORT',['three_bars','prior_uptrend'])
            if abs(m.close-m.open)<= (m.high-m.low)*D('.1'):add('evening_doji_star','SHORT')
    if len(bars)>=200:
        c=features(bars);add('ema_alignment',c['direction']);add('adx_strength',c['direction'] if c['adx']>=25 else None)
        if c['relative_volume'] is not None and c['relative_volume']>=2:add('volume_spike')
        if c['volatility_ratio']>=1.5:add('atr_expansion')
        if c['volatility_ratio']<=.65:add('atr_compression')
        if b.close>max(x.high for x in bars[-21:-1]):add('breakout','LONG')
        if b.close<min(x.low for x in bars[-21:-1]):add('breakout','SHORT')
    if len(bars)>=5:
        p=bars[-3]
        if p.high>max(x.high for x in bars[-5:-3]+bars[-2:]):add('swing_high',None,['pivot_time:'+str(p.time),'confirmed2_right_bars'])
        if p.low<min(x.low for x in bars[-5:-3]+bars[-2:]):add('swing_low',None,['pivot_time:'+str(p.time),'confirmed2_right_bars'])
        if b.low>bars[-3].high:add('fvg','LONG',['three_bar_nonoverlap'])
        if b.high<bars[-3].low:add('fvg','SHORT',['three_bar_nonoverlap'])
    for k,detector in EXTENSIONS.items():
        side=detector(tuple(bars))
        if side not in (None,'LONG','SHORT'):raise ValueError('Invalid detector output')
        if side:add(k,side,['registered_pure_detector'])
    return found


def catalogue():
    return [dict(id=p.id,name_ru=p.ru,name_en=p.id.replace('_',' ').title(),category=p.category,status=p.status,version=p.version,timeframes=['15m','1h','4h'],parameters={'definition':'body fractions, contextual4-close trend; docs'},algorithm='app.intelligence.patterns.detect' if p.status!='PLANNED' else None,tests='tests/test_intelligence.py' if p.status!='PLANNED' else None,limitations=p.limitation) for p in REGISTRY.values()]
