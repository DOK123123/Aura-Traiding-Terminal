"""Bounded public-data, read-only adapter for causal Market Intelligence 3.

No historical outcome pack is shipped: Adaptive Intelligence 1's nine-feature
pack cannot be used with CONTEXT_VECTOR_1.1's 21 features/exit models.
"""
import asyncio
from bisect import bisect_right
from copy import deepcopy
import logging
import time

import httpx
from app.lab.data import public_page
from app.lab.models import Bar, LabError, number, validate_series, digest
from app.lab.series import higher, split_parts
from research.market_intelligence.structure import segment_states, VERSION, VECTOR_NAMES

logger = logging.getLogger(__name__)
ADAPTER_VERSION = 'MARKET_CONTEXT_ONLINE_3.1'
SOURCE = 'Binance · Spot / data-api.binance.vision'
STEPS = {'15m': 900, '1h': 3600, '4h': 14400}
MAX_BARS = 4175  # 260 full 4h blocks plus at most 15 subsequent 15m bars
CACHE_TTL = 30
FETCH_SECONDS = 12
COMPUTE_SECONDS = 8
RESEARCH_REPORT_SHA256 = '4333735fbd71e2d736cca0dd2f5b497bc0384fa32463262f319a6a58009225bf'
RESEARCH_COMMIT = '7711696737630a69994eb37c81ac633874ad0fb4'
DEFINITIONS = {
    'swing': 'Экстремум двух свечей слева и двух справа; известен только после закрытия второй правой свечи. Время pivot и время подтверждения различаются.',
    'structure': 'HH/HL/LH/LL по последним подтверждённым экстремумам; равенство в пределах 0.25 ATR. BOS — закрытие за подтверждённым уровнем на 0.1 ATR; CHoCH — такой пробой против ранее известной структуры.',
    'breakout': 'Закрытие за последним подтверждённым экстремумом на 0.1 ATR; при отсутствии экстремума — отдельный rolling20 fallback, не BOS.',
    'retest': 'Через 1–8 закрытых свечей после пробоя: касание зоны 0.25 ATR и направленное тело/закрытие за уровнем на 0.1 ATR. Возврат закрытия через уровень на 0.1 ATR — failed breakout.',
    'liquidity_sweep': 'Тень за уровнем на 0.1 ATR, закрытие обратно внутри. Двустороннее касание неоднозначно, без направления.',
    'levels': 'Кластеры максимум 32 подтверждённых экстремумов с допуском 0.25 ATR; ближайший подходящий уровень. Если нет — экстремум предыдущих 50 свечей, явно обозначенный fallback.',
    'regime': 'Тренд: направление EMA20/50 и ADX≥25. Диапазон: ADX≤20 и ширина предыдущих 50 свечей≤6 ATR. Иначе UNKNOWN.',
    'volatility': 'ATR/close относительно медианы предыдущих 64 значений: ≥1.5 расширение, ≤0.65 сжатие.',
    'volume': 'Объём текущей закрытой свечи к среднему предыдущих 20; подтверждение ≥1.5. Нулевая база — отсутствие данных.',
    'mtf': '1h/4h только из полных UTC-блоков 4/16 свечей 15m; собственный прогрев 250 свечей, сброс после разрыва. Уровни и структура относятся к выбранному таймфрейму.',
    'smc': 'FVG: непересечение первой и третьей свечи, подтверждение по третьему close; срок 64 свечи/полное заполнение. Order block: последнее противоположное тело за 8 свечей до BOS/CHoCH, срок 16 свечей/пробой дальней границы. Операционные экспериментальные определения, не доказательство действий институциональных участников.',
}
LIMITATIONS = [
    'Только чтение; итог всегда WAIT. Подтверждённого преимущества в исследовании 3.0 не найдено.',
    'Веб-окно ограничено 4175 свечами 15m; EMA/ATR начинаются с этого окна, не с полной истории. После разрыва прогрев начинается заново.',
    'Совместимый проверенный пакет аналогов 3.0 не установлен. Пакет replay 1.0 не используется: другие признаки, нормализация и модель выхода.',
    '2025 уже изучен, не является новым blind holdout. Нужна отдельная forward validation.',
    'Публичный REST snapshot, не подтверждение WebSocket или работы торгового бота.',
]


def unavailable(code='UNAVAILABLE', freshness='UNAVAILABLE'):
    return dict(symbol='BTCUSDT', timeframe=None, source=SOURCE,
        last_closed_at=None, fetched_at=None, analyzed_at=None, status=code,
        freshness=dict(status=freshness, age_seconds=None, delivery_age_seconds=None),
        state=None, structure_events=[], levels=None, regime='UNKNOWN', mtf=None,
        history=None, analog_availability=dict(status='ANALOG_DATA_UNAVAILABLE',
            model_version=VERSION, pack_version=None, sha256=None, coverage=None,
            sample_count=None, feature_definitions=list(VECTOR_NAMES), exit_model=None,
            reason='INCOMPATIBLE_V1_PACK', limitations=LIMITATIONS[2:3]),
        research_evidence=dict(status='NO_EDGE_FOUND', hypotheses=42, candidates=0,
            live_expectancy=None, source='docs/AURA_MARKET_INTELLIGENCE_3.json',
            source_sha256=RESEARCH_REPORT_SHA256, source_commit=RESEARCH_COMMIT,
            interpretation='Историческое исследование, не статистика текущей ситуации и не разрешение сделки.'),
        decision=dict(action='WAIT', mode='READ_ONLY', reason=code,
            validation='FORWARD_VALIDATION_REQUIRED', execution_enabled=False,
            real_money_execution='DISABLED'),
        limitations=list(LIMITATIONS), definitions=DEFINITIONS,
        model_version=VERSION, adapter_version=ADAPTER_VERSION)


async def fetch_window(page, now):
    """Reuse fixed public_page transport; <=5 bounded pages, no disk/history writes."""
    end = int(now) // 900 * 900
    start = end // 14400 * 14400 - 4160 * 900
    cursor = start
    bars = []
    forming = 0
    async with asyncio.timeout(FETCH_SECONDS):
        for _ in range(5):
            if cursor >= end:
                break
            rows = await page(dict(symbol='BTCUSDT', interval='15m',
                startTime=cursor*1000, endTime=end*1000-1,
                limit=min(1000, (end-cursor)//900)))
            if not isinstance(rows, list) or len(rows)>1000:
                raise LabError('INVALID_DATA')
            if not rows:
                break
            accepted = []
            previous = None
            for row in rows:
                if not isinstance(row, list) or len(row)!=12 or type(row[0]) is not int or type(row[6]) is not int or row[0]%900000:
                    raise LabError('INVALID_TIMESTAMPS')
                stamp = row[0]//1000
                if previous is not None and stamp <= previous:
                    raise LabError('DUPLICATE_OR_UNORDERED')
                previous = stamp
                if row[6] != (stamp+900)*1000-1:
                    raise LabError('INVALID_CLOSE_TIME')
                b = Bar(stamp, *[number(row[k]) for k in (1,2,3,4,5)])
                # Validate price integrity even for an unexpected forming row.
                b.validate(900, stamp+900)
                if stamp >= end:
                    forming += 1
                    continue
                if stamp < cursor or stamp < start:
                    raise LabError('DUPLICATE_OR_UNORDERED')
                accepted.append(b)
            if not accepted:
                break
            bars.extend(accepted)
            if len(bars)>MAX_BARS:
                raise LabError('DATA_LIMIT')
            cursor = bars[-1].time+900
    # Gaps allowed as explicit resets; duplicates/order are never repaired by sorting.
    for a,b in zip(bars,bars[1:]):
        if b.time<=a.time:
            raise LabError('DUPLICATE_OR_UNORDERED')
    return bars, dict(requested_start=start, requested_end_exclusive=end,
        received_count=len(bars), forming_excluded=forming,
        complete=bool(bars) and bars[0].time==start and bars[-1].time+900==end
            and len(bars)==(end-start)//900,
        max_bars=MAX_BARS, fetch_pages_limit=5)


def analyze_window(bars, now, provenance=None):
    """Same 3.0 algorithms. All frames reset across gaps; no future pivot or fill."""
    if not bars or len(bars)>MAX_BARS:
        raise LabError('INSUFFICIENT_HISTORY' if not bars else 'DATA_LIMIT')
    for b in bars:
        b.validate(900, int(now))
    if any(b.time<=a.time for a,b in zip(bars,bars[1:])):
        raise LabError('DUPLICATE_OR_UNORDERED')
    deadline = time.monotonic()+COMPUTE_SECONDS
    gaps=[dict(previous_closed_at=a.time+900, next_open_at=b.time,
               missing_candles=(b.time-a.time)//900-1) for a,b in zip(bars,bars[1:]) if b.time-a.time!=900]
    # Only the final known continuous segment is eligible for current context.
    latest_part = split_parts(bars, 900)[-1]
    maps = {}
    raw_last = {}
    for tf,step in STEPS.items():
        frame = bars if step==900 else higher(bars, step)
        raw_last[tf] = frame[-1].time+step if frame else None
        mapping = {}
        for part in split_parts(frame, step):
            validate_series(part, step, int(now))
            for state in segment_states(part, step, deadline=deadline):
                if state:
                    mapping[state['timestamp']] = state
        maps[tf] = mapping
    snapshots = {}
    history = dict(provenance or {}, source_sha256=digest([b.data() for b in bars]),
        window_start=bars[0].time, window_end_exclusive=bars[-1].time+900,
        base_count=len(bars), continuous_base_count=len(latest_part), gaps=gaps,
        missing_candles=sum(g['missing_candles'] for g in gaps),
        policy='RESET_WARMUP_NO_SYNTHETIC_FILL', warmup_per_timeframe=250)
    for tf,step in STEPS.items():
        value = unavailable('INSUFFICIENT_HISTORY', 'INSUFFICIENT_HISTORY')
        value.update(timeframe=tf, last_closed_at=raw_last[tf], history=history)
        at = raw_last[tf]
        state = maps[tf].get(at)
        # Reject older pre-gap state. A partial current higher block is not a candle.
        if not state or state['segment_start'] < (latest_part[0].time+step-1)//step*step:
            snapshots[tf] = value
            continue
        state = deepcopy(state)
        mask = 0
        for j, key in enumerate(('1h','4h')):
            other_step = STEPS[key]
            times = sorted(maps[key])
            k = bisect_right(times, state['timestamp'])-1
            other = maps[key][times[k]] if k>=0 else None
            if (other and other['segment_start'] >= (latest_part[0].time+other_step-1)//other_step*other_step
                    and state['timestamp']-other['timestamp']<other_step):
                mask |= 1<<j
                state['mtf']['h1' if j==0 else 'h4'] = dict(direction=other['trend_direction'], closed_at=other['timestamp'])
        state['mtf']['known_mask'] = mask
        directions=[state['mtf'][key]['direction'] if state['mtf'][key] else 0 for key in ('h1','h4')]
        state['mtf']['alignment']=mask==3 and directions[0]==directions[1]==state['trend_direction']!=0
        state['vector'][-3:]=directions+[mask]
        events=[]
        for row in list(maps[tf].values())[-32:]:
            if row['segment_start'] != state['segment_start']:
                continue
            for name in ('breakout','failed_breakout','retest','structure_event','liquidity_sweep'):
                if row[name]:
                    events.append(dict(type=name, value=row[name], confirmed_at=row['timestamp']))
            for pivot in row['confirmed_pivots']:
                events.append(dict(type='swing', **pivot))
        # Research setups deliberately omitted: no unvalidated BUY/SELL plan.
        value.update(status='OK', state=state, regime=state['regime'],
            structure_events=events[-32:], mtf=state['mtf'],
            levels=dict(support=state['support'], resistance=state['resistance'],
                support_source=state['support_source'], resistance_source=state['resistance_source'],
                support_zones=state['support_zones'], resistance_zones=state['resistance_zones']),
            decision=dict(value['decision'], reason='NO_EDGE_FOUND'))
        snapshots[tf] = value
    return snapshots


def error_code(exc):
    if isinstance(exc, (TimeoutError, httpx.TimeoutException)):
        return 'TIMEOUT'
    if isinstance(exc, httpx.HTTPStatusError):
        status=exc.response.status_code
        return 'RATE_LIMIT' if status in (418,429) else 'REGION_RESTRICTED' if status in (403,451) else 'UPSTREAM_HTTP_ERROR'
    if isinstance(exc, httpx.RequestError):
        return 'NETWORK_ERROR'
    if isinstance(exc, LabError):
        allowed={'INVALID_DATA','INVALID_TIMESTAMPS','DUPLICATE_OR_UNORDERED',
            'INVALID_CLOSE_TIME','INVALID_OHLCV','DATA_LIMIT','INSUFFICIENT_HISTORY',
            'MISSING_CANDLES','PUBLIC_DATA_UNAVAILABLE'}
        return exc.code if exc.code in allowed else 'UNAVAILABLE'
    return 'UNAVAILABLE'


class MarketContext:
    """One shared refresh task/cache across three frames, bounded request/CPU work."""
    def __init__(self, page, clock=time.time, monotonic=time.monotonic):
        self.page, self.clock, self.monotonic = page, clock, monotonic
        self.cache = None
        self.at = None
        self.task = None
        self.closed = False
        self.cooldown_until = 0

    @classmethod
    def from_client(cls, client):
        async def page(query):
            return await public_page(client, query)
        return cls(page)

    async def refresh(self):
        try:
            bars, provenance = await fetch_window(self.page, self.clock())
            data = await asyncio.to_thread(analyze_window, bars, self.clock(), provenance)
            self.cache = data
            for value in data.values():
                value['fetched_at'] = self.clock()
                value['analyzed_at'] = self.clock()
        except asyncio.CancelledError:
            raise
        except (httpx.HTTPError, LabError, ValueError, TypeError, KeyError, IndexError, TimeoutError) as exc:
            code=error_code(exc)
            # Whitelisted code only: never exception body, URL, headers or credentials.
            logger.warning('Market context public snapshot failed: code=%s', code)
            if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (418,429):
                retry = exc.response.headers.get('Retry-After','')
                if retry.isdigit() and len(retry)<=8:
                    self.cooldown_until=self.monotonic()+int(retry)
            self.cache = {tf: dict(unavailable(code), timeframe=tf) for tf in STEPS}
        finally:
            self.at = self.monotonic()

    async def snapshot(self, timeframe):
        if timeframe not in STEPS:
            raise ValueError('INVALID_TIMEFRAME')
        if self.closed:
            return dict(unavailable(), timeframe=timeframe)
        if self.task is None or self.task.done():
            if (self.at is None or self.monotonic()-self.at>=CACHE_TTL) and self.monotonic()>=self.cooldown_until:
                self.task=asyncio.create_task(self.refresh())
        if self.task and not self.task.done():
            try:
                # Shield a single bounded refresh from disconnected HTTP clients.
                await asyncio.wait_for(asyncio.shield(self.task), FETCH_SECONDS+COMPUTE_SECONDS+2)
            except TimeoutError:
                return dict(unavailable('TIMEOUT'), timeframe=timeframe)
        value = deepcopy(self.cache[timeframe]) if self.cache else dict(unavailable(), timeframe=timeframe)
        now = self.clock()
        if value['last_closed_at'] is not None:
            age = max(0,now-value['last_closed_at'])
            delivery_age = max(0,now-value['fetched_at']) if value['fetched_at'] is not None else None
            base_closed_at = (value.get('history') or {}).get('window_end_exclusive')
            base_age = now-base_closed_at if base_closed_at is not None else None
            if now < value['last_closed_at'] or age>=STEPS[timeframe] or base_age is not None and (base_age<0 or base_age>=900) or delivery_age is not None and delivery_age>90:
                value.update(status='STALE', state=None, levels=None, structure_events=[], mtf=None, regime='UNKNOWN')
                value['freshness']=dict(status='STALE',age_seconds=age,delivery_age_seconds=delivery_age,base_age_seconds=base_age)
                value['decision']['reason']='STALE_DATA'
            else:
                value['freshness']=dict(status='FRESH' if value['status']=='OK' else 'INSUFFICIENT_HISTORY', age_seconds=age, delivery_age_seconds=delivery_age,base_age_seconds=base_age)
        return value

    async def close(self):
        self.closed=True
        if self.task and not self.task.done():
            self.task.cancel()
            await asyncio.gather(self.task,return_exceptions=True)
