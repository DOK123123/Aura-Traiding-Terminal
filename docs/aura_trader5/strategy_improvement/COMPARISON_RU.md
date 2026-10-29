# Сравнение baseline и зафиксированных кандидатов

Все данные уже известны, UNVALIDATED. Группы — стратегия × направление × таймфрейм, без объединения в портфель. Периоды 5 августа–29 октября с отдельной цензурой каждого месяца. PnL и DD — сумма независимых гипотез 1 BTC, не капитал. n = сигналы / входы / определённые закрытые; U = UNKNOWN. WR по положительному net PnL; TIMEOUT с входом включён. Неисполненные и UNKNOWN исключены из метрик. Каждый вариант показан, включая нулевые и ухудшившиеся результаты. Соседние COMBINED_LOOSE/STRICT не допускаются к выбору.

| TF | Вариант | Стратегия / сторона | n | U | WR % | PF | E[R], расходы ×1 | 95% CI E[R] | PnL USDT | DD USDT / R | ×1.5 входы/закрыто; E[R] / PF | ×2 входы/закрыто; E[R] / PF |
|---|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|
| 15m | BASELINE | TREND_PULLBACK / LONG | 30/29/29 | 0 | 20.7 | 0.373 | -0.550 | [-1.141; -0.086] | -11030.09 | 11186.55 / 16.056 | 29/29; -0.758 / 0.288 | 29/29; -0.965 / 0.223 |
| 15m | BASELINE | TREND_PULLBACK / SHORT | 25/24/24 | 0 | 12.5 | 0.143 | -1.055 | [-1.447; -0.554] | -14279.53 | 14760.96 / 26.298 | 24/24; -1.282 / 0.108 | 24/24; -1.508 / 0.084 |
| 15m | BASELINE | BREAKOUT_RETEST / LONG | 14/14/12 | 2 | 16.7 | 0.329 | -0.741 | [-1.442; 1.268] | -5787.20 | 8621.16 / 14.055 | 14/12; -0.944 / 0.266 | 13/11; -1.101 / 0.243 |
| 15m | BASELINE | BREAKOUT_RETEST / SHORT | 13/13/12 | 1 | 8.3 | 0.018 | -0.975 | [-1.413; -0.396] | -6963.47 | 6963.47 / 11.702 | 13/12; -1.170 / 0.001 | 13/12; -1.365 / 0.000 |
| 15m | BASELINE | SR_REVERSAL / LONG | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 15m | BASELINE | SR_REVERSAL / SHORT | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 15m | TREND_REGIME | TREND_PULLBACK / LONG | 6/5/5 | 0 | 40.0 | 1.200 | 0.382 | INSUFFICIENT_EVIDENCE | 416.43 | 2078.99 / 3.193 | 5/5; 0.185 / 0.926 | 5/5; -0.012 / 0.725 |
| 15m | TREND_REGIME | TREND_PULLBACK / SHORT | 7/7/7 | 0 | 0.0 | 0.000 | -1.449 | INSUFFICIENT_EVIDENCE | -5705.93 | 5705.93 / 10.142 | 7/7; -1.673 / 0.000 | 7/7; -1.898 / 0.000 |
| 15m | TREND_REGIME | BREAKOUT_RETEST / LONG | 14/14/12 | 2 | 16.7 | 0.329 | -0.741 | [-1.439; 1.283] | -5787.20 | 8621.16 / 14.055 | 14/12; -0.944 / 0.266 | 13/11; -1.101 / 0.243 |
| 15m | TREND_REGIME | BREAKOUT_RETEST / SHORT | 13/13/12 | 1 | 8.3 | 0.018 | -0.975 | [-1.414; -0.412] | -6963.47 | 6963.47 / 11.702 | 13/12; -1.170 / 0.001 | 13/12; -1.365 / 0.000 |
| 15m | TREND_REGIME | SR_REVERSAL / LONG | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 15m | TREND_REGIME | SR_REVERSAL / SHORT | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 15m | BREAKOUT_CONFIRM | TREND_PULLBACK / LONG | 30/29/29 | 0 | 20.7 | 0.373 | -0.550 | [-1.135; -0.057] | -11030.09 | 11186.55 / 16.056 | 29/29; -0.758 / 0.288 | 29/29; -0.965 / 0.223 |
| 15m | BREAKOUT_CONFIRM | TREND_PULLBACK / SHORT | 25/24/24 | 0 | 12.5 | 0.143 | -1.055 | [-1.464; -0.569] | -14279.53 | 14760.96 / 26.298 | 24/24; -1.282 / 0.108 | 24/24; -1.508 / 0.084 |
| 15m | BREAKOUT_CONFIRM | BREAKOUT_RETEST / LONG | 4/4/3 | 1 | 0.0 | 0.000 | -1.381 | INSUFFICIENT_EVIDENCE | -2661.48 | 2661.48 / 4.144 | 4/3; -1.572 / 0.000 | 4/3; -1.763 / 0.000 |
| 15m | BREAKOUT_CONFIRM | BREAKOUT_RETEST / SHORT | 1/1/1 | 0 | 0.0 | 0.000 | -1.501 | INSUFFICIENT_EVIDENCE | -719.77 | 719.77 / 1.501 | 1/1; -1.751 / 0.000 | 1/1; -2.002 / 0.000 |
| 15m | BREAKOUT_CONFIRM | SR_REVERSAL / LONG | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 15m | BREAKOUT_CONFIRM | SR_REVERSAL / SHORT | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 15m | QUALITY | TREND_PULLBACK / LONG | 4/4/4 | 0 | 0.0 | 0.000 | -1.046 | INSUFFICIENT_EVIDENCE | -3668.18 | 3668.18 / 4.185 | 4/4; -1.179 / 0.000 | 4/4; -1.311 / 0.000 |
| 15m | QUALITY | TREND_PULLBACK / SHORT | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 15m | QUALITY | BREAKOUT_RETEST / LONG | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 15m | QUALITY | BREAKOUT_RETEST / SHORT | 1/1/1 | 0 | 0.0 | 0.000 | -1.247 | INSUFFICIENT_EVIDENCE | -1157.72 | 1157.72 / 1.247 | 1/1; -1.370 / 0.000 | 1/1; -1.493 / 0.000 |
| 15m | QUALITY | SR_REVERSAL / LONG | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 15m | QUALITY | SR_REVERSAL / SHORT | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 15m | ATR_EXITS | TREND_PULLBACK / LONG | 3/3/3 | 0 | 66.7 | 6.542 | 1.345 | INSUFFICIENT_EVIDENCE | 2389.84 | 431.26 / 0.290 | 3/3; 1.205 / 4.696 | 3/3; 1.065 / 3.520 |
| 15m | ATR_EXITS | TREND_PULLBACK / SHORT | 2/2/2 | 0 | 0.0 | 0.000 | -1.296 | INSUFFICIENT_EVIDENCE | -2225.30 | 2225.30 / 2.591 | 2/2; -1.443 / 0.000 | 2/2; -1.591 / 0.000 |
| 15m | ATR_EXITS | BREAKOUT_RETEST / LONG | 4/4/4 | 0 | 50.0 | 1.444 | 0.452 | INSUFFICIENT_EVIDENCE | 1027.61 | 1183.29 / 1.293 | 4/4; 0.303 / 1.210 | 4/4; 0.154 / 1.018 |
| 15m | ATR_EXITS | BREAKOUT_RETEST / SHORT | 4/4/4 | 0 | 0.0 | 0.000 | -0.881 | INSUFFICIENT_EVIDENCE | -2864.04 | 2864.04 / 3.526 | 4/4; -1.030 / 0.000 | 4/4; -1.179 / 0.000 |
| 15m | ATR_EXITS | SR_REVERSAL / LONG | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 15m | ATR_EXITS | SR_REVERSAL / SHORT | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 15m | COMBINED | TREND_PULLBACK / LONG | 1/1/1 | 0 | 0.0 | 0.000 | -0.290 | INSUFFICIENT_EVIDENCE | -431.26 | 431.26 / 0.290 | 1/1; -0.373 / 0.000 | 1/1; -0.455 / 0.000 |
| 15m | COMBINED | TREND_PULLBACK / SHORT | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 15m | COMBINED | BREAKOUT_RETEST / LONG | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 15m | COMBINED | BREAKOUT_RETEST / SHORT | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 15m | COMBINED | SR_REVERSAL / LONG | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 15m | COMBINED | SR_REVERSAL / SHORT | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 15m | COMBINED_LOOSE | TREND_PULLBACK / LONG | 1/1/1 | 0 | 0.0 | 0.000 | -0.290 | INSUFFICIENT_EVIDENCE | -431.26 | 431.26 / 0.290 | 1/1; -0.373 / 0.000 | 1/1; -0.455 / 0.000 |
| 15m | COMBINED_LOOSE | TREND_PULLBACK / SHORT | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 15m | COMBINED_LOOSE | BREAKOUT_RETEST / LONG | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 15m | COMBINED_LOOSE | BREAKOUT_RETEST / SHORT | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 15m | COMBINED_LOOSE | SR_REVERSAL / LONG | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 15m | COMBINED_LOOSE | SR_REVERSAL / SHORT | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 15m | COMBINED_STRICT | TREND_PULLBACK / LONG | 1/1/1 | 0 | 0.0 | 0.000 | -0.290 | INSUFFICIENT_EVIDENCE | -431.26 | 431.26 / 0.290 | 1/1; -0.373 / 0.000 | 1/1; -0.455 / 0.000 |
| 15m | COMBINED_STRICT | TREND_PULLBACK / SHORT | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 15m | COMBINED_STRICT | BREAKOUT_RETEST / LONG | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 15m | COMBINED_STRICT | BREAKOUT_RETEST / SHORT | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 15m | COMBINED_STRICT | SR_REVERSAL / LONG | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 15m | COMBINED_STRICT | SR_REVERSAL / SHORT | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 1h | BASELINE | TREND_PULLBACK / LONG | 31/29/29 | 0 | 20.7 | 0.343 | -0.635 | [-1.078; -0.292] | -15365.56 | 15365.56 / 18.451 | 28/28; -0.769 / 0.290 | 27/27; -0.910 / 0.251 |
| 1h | BASELINE | TREND_PULLBACK / SHORT | 24/23/23 | 0 | 13.0 | 0.290 | -0.829 | [-1.374; -0.153] | -13292.38 | 14020.48 / 19.076 | 23/23; -1.005 / 0.241 | 23/23; -1.181 / 0.202 |
| 1h | BASELINE | BREAKOUT_RETEST / LONG | 20/18/16 | 2 | 25.0 | 0.457 | -0.317 | [-1.318; 0.215] | -7752.74 | 7752.74 / 5.234 | 18/16; -0.476 / 0.384 | 18/16; -0.634 / 0.324 |
| 1h | BASELINE | BREAKOUT_RETEST / SHORT | 37/37/37 | 0 | 27.0 | 0.631 | -0.325 | [-0.929; 0.185] | -8960.47 | 10633.36 / 14.112 | 37/37; -0.511 / 0.514 | 36/36; -0.779 / 0.366 |
| 1h | BASELINE | SR_REVERSAL / LONG | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 1h | BASELINE | SR_REVERSAL / SHORT | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 1h | TREND_REGIME | TREND_PULLBACK / LONG | 6/6/6 | 0 | 33.3 | 0.681 | 0.030 | INSUFFICIENT_EVIDENCE | -1555.52 | 3194.46 / 2.351 | 6/6; -0.121 / 0.580 | 6/6; -0.273 / 0.496 |
| 1h | TREND_REGIME | TREND_PULLBACK / SHORT | 4/4/4 | 0 | 25.0 | 0.420 | -0.281 | INSUFFICIENT_EVIDENCE | -2265.59 | 3903.57 / 3.752 | 4/4; -0.421 / 0.357 | 4/4; -0.562 / 0.304 |
| 1h | TREND_REGIME | BREAKOUT_RETEST / LONG | 20/18/16 | 2 | 25.0 | 0.457 | -0.317 | [-1.319; 0.208] | -7752.74 | 7752.74 / 5.234 | 18/16; -0.476 / 0.384 | 18/16; -0.634 / 0.324 |
| 1h | TREND_REGIME | BREAKOUT_RETEST / SHORT | 37/37/37 | 0 | 27.0 | 0.631 | -0.325 | [-0.967; 0.163] | -8960.47 | 10633.36 / 14.112 | 37/37; -0.511 / 0.514 | 36/36; -0.779 / 0.366 |
| 1h | TREND_REGIME | SR_REVERSAL / LONG | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 1h | TREND_REGIME | SR_REVERSAL / SHORT | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 1h | BREAKOUT_CONFIRM | TREND_PULLBACK / LONG | 31/29/29 | 0 | 20.7 | 0.343 | -0.635 | [-1.097; -0.295] | -15365.56 | 15365.56 / 18.451 | 28/28; -0.769 / 0.290 | 27/27; -0.910 / 0.251 |
| 1h | BREAKOUT_CONFIRM | TREND_PULLBACK / SHORT | 24/23/23 | 0 | 13.0 | 0.290 | -0.829 | [-1.375; -0.184] | -13292.38 | 14020.48 / 19.076 | 23/23; -1.005 / 0.241 | 23/23; -1.181 / 0.202 |
| 1h | BREAKOUT_CONFIRM | BREAKOUT_RETEST / LONG | 3/3/3 | 0 | 0.0 | 0.000 | -1.305 | INSUFFICIENT_EVIDENCE | -3179.02 | 3179.02 / 3.914 | 3/3; -1.457 / 0.000 | 3/3; -1.609 / 0.000 |
| 1h | BREAKOUT_CONFIRM | BREAKOUT_RETEST / SHORT | 1/1/1 | 0 | 0.0 | 0.000 | -0.508 | INSUFFICIENT_EVIDENCE | -378.04 | 378.04 / 0.508 | 1/1; -0.676 / 0.000 | 1/1; -0.844 / 0.000 |
| 1h | BREAKOUT_CONFIRM | SR_REVERSAL / LONG | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 1h | BREAKOUT_CONFIRM | SR_REVERSAL / SHORT | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 1h | QUALITY | TREND_PULLBACK / LONG | 9/8/8 | 0 | 25.0 | 0.490 | -0.244 | INSUFFICIENT_EVIDENCE | -4245.95 | 5237.17 / 3.560 | 8/8; -0.366 / 0.423 | 8/8; -0.488 / 0.367 |
| 1h | QUALITY | TREND_PULLBACK / SHORT | 2/2/2 | 0 | 0.0 | 0.000 | -1.301 | INSUFFICIENT_EVIDENCE | -1816.32 | 1816.32 / 2.601 | 2/2; -1.451 / 0.000 | 2/2; -1.601 / 0.000 |
| 1h | QUALITY | BREAKOUT_RETEST / LONG | 3/3/3 | 0 | 0.0 | 0.000 | -1.193 | INSUFFICIENT_EVIDENCE | -5001.86 | 5001.86 / 3.579 | 3/3; -1.289 / 0.000 | 3/3; -1.386 / 0.000 |
| 1h | QUALITY | BREAKOUT_RETEST / SHORT | 3/3/3 | 0 | 33.3 | 0.345 | -0.411 | INSUFFICIENT_EVIDENCE | -990.04 | 1133.25 / 1.294 | 3/3; -0.562 / 0.223 | 3/3; -0.713 / 0.132 |
| 1h | QUALITY | SR_REVERSAL / LONG | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 1h | QUALITY | SR_REVERSAL / SHORT | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 1h | ATR_EXITS | TREND_PULLBACK / LONG | 3/3/3 | 0 | 0.0 | 0.000 | -1.200 | INSUFFICIENT_EVIDENCE | -4521.50 | 4521.50 / 3.599 | 3/3; -1.300 / 0.000 | 3/3; -1.399 / 0.000 |
| 1h | ATR_EXITS | TREND_PULLBACK / SHORT | 4/4/4 | 0 | 0.0 | 0.000 | -1.260 | INSUFFICIENT_EVIDENCE | -5010.48 | 5010.48 / 5.039 | 4/4; -1.390 / 0.000 | 4/4; -1.520 / 0.000 |
| 1h | ATR_EXITS | BREAKOUT_RETEST / LONG | 7/7/7 | 0 | 14.3 | 0.137 | -0.704 | INSUFFICIENT_EVIDENCE | -8733.53 | 8733.53 / 4.928 | 7/7; -0.806 / 0.117 | 7/7; -0.908 / 0.100 |
| 1h | ATR_EXITS | BREAKOUT_RETEST / SHORT | 9/9/9 | 0 | 44.4 | 1.041 | 0.305 | INSUFFICIENT_EVIDENCE | 287.62 | 5744.29 / 4.836 | 9/9; 0.180 / 0.895 | 9/9; 0.055 / 0.771 |
| 1h | ATR_EXITS | SR_REVERSAL / LONG | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 1h | ATR_EXITS | SR_REVERSAL / SHORT | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 1h | COMBINED | TREND_PULLBACK / LONG | 2/2/2 | 0 | 0.0 | 0.000 | -1.171 | INSUFFICIENT_EVIDENCE | -3256.68 | 3256.68 / 2.342 | 2/2; -1.257 / 0.000 | 2/2; -1.342 / 0.000 |
| 1h | COMBINED | TREND_PULLBACK / SHORT | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 1h | COMBINED | BREAKOUT_RETEST / LONG | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 1h | COMBINED | BREAKOUT_RETEST / SHORT | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 1h | COMBINED | SR_REVERSAL / LONG | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 1h | COMBINED | SR_REVERSAL / SHORT | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 1h | COMBINED_LOOSE | TREND_PULLBACK / LONG | 2/2/2 | 0 | 0.0 | 0.000 | -1.175 | INSUFFICIENT_EVIDENCE | -3194.46 | 3194.46 / 2.351 | 2/2; -1.263 / 0.000 | 2/2; -1.351 / 0.000 |
| 1h | COMBINED_LOOSE | TREND_PULLBACK / SHORT | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 1h | COMBINED_LOOSE | BREAKOUT_RETEST / LONG | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 1h | COMBINED_LOOSE | BREAKOUT_RETEST / SHORT | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 1h | COMBINED_LOOSE | SR_REVERSAL / LONG | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 1h | COMBINED_LOOSE | SR_REVERSAL / SHORT | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 1h | COMBINED_STRICT | TREND_PULLBACK / LONG | 1/1/1 | 0 | 0.0 | 0.000 | -1.156 | INSUFFICIENT_EVIDENCE | -1751.66 | 1751.66 / 1.156 | 1/1; -1.234 / 0.000 | 1/1; -1.313 / 0.000 |
| 1h | COMBINED_STRICT | TREND_PULLBACK / SHORT | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 1h | COMBINED_STRICT | BREAKOUT_RETEST / LONG | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 1h | COMBINED_STRICT | BREAKOUT_RETEST / SHORT | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 1h | COMBINED_STRICT | SR_REVERSAL / LONG | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 1h | COMBINED_STRICT | SR_REVERSAL / SHORT | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 4h | BASELINE | TREND_PULLBACK / LONG | 12/12/9 | 3 | 0.0 | 0.000 | -1.181 | INSUFFICIENT_EVIDENCE | -14375.78 | 14375.78 / 10.627 | 12/9; -1.271 / 0.000 | 12/9; -1.361 / 0.000 |
| 4h | BASELINE | TREND_PULLBACK / SHORT | 7/7/7 | 0 | 0.0 | 0.000 | -1.179 | INSUFFICIENT_EVIDENCE | -11268.38 | 11268.38 / 8.253 | 7/7; -1.268 / 0.000 | 7/7; -1.358 / 0.000 |
| 4h | BASELINE | BREAKOUT_RETEST / LONG | 7/7/7 | 0 | 14.3 | 0.174 | -0.638 | INSUFFICIENT_EVIDENCE | -7696.73 | 9316.34 / 7.138 | 7/7; -0.742 / 0.151 | 7/7; -0.847 / 0.132 |
| 4h | BASELINE | BREAKOUT_RETEST / SHORT | 7/7/7 | 0 | 28.6 | 0.778 | -0.052 | INSUFFICIENT_EVIDENCE | -1700.44 | 6329.73 / 4.711 | 7/7; -0.150 / 0.693 | 7/7; -0.247 / 0.620 |
| 4h | BASELINE | SR_REVERSAL / LONG | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 4h | BASELINE | SR_REVERSAL / SHORT | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 4h | TREND_REGIME | TREND_PULLBACK / LONG | 1/1/0 | 1 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 1/0; — / — | 1/0; — / — |
| 4h | TREND_REGIME | TREND_PULLBACK / SHORT | 1/1/1 | 0 | 0.0 | 0.000 | -1.188 | INSUFFICIENT_EVIDENCE | -1569.53 | 1569.53 / 1.188 | 1/1; -1.283 / 0.000 | 1/1; -1.377 / 0.000 |
| 4h | TREND_REGIME | BREAKOUT_RETEST / LONG | 7/7/7 | 0 | 14.3 | 0.174 | -0.638 | INSUFFICIENT_EVIDENCE | -7696.73 | 9316.34 / 7.138 | 7/7; -0.742 / 0.151 | 7/7; -0.847 / 0.132 |
| 4h | TREND_REGIME | BREAKOUT_RETEST / SHORT | 7/7/7 | 0 | 28.6 | 0.778 | -0.052 | INSUFFICIENT_EVIDENCE | -1700.44 | 6329.73 / 4.711 | 7/7; -0.150 / 0.693 | 7/7; -0.247 / 0.620 |
| 4h | TREND_REGIME | SR_REVERSAL / LONG | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 4h | TREND_REGIME | SR_REVERSAL / SHORT | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 4h | BREAKOUT_CONFIRM | TREND_PULLBACK / LONG | 12/12/9 | 3 | 0.0 | 0.000 | -1.181 | INSUFFICIENT_EVIDENCE | -14375.78 | 14375.78 / 10.627 | 12/9; -1.271 / 0.000 | 12/9; -1.361 / 0.000 |
| 4h | BREAKOUT_CONFIRM | TREND_PULLBACK / SHORT | 7/7/7 | 0 | 0.0 | 0.000 | -1.179 | INSUFFICIENT_EVIDENCE | -11268.38 | 11268.38 / 8.253 | 7/7; -1.268 / 0.000 | 7/7; -1.358 / 0.000 |
| 4h | BREAKOUT_CONFIRM | BREAKOUT_RETEST / LONG | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 4h | BREAKOUT_CONFIRM | BREAKOUT_RETEST / SHORT | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 4h | BREAKOUT_CONFIRM | SR_REVERSAL / LONG | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 4h | BREAKOUT_CONFIRM | SR_REVERSAL / SHORT | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 4h | QUALITY | TREND_PULLBACK / LONG | 6/6/4 | 2 | 0.0 | 0.000 | -1.158 | INSUFFICIENT_EVIDENCE | -6942.06 | 6942.06 / 4.633 | 6/4; -1.237 / 0.000 | 6/4; -1.316 / 0.000 |
| 4h | QUALITY | TREND_PULLBACK / SHORT | 3/3/3 | 0 | 0.0 | 0.000 | -1.150 | INSUFFICIENT_EVIDENCE | -5697.13 | 5697.13 / 3.451 | 3/3; -1.226 / 0.000 | 3/3; -1.301 / 0.000 |
| 4h | QUALITY | BREAKOUT_RETEST / LONG | 2/2/2 | 0 | 0.0 | 0.000 | -1.209 | INSUFFICIENT_EVIDENCE | -2844.53 | 2844.53 / 2.417 | 2/2; -1.313 / 0.000 | 2/2; -1.417 / 0.000 |
| 4h | QUALITY | BREAKOUT_RETEST / SHORT | 1/1/1 | 0 | 0.0 | 0.000 | -1.201 | INSUFFICIENT_EVIDENCE | -1474.88 | 1474.88 / 1.201 | 1/1; -1.301 / 0.000 | 1/1; -1.401 / 0.000 |
| 4h | QUALITY | SR_REVERSAL / LONG | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 4h | QUALITY | SR_REVERSAL / SHORT | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 4h | ATR_EXITS | TREND_PULLBACK / LONG | 12/12/6 | 6 | 0.0 | 0.000 | -1.152 | INSUFFICIENT_EVIDENCE | -10915.91 | 10915.91 / 6.912 | 12/6; -1.228 / 0.000 | 12/6; -1.304 / 0.000 |
| 4h | ATR_EXITS | TREND_PULLBACK / SHORT | 7/7/7 | 0 | 0.0 | 0.000 | -1.152 | INSUFFICIENT_EVIDENCE | -12729.50 | 12729.50 / 8.061 | 7/7; -1.227 / 0.000 | 7/7; -1.303 / 0.000 |
| 4h | ATR_EXITS | BREAKOUT_RETEST / LONG | 7/7/7 | 0 | 14.3 | 0.156 | -0.660 | INSUFFICIENT_EVIDENCE | -9869.18 | 11690.31 / 6.874 | 7/7; -0.740 / 0.139 | 7/7; -0.819 / 0.124 |
| 4h | ATR_EXITS | BREAKOUT_RETEST / SHORT | 7/7/7 | 0 | 28.6 | 0.534 | -0.290 | INSUFFICIENT_EVIDENCE | -4568.54 | 9798.84 / 5.700 | 7/7; -0.363 / 0.481 | 7/7; -0.436 / 0.434 |
| 4h | ATR_EXITS | SR_REVERSAL / LONG | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 4h | ATR_EXITS | SR_REVERSAL / SHORT | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 4h | COMBINED | TREND_PULLBACK / LONG | 1/1/0 | 1 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 1/0; — / — | 1/0; — / — |
| 4h | COMBINED | TREND_PULLBACK / SHORT | 1/1/1 | 0 | 0.0 | 0.000 | -1.144 | INSUFFICIENT_EVIDENCE | -1980.50 | 1980.50 / 1.144 | 1/1; -1.216 / 0.000 | 1/1; -1.288 / 0.000 |
| 4h | COMBINED | BREAKOUT_RETEST / LONG | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 4h | COMBINED | BREAKOUT_RETEST / SHORT | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 4h | COMBINED | SR_REVERSAL / LONG | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 4h | COMBINED | SR_REVERSAL / SHORT | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 4h | COMBINED_LOOSE | TREND_PULLBACK / LONG | 1/1/0 | 1 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 1/0; — / — | 1/0; — / — |
| 4h | COMBINED_LOOSE | TREND_PULLBACK / SHORT | 1/1/1 | 0 | 0.0 | 0.000 | -1.164 | INSUFFICIENT_EVIDENCE | -1763.80 | 1763.80 / 1.164 | 1/1; -1.247 / 0.000 | 1/1; -1.329 / 0.000 |
| 4h | COMBINED_LOOSE | BREAKOUT_RETEST / LONG | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 4h | COMBINED_LOOSE | BREAKOUT_RETEST / SHORT | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 4h | COMBINED_LOOSE | SR_REVERSAL / LONG | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 4h | COMBINED_LOOSE | SR_REVERSAL / SHORT | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 4h | COMBINED_STRICT | TREND_PULLBACK / LONG | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 4h | COMBINED_STRICT | TREND_PULLBACK / SHORT | 1/1/1 | 0 | 0.0 | 0.000 | -1.128 | INSUFFICIENT_EVIDENCE | -2197.21 | 2197.21 / 1.128 | 1/1; -1.192 / 0.000 | 1/1; -1.257 / 0.000 |
| 4h | COMBINED_STRICT | BREAKOUT_RETEST / LONG | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 4h | COMBINED_STRICT | BREAKOUT_RETEST / SHORT | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 4h | COMBINED_STRICT | SR_REVERSAL / LONG | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
| 4h | COMBINED_STRICT | SR_REVERSAL / SHORT | 0/0/0 | 0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0/0; — / — | 0/0; — / — |
