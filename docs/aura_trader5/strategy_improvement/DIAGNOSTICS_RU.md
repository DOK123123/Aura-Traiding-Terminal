# Диагностика baseline

Сопоставления описательные, а не установленные причины убытков. Все числовые признаки сохранены в results.json.gz. flat/EMA/RSI/ATR/структура/час рассчитаны только на момент сигнала. reversal_POSTHOC и MAE/MFE рассчитаны позднее исключительно для объяснения — ни один вариант их не видит. Количество проверенных срезов велико: случайные удачные подгруппы ожидаемы, использовать их для выбора часового фильтра нельзя.

| TF / стратегия / сторона / срез / значение | n / закрыто | SL / TP / TIMEOUT | E[R] | PF | До комиссии, fill R | Комиссия R |
|---|---:|---:|---:|---:|---:|---:|
| 15m / TREND_PULLBACK / LONG / flat / FLAT_CAUSAL | 5/5 | 3/1/1 | -0.402 | 0.445 | -0.129 | 0.273 |
| 15m / TREND_PULLBACK / LONG / structure / HH_HL | 30/29 | 20/5/5 | -0.550 | 0.373 | -0.275 | 0.275 |
| 15m / TREND_PULLBACK / LONG / trend / LONG | 30/29 | 20/5/5 | -0.550 | 0.373 | -0.275 | 0.275 |
| 15m / TREND_PULLBACK / LONG / ema_separation / <0.5 | 8/8 | 5/1/2 | -0.650 | 0.264 | -0.380 | 0.270 |
| 15m / TREND_PULLBACK / LONG / rsi / 50–60 | 13/13 | 9/2/2 | -0.552 | 0.376 | -0.279 | 0.272 |
| 15m / TREND_PULLBACK / LONG / atr_percent / <0.3% | 10/10 | 7/1/2 | -0.846 | 0.194 | -0.546 | 0.300 |
| 15m / TREND_PULLBACK / LONG / risk_atr / >=3 | 2/2 | 0/0/2 | -0.294 | 0.000 | -0.129 | 0.164 |
| 15m / TREND_PULLBACK / LONG / cost_burden / 0.25–0.5 | 19/18 | 13/3/3 | -0.600 | 0.321 | -0.347 | 0.253 |
| 15m / TREND_PULLBACK / LONG / utc_hour / 12–17 | 16/16 | 12/1/3 | -0.931 | 0.110 | -0.689 | 0.241 |
| 15m / TREND_PULLBACK / LONG / reversal_POSTHOC / OTHER | 18/17 | 8/5/5 | 0.055 | 0.884 | 0.332 | 0.278 |
| 15m / TREND_PULLBACK / LONG / flat / OTHER | 25/24 | 17/4/4 | -0.581 | 0.358 | -0.306 | 0.276 |
| 15m / TREND_PULLBACK / LONG / rsi / 60–70 | 16/15 | 10/3/3 | -0.493 | 0.407 | -0.214 | 0.278 |
| 15m / TREND_PULLBACK / LONG / risk_atr / 2–3 | 12/12 | 11/0/1 | -1.343 | 0.000 | -1.059 | 0.284 |
| 15m / TREND_PULLBACK / LONG / ema_separation / 0.5–1 | 7/7 | 4/2/1 | -0.016 | 0.870 | 0.290 | 0.306 |
| 15m / TREND_PULLBACK / LONG / atr_percent / 0.3–0.8% | 20/19 | 13/4/3 | -0.395 | 0.461 | -0.133 | 0.262 |
| 15m / TREND_PULLBACK / LONG / cost_burden / >=0.5 | 10/10 | 7/2/1 | -0.487 | 0.529 | -0.156 | 0.332 |
| 15m / TREND_PULLBACK / LONG / ema_separation / >=1 | 15/14 | 11/2/2 | -0.760 | 0.262 | -0.498 | 0.263 |
| 15m / TREND_PULLBACK / LONG / reversal_POSTHOC / ADVERSE_CLOSE_AFTER_SIGNAL | 12/12 | 12/0/0 | -1.408 | 0.000 | -1.136 | 0.272 |
| 15m / TREND_PULLBACK / LONG / risk_atr / <2 | 16/15 | 9/5/2 | 0.049 | 0.850 | 0.332 | 0.283 |
| 15m / TREND_PULLBACK / LONG / utc_hour / 00–05 | 9/8 | 6/1/2 | -0.703 | 0.367 | -0.393 | 0.311 |
| 15m / BREAKOUT_RETEST / SHORT / flat / OTHER | 12/11 | 7/0/4 | -1.013 | 0.019 | -0.757 | 0.256 |
| 15m / BREAKOUT_RETEST / SHORT / structure / HH_HL | 1/1 | 1/0/0 | -1.468 | 0.000 | -1.156 | 0.312 |
| 15m / BREAKOUT_RETEST / SHORT / trend / LONG | 6/5 | 4/0/1 | -1.257 | 0.000 | -0.974 | 0.284 |
| 15m / BREAKOUT_RETEST / SHORT / ema_separation / >=1 | 4/4 | 4/0/0 | -1.432 | 0.000 | -1.144 | 0.288 |
| 15m / BREAKOUT_RETEST / SHORT / rsi / 40–50 | 4/3 | 3/0/0 | -1.448 | 0.000 | -1.149 | 0.299 |
| 15m / BREAKOUT_RETEST / SHORT / atr_percent / 0.3–0.8% | 13/12 | 7/0/5 | -0.975 | 0.018 | -0.718 | 0.257 |
| 15m / BREAKOUT_RETEST / SHORT / risk_atr / <2 | 11/10 | 5/0/5 | -0.912 | 0.026 | -0.642 | 0.269 |
| 15m / BREAKOUT_RETEST / SHORT / cost_burden / 0.25–0.5 | 11/10 | 5/0/5 | -0.871 | 0.022 | -0.629 | 0.242 |
| 15m / BREAKOUT_RETEST / SHORT / utc_hour / 00–05 | 5/5 | 5/0/0 | -1.395 | 0.000 | -1.132 | 0.263 |
| 15m / BREAKOUT_RETEST / SHORT / reversal_POSTHOC / ADVERSE_CLOSE_AFTER_SIGNAL | 6/5 | 5/0/0 | -1.408 | 0.000 | -1.136 | 0.272 |
| 15m / BREAKOUT_RETEST / SHORT / structure / RANGE | 5/4 | 2/0/2 | -1.004 | 0.000 | -0.736 | 0.267 |
| 15m / BREAKOUT_RETEST / SHORT / rsi / 50–60 | 2/2 | 2/0/0 | -1.442 | 0.000 | -1.147 | 0.295 |
| 15m / BREAKOUT_RETEST / SHORT / cost_burden / >=0.5 | 2/2 | 2/0/0 | -1.494 | 0.000 | -1.165 | 0.329 |
| 15m / BREAKOUT_RETEST / LONG / flat / OTHER | 11/10 | 8/2/0 | -0.608 | 0.410 | -0.336 | 0.272 |
| 15m / BREAKOUT_RETEST / LONG / structure / RANGE | 8/6 | 5/1/0 | -0.713 | 0.386 | -0.460 | 0.253 |
| 15m / BREAKOUT_RETEST / LONG / trend / LONG | 10/10 | 8/2/0 | -0.592 | 0.393 | -0.331 | 0.261 |
| 15m / BREAKOUT_RETEST / LONG / ema_separation / >=1 | 7/7 | 5/2/0 | -0.244 | 0.606 | 0.014 | 0.258 |
| 15m / BREAKOUT_RETEST / LONG / rsi / 60–70 | 7/6 | 5/1/0 | -0.705 | 0.379 | -0.457 | 0.248 |
| 15m / BREAKOUT_RETEST / LONG / atr_percent / 0.3–0.8% | 13/12 | 10/2/0 | -0.741 | 0.329 | -0.469 | 0.272 |
| 15m / BREAKOUT_RETEST / LONG / risk_atr / <2 | 12/11 | 9/2/0 | -0.691 | 0.374 | -0.412 | 0.279 |
| 15m / BREAKOUT_RETEST / LONG / cost_burden / 0.25–0.5 | 8/8 | 7/1/0 | -0.859 | 0.259 | -0.620 | 0.239 |
| 15m / BREAKOUT_RETEST / LONG / utc_hour / 12–17 | 9/8 | 7/1/0 | -0.893 | 0.279 | -0.631 | 0.262 |
| 15m / BREAKOUT_RETEST / LONG / reversal_POSTHOC / OTHER | 9/7 | 5/2/0 | -0.253 | 0.645 | 0.011 | 0.264 |
| 15m / TREND_PULLBACK / LONG / utc_hour / 18–23 | 3/3 | 1/2/0 | 1.204 | 3.420 | 1.512 | 0.309 |
| 15m / BREAKOUT_RETEST / LONG / structure / HH_HL | 5/5 | 4/1/0 | -0.621 | 0.323 | -0.340 | 0.280 |
| 15m / BREAKOUT_RETEST / LONG / rsi / >=70 | 4/4 | 3/1/0 | -0.422 | 0.416 | -0.141 | 0.281 |
| 15m / BREAKOUT_RETEST / LONG / cost_burden / >=0.5 | 6/4 | 3/1/0 | -0.505 | 0.538 | -0.168 | 0.336 |
| 15m / BREAKOUT_RETEST / LONG / utc_hour / 00–05 | 1/1 | 0/1/0 | 2.515 | — | 2.838 | 0.324 |
| 15m / BREAKOUT_RETEST / SHORT / reversal_POSTHOC / OTHER | 7/7 | 2/0/5 | -0.666 | 0.043 | -0.420 | 0.246 |
| 15m / BREAKOUT_RETEST / SHORT / structure / LH_LL | 7/7 | 4/0/3 | -0.889 | 0.030 | -0.645 | 0.243 |
| 15m / TREND_PULLBACK / SHORT / flat / OTHER | 21/20 | 17/2/2 | -0.968 | 0.174 | -0.671 | 0.297 |
| 15m / TREND_PULLBACK / SHORT / structure / LH_LL | 25/24 | 21/2/2 | -1.055 | 0.143 | -0.753 | 0.302 |
| 15m / TREND_PULLBACK / SHORT / trend / SHORT | 25/24 | 21/2/2 | -1.055 | 0.143 | -0.753 | 0.302 |
| 15m / TREND_PULLBACK / SHORT / ema_separation / 0.5–1 | 10/10 | 9/0/1 | -1.232 | 0.009 | -0.974 | 0.258 |
| 15m / TREND_PULLBACK / SHORT / rsi / <40 | 18/17 | 15/1/2 | -1.113 | 0.103 | -0.820 | 0.293 |
| 15m / TREND_PULLBACK / SHORT / atr_percent / 0.3–0.8% | 19/19 | 18/0/1 | -1.358 | 0.005 | -1.065 | 0.293 |
| 15m / TREND_PULLBACK / SHORT / risk_atr / <2 | 13/13 | 12/1/0 | -1.173 | 0.127 | -0.852 | 0.320 |
| 15m / TREND_PULLBACK / SHORT / cost_burden / 0.25–0.5 | 10/10 | 9/0/1 | -1.249 | 0.009 | -0.980 | 0.270 |
| 15m / TREND_PULLBACK / SHORT / utc_hour / 06–11 | 2/2 | 2/0/0 | -1.483 | 0.000 | -1.161 | 0.322 |
| 15m / TREND_PULLBACK / SHORT / reversal_POSTHOC / ADVERSE_CLOSE_AFTER_SIGNAL | 7/7 | 7/0/0 | -1.426 | 0.000 | -1.142 | 0.284 |
| 15m / BREAKOUT_RETEST / SHORT / trend / SHORT | 6/6 | 3/0/3 | -0.800 | 0.037 | -0.569 | 0.232 |
| 15m / BREAKOUT_RETEST / SHORT / ema_separation / 0.5–1 | 6/5 | 2/0/3 | -0.660 | 0.047 | -0.449 | 0.212 |
| 15m / BREAKOUT_RETEST / SHORT / rsi / <40 | 7/7 | 2/0/5 | -0.639 | 0.038 | -0.411 | 0.228 |
| 15m / BREAKOUT_RETEST / SHORT / risk_atr / >=3 | 1/1 | 1/0/0 | -1.247 | 0.000 | -1.082 | 0.164 |
| 15m / BREAKOUT_RETEST / LONG / ema_separation / 0.5–1 | 3/3 | 3/0/0 | -1.459 | 0.000 | -1.153 | 0.306 |
| 15m / TREND_PULLBACK / LONG / cost_burden / <0.25 | 1/1 | 0/0/1 | -0.290 | 0.000 | -0.184 | 0.106 |
| 15m / BREAKOUT_RETEST / LONG / reversal_POSTHOC / ADVERSE_CLOSE_AFTER_SIGNAL | 5/5 | 5/0/0 | -1.423 | 0.000 | -1.141 | 0.282 |
| 15m / TREND_PULLBACK / SHORT / risk_atr / 2–3 | 11/10 | 8/1/2 | -0.884 | 0.192 | -0.591 | 0.293 |
| 15m / TREND_PULLBACK / SHORT / utc_hour / 18–23 | 5/5 | 4/0/1 | -1.136 | 0.023 | -0.838 | 0.298 |
| 15m / TREND_PULLBACK / SHORT / reversal_POSTHOC / OTHER | 18/17 | 14/2/2 | -0.902 | 0.220 | -0.593 | 0.309 |
| 15m / TREND_PULLBACK / SHORT / rsi / 40–50 | 7/7 | 6/1/0 | -0.914 | 0.249 | -0.590 | 0.324 |
| 15m / TREND_PULLBACK / SHORT / cost_burden / >=0.5 | 14/13 | 11/2/1 | -0.892 | 0.297 | -0.554 | 0.338 |
| 15m / TREND_PULLBACK / SHORT / utc_hour / 12–17 | 10/10 | 10/0/0 | -1.461 | 0.000 | -1.154 | 0.307 |
| 15m / BREAKOUT_RETEST / SHORT / utc_hour / 12–17 | 4/3 | 2/0/1 | -1.144 | 0.000 | -0.882 | 0.262 |
| 15m / TREND_PULLBACK / SHORT / utc_hour / 00–05 | 8/7 | 5/2/1 | -0.295 | 0.518 | -0.003 | 0.292 |
| 15m / BREAKOUT_RETEST / LONG / flat / FLAT_CAUSAL | 3/2 | 2/0/0 | -1.404 | 0.000 | -1.135 | 0.269 |
| 15m / BREAKOUT_RETEST / LONG / trend / NEUTRAL | 1/0 | 0/0/0 | — | — | — | — |
| 15m / BREAKOUT_RETEST / LONG / ema_separation / <0.5 | 4/2 | 2/0/0 | -1.404 | 0.000 | -1.135 | 0.269 |
| 15m / BREAKOUT_RETEST / LONG / rsi / 50–60 | 3/2 | 2/0/0 | -1.485 | 0.000 | -1.162 | 0.324 |
| 15m / TREND_PULLBACK / SHORT / ema_separation / >=1 | 10/9 | 7/2/1 | -0.622 | 0.477 | -0.281 | 0.341 |
| 15m / BREAKOUT_RETEST / LONG / trend / SHORT | 3/2 | 2/0/0 | -1.485 | 0.000 | -1.162 | 0.324 |
| 15m / BREAKOUT_RETEST / LONG / risk_atr / 2–3 | 2/1 | 1/0/0 | -1.289 | 0.000 | -1.096 | 0.192 |
| 15m / BREAKOUT_RETEST / SHORT / flat / FLAT_CAUSAL | 1/1 | 0/0/1 | -0.559 | 0.000 | -0.292 | 0.267 |
| 15m / BREAKOUT_RETEST / SHORT / ema_separation / <0.5 | 3/3 | 1/0/2 | -0.891 | 0.000 | -0.600 | 0.291 |
| 15m / BREAKOUT_RETEST / SHORT / utc_hour / 18–23 | 4/4 | 0/0/4 | -0.324 | 0.145 | -0.079 | 0.245 |
| 15m / BREAKOUT_RETEST / SHORT / trend / NEUTRAL | 1/1 | 0/0/1 | -0.612 | 0.000 | -0.339 | 0.272 |
| 15m / BREAKOUT_RETEST / LONG / structure / LH_LL | 1/1 | 1/0/0 | -1.507 | 0.000 | -1.169 | 0.338 |
| 15m / BREAKOUT_RETEST / LONG / utc_hour / 18–23 | 3/2 | 2/0/0 | -1.480 | 0.000 | -1.160 | 0.320 |
| 15m / TREND_PULLBACK / LONG / utc_hour / 06–11 | 2/2 | 1/1/0 | 0.471 | 1.519 | 0.824 | 0.352 |
| 15m / BREAKOUT_RETEST / LONG / utc_hour / 06–11 | 1/1 | 1/0/0 | -1.302 | 0.000 | -1.101 | 0.202 |
| 15m / TREND_PULLBACK / SHORT / atr_percent / <0.3% | 6/5 | 3/2/1 | 0.099 | 1.022 | 0.433 | 0.334 |
| 15m / TREND_PULLBACK / LONG / rsi / 40–50 | 1/1 | 1/0/0 | -1.401 | 0.000 | -1.134 | 0.268 |
| 15m / TREND_PULLBACK / SHORT / flat / FLAT_CAUSAL | 4/4 | 4/0/0 | -1.488 | 0.000 | -1.163 | 0.326 |
| 15m / TREND_PULLBACK / SHORT / ema_separation / <0.5 | 5/5 | 5/0/0 | -1.480 | 0.000 | -1.160 | 0.320 |
| 15m / TREND_PULLBACK / SHORT / risk_atr / >=3 | 1/1 | 1/0/0 | -1.234 | 0.000 | -1.078 | 0.156 |
| 15m / TREND_PULLBACK / SHORT / cost_burden / <0.25 | 1/1 | 1/0/0 | -1.234 | 0.000 | -1.078 | 0.156 |
| 15m / BREAKOUT_RETEST / SHORT / risk_atr / 2–3 | 1/1 | 1/0/0 | -1.339 | 0.000 | -1.113 | 0.226 |
| 15m / BREAKOUT_RETEST / LONG / atr_percent / <0.3% | 1/0 | 0/0/0 | — | — | — | — |
| 1h / TREND_PULLBACK / LONG / flat / OTHER | 25/24 | 19/3/3 | -0.649 | 0.320 | -0.431 | 0.218 |
| 1h / TREND_PULLBACK / LONG / structure / HH_HL | 31/29 | 23/4/4 | -0.635 | 0.343 | -0.412 | 0.223 |
| 1h / TREND_PULLBACK / LONG / trend / LONG | 31/29 | 23/4/4 | -0.635 | 0.343 | -0.412 | 0.223 |
| 1h / TREND_PULLBACK / LONG / ema_separation / 0.5–1 | 12/11 | 7/2/3 | -0.234 | 0.645 | 0.000 | 0.234 |
| 1h / TREND_PULLBACK / LONG / rsi / 50–60 | 14/13 | 9/3/2 | -0.295 | 0.805 | -0.042 | 0.253 |
| 1h / TREND_PULLBACK / LONG / atr_percent / 0.3–0.8% | 30/28 | 22/4/4 | -0.615 | 0.367 | -0.389 | 0.226 |
| 1h / TREND_PULLBACK / LONG / risk_atr / <2 | 23/21 | 18/2/3 | -0.882 | 0.253 | -0.640 | 0.242 |
| 1h / TREND_PULLBACK / LONG / cost_burden / 0.25–0.5 | 24/22 | 16/4/4 | -0.430 | 0.548 | -0.195 | 0.235 |
| 1h / TREND_PULLBACK / LONG / utc_hour / 00–05 | 9/7 | 6/0/3 | -1.038 | 0.056 | -0.812 | 0.225 |
| 1h / TREND_PULLBACK / LONG / reversal_POSTHOC / OTHER | 22/20 | 14/4/4 | -0.311 | 0.548 | -0.094 | 0.217 |
| 1h / TREND_PULLBACK / LONG / rsi / 60–70 | 15/14 | 12/1/2 | -0.845 | 0.138 | -0.654 | 0.191 |
| 1h / TREND_PULLBACK / LONG / utc_hour / 12–17 | 7/7 | 5/1/1 | -0.421 | 0.338 | -0.218 | 0.204 |
| 1h / TREND_PULLBACK / LONG / risk_atr / 2–3 | 8/8 | 5/2/1 | 0.014 | 0.553 | 0.187 | 0.173 |
| 1h / TREND_PULLBACK / LONG / ema_separation / >=1 | 10/10 | 9/1/0 | -0.916 | 0.205 | -0.705 | 0.210 |
| 1h / TREND_PULLBACK / LONG / utc_hour / 06–11 | 8/8 | 6/2/0 | -0.308 | 0.576 | -0.103 | 0.205 |
| 1h / TREND_PULLBACK / LONG / cost_burden / >=0.5 | 2/2 | 2/0/0 | -1.485 | 0.000 | -1.162 | 0.323 |
| 1h / TREND_PULLBACK / LONG / utc_hour / 18–23 | 7/7 | 6/1/0 | -0.818 | 0.386 | -0.558 | 0.260 |
| 1h / BREAKOUT_RETEST / SHORT / flat / OTHER | 29/29 | 20/7/2 | -0.315 | 0.658 | -0.067 | 0.248 |
| 1h / BREAKOUT_RETEST / SHORT / structure / RANGE | 11/11 | 9/2/0 | -0.673 | 0.301 | -0.406 | 0.267 |
| 1h / BREAKOUT_RETEST / SHORT / trend / LONG | 10/10 | 7/3/0 | -0.149 | 0.717 | 0.084 | 0.233 |
| 1h / BREAKOUT_RETEST / SHORT / ema_separation / <0.5 | 13/13 | 9/3/1 | -0.295 | 0.568 | -0.056 | 0.240 |
| 1h / BREAKOUT_RETEST / SHORT / rsi / <40 | 26/26 | 18/6/2 | -0.347 | 0.566 | -0.099 | 0.248 |
| 1h / BREAKOUT_RETEST / SHORT / atr_percent / 0.3–0.8% | 35/35 | 24/9/2 | -0.266 | 0.694 | -0.019 | 0.247 |
| 1h / BREAKOUT_RETEST / SHORT / risk_atr / 2–3 | 2/2 | 1/1/0 | 0.522 | 1.823 | 0.841 | 0.319 |
| 1h / BREAKOUT_RETEST / SHORT / cost_burden / 0.25–0.5 | 32/32 | 22/8/2 | -0.273 | 0.674 | -0.036 | 0.238 |
| 1h / BREAKOUT_RETEST / SHORT / utc_hour / 12–17 | 18/18 | 13/4/1 | -0.385 | 0.589 | -0.134 | 0.250 |
| 1h / BREAKOUT_RETEST / SHORT / reversal_POSTHOC / OTHER | 24/24 | 13/9/2 | 0.243 | 1.218 | 0.488 | 0.245 |
| 1h / TREND_PULLBACK / SHORT / flat / OTHER | 20/19 | 18/1/1 | -1.143 | 0.097 | -0.907 | 0.235 |
| 1h / TREND_PULLBACK / SHORT / structure / LH_LL | 24/23 | 20/3/1 | -0.829 | 0.290 | -0.595 | 0.234 |
| 1h / TREND_PULLBACK / SHORT / trend / SHORT | 24/23 | 20/3/1 | -0.829 | 0.290 | -0.595 | 0.234 |
| 1h / TREND_PULLBACK / SHORT / ema_separation / >=1 | 8/7 | 7/0/1 | -1.374 | 0.000 | -1.125 | 0.250 |
| 1h / TREND_PULLBACK / SHORT / rsi / <40 | 8/7 | 7/0/1 | -1.301 | 0.000 | -1.100 | 0.201 |
| 1h / TREND_PULLBACK / SHORT / atr_percent / 0.3–0.8% | 23/22 | 19/3/1 | -0.815 | 0.320 | -0.575 | 0.240 |
| 1h / TREND_PULLBACK / SHORT / risk_atr / 2–3 | 6/6 | 6/0/0 | -1.298 | 0.000 | -1.099 | 0.199 |
| 1h / TREND_PULLBACK / SHORT / cost_burden / 0.25–0.5 | 22/21 | 18/3/1 | -0.782 | 0.331 | -0.546 | 0.236 |
| 1h / TREND_PULLBACK / SHORT / utc_hour / 12–17 | 6/6 | 6/0/0 | -1.309 | 0.000 | -1.103 | 0.206 |
| 1h / TREND_PULLBACK / SHORT / reversal_POSTHOC / OTHER | 18/17 | 14/3/1 | -0.636 | 0.407 | -0.408 | 0.228 |
| 1h / BREAKOUT_RETEST / SHORT / trend / SHORT | 23/23 | 16/6/1 | -0.305 | 0.669 | -0.049 | 0.256 |
| 1h / BREAKOUT_RETEST / SHORT / ema_separation / >=1 | 11/11 | 5/6/0 | 0.823 | 2.054 | 1.062 | 0.239 |
| 1h / BREAKOUT_RETEST / SHORT / risk_atr / <2 | 35/35 | 25/8/2 | -0.374 | 0.598 | -0.131 | 0.243 |
| 1h / BREAKOUT_RETEST / SHORT / cost_burden / >=0.5 | 4/4 | 3/1/0 | -0.528 | 0.670 | -0.176 | 0.352 |
| 1h / BREAKOUT_RETEST / SHORT / structure / HH_HL | 13/13 | 9/2/2 | -0.541 | 0.506 | -0.301 | 0.240 |
| 1h / BREAKOUT_RETEST / SHORT / ema_separation / 0.5–1 | 13/13 | 12/0/1 | -1.327 | 0.000 | -1.067 | 0.260 |
| 1h / BREAKOUT_RETEST / SHORT / rsi / 40–50 | 10/10 | 7/3/0 | -0.183 | 0.972 | 0.072 | 0.256 |
| 1h / BREAKOUT_RETEST / SHORT / utc_hour / 18–23 | 6/6 | 4/2/0 | -0.055 | 1.130 | 0.204 | 0.259 |
| 1h / BREAKOUT_RETEST / SHORT / structure / LH_LL | 13/13 | 8/5/0 | 0.184 | 1.123 | 0.420 | 0.236 |
| 1h / BREAKOUT_RETEST / SHORT / reversal_POSTHOC / ADVERSE_CLOSE_AFTER_SIGNAL | 13/13 | 13/0/0 | -1.374 | 0.000 | -1.125 | 0.249 |
| 1h / TREND_PULLBACK / SHORT / ema_separation / 0.5–1 | 9/9 | 8/1/0 | -0.893 | 0.205 | -0.668 | 0.225 |
| 1h / TREND_PULLBACK / SHORT / utc_hour / 06–11 | 5/4 | 3/1/1 | -0.384 | 0.685 | -0.128 | 0.256 |
| 1h / TREND_PULLBACK / SHORT / rsi / 40–50 | 16/16 | 13/3/0 | -0.623 | 0.478 | -0.374 | 0.249 |
| 1h / TREND_PULLBACK / SHORT / risk_atr / <2 | 18/17 | 14/3/1 | -0.664 | 0.439 | -0.417 | 0.246 |
| 1h / TREND_PULLBACK / SHORT / cost_burden / >=0.5 | 1/1 | 1/0/0 | -1.497 | 0.000 | -1.166 | 0.331 |
| 1h / TREND_PULLBACK / SHORT / utc_hour / 18–23 | 12/12 | 10/2/0 | -0.693 | 0.400 | -0.453 | 0.240 |
| 1h / BREAKOUT_RETEST / SHORT / rsi / 50–60 | 1/1 | 1/0/0 | -1.180 | 0.000 | -1.060 | 0.120 |
| 1h / BREAKOUT_RETEST / SHORT / atr_percent / >=0.8% | 1/1 | 1/0/0 | -1.180 | 0.000 | -1.060 | 0.120 |
| 1h / BREAKOUT_RETEST / SHORT / cost_burden / <0.25 | 1/1 | 1/0/0 | -1.180 | 0.000 | -1.060 | 0.120 |
| 1h / BREAKOUT_RETEST / SHORT / utc_hour / 06–11 | 7/7 | 4/3/0 | 0.357 | 1.098 | 0.595 | 0.238 |
| 1h / TREND_PULLBACK / LONG / reversal_POSTHOC / ADVERSE_CLOSE_AFTER_SIGNAL | 9/9 | 9/0/0 | -1.354 | 0.000 | -1.118 | 0.236 |
| 1h / TREND_PULLBACK / LONG / atr_percent / >=0.8% | 1/1 | 1/0/0 | -1.185 | 0.000 | -1.062 | 0.123 |
| 1h / TREND_PULLBACK / LONG / cost_burden / <0.25 | 5/5 | 5/0/0 | -1.195 | 0.000 | -1.065 | 0.130 |
| 1h / BREAKOUT_RETEST / SHORT / flat / FLAT_CAUSAL | 8/8 | 6/2/0 | -0.361 | 0.544 | -0.120 | 0.241 |
| 1h / TREND_PULLBACK / LONG / flat / FLAT_CAUSAL | 6/5 | 4/1/1 | -0.566 | 0.467 | -0.322 | 0.244 |
| 1h / TREND_PULLBACK / LONG / ema_separation / <0.5 | 9/8 | 7/1/1 | -0.834 | 0.244 | -0.611 | 0.223 |
| 1h / BREAKOUT_RETEST / SHORT / trend / NEUTRAL | 4/4 | 3/0/1 | -0.885 | 0.196 | -0.656 | 0.229 |
| 1h / BREAKOUT_RETEST / SHORT / utc_hour / 00–05 | 6/6 | 5/0/1 | -1.214 | 0.000 | -0.981 | 0.233 |
| 1h / TREND_PULLBACK / SHORT / reversal_POSTHOC / ADVERSE_CLOSE_AFTER_SIGNAL | 6/6 | 6/0/0 | -1.379 | 0.000 | -1.126 | 0.252 |
| 1h / BREAKOUT_RETEST / LONG / flat / OTHER | 13/12 | 9/3/0 | -0.322 | 0.428 | -0.107 | 0.214 |
| 1h / BREAKOUT_RETEST / LONG / structure / RANGE | 12/9 | 6/3/2 | 0.030 | 0.571 | 0.232 | 0.202 |
| 1h / BREAKOUT_RETEST / LONG / trend / SHORT | 10/7 | 6/1/1 | -0.705 | 0.284 | -0.521 | 0.184 |
| 1h / BREAKOUT_RETEST / LONG / ema_separation / <0.5 | 12/8 | 5/3/2 | 0.169 | 0.652 | 0.390 | 0.221 |
| 1h / BREAKOUT_RETEST / LONG / rsi / 50–60 | 9/6 | 4/2/2 | 0.038 | 0.894 | 0.235 | 0.197 |
| 1h / BREAKOUT_RETEST / LONG / atr_percent / 0.3–0.8% | 17/13 | 9/4/2 | -0.107 | 0.630 | 0.118 | 0.225 |
| 1h / BREAKOUT_RETEST / LONG / risk_atr / <2 | 18/14 | 10/4/2 | -0.195 | 0.617 | 0.030 | 0.225 |
| 1h / BREAKOUT_RETEST / LONG / cost_burden / 0.25–0.5 | 17/13 | 10/3/2 | -0.404 | 0.505 | -0.186 | 0.218 |
| 1h / BREAKOUT_RETEST / LONG / utc_hour / 00–05 | 3/3 | 2/1/0 | -0.058 | 0.612 | 0.203 | 0.261 |
| 1h / BREAKOUT_RETEST / LONG / reversal_POSTHOC / OTHER | 16/12 | 8/4/2 | -0.005 | 0.759 | 0.220 | 0.226 |
| 1h / BREAKOUT_RETEST / LONG / structure / HH_HL | 5/5 | 4/1/0 | -0.524 | 0.440 | -0.308 | 0.216 |
| 1h / BREAKOUT_RETEST / LONG / trend / LONG | 8/8 | 6/2/0 | -0.330 | 0.483 | -0.110 | 0.220 |
| 1h / BREAKOUT_RETEST / LONG / ema_separation / >=1 | 3/3 | 3/0/0 | -1.250 | 0.000 | -1.083 | 0.166 |
| 1h / BREAKOUT_RETEST / LONG / rsi / >=70 | 5/5 | 5/0/0 | -1.246 | 0.000 | -1.082 | 0.164 |
| 1h / BREAKOUT_RETEST / LONG / utc_hour / 18–23 | 4/3 | 1/2/1 | 1.361 | 3.554 | 1.565 | 0.204 |
| 1h / BREAKOUT_RETEST / LONG / reversal_POSTHOC / ADVERSE_CLOSE_AFTER_SIGNAL | 4/4 | 4/0/0 | -1.252 | 0.000 | -1.084 | 0.168 |
| 1h / BREAKOUT_RETEST / LONG / flat / FLAT_CAUSAL | 7/4 | 3/1/2 | -0.304 | 0.549 | -0.101 | 0.202 |
| 1h / BREAKOUT_RETEST / LONG / utc_hour / 06–11 | 2/1 | 0/1/1 | 2.539 | — | 2.846 | 0.307 |
| 1h / TREND_PULLBACK / SHORT / flat / FLAT_CAUSAL | 4/4 | 2/2/0 | 0.659 | 2.014 | 0.886 | 0.227 |
| 1h / TREND_PULLBACK / SHORT / ema_separation / <0.5 | 7/7 | 5/2/0 | -0.203 | 0.793 | 0.028 | 0.231 |
| 1h / BREAKOUT_RETEST / LONG / risk_atr / >=3 | 1/1 | 1/0/0 | -1.109 | 0.000 | -1.036 | 0.073 |
| 1h / BREAKOUT_RETEST / LONG / cost_burden / <0.25 | 2/2 | 2/0/0 | -1.162 | 0.000 | -1.054 | 0.108 |
| 1h / BREAKOUT_RETEST / LONG / utc_hour / 12–17 | 11/9 | 9/0/0 | -1.280 | 0.000 | -1.093 | 0.187 |
| 1h / BREAKOUT_RETEST / LONG / atr_percent / >=0.8% | 3/3 | 3/0/0 | -1.230 | 0.000 | -1.077 | 0.153 |
| 1h / BREAKOUT_RETEST / SHORT / atr_percent / <0.3% | 1/1 | 1/0/0 | -1.542 | 0.000 | -1.181 | 0.362 |
| 1h / BREAKOUT_RETEST / LONG / trend / NEUTRAL | 2/1 | 0/1/1 | 2.500 | — | 2.833 | 0.334 |
| 1h / BREAKOUT_RETEST / LONG / rsi / 60–70 | 5/4 | 2/2/0 | 0.584 | 1.327 | 0.861 | 0.277 |
| 1h / BREAKOUT_RETEST / LONG / cost_burden / >=0.5 | 1/1 | 0/1/0 | 2.500 | — | 2.833 | 0.334 |
| 1h / BREAKOUT_RETEST / LONG / ema_separation / 0.5–1 | 5/5 | 4/1/0 | -0.536 | 0.568 | -0.312 | 0.224 |
| 1h / TREND_PULLBACK / SHORT / atr_percent / >=0.8% | 1/1 | 1/0/0 | -1.151 | 0.000 | -1.050 | 0.101 |
| 1h / TREND_PULLBACK / SHORT / cost_burden / <0.25 | 1/1 | 1/0/0 | -1.151 | 0.000 | -1.050 | 0.101 |
| 1h / TREND_PULLBACK / LONG / rsi / 40–50 | 2/2 | 2/0/0 | -1.369 | 0.000 | -1.123 | 0.246 |
| 1h / BREAKOUT_RETEST / LONG / structure / LH_LL | 3/2 | 2/0/0 | -1.363 | 0.000 | -1.121 | 0.242 |
| 1h / BREAKOUT_RETEST / LONG / rsi / 40–50 | 1/1 | 1/0/0 | -1.413 | 0.000 | -1.138 | 0.275 |
| 1h / BREAKOUT_RETEST / LONG / risk_atr / 2–3 | 1/1 | 1/0/0 | -1.236 | 0.000 | -1.079 | 0.157 |
| 1h / TREND_PULLBACK / SHORT / utc_hour / 00–05 | 1/1 | 1/0/0 | -1.368 | 0.000 | -1.123 | 0.245 |
| 4h / TREND_PULLBACK / LONG / flat / OTHER | 9/8 | 8/0/0 | -1.180 | 0.000 | -1.060 | 0.120 |
| 4h / TREND_PULLBACK / LONG / structure / HH_HL | 12/9 | 9/0/0 | -1.181 | 0.000 | -1.060 | 0.120 |
| 4h / TREND_PULLBACK / LONG / trend / LONG | 12/9 | 9/0/0 | -1.181 | 0.000 | -1.060 | 0.120 |
| 4h / TREND_PULLBACK / LONG / ema_separation / <0.5 | 4/2 | 2/0/0 | -1.191 | 0.000 | -1.064 | 0.128 |
| 4h / TREND_PULLBACK / LONG / rsi / 60–70 | 2/2 | 2/0/0 | -1.159 | 0.000 | -1.053 | 0.106 |
| 4h / TREND_PULLBACK / LONG / atr_percent / >=0.8% | 12/9 | 9/0/0 | -1.181 | 0.000 | -1.060 | 0.120 |
| 4h / TREND_PULLBACK / LONG / risk_atr / <2 | 12/9 | 9/0/0 | -1.181 | 0.000 | -1.060 | 0.120 |
| 4h / TREND_PULLBACK / LONG / cost_burden / <0.25 | 12/9 | 9/0/0 | -1.181 | 0.000 | -1.060 | 0.120 |
| 4h / TREND_PULLBACK / LONG / utc_hour / 12–17 | 7/5 | 5/0/0 | -1.195 | 0.000 | -1.065 | 0.130 |
| 4h / TREND_PULLBACK / LONG / reversal_POSTHOC / OTHER | 10/9 | 9/0/0 | -1.181 | 0.000 | -1.060 | 0.120 |
| 4h / TREND_PULLBACK / SHORT / flat / OTHER | 3/3 | 3/0/0 | -1.201 | 0.000 | -1.067 | 0.134 |
| 4h / TREND_PULLBACK / SHORT / structure / LH_LL | 7/7 | 7/0/0 | -1.179 | 0.000 | -1.060 | 0.119 |
| 4h / TREND_PULLBACK / SHORT / trend / SHORT | 7/7 | 7/0/0 | -1.179 | 0.000 | -1.060 | 0.119 |
| 4h / TREND_PULLBACK / SHORT / ema_separation / <0.5 | 5/5 | 5/0/0 | -1.164 | 0.000 | -1.055 | 0.109 |
| 4h / TREND_PULLBACK / SHORT / rsi / <40 | 3/3 | 3/0/0 | -1.201 | 0.000 | -1.067 | 0.134 |
| 4h / TREND_PULLBACK / SHORT / atr_percent / 0.3–0.8% | 1/1 | 1/0/0 | -1.169 | 0.000 | -1.056 | 0.113 |
| 4h / TREND_PULLBACK / SHORT / risk_atr / 2–3 | 2/2 | 2/0/0 | -1.140 | 0.000 | -1.047 | 0.093 |
| 4h / TREND_PULLBACK / SHORT / cost_burden / <0.25 | 6/6 | 6/0/0 | -1.168 | 0.000 | -1.056 | 0.112 |
| 4h / TREND_PULLBACK / SHORT / utc_hour / 12–17 | 3/3 | 3/0/0 | -1.186 | 0.000 | -1.062 | 0.124 |
| 4h / TREND_PULLBACK / SHORT / reversal_POSTHOC / OTHER | 6/6 | 6/0/0 | -1.168 | 0.000 | -1.056 | 0.112 |
| 4h / BREAKOUT_RETEST / LONG / flat / OTHER | 6/6 | 5/1/0 | -0.543 | 0.205 | -0.403 | 0.139 |
| 4h / BREAKOUT_RETEST / LONG / structure / RANGE | 3/3 | 2/1/0 | 0.097 | 0.514 | 0.255 | 0.157 |
| 4h / BREAKOUT_RETEST / LONG / trend / LONG | 4/4 | 3/1/0 | -0.212 | 0.317 | -0.071 | 0.141 |
| 4h / BREAKOUT_RETEST / LONG / ema_separation / <0.5 | 5/5 | 4/1/0 | -0.420 | 0.266 | -0.273 | 0.147 |
| 4h / BREAKOUT_RETEST / LONG / rsi / 60–70 | 5/5 | 4/1/0 | -0.406 | 0.244 | -0.269 | 0.137 |
| 4h / BREAKOUT_RETEST / LONG / atr_percent / 0.3–0.8% | 1/1 | 0/1/0 | 2.675 | — | 2.892 | 0.217 |
| 4h / BREAKOUT_RETEST / LONG / risk_atr / <2 | 7/7 | 6/1/0 | -0.638 | 0.174 | -0.498 | 0.139 |
| 4h / BREAKOUT_RETEST / LONG / cost_burden / 0.25–0.5 | 1/1 | 0/1/0 | 2.675 | — | 2.892 | 0.217 |
| 4h / BREAKOUT_RETEST / LONG / utc_hour / 00–05 | 3/3 | 2/1/0 | 0.097 | 0.514 | 0.255 | 0.157 |
| 4h / BREAKOUT_RETEST / LONG / reversal_POSTHOC / ADVERSE_CLOSE_AFTER_SIGNAL | 4/4 | 3/1/0 | -0.227 | 0.357 | -0.076 | 0.151 |
| 4h / TREND_PULLBACK / LONG / ema_separation / >=1 | 5/4 | 4/0/0 | -1.166 | 0.000 | -1.055 | 0.111 |
| 4h / TREND_PULLBACK / LONG / utc_hour / 00–05 | 4/4 | 4/0/0 | -1.163 | 0.000 | -1.054 | 0.109 |
| 4h / TREND_PULLBACK / LONG / rsi / 50–60 | 9/7 | 7/0/0 | -1.187 | 0.000 | -1.062 | 0.125 |
| 4h / BREAKOUT_RETEST / LONG / structure / LH_LL | 4/4 | 4/0/0 | -1.189 | 0.000 | -1.063 | 0.126 |
| 4h / BREAKOUT_RETEST / LONG / ema_separation / >=1 | 1/1 | 1/0/0 | -1.138 | 0.000 | -1.046 | 0.092 |
| 4h / BREAKOUT_RETEST / LONG / atr_percent / >=0.8% | 6/6 | 6/0/0 | -1.190 | 0.000 | -1.063 | 0.126 |
| 4h / BREAKOUT_RETEST / LONG / cost_burden / <0.25 | 6/6 | 6/0/0 | -1.190 | 0.000 | -1.063 | 0.126 |
| 4h / BREAKOUT_RETEST / LONG / utc_hour / 12–17 | 2/2 | 2/0/0 | -1.160 | 0.000 | -1.053 | 0.107 |
| 4h / BREAKOUT_RETEST / LONG / reversal_POSTHOC / OTHER | 3/3 | 3/0/0 | -1.186 | 0.000 | -1.062 | 0.124 |
| 4h / TREND_PULLBACK / LONG / rsi / 40–50 | 1/0 | 0/0/0 | — | — | — | — |
| 4h / TREND_PULLBACK / LONG / utc_hour / 06–11 | 1/0 | 0/0/0 | — | — | — | — |
| 4h / TREND_PULLBACK / LONG / ema_separation / 0.5–1 | 3/3 | 3/0/0 | -1.193 | 0.000 | -1.064 | 0.129 |
| 4h / BREAKOUT_RETEST / SHORT / flat / OTHER | 7/7 | 5/2/0 | -0.052 | 0.778 | 0.078 | 0.130 |
| 4h / BREAKOUT_RETEST / SHORT / structure / RANGE | 5/5 | 3/2/0 | 0.397 | 1.336 | 0.532 | 0.135 |
| 4h / BREAKOUT_RETEST / SHORT / trend / LONG | 3/3 | 1/2/0 | 1.448 | 4.523 | 1.594 | 0.145 |
| 4h / BREAKOUT_RETEST / SHORT / ema_separation / 0.5–1 | 5/5 | 3/2/0 | 0.403 | 1.273 | 0.534 | 0.131 |
| 4h / BREAKOUT_RETEST / SHORT / rsi / 40–50 | 4/4 | 2/2/0 | 0.796 | 1.924 | 0.932 | 0.136 |
| 4h / BREAKOUT_RETEST / SHORT / atr_percent / >=0.8% | 7/7 | 5/2/0 | -0.052 | 0.778 | 0.078 | 0.130 |
| 4h / BREAKOUT_RETEST / SHORT / risk_atr / <2 | 7/7 | 5/2/0 | -0.052 | 0.778 | 0.078 | 0.130 |
| 4h / BREAKOUT_RETEST / SHORT / cost_burden / <0.25 | 7/7 | 5/2/0 | -0.052 | 0.778 | 0.078 | 0.130 |
| 4h / BREAKOUT_RETEST / SHORT / utc_hour / 00–05 | 4/4 | 2/2/0 | 0.806 | 1.815 | 0.935 | 0.129 |
| 4h / BREAKOUT_RETEST / SHORT / reversal_POSTHOC / OTHER | 7/7 | 5/2/0 | -0.052 | 0.778 | 0.078 | 0.130 |
| 4h / BREAKOUT_RETEST / SHORT / ema_separation / <0.5 | 2/2 | 2/0/0 | -1.190 | 0.000 | -1.063 | 0.127 |
| 4h / BREAKOUT_RETEST / SHORT / rsi / <40 | 3/3 | 3/0/0 | -1.183 | 0.000 | -1.061 | 0.122 |
| 4h / BREAKOUT_RETEST / SHORT / utc_hour / 12–17 | 3/3 | 3/0/0 | -1.197 | 0.000 | -1.066 | 0.131 |
| 4h / TREND_PULLBACK / SHORT / ema_separation / 0.5–1 | 2/2 | 2/0/0 | -1.216 | 0.000 | -1.072 | 0.144 |
| 4h / TREND_PULLBACK / SHORT / atr_percent / >=0.8% | 6/6 | 6/0/0 | -1.181 | 0.000 | -1.060 | 0.120 |
| 4h / TREND_PULLBACK / SHORT / risk_atr / <2 | 5/5 | 5/0/0 | -1.194 | 0.000 | -1.065 | 0.130 |
| 4h / TREND_PULLBACK / SHORT / cost_burden / 0.25–0.5 | 1/1 | 1/0/0 | -1.244 | 0.000 | -1.081 | 0.163 |
| 4h / TREND_PULLBACK / SHORT / utc_hour / 00–05 | 2/2 | 2/0/0 | -1.178 | 0.000 | -1.059 | 0.118 |
| 4h / TREND_PULLBACK / SHORT / reversal_POSTHOC / ADVERSE_CLOSE_AFTER_SIGNAL | 1/1 | 1/0/0 | -1.244 | 0.000 | -1.081 | 0.163 |
| 4h / BREAKOUT_RETEST / LONG / trend / SHORT | 3/3 | 3/0/0 | -1.205 | 0.000 | -1.068 | 0.137 |
| 4h / BREAKOUT_RETEST / LONG / ema_separation / 0.5–1 | 1/1 | 1/0/0 | -1.226 | 0.000 | -1.075 | 0.151 |
| 4h / BREAKOUT_RETEST / LONG / rsi / 50–60 | 2/2 | 2/0/0 | -1.217 | 0.000 | -1.072 | 0.145 |
| 4h / BREAKOUT_RETEST / LONG / utc_hour / 06–11 | 2/2 | 2/0/0 | -1.217 | 0.000 | -1.072 | 0.145 |
| 4h / TREND_PULLBACK / SHORT / flat / FLAT_CAUSAL | 4/4 | 4/0/0 | -1.163 | 0.000 | -1.054 | 0.109 |
| 4h / TREND_PULLBACK / SHORT / rsi / 40–50 | 3/3 | 3/0/0 | -1.148 | 0.000 | -1.049 | 0.099 |
| 4h / TREND_PULLBACK / SHORT / utc_hour / 06–11 | 1/1 | 1/0/0 | -1.152 | 0.000 | -1.051 | 0.101 |
| 4h / BREAKOUT_RETEST / SHORT / trend / SHORT | 4/4 | 4/0/0 | -1.178 | 0.000 | -1.059 | 0.118 |
| 4h / BREAKOUT_RETEST / SHORT / structure / LH_LL | 1/1 | 1/0/0 | -1.170 | 0.000 | -1.057 | 0.113 |
| 4h / TREND_PULLBACK / LONG / flat / FLAT_CAUSAL | 3/1 | 1/0/0 | -1.188 | 0.000 | -1.063 | 0.126 |
| 4h / TREND_PULLBACK / LONG / reversal_POSTHOC / CENSORED_<4_BARS | 2/0 | 0/0/0 | — | — | — | — |
| 4h / TREND_PULLBACK / SHORT / utc_hour / 18–23 | 1/1 | 1/0/0 | -1.188 | 0.000 | -1.063 | 0.126 |
| 4h / BREAKOUT_RETEST / SHORT / structure / HH_HL | 1/1 | 1/0/0 | -1.180 | 0.000 | -1.060 | 0.120 |
| 4h / BREAKOUT_RETEST / LONG / flat / FLAT_CAUSAL | 1/1 | 1/0/0 | -1.208 | 0.000 | -1.069 | 0.138 |
| 4h / TREND_PULLBACK / SHORT / rsi / 50–60 | 1/1 | 1/0/0 | -1.206 | 0.000 | -1.069 | 0.137 |

## Причины исходов, включая TIMEOUT без входа

| TF / стратегия / сторона | Сигналы | TP | SL | TIMEOUT с входом | TIMEOUT без входа | UNKNOWN | Неоднозначные | До комиссии, fill R | Комиссия R | Net E[R] |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 15m / TREND_PULLBACK / LONG | 30 | 5 | 20 | 4 | 1 | 0 | 0 | -0.275 | 0.275 | -0.550 |
| 15m / TREND_PULLBACK / SHORT | 25 | 2 | 21 | 1 | 1 | 0 | 1 | -0.753 | 0.302 | -1.055 |
| 15m / BREAKOUT_RETEST / LONG | 14 | 2 | 10 | 0 | 0 | 2 | 2 | -0.469 | 0.272 | -0.741 |
| 15m / BREAKOUT_RETEST / SHORT | 13 | 0 | 7 | 5 | 0 | 1 | 1 | -0.718 | 0.257 | -0.975 |
| 15m / SR_REVERSAL / LONG | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | — |
| 15m / SR_REVERSAL / SHORT | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | — |
| 1h / TREND_PULLBACK / LONG | 31 | 4 | 23 | 2 | 2 | 0 | 2 | -0.412 | 0.223 | -0.635 |
| 1h / TREND_PULLBACK / SHORT | 24 | 3 | 20 | 0 | 1 | 0 | 0 | -0.595 | 0.234 | -0.829 |
| 1h / BREAKOUT_RETEST / LONG | 20 | 4 | 12 | 0 | 2 | 2 | 2 | -0.106 | 0.211 | -0.317 |
| 1h / BREAKOUT_RETEST / SHORT | 37 | 9 | 26 | 2 | 0 | 0 | 1 | -0.079 | 0.247 | -0.325 |
| 1h / SR_REVERSAL / LONG | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | — |
| 1h / SR_REVERSAL / SHORT | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | — |
| 4h / TREND_PULLBACK / LONG | 12 | 0 | 9 | 0 | 0 | 3 | 0 | -1.060 | 0.120 | -1.181 |
| 4h / TREND_PULLBACK / SHORT | 7 | 0 | 7 | 0 | 0 | 0 | 1 | -1.060 | 0.119 | -1.179 |
| 4h / BREAKOUT_RETEST / LONG | 7 | 1 | 6 | 0 | 0 | 0 | 0 | -0.498 | 0.139 | -0.638 |
| 4h / BREAKOUT_RETEST / SHORT | 7 | 2 | 5 | 0 | 0 | 0 | 0 | 0.078 | 0.130 | -0.052 |
| 4h / SR_REVERSAL / LONG | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | — |
| 4h / SR_REVERSAL / SHORT | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | — |

## Конкретные примеры

Для каждой группы взят первый хронологический положительный и отрицательный net исход, а не лучший/худший PnL. Прочерк означает отсутствие подходящей реальной сделки.

| TF / стратегия / сторона | Категория | Сигнал UTC | Entry / SL / TP | Исход / причина | Net R | Признаки на входе | Диагностика после сигнала |
|---|---|---|---|---|---:|---|---|
| 15m / TREND_PULLBACK / LONG | POSITIVE_NET | 2026-08-20T19:30:00.000Z | 72563.20 / 72068.98 / 74045.87 | TP / TARGET_TOUCHED | 2.555 | EMA sep 2.003 ATR; slope 0.521 ATR; RSI 58.4; ATR 0.454%; ER 0.380; HH_HL; риск 1.500 ATR; RR 1.693; cost/risk 0.470 | adverse 4 bars: false; MAE/MFE envelope 0.232 / 4.627 R; fees 0.297 R |
| 15m / TREND_PULLBACK / LONG | NEGATIVE_NET | 2026-08-05T14:00:00.000Z | 64378.60 / 63799.21 / 66116.78 | TIMEOUT / HOLD_LIMIT_CLOSE | -0.297 | EMA sep 0.142 ATR; slope 0.051 ATR; RSI 58.5; ATR 0.268%; ER 0.192; HH_HL; риск 3.361 ATR; RR 1.926; cost/risk 0.356 | adverse 4 bars: false; MAE/MFE envelope 0.399 / 1.053 R; fees 0.222 R |
| 15m / TREND_PULLBACK / SHORT | POSITIVE_NET | 2026-08-25T19:45:00.000Z | 78703.20 / 79256.35 / 77043.74 | TIMEOUT / HOLD_LIMIT_CLOSE | 0.126 | EMA sep 0.604 ATR; slope -0.213 ATR; RSI 38.1; ATR 0.337%; ER 0.162; LH_LL; риск 2.084 ATR; RR 1.723; cost/risk 0.455 | adverse 4 bars: false; MAE/MFE envelope 0.916 / 2.032 R; fees 0.284 R |
| 15m / TREND_PULLBACK / SHORT | NEGATIVE_NET | 2026-08-22T11:15:00.000Z | 76852.80 / 77364.18 / 75318.65 | SL / STOP_TOUCHED | -1.452 | EMA sep 0.702 ATR; slope -0.344 ATR; RSI 39.3; ATR 0.444%; ER 0.108; LH_LL; риск 1.500 ATR; RR 1.675; cost/risk 0.481 | adverse 4 bars: true; MAE/MFE envelope 1.049 / 0.000 R; fees 0.302 R |
| 15m / BREAKOUT_RETEST / LONG | POSITIVE_NET | 2026-08-20T15:30:00.000Z | 72382.00 / 71749.28 / 74280.15 | TP / TARGET_TOUCHED | 2.652 | EMA sep 1.781 ATR; slope 0.467 ATR; RSI 65.7; ATR 0.583%; ER 0.104; RANGE; риск 1.500 ATR; RR 1.903; cost/risk 0.366 | adverse 4 bars: false; MAE/MFE envelope 0.419 / 3.901 R; fees 0.232 R |
| 15m / BREAKOUT_RETEST / LONG | NEGATIVE_NET | 2026-08-24T12:30:00.000Z | 78404.90 / 77842.92 / 80090.83 | SL / STOP_TOUCHED | -1.417 | EMA sep 0.778 ATR; slope 0.491 ATR; RSI 64.4; ATR 0.419%; ER 0.228; HH_HL; риск 1.712 ATR; RR 1.738; cost/risk 0.446 | adverse 4 bars: false; MAE/MFE envelope 1.116 / 1.753 R; fees 0.278 R |
| 15m / BREAKOUT_RETEST / SHORT | POSITIVE_NET | 2026-09-15T19:30:00.000Z | 75877.60 / 76566.81 / 73809.97 | TIMEOUT / HOLD_LIMIT_CLOSE | 0.186 | EMA sep 0.730 ATR; slope -0.299 ATR; RSI 38.6; ATR 0.606%; ER 0.110; LH_LL; риск 1.500 ATR; RR 1.935; cost/risk 0.352 | adverse 4 bars: false; MAE/MFE envelope 0.947 / 1.263 R; fees 0.220 R |
| 15m / BREAKOUT_RETEST / SHORT | NEGATIVE_NET | 2026-08-20T03:30:00.000Z | 68955.30 / 69399.04 / 67624.07 | SL / STOP_TOUCHED | -1.468 | EMA sep 2.477 ATR; slope 0.498 ATR; RSI 44.9; ATR 0.429%; ER 0.071; HH_HL; риск 1.500 ATR; RR 1.645; cost/risk 0.497 | adverse 4 bars: true; MAE/MFE envelope 1.014 / 0.000 R; fees 0.312 R |
| 15m / SR_REVERSAL / LONG | POSITIVE_NET | — | — | NO_MATCHING_REAL_TRADE | — | — | — |
| 15m / SR_REVERSAL / LONG | NEGATIVE_NET | — | — | NO_MATCHING_REAL_TRADE | — | — | — |
| 15m / SR_REVERSAL / SHORT | POSITIVE_NET | — | — | NO_MATCHING_REAL_TRADE | — | — | — |
| 15m / SR_REVERSAL / SHORT | NEGATIVE_NET | — | — | NO_MATCHING_REAL_TRADE | — | — | — |
| 1h / TREND_PULLBACK / LONG | POSITIVE_NET | 2026-08-05T02:00:00.000Z | 64305.70 / 63826.64 / 65742.88 | TIMEOUT / HOLD_LIMIT_CLOSE | 0.697 | EMA sep 0.841 ATR; slope 0.293 ATR; RSI 59.8; ATR 0.497%; ER 0.190; HH_HL; риск 1.500 ATR; RR 1.771; cost/risk 0.430 | adverse 4 bars: false; MAE/MFE envelope 0.967 / 2.159 R; fees 0.270 R |
| 1h / TREND_PULLBACK / LONG | NEGATIVE_NET | 2026-08-05T03:00:00.000Z | 64335.50 / 63837.61 / 65829.17 | SL / STOP_TOUCHED | -1.386 | EMA sep 0.895 ATR; slope 0.312 ATR; RSI 60.3; ATR 0.481%; ER 0.258; HH_HL; риск 1.608 ATR; RR 1.803; cost/risk 0.413 | adverse 4 bars: false; MAE/MFE envelope 0.991 / 0.443 R; fees 0.257 R |
| 1h / TREND_PULLBACK / SHORT | POSITIVE_NET | 2026-09-09T19:00:00.000Z | 78381.50 / 79093.04 / 76246.88 | TP / TARGET_TOUCHED | 2.674 | EMA sep 0.140 ATR; slope -0.118 ATR; RSI 42.6; ATR 0.605%; ER 0.028; LH_LL; риск 1.500 ATR; RR 1.935; cost/risk 0.353 | adverse 4 bars: false; MAE/MFE envelope 0.210 / 3.421 R; fees 0.217 R |
| 1h / TREND_PULLBACK / SHORT | NEGATIVE_NET | 2026-08-11T15:00:00.000Z | 63744.90 / 64393.63 / 61798.71 | SL / STOP_TOUCHED | -1.296 | EMA sep 1.106 ATR; slope -0.268 ATR; RSI 34.8; ATR 0.345%; ER 0.063; LH_LL; риск 2.947 ATR; RR 2.022; cost/risk 0.314 | adverse 4 bars: false; MAE/MFE envelope 1.078 / 0.812 R; fees 0.198 R |
| 1h / BREAKOUT_RETEST / LONG | POSITIVE_NET | 2026-09-14T05:00:00.000Z | 77645.10 / 77175.27 / 79054.58 | TP / TARGET_TOUCHED | 2.500 | EMA sep 0.079 ATR; slope 0.093 ATR; RSI 62.8; ATR 0.403%; ER 0.307; RANGE; риск 1.500 ATR; RR 1.587; cost/risk 0.529 | adverse 4 bars: false; MAE/MFE envelope 0.664 / 3.497 R; fees 0.334 R |
| 1h / BREAKOUT_RETEST / LONG | NEGATIVE_NET | 2026-09-03T05:00:00.000Z | 77751.60 / 77109.70 / 79677.30 | SL / ENTRY_STOP_ORDER_CONSERVATIVE | -1.362 | EMA sep 0.367 ATR; slope 0.008 ATR; RSI 57.5; ATR 0.550%; ER 0.246; RANGE; риск 1.500 ATR; RR 1.856; cost/risk 0.388 | adverse 4 bars: false; MAE/MFE envelope — / — R; fees 0.241 R |
| 1h / BREAKOUT_RETEST / SHORT | POSITIVE_NET | 2026-08-10T14:00:00.000Z | 64541.00 / 65003.97 / 63152.08 | TP / TARGET_TOUCHED | 2.586 | EMA sep 0.115 ATR; slope -0.094 ATR; RSI 35.0; ATR 0.351%; ER 0.263; RANGE; риск 2.046 ATR; RR 1.741; cost/risk 0.446 | adverse 4 bars: false; MAE/MFE envelope 0.307 / 3.717 R; fees 0.276 R |
| 1h / BREAKOUT_RETEST / SHORT | NEGATIVE_NET | 2026-08-11T16:00:00.000Z | 63592.30 / 63944.63 / 62535.32 | SL / STOP_TOUCHED | -1.543 | EMA sep 1.133 ATR; slope -0.343 ATR; RSI 31.7; ATR 0.369%; ER 0.209; RANGE; риск 1.500 ATR; RR 1.508; cost/risk 0.578 | adverse 4 bars: false; MAE/MFE envelope 1.384 / 1.061 R; fees 0.362 R |
| 1h / SR_REVERSAL / LONG | POSITIVE_NET | — | — | NO_MATCHING_REAL_TRADE | — | — | — |
| 1h / SR_REVERSAL / LONG | NEGATIVE_NET | — | — | NO_MATCHING_REAL_TRADE | — | — | — |
| 1h / SR_REVERSAL / SHORT | POSITIVE_NET | — | — | NO_MATCHING_REAL_TRADE | — | — | — |
| 1h / SR_REVERSAL / SHORT | NEGATIVE_NET | — | — | NO_MATCHING_REAL_TRADE | — | — | — |
| 4h / TREND_PULLBACK / LONG | POSITIVE_NET | — | — | NO_MATCHING_REAL_TRADE | — | — | — |
| 4h / TREND_PULLBACK / LONG | NEGATIVE_NET | 2026-08-07T12:00:00.000Z | 64978.70 / 63984.21 / 67962.16 | SL / STOP_TOUCHED | -1.195 | EMA sep 0.423 ATR; slope 0.161 ATR; RSI 63.7; ATR 0.832%; ER 0.343; HH_HL; риск 1.840 ATR; RR 2.290; cost/risk 0.209 | adverse 4 bars: false; MAE/MFE envelope 1.194 / 0.507 R; fees 0.130 R |
| 4h / TREND_PULLBACK / SHORT | POSITIVE_NET | — | — | NO_MATCHING_REAL_TRADE | — | — | — |
| 4h / TREND_PULLBACK / SHORT | NEGATIVE_NET | 2026-08-12T16:00:00.000Z | 63428.40 / 64563.50 / 60023.09 | SL / STOP_TOUCHED | -1.169 | EMA sep 0.293 ATR; slope -0.234 ATR; RSI 37.9; ATR 0.754%; ER 0.267; LH_LL; риск 2.375 ATR; RR 2.378; cost/risk 0.179 | adverse 4 bars: false; MAE/MFE envelope 1.012 / 0.800 R; fees 0.113 R |
| 4h / BREAKOUT_RETEST / LONG | POSITIVE_NET | 2026-08-19T00:00:00.000Z | 64696.40 / 64090.93 / 66512.82 | TP / TARGET_TOUCHED | 2.675 | EMA sep 0.408 ATR; slope 0.404 ATR; RSI 67.6; ATR 0.624%; ER 0.464; RANGE; риск 1.500 ATR; RR 1.956; cost/risk 0.342 | adverse 4 bars: true; MAE/MFE envelope 0.909 / 8.391 R; fees 0.217 R |
| 4h / BREAKOUT_RETEST / LONG | NEGATIVE_NET | 2026-08-27T16:00:00.000Z | 80262.20 / 78539.44 / 85430.47 | SL / STOP_TOUCHED | -1.138 | EMA sep 2.379 ATR; slope 0.659 ATR; RSI 66.2; ATR 1.431%; ER 0.274; LH_LL; риск 1.500 ATR; RR 2.466; cost/risk 0.149 | adverse 4 bars: false; MAE/MFE envelope 1.156 / 0.698 R; fees 0.092 R |
| 4h / BREAKOUT_RETEST / SHORT | POSITIVE_NET | 2026-09-08T00:00:00.000Z | 79076.50 / 80140.21 / 75885.37 | TP / TARGET_TOUCHED | 2.781 | EMA sep 0.635 ATR; slope 0.048 ATR; RSI 46.1; ATR 0.897%; ER 0.064; RANGE; риск 1.500 ATR; RR 2.213; cost/risk 0.238 | adverse 4 bars: false; MAE/MFE envelope 0.763 / 3.306 R; fees 0.146 R |
| 4h / BREAKOUT_RETEST / SHORT | NEGATIVE_NET | 2026-09-08T12:00:00.000Z | 78398.70 / 79475.92 / 75167.05 | SL / STOP_TOUCHED | -1.220 | EMA sep 0.367 ATR; slope -0.053 ATR; RSI 39.6; ATR 0.916%; ER 0.236; RANGE; риск 1.500 ATR; RR 2.226; cost/risk 0.233 | adverse 4 bars: false; MAE/MFE envelope 1.241 / 0.162 R; fees 0.147 R |
| 4h / SR_REVERSAL / LONG | POSITIVE_NET | — | — | NO_MATCHING_REAL_TRADE | — | — | — |
| 4h / SR_REVERSAL / LONG | NEGATIVE_NET | — | — | NO_MATCHING_REAL_TRADE | — | — | — |
| 4h / SR_REVERSAL / SHORT | POSITIVE_NET | — | — | NO_MATCHING_REAL_TRADE | — | — | — |
| 4h / SR_REVERSAL / SHORT | NEGATIVE_NET | — | — | NO_MATCHING_REAL_TRADE | — | — | — |
