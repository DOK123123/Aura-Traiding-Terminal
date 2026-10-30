# Aura 6 · Полное сравнение

Все строки — отдельная стратегия/вариант/сторона/TF, не портфель. Комиссия 10 bps/сторону, проскальзывание 5 bps/сторону, модельный полный спред 2 bps; стресс умножает все расходы. Funding: реальные ставки с 2026-08-01, до этого явно модельный дебет 1 bp/8h (×1.5/×2 в stress). M — количество модельных начислений funding. Результаты с M>0 не подтверждают реальную прибыльность. Позиции одного семейства/варианта/стороны/TF не пересекаются; разные группы не суммируются в доходность.

| TF | Семейство | Вариант | Сторона | Период | Расходы | Сигналы / входы / закрыто | WR % | PF | E[R] | 95% CI E[R] | PnL USDT | DD USDT / R | Funding USDT / M |
|---|---|---|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|
| 5m | TREND_PULLBACK | BASE | LONG | train | ×1 | 29/26/26 | 26.9 | 0.534 | -0.441 | INSUFFICIENT_EVIDENCE | -3007.33 | 3085.24 / 12.672 | 18.53 / 6 |
| 5m | TREND_PULLBACK | BASE | SHORT | train | ×1 | 55/48/48 | 39.6 | 1.070 | -0.020 | [-0.413; 0.385] | 799.14 | 2969.67 / 8.730 | 54.90 / 16 |
| 5m | TREND_PULLBACK | STRICT | LONG | train | ×1 | 2/2/2 | 50.0 | 2.775 | 0.448 | INSUFFICIENT_EVIDENCE | 459.97 | 259.11 / 1.318 | 0.00 / 0 |
| 5m | TREND_PULLBACK | STRICT | SHORT | train | ×1 | 10/9/9 | 55.6 | 3.005 | 0.472 | INSUFFICIENT_EVIDENCE | 2271.78 | 656.86 / 2.646 | 4.35 / 1 |
| 5m | BREAKOUT_RETEST | BASE | LONG | train | ×1 | 17/15/15 | 20.0 | 0.189 | -0.528 | INSUFFICIENT_EVIDENCE | -5891.98 | 5937.83 / 8.614 | 13.17 / 4 |
| 5m | BREAKOUT_RETEST | BASE | SHORT | train | ×1 | 29/24/24 | 50.0 | 0.997 | 0.046 | INSUFFICIENT_EVIDENCE | -29.07 | 3472.72 / 3.548 | 7.99 / 4 |
| 5m | BREAKOUT_RETEST | STRICT | LONG | train | ×1 | 16/14/14 | 14.3 | 0.038 | -0.695 | INSUFFICIENT_EVIDENCE | -6986.70 | 7032.56 / 9.765 | 13.17 / 4 |
| 5m | BREAKOUT_RETEST | STRICT | SHORT | train | ×1 | 26/22/22 | 50.0 | 1.062 | 0.097 | INSUFFICIENT_EVIDENCE | 552.76 | 3472.72 / 3.548 | 5.91 / 3 |
| 5m | MOMENTUM_EXPANSION | BASE | LONG | train | ×1 | 50/42/42 | 33.3 | 0.549 | -0.309 | [-0.693; -0.042] | -4579.67 | 4579.67 / 13.130 | 21.84 / 9 |
| 5m | MOMENTUM_EXPANSION | BASE | SHORT | train | ×1 | 72/63/63 | 25.4 | 0.464 | -0.449 | [-0.871; -0.183] | -9476.62 | 10497.98 / 31.323 | 17.21 / 5 |
| 5m | MOMENTUM_EXPANSION | STRICT | LONG | train | ×1 | 37/32/32 | 28.1 | 0.438 | -0.447 | [-0.872; -0.251] | -4618.85 | 4618.85 / 14.319 | 11.26 / 5 |
| 5m | MOMENTUM_EXPANSION | STRICT | SHORT | train | ×1 | 48/42/42 | 23.8 | 0.391 | -0.559 | [-1.082; -0.221] | -7697.21 | 8377.39 / 23.579 | 12.64 / 3 |
| 5m | MEAN_REVERSION | BASE | LONG | train | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | MEAN_REVERSION | BASE | SHORT | train | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | MEAN_REVERSION | STRICT | LONG | train | ×1 | 1/1/1 | 0.0 | 0.000 | -1.193 | INSUFFICIENT_EVIDENCE | -697.12 | 697.12 / 1.193 | 0.00 / 0 |
| 5m | MEAN_REVERSION | STRICT | SHORT | train | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | LIQUIDITY_SWEEP | BASE | LONG | train | ×1 | 11/11/11 | 45.5 | 0.779 | -0.108 | INSUFFICIENT_EVIDENCE | -1021.44 | 2176.80 / 4.293 | 6.98 / 2 |
| 5m | LIQUIDITY_SWEEP | BASE | SHORT | train | ×1 | 7/7/7 | 42.9 | 0.338 | -0.379 | INSUFFICIENT_EVIDENCE | -1418.15 | 2142.75 / 3.697 | 1.90 / 1 |
| 5m | LIQUIDITY_SWEEP | STRICT | LONG | train | ×1 | 11/11/11 | 45.5 | 0.779 | -0.108 | INSUFFICIENT_EVIDENCE | -1021.44 | 2176.80 / 4.293 | 6.98 / 2 |
| 5m | LIQUIDITY_SWEEP | STRICT | SHORT | train | ×1 | 7/7/7 | 42.9 | 0.338 | -0.379 | INSUFFICIENT_EVIDENCE | -1418.15 | 2142.75 / 3.697 | 1.90 / 1 |
| 5m | RANGE_REJECTION | BASE | LONG | train | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | RANGE_REJECTION | BASE | SHORT | train | ×1 | 1/1/1 | 100.0 | — | 2.415 | INSUFFICIENT_EVIDENCE | 405.93 | 0.00 / 0.000 | 0.00 / 0 |
| 5m | RANGE_REJECTION | STRICT | LONG | train | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | RANGE_REJECTION | STRICT | SHORT | train | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | TREND_PULLBACK | BASE | LONG | train | ×1.5 | 29/26/26 | 23.1 | 0.434 | -0.598 | INSUFFICIENT_EVIDENCE | -4165.30 | 4165.30 / 15.976 | 27.80 / 6 |
| 5m | TREND_PULLBACK | BASE | SHORT | train | ×1.5 | 55/48/48 | 39.6 | 0.862 | -0.164 | [-0.561; 0.251] | -1772.74 | 3337.64 / 10.514 | 82.35 / 16 |
| 5m | TREND_PULLBACK | STRICT | LONG | train | ×1.5 | 2/2/2 | 50.0 | 2.317 | 0.298 | INSUFFICIENT_EVIDENCE | 382.39 | 290.34 / 1.476 | 0.00 / 0 |
| 5m | TREND_PULLBACK | STRICT | SHORT | train | ×1.5 | 10/9/9 | 55.6 | 2.460 | 0.338 | INSUFFICIENT_EVIDENCE | 1843.28 | 818.56 / 2.969 | 6.52 / 1 |
| 5m | BREAKOUT_RETEST | BASE | LONG | train | ×1.5 | 17/15/15 | 13.3 | 0.157 | -0.603 | INSUFFICIENT_EVIDENCE | -6597.61 | 6597.61 / 9.507 | 19.75 / 4 |
| 5m | BREAKOUT_RETEST | BASE | SHORT | train | ×1.5 | 29/24/24 | 50.0 | 0.887 | -0.028 | INSUFFICIENT_EVIDENCE | -1153.81 | 3611.49 / 3.868 | 11.98 / 4 |
| 5m | BREAKOUT_RETEST | STRICT | LONG | train | ×1.5 | 16/14/14 | 7.1 | 0.025 | -0.769 | INSUFFICIENT_EVIDENCE | -7635.36 | 7635.36 / 10.760 | 19.75 / 4 |
| 5m | BREAKOUT_RETEST | STRICT | SHORT | train | ×1.5 | 26/22/22 | 50.0 | 0.948 | 0.024 | INSUFFICIENT_EVIDENCE | -491.60 | 3611.49 / 3.899 | 8.86 / 3 |
| 5m | MOMENTUM_EXPANSION | BASE | LONG | train | ×1.5 | 50/42/42 | 31.0 | 0.436 | -0.459 | [-0.800; -0.213] | -6427.09 | 6427.09 / 19.265 | 32.77 / 9 |
| 5m | MOMENTUM_EXPANSION | BASE | SHORT | train | ×1.5 | 72/63/63 | 23.8 | 0.385 | -0.596 | [-0.982; -0.314] | -12192.68 | 12894.70 / 40.166 | 25.82 / 5 |
| 5m | MOMENTUM_EXPANSION | STRICT | LONG | train | ×1.5 | 37/32/32 | 25.0 | 0.350 | -0.596 | [-0.985; -0.391] | -6020.47 | 6020.47 / 19.078 | 16.89 / 5 |
| 5m | MOMENTUM_EXPANSION | STRICT | SHORT | train | ×1.5 | 48/42/42 | 21.4 | 0.325 | -0.705 | [-1.248; -0.360] | -9534.02 | 9991.87 / 29.605 | 18.96 / 3 |
| 5m | MEAN_REVERSION | BASE | LONG | train | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | MEAN_REVERSION | BASE | SHORT | train | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | MEAN_REVERSION | STRICT | LONG | train | ×1.5 | 1/1/1 | 0.0 | 0.000 | -1.289 | INSUFFICIENT_EVIDENCE | -753.44 | 753.44 / 1.289 | 0.00 / 0 |
| 5m | MEAN_REVERSION | STRICT | SHORT | train | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | LIQUIDITY_SWEEP | BASE | LONG | train | ×1.5 | 11/11/11 | 45.5 | 0.689 | -0.177 | INSUFFICIENT_EVIDENCE | -1525.53 | 2402.05 / 4.602 | 10.47 / 2 |
| 5m | LIQUIDITY_SWEEP | BASE | SHORT | train | ×1.5 | 7/7/7 | 28.6 | 0.272 | -0.445 | INSUFFICIENT_EVIDENCE | -1673.08 | 2276.73 / 3.943 | 2.85 / 1 |
| 5m | LIQUIDITY_SWEEP | STRICT | LONG | train | ×1.5 | 11/11/11 | 45.5 | 0.689 | -0.177 | INSUFFICIENT_EVIDENCE | -1525.53 | 2402.05 / 4.602 | 10.47 / 2 |
| 5m | LIQUIDITY_SWEEP | STRICT | SHORT | train | ×1.5 | 7/7/7 | 28.6 | 0.272 | -0.445 | INSUFFICIENT_EVIDENCE | -1673.08 | 2276.73 / 3.943 | 2.85 / 1 |
| 5m | RANGE_REJECTION | BASE | LONG | train | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | RANGE_REJECTION | BASE | SHORT | train | ×1.5 | 1/1/1 | 100.0 | — | 2.160 | INSUFFICIENT_EVIDENCE | 363.15 | 0.00 / 0.000 | 0.00 / 0 |
| 5m | RANGE_REJECTION | STRICT | LONG | train | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | RANGE_REJECTION | STRICT | SHORT | train | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | TREND_PULLBACK | BASE | LONG | train | ×2 | 29/26/26 | 23.1 | 0.359 | -0.755 | INSUFFICIENT_EVIDENCE | -5323.31 | 5323.31 / 19.696 | 37.06 / 6 |
| 5m | TREND_PULLBACK | BASE | SHORT | train | ×2 | 55/48/48 | 37.5 | 0.679 | -0.323 | [-0.740; 0.111] | -4621.39 | 4621.39 / 15.892 | 109.80 / 16 |
| 5m | TREND_PULLBACK | STRICT | LONG | train | ×2 | 2/2/2 | 50.0 | 1.948 | 0.147 | INSUFFICIENT_EVIDENCE | 304.81 | 321.58 / 1.635 | 0.00 / 0 |
| 5m | TREND_PULLBACK | STRICT | SHORT | train | ×2 | 10/9/9 | 55.6 | 2.016 | 0.204 | INSUFFICIENT_EVIDENCE | 1414.78 | 980.26 / 3.370 | 8.70 / 1 |
| 5m | BREAKOUT_RETEST | BASE | LONG | train | ×2 | 17/15/15 | 13.3 | 0.135 | -0.678 | INSUFFICIENT_EVIDENCE | -7303.26 | 7303.26 / 10.401 | 26.33 / 4 |
| 5m | BREAKOUT_RETEST | BASE | SHORT | train | ×2 | 29/24/24 | 45.8 | 0.789 | -0.102 | INSUFFICIENT_EVIDENCE | -2278.52 | 3750.24 / 4.652 | 15.97 / 4 |
| 5m | BREAKOUT_RETEST | STRICT | LONG | train | ×2 | 16/14/14 | 7.1 | 0.018 | -0.842 | INSUFFICIENT_EVIDENCE | -8284.04 | 8284.04 / 11.794 | 26.33 / 4 |
| 5m | BREAKOUT_RETEST | STRICT | SHORT | train | ×2 | 26/22/22 | 50.0 | 0.847 | -0.050 | INSUFFICIENT_EVIDENCE | -1535.92 | 3750.24 / 4.636 | 11.81 / 3 |
| 5m | MOMENTUM_EXPANSION | BASE | LONG | train | ×2 | 50/42/42 | 28.6 | 0.349 | -0.608 | [-0.964; -0.355] | -8274.58 | 8274.58 / 25.533 | 43.69 / 9 |
| 5m | MOMENTUM_EXPANSION | BASE | SHORT | train | ×2 | 72/63/63 | 23.8 | 0.321 | -0.742 | [-1.160; -0.458] | -14908.63 | 15528.04 / 49.123 | 34.42 / 5 |
| 5m | MOMENTUM_EXPANSION | STRICT | LONG | train | ×2 | 37/32/32 | 25.0 | 0.280 | -0.745 | [-1.173; -0.528] | -7422.13 | 7422.13 / 23.837 | 22.52 / 5 |
| 5m | MOMENTUM_EXPANSION | STRICT | SHORT | train | ×2 | 48/42/42 | 21.4 | 0.272 | -0.851 | [-1.419; -0.489] | -11370.74 | 11606.28 / 35.744 | 25.28 / 3 |
| 5m | MEAN_REVERSION | BASE | LONG | train | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | MEAN_REVERSION | BASE | SHORT | train | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | MEAN_REVERSION | STRICT | LONG | train | ×2 | 1/1/1 | 0.0 | 0.000 | -1.385 | INSUFFICIENT_EVIDENCE | -809.76 | 809.76 / 1.385 | 0.00 / 0 |
| 5m | MEAN_REVERSION | STRICT | SHORT | train | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | LIQUIDITY_SWEEP | BASE | LONG | train | ×2 | 11/11/11 | 45.5 | 0.609 | -0.245 | INSUFFICIENT_EVIDENCE | -2029.63 | 2627.31 / 4.910 | 13.95 / 2 |
| 5m | LIQUIDITY_SWEEP | BASE | SHORT | train | ×2 | 7/7/7 | 28.6 | 0.216 | -0.511 | INSUFFICIENT_EVIDENCE | -1928.01 | 2410.70 / 4.190 | 3.80 / 1 |
| 5m | LIQUIDITY_SWEEP | STRICT | LONG | train | ×2 | 11/11/11 | 45.5 | 0.609 | -0.245 | INSUFFICIENT_EVIDENCE | -2029.63 | 2627.31 / 4.910 | 13.95 / 2 |
| 5m | LIQUIDITY_SWEEP | STRICT | SHORT | train | ×2 | 7/7/7 | 28.6 | 0.216 | -0.511 | INSUFFICIENT_EVIDENCE | -1928.01 | 2410.70 / 4.190 | 3.80 / 1 |
| 5m | RANGE_REJECTION | BASE | LONG | train | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | RANGE_REJECTION | BASE | SHORT | train | ×2 | 1/1/1 | 100.0 | — | 1.906 | INSUFFICIENT_EVIDENCE | 320.37 | 0.00 / 0.000 | 0.00 / 0 |
| 5m | RANGE_REJECTION | STRICT | LONG | train | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | RANGE_REJECTION | STRICT | SHORT | train | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | TREND_PULLBACK | BASE | LONG | validation | ×1 | 3/3/3 | 33.3 | 0.191 | -0.785 | INSUFFICIENT_EVIDENCE | -958.58 | 958.58 / 2.354 | 4.41 / 1 |
| 5m | TREND_PULLBACK | BASE | SHORT | validation | ×1 | 19/16/16 | 37.5 | 0.736 | -0.226 | INSUFFICIENT_EVIDENCE | -1750.13 | 4573.39 / 7.082 | 35.24 / 6 |
| 5m | TREND_PULLBACK | STRICT | LONG | validation | ×1 | 1/1/1 | 0.0 | 0.000 | -1.358 | INSUFFICIENT_EVIDENCE | -533.95 | 533.95 / 1.358 | 4.41 / 1 |
| 5m | TREND_PULLBACK | STRICT | SHORT | validation | ×1 | 3/3/3 | 33.3 | 1.839 | 0.174 | INSUFFICIENT_EVIDENCE | 503.93 | 600.35 / 1.006 | 5.70 / 1 |
| 5m | BREAKOUT_RETEST | BASE | LONG | validation | ×1 | 5/5/5 | 40.0 | 0.159 | -0.146 | INSUFFICIENT_EVIDENCE | -1837.57 | 2157.45 / 1.277 | 8.91 / 3 |
| 5m | BREAKOUT_RETEST | BASE | SHORT | validation | ×1 | 4/4/4 | 50.0 | 1.793 | 0.480 | INSUFFICIENT_EVIDENCE | 1672.70 | 2108.74 / 1.761 | 5.94 / 1 |
| 5m | BREAKOUT_RETEST | STRICT | LONG | validation | ×1 | 4/4/4 | 25.0 | 0.024 | -0.301 | INSUFFICIENT_EVIDENCE | -2131.76 | 2157.45 / 1.277 | 8.91 / 3 |
| 5m | BREAKOUT_RETEST | STRICT | SHORT | validation | ×1 | 3/3/3 | 66.7 | 3.780 | 1.029 | INSUFFICIENT_EVIDENCE | 2781.09 | 1000.35 / 0.595 | 5.94 / 1 |
| 5m | MOMENTUM_EXPANSION | BASE | LONG | validation | ×1 | 12/11/11 | 36.4 | 0.834 | -0.101 | INSUFFICIENT_EVIDENCE | -641.31 | 1957.31 / 3.148 | 18.39 / 3 |
| 5m | MOMENTUM_EXPANSION | BASE | SHORT | validation | ×1 | 34/29/29 | 31.0 | 0.492 | -0.454 | INSUFFICIENT_EVIDENCE | -7532.25 | 7532.25 / 13.155 | 41.66 / 7 |
| 5m | MOMENTUM_EXPANSION | STRICT | LONG | validation | ×1 | 8/7/7 | 42.9 | 1.292 | 0.178 | INSUFFICIENT_EVIDENCE | 601.37 | 1658.76 / 2.590 | 0.00 / 0 |
| 5m | MOMENTUM_EXPANSION | STRICT | SHORT | validation | ×1 | 24/22/22 | 31.8 | 0.483 | -0.497 | INSUFFICIENT_EVIDENCE | -5399.53 | 6610.25 / 10.936 | 35.15 / 6 |
| 5m | MEAN_REVERSION | BASE | LONG | validation | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | MEAN_REVERSION | BASE | SHORT | validation | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | MEAN_REVERSION | STRICT | LONG | validation | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | MEAN_REVERSION | STRICT | SHORT | validation | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | LIQUIDITY_SWEEP | BASE | LONG | validation | ×1 | 2/2/2 | 50.0 | 0.958 | -0.276 | INSUFFICIENT_EVIDENCE | -65.82 | 1580.58 / 1.144 | 0.00 / 0 |
| 5m | LIQUIDITY_SWEEP | BASE | SHORT | validation | ×1 | 2/2/2 | 100.0 | — | 0.798 | INSUFFICIENT_EVIDENCE | 2141.05 | 0.00 / 0.000 | 10.00 / 2 |
| 5m | LIQUIDITY_SWEEP | STRICT | LONG | validation | ×1 | 2/2/2 | 50.0 | 0.958 | -0.276 | INSUFFICIENT_EVIDENCE | -65.82 | 1580.58 / 1.144 | 0.00 / 0 |
| 5m | LIQUIDITY_SWEEP | STRICT | SHORT | validation | ×1 | 2/2/2 | 100.0 | — | 0.798 | INSUFFICIENT_EVIDENCE | 2141.05 | 0.00 / 0.000 | 10.00 / 2 |
| 5m | RANGE_REJECTION | BASE | LONG | validation | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | RANGE_REJECTION | BASE | SHORT | validation | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | RANGE_REJECTION | STRICT | LONG | validation | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | RANGE_REJECTION | STRICT | SHORT | validation | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | TREND_PULLBACK | BASE | LONG | validation | ×1.5 | 3/3/3 | 33.3 | 0.095 | -0.961 | INSUFFICIENT_EVIDENCE | -1215.80 | 1215.80 / 2.882 | 6.62 / 1 |
| 5m | TREND_PULLBACK | BASE | SHORT | validation | ×1.5 | 19/16/16 | 31.2 | 0.564 | -0.379 | INSUFFICIENT_EVIDENCE | -3287.26 | 5532.82 / 8.546 | 52.86 / 6 |
| 5m | TREND_PULLBACK | STRICT | LONG | validation | ×1.5 | 1/1/1 | 0.0 | 0.000 | -1.537 | INSUFFICIENT_EVIDENCE | -604.34 | 604.34 / 1.537 | 6.62 / 1 |
| 5m | TREND_PULLBACK | STRICT | SHORT | validation | ×1.5 | 3/3/3 | 33.3 | 1.268 | 0.027 | INSUFFICIENT_EVIDENCE | 212.65 | 792.08 / 1.310 | 8.55 / 1 |
| 5m | BREAKOUT_RETEST | BASE | LONG | validation | ×1.5 | 5/5/5 | 40.0 | 0.103 | -0.209 | INSUFFICIENT_EVIDENCE | -2089.50 | 2324.04 / 1.420 | 13.36 / 3 |
| 5m | BREAKOUT_RETEST | BASE | SHORT | validation | ×1.5 | 4/4/4 | 50.0 | 1.584 | 0.406 | INSUFFICIENT_EVIDENCE | 1334.07 | 2284.16 / 1.901 | 8.91 / 1 |
| 5m | BREAKOUT_RETEST | STRICT | LONG | validation | ×1.5 | 4/4/4 | 25.0 | 0.003 | -0.355 | INSUFFICIENT_EVIDENCE | -2324.04 | 2324.04 / 1.420 | 13.36 / 3 |
| 5m | BREAKOUT_RETEST | STRICT | SHORT | validation | ×1.5 | 3/3/3 | 66.7 | 3.298 | 0.957 | INSUFFICIENT_EVIDENCE | 2521.06 | 1097.17 / 0.653 | 8.91 / 1 |
| 5m | MOMENTUM_EXPANSION | BASE | LONG | validation | ×1.5 | 12/11/11 | 36.4 | 0.627 | -0.268 | INSUFFICIENT_EVIDENCE | -1680.29 | 2421.69 / 3.976 | 27.59 / 3 |
| 5m | MOMENTUM_EXPANSION | BASE | SHORT | validation | ×1.5 | 34/29/29 | 24.1 | 0.393 | -0.615 | INSUFFICIENT_EVIDENCE | -10142.38 | 10142.38 / 17.822 | 62.49 / 7 |
| 5m | MOMENTUM_EXPANSION | STRICT | LONG | validation | ×1.5 | 8/7/7 | 42.9 | 0.985 | 0.020 | INSUFFICIENT_EVIDENCE | -35.32 | 1846.08 / 2.884 | 0.00 / 0 |
| 5m | MOMENTUM_EXPANSION | STRICT | SHORT | validation | ×1.5 | 24/22/22 | 22.7 | 0.379 | -0.659 | INSUFFICIENT_EVIDENCE | -7342.91 | 8221.95 / 14.494 | 52.73 / 6 |
| 5m | MEAN_REVERSION | BASE | LONG | validation | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | MEAN_REVERSION | BASE | SHORT | validation | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | MEAN_REVERSION | STRICT | LONG | validation | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | MEAN_REVERSION | STRICT | SHORT | validation | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | LIQUIDITY_SWEEP | BASE | LONG | validation | ×1.5 | 2/2/2 | 50.0 | 0.842 | -0.331 | INSUFFICIENT_EVIDENCE | -264.89 | 1679.92 / 1.216 | 0.00 / 0 |
| 5m | LIQUIDITY_SWEEP | BASE | SHORT | validation | ×1.5 | 2/2/2 | 100.0 | — | 0.735 | INSUFFICIENT_EVIDENCE | 1975.88 | 0.00 / 0.000 | 15.00 / 2 |
| 5m | LIQUIDITY_SWEEP | STRICT | LONG | validation | ×1.5 | 2/2/2 | 50.0 | 0.842 | -0.331 | INSUFFICIENT_EVIDENCE | -264.89 | 1679.92 / 1.216 | 0.00 / 0 |
| 5m | LIQUIDITY_SWEEP | STRICT | SHORT | validation | ×1.5 | 2/2/2 | 100.0 | — | 0.735 | INSUFFICIENT_EVIDENCE | 1975.88 | 0.00 / 0.000 | 15.00 / 2 |
| 5m | RANGE_REJECTION | BASE | LONG | validation | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | RANGE_REJECTION | BASE | SHORT | validation | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | RANGE_REJECTION | STRICT | LONG | validation | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | RANGE_REJECTION | STRICT | SHORT | validation | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | TREND_PULLBACK | BASE | LONG | validation | ×2 | 3/3/3 | 33.3 | 0.020 | -1.137 | INSUFFICIENT_EVIDENCE | -1473.03 | 1473.03 / 3.410 | 8.82 / 1 |
| 5m | TREND_PULLBACK | BASE | SHORT | validation | ×2 | 19/16/16 | 31.2 | 0.436 | -0.532 | INSUFFICIENT_EVIDENCE | -4824.35 | 6492.22 / 10.009 | 70.48 / 6 |
| 5m | TREND_PULLBACK | STRICT | LONG | validation | ×2 | 1/1/1 | 0.0 | 0.000 | -1.716 | INSUFFICIENT_EVIDENCE | -674.73 | 674.73 / 1.716 | 8.82 / 1 |
| 5m | TREND_PULLBACK | STRICT | SHORT | validation | ×2 | 3/3/3 | 33.3 | 0.920 | -0.120 | INSUFFICIENT_EVIDENCE | -78.63 | 983.81 / 1.613 | 11.40 / 1 |
| 5m | BREAKOUT_RETEST | BASE | LONG | validation | ×2 | 5/5/5 | 20.0 | 0.069 | -0.271 | INSUFFICIENT_EVIDENCE | -2341.43 | 2516.32 / 1.637 | 17.81 / 3 |
| 5m | BREAKOUT_RETEST | BASE | SHORT | validation | ×2 | 4/4/4 | 50.0 | 1.405 | 0.331 | INSUFFICIENT_EVIDENCE | 995.45 | 2459.57 / 2.041 | 11.87 / 1 |
| 5m | BREAKOUT_RETEST | STRICT | LONG | validation | ×2 | 4/4/4 | 0.0 | 0.000 | -0.409 | INSUFFICIENT_EVIDENCE | -2516.32 | 2516.32 / 1.637 | 17.81 / 3 |
| 5m | BREAKOUT_RETEST | STRICT | SHORT | validation | ×2 | 3/3/3 | 66.7 | 2.894 | 0.885 | INSUFFICIENT_EVIDENCE | 2261.04 | 1193.99 / 0.711 | 11.87 / 1 |
| 5m | MOMENTUM_EXPANSION | BASE | LONG | validation | ×2 | 12/11/11 | 36.4 | 0.474 | -0.435 | INSUFFICIENT_EVIDENCE | -2719.29 | 3307.80 / 5.506 | 36.79 / 3 |
| 5m | MOMENTUM_EXPANSION | BASE | SHORT | validation | ×2 | 34/29/29 | 20.7 | 0.321 | -0.775 | INSUFFICIENT_EVIDENCE | -12752.40 | 12752.40 / 22.489 | 83.32 / 7 |
| 5m | MOMENTUM_EXPANSION | STRICT | LONG | validation | ×2 | 8/7/7 | 42.9 | 0.756 | -0.139 | INSUFFICIENT_EVIDENCE | -672.02 | 2033.41 / 3.179 | 0.00 / 0 |
| 5m | MOMENTUM_EXPANSION | STRICT | SHORT | validation | ×2 | 24/22/22 | 18.2 | 0.308 | -0.820 | INSUFFICIENT_EVIDENCE | -9286.23 | 9833.59 / 18.051 | 70.31 / 6 |
| 5m | MEAN_REVERSION | BASE | LONG | validation | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | MEAN_REVERSION | BASE | SHORT | validation | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | MEAN_REVERSION | STRICT | LONG | validation | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | MEAN_REVERSION | STRICT | SHORT | validation | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | LIQUIDITY_SWEEP | BASE | LONG | validation | ×2 | 2/2/2 | 50.0 | 0.739 | -0.387 | INSUFFICIENT_EVIDENCE | -463.95 | 1779.27 / 1.288 | 0.00 / 0 |
| 5m | LIQUIDITY_SWEEP | BASE | SHORT | validation | ×2 | 2/2/2 | 100.0 | — | 0.672 | INSUFFICIENT_EVIDENCE | 1810.71 | 0.00 / 0.000 | 20.00 / 2 |
| 5m | LIQUIDITY_SWEEP | STRICT | LONG | validation | ×2 | 2/2/2 | 50.0 | 0.739 | -0.387 | INSUFFICIENT_EVIDENCE | -463.95 | 1779.27 / 1.288 | 0.00 / 0 |
| 5m | LIQUIDITY_SWEEP | STRICT | SHORT | validation | ×2 | 2/2/2 | 100.0 | — | 0.672 | INSUFFICIENT_EVIDENCE | 1810.71 | 0.00 / 0.000 | 20.00 / 2 |
| 5m | RANGE_REJECTION | BASE | LONG | validation | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | RANGE_REJECTION | BASE | SHORT | validation | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | RANGE_REJECTION | STRICT | LONG | validation | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | RANGE_REJECTION | STRICT | SHORT | validation | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | TREND_PULLBACK | BASE | LONG | test | ×1 | 6/5/5 | 20.0 | 0.506 | -0.182 | INSUFFICIENT_EVIDENCE | -1198.42 | 2420.47 / 2.532 | 27.57 / 3 |
| 5m | TREND_PULLBACK | BASE | SHORT | test | ×1 | 8/8/8 | 37.5 | 0.768 | -0.062 | INSUFFICIENT_EVIDENCE | -1338.92 | 3293.84 / 3.446 | 31.01 / 3 |
| 5m | TREND_PULLBACK | STRICT | LONG | test | ×1 | 2/2/2 | 0.0 | 0.000 | -0.606 | INSUFFICIENT_EVIDENCE | -1045.01 | 1045.01 / 1.212 | 18.65 / 2 |
| 5m | TREND_PULLBACK | STRICT | SHORT | test | ×1 | 2/2/2 | 50.0 | 0.631 | -0.098 | INSUFFICIENT_EVIDENCE | -359.51 | 973.20 / 0.865 | 19.43 / 2 |
| 5m | BREAKOUT_RETEST | BASE | LONG | test | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | BREAKOUT_RETEST | BASE | SHORT | test | ×1 | 4/4/4 | 0.0 | 0.000 | -1.074 | INSUFFICIENT_EVIDENCE | -9498.77 | 9498.77 / 4.297 | 9.71 / 1 |
| 5m | BREAKOUT_RETEST | STRICT | LONG | test | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | BREAKOUT_RETEST | STRICT | SHORT | test | ×1 | 3/3/3 | 0.0 | 0.000 | -1.037 | INSUFFICIENT_EVIDENCE | -7867.60 | 7867.60 / 3.110 | 9.71 / 1 |
| 5m | MOMENTUM_EXPANSION | BASE | LONG | test | ×1 | 12/9/9 | 44.4 | 1.613 | 0.244 | INSUFFICIENT_EVIDENCE | 3339.32 | 2405.90 / 2.681 | 8.89 / 1 |
| 5m | MOMENTUM_EXPANSION | BASE | SHORT | test | ×1 | 24/22/22 | 22.7 | 0.308 | -0.601 | INSUFFICIENT_EVIDENCE | -11803.36 | 11803.36 / 13.229 | 44.03 / 5 |
| 5m | MOMENTUM_EXPANSION | STRICT | LONG | test | ×1 | 11/9/9 | 44.4 | 1.613 | 0.244 | INSUFFICIENT_EVIDENCE | 3339.32 | 2405.90 / 2.681 | 8.89 / 1 |
| 5m | MOMENTUM_EXPANSION | STRICT | SHORT | test | ×1 | 19/17/17 | 23.5 | 0.414 | -0.475 | INSUFFICIENT_EVIDENCE | -7257.40 | 7339.06 / 8.200 | 35.16 / 4 |
| 5m | MEAN_REVERSION | BASE | LONG | test | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | MEAN_REVERSION | BASE | SHORT | test | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | MEAN_REVERSION | STRICT | LONG | test | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | MEAN_REVERSION | STRICT | SHORT | test | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | LIQUIDITY_SWEEP | BASE | LONG | test | ×1 | 3/3/3 | 0.0 | 0.000 | -0.778 | INSUFFICIENT_EVIDENCE | -7114.61 | 7114.61 / 2.334 | 0.00 / 0 |
| 5m | LIQUIDITY_SWEEP | BASE | SHORT | test | ×1 | 1/1/1 | 0.0 | 0.000 | -0.165 | INSUFFICIENT_EVIDENCE | -435.21 | 435.21 / 0.165 | 10.78 / 1 |
| 5m | LIQUIDITY_SWEEP | STRICT | LONG | test | ×1 | 3/3/3 | 0.0 | 0.000 | -0.778 | INSUFFICIENT_EVIDENCE | -7114.61 | 7114.61 / 2.334 | 0.00 / 0 |
| 5m | LIQUIDITY_SWEEP | STRICT | SHORT | test | ×1 | 1/1/1 | 0.0 | 0.000 | -0.165 | INSUFFICIENT_EVIDENCE | -435.21 | 435.21 / 0.165 | 10.78 / 1 |
| 5m | RANGE_REJECTION | BASE | LONG | test | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | RANGE_REJECTION | BASE | SHORT | test | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | RANGE_REJECTION | STRICT | LONG | test | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | RANGE_REJECTION | STRICT | SHORT | test | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | TREND_PULLBACK | BASE | LONG | test | ×1.5 | 6/5/5 | 20.0 | 0.355 | -0.354 | INSUFFICIENT_EVIDENCE | -1962.86 | 2893.23 / 3.030 | 41.36 / 3 |
| 5m | TREND_PULLBACK | BASE | SHORT | test | ×1.5 | 8/8/8 | 37.5 | 0.614 | -0.214 | INSUFFICIENT_EVIDENCE | -2521.51 | 3743.72 / 3.911 | 46.52 / 3 |
| 5m | TREND_PULLBACK | STRICT | LONG | test | ×1.5 | 2/2/2 | 0.0 | 0.000 | -0.775 | INSUFFICIENT_EVIDENCE | -1351.26 | 1351.26 / 1.551 | 27.98 / 2 |
| 5m | TREND_PULLBACK | STRICT | SHORT | test | ×1.5 | 2/2/2 | 50.0 | 0.402 | -0.256 | INSUFFICIENT_EVIDENCE | -679.01 | 1135.56 / 1.010 | 29.14 / 2 |
| 5m | BREAKOUT_RETEST | BASE | LONG | test | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | BREAKOUT_RETEST | BASE | SHORT | test | ×1.5 | 4/4/4 | 0.0 | 0.000 | -1.149 | INSUFFICIENT_EVIDENCE | -10096.10 | 10096.10 / 4.595 | 14.56 / 1 |
| 5m | BREAKOUT_RETEST | STRICT | LONG | test | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | BREAKOUT_RETEST | STRICT | SHORT | test | ×1.5 | 3/3/3 | 0.0 | 0.000 | -1.105 | INSUFFICIENT_EVIDENCE | -8336.37 | 8336.37 / 3.314 | 14.56 / 1 |
| 5m | MOMENTUM_EXPANSION | BASE | LONG | test | ×1.5 | 12/9/9 | 44.4 | 1.343 | 0.088 | INSUFFICIENT_EVIDENCE | 2105.14 | 2711.36 / 3.021 | 13.34 / 1 |
| 5m | MOMENTUM_EXPANSION | BASE | SHORT | test | ×1.5 | 24/22/22 | 13.6 | 0.232 | -0.797 | INSUFFICIENT_EVIDENCE | -15456.89 | 15456.89 / 17.527 | 66.05 / 5 |
| 5m | MOMENTUM_EXPANSION | STRICT | LONG | test | ×1.5 | 11/9/9 | 44.4 | 1.343 | 0.088 | INSUFFICIENT_EVIDENCE | 2105.14 | 2711.36 / 3.021 | 13.34 / 1 |
| 5m | MOMENTUM_EXPANSION | STRICT | SHORT | test | ×1.5 | 19/17/17 | 17.6 | 0.314 | -0.684 | INSUFFICIENT_EVIDENCE | -10227.33 | 10227.33 / 11.623 | 52.73 / 4 |
| 5m | MEAN_REVERSION | BASE | LONG | test | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | MEAN_REVERSION | BASE | SHORT | test | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | MEAN_REVERSION | STRICT | LONG | test | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | MEAN_REVERSION | STRICT | SHORT | test | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | LIQUIDITY_SWEEP | BASE | LONG | test | ×1.5 | 3/3/3 | 0.0 | 0.000 | -0.841 | INSUFFICIENT_EVIDENCE | -7566.61 | 7566.61 / 2.522 | 0.00 / 0 |
| 5m | LIQUIDITY_SWEEP | BASE | SHORT | test | ×1.5 | 1/1/1 | 0.0 | 0.000 | -0.232 | INSUFFICIENT_EVIDENCE | -612.77 | 612.77 / 0.232 | 16.16 / 1 |
| 5m | LIQUIDITY_SWEEP | STRICT | LONG | test | ×1.5 | 3/3/3 | 0.0 | 0.000 | -0.841 | INSUFFICIENT_EVIDENCE | -7566.61 | 7566.61 / 2.522 | 0.00 / 0 |
| 5m | LIQUIDITY_SWEEP | STRICT | SHORT | test | ×1.5 | 1/1/1 | 0.0 | 0.000 | -0.232 | INSUFFICIENT_EVIDENCE | -612.77 | 612.77 / 0.232 | 16.16 / 1 |
| 5m | RANGE_REJECTION | BASE | LONG | test | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | RANGE_REJECTION | BASE | SHORT | test | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | RANGE_REJECTION | STRICT | LONG | test | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | RANGE_REJECTION | STRICT | SHORT | test | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | TREND_PULLBACK | BASE | LONG | test | ×2 | 6/5/5 | 20.0 | 0.255 | -0.525 | INSUFFICIENT_EVIDENCE | -2727.30 | 3366.00 / 3.528 | 55.14 / 3 |
| 5m | TREND_PULLBACK | BASE | SHORT | test | ×2 | 8/8/8 | 37.5 | 0.493 | -0.365 | INSUFFICIENT_EVIDENCE | -3704.06 | 4193.58 / 4.377 | 62.03 / 3 |
| 5m | TREND_PULLBACK | STRICT | LONG | test | ×2 | 2/2/2 | 0.0 | 0.000 | -0.945 | INSUFFICIENT_EVIDENCE | -1657.52 | 1657.52 / 1.890 | 37.30 / 2 |
| 5m | TREND_PULLBACK | STRICT | SHORT | test | ×2 | 2/2/2 | 50.0 | 0.231 | -0.414 | INSUFFICIENT_EVIDENCE | -998.52 | 1297.91 / 1.154 | 38.86 / 2 |
| 5m | BREAKOUT_RETEST | BASE | LONG | test | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | BREAKOUT_RETEST | BASE | SHORT | test | ×2 | 4/4/4 | 0.0 | 0.000 | -1.223 | INSUFFICIENT_EVIDENCE | -10693.41 | 10693.41 / 4.893 | 19.41 / 1 |
| 5m | BREAKOUT_RETEST | STRICT | LONG | test | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | BREAKOUT_RETEST | STRICT | SHORT | test | ×2 | 3/3/3 | 0.0 | 0.000 | -1.173 | INSUFFICIENT_EVIDENCE | -8805.12 | 8805.12 / 3.518 | 19.41 / 1 |
| 5m | MOMENTUM_EXPANSION | BASE | LONG | test | ×2 | 12/9/9 | 44.4 | 1.128 | -0.068 | INSUFFICIENT_EVIDENCE | 870.90 | 3016.84 / 3.361 | 17.78 / 1 |
| 5m | MOMENTUM_EXPANSION | BASE | SHORT | test | ×2 | 24/22/22 | 13.6 | 0.188 | -0.960 | INSUFFICIENT_EVIDENCE | -18490.85 | 18490.85 / 21.124 | 88.06 / 5 |
| 5m | MOMENTUM_EXPANSION | STRICT | LONG | test | ×2 | 11/9/9 | 44.4 | 1.128 | -0.068 | INSUFFICIENT_EVIDENCE | 870.90 | 3016.84 / 3.361 | 17.78 / 1 |
| 5m | MOMENTUM_EXPANSION | STRICT | SHORT | test | ×2 | 19/17/17 | 17.6 | 0.254 | -0.851 | INSUFFICIENT_EVIDENCE | -12577.70 | 12577.70 / 14.470 | 70.31 / 4 |
| 5m | MEAN_REVERSION | BASE | LONG | test | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | MEAN_REVERSION | BASE | SHORT | test | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | MEAN_REVERSION | STRICT | LONG | test | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | MEAN_REVERSION | STRICT | SHORT | test | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | LIQUIDITY_SWEEP | BASE | LONG | test | ×2 | 3/3/3 | 0.0 | 0.000 | -0.903 | INSUFFICIENT_EVIDENCE | -8018.63 | 8018.63 / 2.709 | 0.00 / 0 |
| 5m | LIQUIDITY_SWEEP | BASE | SHORT | test | ×2 | 1/1/1 | 0.0 | 0.000 | -0.300 | INSUFFICIENT_EVIDENCE | -790.32 | 790.32 / 0.300 | 21.55 / 1 |
| 5m | LIQUIDITY_SWEEP | STRICT | LONG | test | ×2 | 3/3/3 | 0.0 | 0.000 | -0.903 | INSUFFICIENT_EVIDENCE | -8018.63 | 8018.63 / 2.709 | 0.00 / 0 |
| 5m | LIQUIDITY_SWEEP | STRICT | SHORT | test | ×2 | 1/1/1 | 0.0 | 0.000 | -0.300 | INSUFFICIENT_EVIDENCE | -790.32 | 790.32 / 0.300 | 21.55 / 1 |
| 5m | RANGE_REJECTION | BASE | LONG | test | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | RANGE_REJECTION | BASE | SHORT | test | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | RANGE_REJECTION | STRICT | LONG | test | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | RANGE_REJECTION | STRICT | SHORT | test | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | TREND_PULLBACK | BASE | LONG | final | ×1 | 4/4/4 | 50.0 | 4.388 | 0.833 | INSUFFICIENT_EVIDENCE | 2269.64 | 412.45 / 0.558 | 0.00 / 0 |
| 5m | TREND_PULLBACK | BASE | SHORT | final | ×1 | 13/11/11 | 27.3 | 0.481 | -0.461 | INSUFFICIENT_EVIDENCE | -4056.81 | 5641.03 / 7.240 | 40.66 / 6 |
| 5m | TREND_PULLBACK | STRICT | LONG | final | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | TREND_PULLBACK | STRICT | SHORT | final | ×1 | 2/2/2 | 0.0 | 0.000 | -1.270 | INSUFFICIENT_EVIDENCE | -2174.37 | 2174.37 / 2.539 | 14.06 / 2 |
| 5m | BREAKOUT_RETEST | BASE | LONG | final | ×1 | 1/1/1 | 0.0 | 0.000 | -0.276 | INSUFFICIENT_EVIDENCE | -381.53 | 381.53 / 0.276 | 0.00 / 0 |
| 5m | BREAKOUT_RETEST | BASE | SHORT | final | ×1 | 3/3/3 | 0.0 | 0.000 | -1.100 | INSUFFICIENT_EVIDENCE | -13860.53 | 13860.53 / 3.300 | 0.00 / 0 |
| 5m | BREAKOUT_RETEST | STRICT | LONG | final | ×1 | 1/1/1 | 0.0 | 0.000 | -0.276 | INSUFFICIENT_EVIDENCE | -381.53 | 381.53 / 0.276 | 0.00 / 0 |
| 5m | BREAKOUT_RETEST | STRICT | SHORT | final | ×1 | 3/3/3 | 0.0 | 0.000 | -1.100 | INSUFFICIENT_EVIDENCE | -13860.53 | 13860.53 / 3.300 | 0.00 / 0 |
| 5m | MOMENTUM_EXPANSION | BASE | LONG | final | ×1 | 11/10/10 | 10.0 | 0.054 | -0.670 | INSUFFICIENT_EVIDENCE | -4902.31 | 4902.31 / 6.702 | 33.46 / 4 |
| 5m | MOMENTUM_EXPANSION | BASE | SHORT | final | ×1 | 25/20/20 | 30.0 | 0.431 | -0.510 | INSUFFICIENT_EVIDENCE | -7571.81 | 7571.81 / 10.197 | 6.77 / 1 |
| 5m | MOMENTUM_EXPANSION | STRICT | LONG | final | ×1 | 7/7/7 | 14.3 | 0.099 | -0.513 | INSUFFICIENT_EVIDENCE | -2555.22 | 2555.22 / 3.592 | 25.57 / 3 |
| 5m | MOMENTUM_EXPANSION | STRICT | SHORT | final | ×1 | 22/17/17 | 29.4 | 0.399 | -0.577 | INSUFFICIENT_EVIDENCE | -6761.98 | 6761.98 / 9.811 | 6.77 / 1 |
| 5m | MEAN_REVERSION | BASE | LONG | final | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | MEAN_REVERSION | BASE | SHORT | final | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | MEAN_REVERSION | STRICT | LONG | final | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | MEAN_REVERSION | STRICT | SHORT | final | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | LIQUIDITY_SWEEP | BASE | LONG | final | ×1 | 1/1/1 | 0.0 | 0.000 | -0.177 | INSUFFICIENT_EVIDENCE | -358.57 | 358.57 / 0.177 | 0.00 / 0 |
| 5m | LIQUIDITY_SWEEP | BASE | SHORT | final | ×1 | 1/1/1 | 0.0 | 0.000 | -0.550 | INSUFFICIENT_EVIDENCE | -680.72 | 680.72 / 0.550 | 6.33 / 1 |
| 5m | LIQUIDITY_SWEEP | STRICT | LONG | final | ×1 | 1/1/1 | 0.0 | 0.000 | -0.177 | INSUFFICIENT_EVIDENCE | -358.57 | 358.57 / 0.177 | 0.00 / 0 |
| 5m | LIQUIDITY_SWEEP | STRICT | SHORT | final | ×1 | 1/1/1 | 0.0 | 0.000 | -0.550 | INSUFFICIENT_EVIDENCE | -680.72 | 680.72 / 0.550 | 6.33 / 1 |
| 5m | RANGE_REJECTION | BASE | LONG | final | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | RANGE_REJECTION | BASE | SHORT | final | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | RANGE_REJECTION | STRICT | LONG | final | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | RANGE_REJECTION | STRICT | SHORT | final | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | TREND_PULLBACK | BASE | LONG | final | ×1.5 | 4/4/4 | 50.0 | 2.936 | 0.653 | INSUFFICIENT_EVIDENCE | 1785.33 | 551.27 / 0.746 | 0.00 / 0 |
| 5m | TREND_PULLBACK | BASE | SHORT | final | ×1.5 | 13/11/11 | 27.3 | 0.395 | -0.605 | INSUFFICIENT_EVIDENCE | -5234.12 | 6695.59 / 8.651 | 60.99 / 6 |
| 5m | TREND_PULLBACK | STRICT | LONG | final | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | TREND_PULLBACK | STRICT | SHORT | final | ×1.5 | 2/2/2 | 0.0 | 0.000 | -1.405 | INSUFFICIENT_EVIDENCE | -2399.86 | 2399.86 / 2.809 | 21.09 / 2 |
| 5m | BREAKOUT_RETEST | BASE | LONG | final | ×1.5 | 1/1/1 | 0.0 | 0.000 | -0.351 | INSUFFICIENT_EVIDENCE | -486.29 | 486.29 / 0.351 | 0.00 / 0 |
| 5m | BREAKOUT_RETEST | BASE | SHORT | final | ×1.5 | 3/3/3 | 0.0 | 0.000 | -1.150 | INSUFFICIENT_EVIDENCE | -14227.34 | 14227.34 / 3.450 | 0.00 / 0 |
| 5m | BREAKOUT_RETEST | STRICT | LONG | final | ×1.5 | 1/1/1 | 0.0 | 0.000 | -0.351 | INSUFFICIENT_EVIDENCE | -486.29 | 486.29 / 0.351 | 0.00 / 0 |
| 5m | BREAKOUT_RETEST | STRICT | SHORT | final | ×1.5 | 3/3/3 | 0.0 | 0.000 | -1.150 | INSUFFICIENT_EVIDENCE | -14227.34 | 14227.34 / 3.450 | 0.00 / 0 |
| 5m | MOMENTUM_EXPANSION | BASE | LONG | final | ×1.5 | 11/10/10 | 10.0 | 0.027 | -0.847 | INSUFFICIENT_EVIDENCE | -6149.98 | 6149.98 / 8.471 | 50.18 / 4 |
| 5m | MOMENTUM_EXPANSION | BASE | SHORT | final | ×1.5 | 25/20/20 | 30.0 | 0.342 | -0.671 | INSUFFICIENT_EVIDENCE | -9813.10 | 9813.10 / 13.415 | 10.16 / 1 |
| 5m | MOMENTUM_EXPANSION | STRICT | LONG | final | ×1.5 | 7/7/7 | 14.3 | 0.046 | -0.695 | INSUFFICIENT_EVIDENCE | -3441.04 | 3441.04 / 4.868 | 38.36 / 3 |
| 5m | MOMENTUM_EXPANSION | STRICT | SHORT | final | ×1.5 | 22/17/17 | 29.4 | 0.312 | -0.740 | INSUFFICIENT_EVIDENCE | -8683.10 | 8683.10 / 12.586 | 10.16 / 1 |
| 5m | MEAN_REVERSION | BASE | LONG | final | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | MEAN_REVERSION | BASE | SHORT | final | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | MEAN_REVERSION | STRICT | LONG | final | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | MEAN_REVERSION | STRICT | SHORT | final | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | LIQUIDITY_SWEEP | BASE | LONG | final | ×1.5 | 1/1/1 | 0.0 | 0.000 | -0.239 | INSUFFICIENT_EVIDENCE | -482.55 | 482.55 / 0.239 | 0.00 / 0 |
| 5m | LIQUIDITY_SWEEP | BASE | SHORT | final | ×1.5 | 1/1/1 | 0.0 | 0.000 | -0.634 | INSUFFICIENT_EVIDENCE | -785.28 | 785.28 / 0.634 | 9.50 / 1 |
| 5m | LIQUIDITY_SWEEP | STRICT | LONG | final | ×1.5 | 1/1/1 | 0.0 | 0.000 | -0.239 | INSUFFICIENT_EVIDENCE | -482.55 | 482.55 / 0.239 | 0.00 / 0 |
| 5m | LIQUIDITY_SWEEP | STRICT | SHORT | final | ×1.5 | 1/1/1 | 0.0 | 0.000 | -0.634 | INSUFFICIENT_EVIDENCE | -785.28 | 785.28 / 0.634 | 9.50 / 1 |
| 5m | RANGE_REJECTION | BASE | LONG | final | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | RANGE_REJECTION | BASE | SHORT | final | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | RANGE_REJECTION | STRICT | LONG | final | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | RANGE_REJECTION | STRICT | SHORT | final | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | TREND_PULLBACK | BASE | LONG | final | ×2 | 4/4/4 | 50.0 | 2.108 | 0.474 | INSUFFICIENT_EVIDENCE | 1301.02 | 690.10 / 0.934 | 0.00 / 0 |
| 5m | TREND_PULLBACK | BASE | SHORT | final | ×2 | 13/11/11 | 27.3 | 0.324 | -0.748 | INSUFFICIENT_EVIDENCE | -6411.40 | 7750.12 / 10.061 | 81.32 / 6 |
| 5m | TREND_PULLBACK | STRICT | LONG | final | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | TREND_PULLBACK | STRICT | SHORT | final | ×2 | 2/2/2 | 0.0 | 0.000 | -1.539 | INSUFFICIENT_EVIDENCE | -2625.33 | 2625.33 / 3.079 | 28.12 / 2 |
| 5m | BREAKOUT_RETEST | BASE | LONG | final | ×2 | 1/1/1 | 0.0 | 0.000 | -0.427 | INSUFFICIENT_EVIDENCE | -591.05 | 591.05 / 0.427 | 0.00 / 0 |
| 5m | BREAKOUT_RETEST | BASE | SHORT | final | ×2 | 3/3/3 | 0.0 | 0.000 | -1.200 | INSUFFICIENT_EVIDENCE | -14594.14 | 14594.14 / 3.600 | 0.00 / 0 |
| 5m | BREAKOUT_RETEST | STRICT | LONG | final | ×2 | 1/1/1 | 0.0 | 0.000 | -0.427 | INSUFFICIENT_EVIDENCE | -591.05 | 591.05 / 0.427 | 0.00 / 0 |
| 5m | BREAKOUT_RETEST | STRICT | SHORT | final | ×2 | 3/3/3 | 0.0 | 0.000 | -1.200 | INSUFFICIENT_EVIDENCE | -14594.14 | 14594.14 / 3.600 | 0.00 / 0 |
| 5m | MOMENTUM_EXPANSION | BASE | LONG | final | ×2 | 11/10/10 | 10.0 | 0.007 | -1.024 | INSUFFICIENT_EVIDENCE | -7397.67 | 7397.67 / 10.240 | 66.91 / 4 |
| 5m | MOMENTUM_EXPANSION | BASE | SHORT | final | ×2 | 25/20/20 | 30.0 | 0.270 | -0.832 | INSUFFICIENT_EVIDENCE | -12054.31 | 12054.31 / 16.633 | 13.55 / 1 |
| 5m | MOMENTUM_EXPANSION | STRICT | LONG | final | ×2 | 7/7/7 | 14.3 | 0.013 | -0.878 | INSUFFICIENT_EVIDENCE | -4326.87 | 4326.87 / 6.144 | 51.14 / 3 |
| 5m | MOMENTUM_EXPANSION | STRICT | SHORT | final | ×2 | 22/17/17 | 29.4 | 0.243 | -0.904 | INSUFFICIENT_EVIDENCE | -10604.15 | 10604.15 / 15.362 | 13.55 / 1 |
| 5m | MEAN_REVERSION | BASE | LONG | final | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | MEAN_REVERSION | BASE | SHORT | final | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | MEAN_REVERSION | STRICT | LONG | final | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | MEAN_REVERSION | STRICT | SHORT | final | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | LIQUIDITY_SWEEP | BASE | LONG | final | ×2 | 1/1/1 | 0.0 | 0.000 | -0.300 | INSUFFICIENT_EVIDENCE | -606.54 | 606.54 / 0.300 | 0.00 / 0 |
| 5m | LIQUIDITY_SWEEP | BASE | SHORT | final | ×2 | 1/1/1 | 0.0 | 0.000 | -0.718 | INSUFFICIENT_EVIDENCE | -889.84 | 889.84 / 0.718 | 12.67 / 1 |
| 5m | LIQUIDITY_SWEEP | STRICT | LONG | final | ×2 | 1/1/1 | 0.0 | 0.000 | -0.300 | INSUFFICIENT_EVIDENCE | -606.54 | 606.54 / 0.300 | 0.00 / 0 |
| 5m | LIQUIDITY_SWEEP | STRICT | SHORT | final | ×2 | 1/1/1 | 0.0 | 0.000 | -0.718 | INSUFFICIENT_EVIDENCE | -889.84 | 889.84 / 0.718 | 12.67 / 1 |
| 5m | RANGE_REJECTION | BASE | LONG | final | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | RANGE_REJECTION | BASE | SHORT | final | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | RANGE_REJECTION | STRICT | LONG | final | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 5m | RANGE_REJECTION | STRICT | SHORT | final | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | TREND_PULLBACK | BASE | LONG | train | ×1 | 34/30/30 | 23.3 | 0.286 | -0.552 | [-0.908; -0.133] | -8260.01 | 9440.69 / 18.727 | 74.97 / 22 |
| 15m | TREND_PULLBACK | BASE | SHORT | train | ×1 | 54/51/51 | 25.5 | 0.517 | -0.495 | [-0.774; -0.219] | -10580.12 | 10580.12 / 25.269 | 119.25 / 36 |
| 15m | TREND_PULLBACK | STRICT | LONG | train | ×1 | 5/5/5 | 40.0 | 0.438 | -0.205 | INSUFFICIENT_EVIDENCE | -645.42 | 892.98 / 2.286 | 16.87 / 7 |
| 15m | TREND_PULLBACK | STRICT | SHORT | train | ×1 | 10/10/10 | 30.0 | 0.404 | -0.432 | INSUFFICIENT_EVIDENCE | -2206.48 | 2568.41 / 5.185 | 20.15 / 7 |
| 15m | BREAKOUT_RETEST | BASE | LONG | train | ×1 | 26/22/22 | 31.8 | 0.826 | -0.130 | INSUFFICIENT_EVIDENCE | -1319.58 | 4830.32 / 7.178 | 43.65 / 17 |
| 15m | BREAKOUT_RETEST | BASE | SHORT | train | ×1 | 60/45/45 | 35.6 | 0.812 | -0.103 | [-0.444; 0.239] | -3265.22 | 7032.74 / 9.903 | 94.24 / 33 |
| 15m | BREAKOUT_RETEST | STRICT | LONG | train | ×1 | 24/21/21 | 33.3 | 0.883 | -0.130 | INSUFFICIENT_EVIDENCE | -825.55 | 4336.29 / 7.054 | 40.71 / 16 |
| 15m | BREAKOUT_RETEST | STRICT | SHORT | train | ×1 | 47/35/35 | 37.1 | 0.929 | -0.034 | [-0.509; 0.333] | -919.06 | 4006.63 / 5.692 | 73.93 / 26 |
| 15m | MOMENTUM_EXPANSION | BASE | LONG | train | ×1 | 95/85/85 | 24.7 | 0.407 | -0.471 | [-0.732; -0.230] | -16157.10 | 16980.44 / 41.178 | 139.60 / 38 |
| 15m | MOMENTUM_EXPANSION | BASE | SHORT | train | ×1 | 137/123/123 | 29.3 | 0.487 | -0.436 | [-0.590; -0.257] | -20703.99 | 20747.53 / 53.692 | 145.46 / 48 |
| 15m | MOMENTUM_EXPANSION | STRICT | LONG | train | ×1 | 74/70/70 | 27.1 | 0.417 | -0.440 | [-0.697; -0.136] | -12891.24 | 13714.58 / 31.941 | 117.40 / 32 |
| 15m | MOMENTUM_EXPANSION | STRICT | SHORT | train | ×1 | 96/89/89 | 30.3 | 0.472 | -0.434 | [-0.658; -0.214] | -14403.49 | 14461.86 / 39.099 | 112.29 / 37 |
| 15m | MEAN_REVERSION | BASE | LONG | train | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | MEAN_REVERSION | BASE | SHORT | train | ×1 | 1/1/1 | 0.0 | 0.000 | -0.332 | INSUFFICIENT_EVIDENCE | -158.52 | 158.52 / 0.332 | 5.98 / 1 |
| 15m | MEAN_REVERSION | STRICT | LONG | train | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | MEAN_REVERSION | STRICT | SHORT | train | ×1 | 1/1/1 | 0.0 | 0.000 | -0.286 | INSUFFICIENT_EVIDENCE | -140.06 | 140.06 / 0.286 | 5.98 / 1 |
| 15m | LIQUIDITY_SWEEP | BASE | LONG | train | ×1 | 26/26/26 | 46.2 | 0.534 | -0.118 | INSUFFICIENT_EVIDENCE | -4346.08 | 6274.89 / 7.761 | 71.53 / 19 |
| 15m | LIQUIDITY_SWEEP | BASE | SHORT | train | ×1 | 25/24/24 | 33.3 | 0.799 | -0.185 | INSUFFICIENT_EVIDENCE | -1606.64 | 6965.17 / 12.134 | 45.05 / 16 |
| 15m | LIQUIDITY_SWEEP | STRICT | LONG | train | ×1 | 24/24/24 | 50.0 | 0.612 | -0.030 | INSUFFICIENT_EVIDENCE | -3156.54 | 5085.35 / 5.426 | 71.53 / 19 |
| 15m | LIQUIDITY_SWEEP | STRICT | SHORT | train | ×1 | 23/22/22 | 31.8 | 0.700 | -0.233 | INSUFFICIENT_EVIDENCE | -2246.65 | 6454.03 / 10.985 | 41.51 / 15 |
| 15m | RANGE_REJECTION | BASE | LONG | train | ×1 | 1/1/1 | 0.0 | 0.000 | -1.274 | INSUFFICIENT_EVIDENCE | -278.93 | 278.93 / 1.274 | 0.00 / 0 |
| 15m | RANGE_REJECTION | BASE | SHORT | train | ×1 | 2/1/1 | 100.0 | — | 2.553 | INSUFFICIENT_EVIDENCE | 926.78 | 0.00 / 0.000 | 0.00 / 0 |
| 15m | RANGE_REJECTION | STRICT | LONG | train | ×1 | 1/1/1 | 0.0 | 0.000 | -1.274 | INSUFFICIENT_EVIDENCE | -278.93 | 278.93 / 1.274 | 0.00 / 0 |
| 15m | RANGE_REJECTION | STRICT | SHORT | train | ×1 | 1/1/1 | 100.0 | — | 2.551 | INSUFFICIENT_EVIDENCE | 924.28 | 0.00 / 0.000 | 0.00 / 0 |
| 15m | TREND_PULLBACK | BASE | LONG | train | ×1.5 | 34/30/30 | 23.3 | 0.229 | -0.695 | [-1.063; -0.323] | -10007.32 | 11099.78 / 22.864 | 112.45 / 22 |
| 15m | TREND_PULLBACK | BASE | SHORT | train | ×1.5 | 54/51/51 | 23.5 | 0.439 | -0.621 | [-0.925; -0.332] | -13463.40 | 13463.40 / 31.646 | 178.88 / 36 |
| 15m | TREND_PULLBACK | STRICT | LONG | train | ×1.5 | 5/5/5 | 40.0 | 0.338 | -0.328 | INSUFFICIENT_EVIDENCE | -852.19 | 1066.53 / 2.731 | 25.30 / 7 |
| 15m | TREND_PULLBACK | STRICT | SHORT | train | ×1.5 | 10/10/10 | 30.0 | 0.320 | -0.561 | INSUFFICIENT_EVIDENCE | -2759.19 | 2923.68 / 6.155 | 30.23 / 7 |
| 15m | BREAKOUT_RETEST | BASE | LONG | train | ×1.5 | 26/22/22 | 31.8 | 0.724 | -0.205 | INSUFFICIENT_EVIDENCE | -2243.04 | 5497.03 / 8.493 | 65.47 / 17 |
| 15m | BREAKOUT_RETEST | BASE | SHORT | train | ×1.5 | 60/45/45 | 35.6 | 0.715 | -0.178 | [-0.566; 0.150] | -5305.24 | 8095.79 / 12.124 | 141.36 / 33 |
| 15m | BREAKOUT_RETEST | STRICT | LONG | train | ×1.5 | 24/21/21 | 33.3 | 0.776 | -0.206 | INSUFFICIENT_EVIDENCE | -1701.39 | 4955.38 / 8.325 | 61.06 / 16 |
| 15m | BREAKOUT_RETEST | STRICT | SHORT | train | ×1.5 | 47/35/35 | 37.1 | 0.817 | -0.110 | [-0.585; 0.239] | -2556.69 | 4448.31 / 6.282 | 110.90 / 26 |
| 15m | MOMENTUM_EXPANSION | BASE | LONG | train | ×1.5 | 95/85/85 | 24.7 | 0.322 | -0.625 | [-0.865; -0.379] | -21026.52 | 21317.76 / 53.790 | 209.39 / 38 |
| 15m | MOMENTUM_EXPANSION | BASE | SHORT | train | ×1.5 | 137/123/123 | 26.8 | 0.396 | -0.581 | [-0.754; -0.406] | -27173.01 | 27173.01 / 71.514 | 218.19 / 48 |
| 15m | MOMENTUM_EXPANSION | STRICT | LONG | train | ×1.5 | 74/70/70 | 27.1 | 0.326 | -0.598 | [-0.861; -0.291] | -16986.68 | 17277.92 / 42.545 | 176.10 / 32 |
| 15m | MOMENTUM_EXPANSION | STRICT | SHORT | train | ×1.5 | 96/89/89 | 28.1 | 0.382 | -0.579 | [-0.809; -0.350] | -18793.27 | 18793.27 / 51.513 | 168.43 / 37 |
| 15m | MEAN_REVERSION | BASE | LONG | train | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | MEAN_REVERSION | BASE | SHORT | train | ×1.5 | 1/1/1 | 0.0 | 0.000 | -0.537 | INSUFFICIENT_EVIDENCE | -256.53 | 256.53 / 0.537 | 8.96 / 1 |
| 15m | MEAN_REVERSION | STRICT | LONG | train | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | MEAN_REVERSION | STRICT | SHORT | train | ×1.5 | 1/1/1 | 0.0 | 0.000 | -0.485 | INSUFFICIENT_EVIDENCE | -238.09 | 238.09 / 0.485 | 8.96 / 1 |
| 15m | LIQUIDITY_SWEEP | BASE | LONG | train | ×1.5 | 26/26/26 | 38.5 | 0.430 | -0.192 | INSUFFICIENT_EVIDENCE | -5827.97 | 7369.35 / 9.201 | 107.29 / 19 |
| 15m | LIQUIDITY_SWEEP | BASE | SHORT | train | ×1.5 | 25/24/24 | 33.3 | 0.693 | -0.261 | INSUFFICIENT_EVIDENCE | -2668.80 | 7657.10 / 13.438 | 67.58 / 16 |
| 15m | LIQUIDITY_SWEEP | STRICT | LONG | train | ×1.5 | 24/24/24 | 41.7 | 0.491 | -0.104 | INSUFFICIENT_EVIDENCE | -4551.16 | 6092.54 / 6.699 | 107.29 / 19 |
| 15m | LIQUIDITY_SWEEP | STRICT | SHORT | train | ×1.5 | 23/22/22 | 31.8 | 0.605 | -0.308 | INSUFFICIENT_EVIDENCE | -3219.34 | 7112.76 / 12.214 | 62.26 / 15 |
| 15m | RANGE_REJECTION | BASE | LONG | train | ×1.5 | 1/1/1 | 0.0 | 0.000 | -1.410 | INSUFFICIENT_EVIDENCE | -308.89 | 308.89 / 1.410 | 0.00 / 0 |
| 15m | RANGE_REJECTION | BASE | SHORT | train | ×1.5 | 2/1/1 | 100.0 | — | 2.315 | INSUFFICIENT_EVIDENCE | 840.30 | 0.00 / 0.000 | 0.00 / 0 |
| 15m | RANGE_REJECTION | STRICT | LONG | train | ×1.5 | 1/1/1 | 0.0 | 0.000 | -1.410 | INSUFFICIENT_EVIDENCE | -308.89 | 308.89 / 1.410 | 0.00 / 0 |
| 15m | RANGE_REJECTION | STRICT | SHORT | train | ×1.5 | 1/1/1 | 100.0 | — | 2.312 | INSUFFICIENT_EVIDENCE | 837.80 | 0.00 / 0.000 | 0.00 / 0 |
| 15m | TREND_PULLBACK | BASE | LONG | train | ×2 | 34/30/30 | 23.3 | 0.184 | -0.838 | [-1.201; -0.450] | -11754.70 | 12758.94 / 27.001 | 149.93 / 22 |
| 15m | TREND_PULLBACK | BASE | SHORT | train | ×2 | 54/51/51 | 19.6 | 0.377 | -0.746 | [-1.046; -0.454] | -16346.57 | 16346.57 / 38.023 | 238.51 / 36 |
| 15m | TREND_PULLBACK | STRICT | LONG | train | ×2 | 5/5/5 | 40.0 | 0.257 | -0.451 | INSUFFICIENT_EVIDENCE | -1058.97 | 1240.09 / 3.175 | 33.73 / 7 |
| 15m | TREND_PULLBACK | STRICT | SHORT | train | ×2 | 10/10/10 | 20.0 | 0.253 | -0.690 | INSUFFICIENT_EVIDENCE | -3311.87 | 3311.87 / 7.125 | 40.31 / 7 |
| 15m | BREAKOUT_RETEST | BASE | LONG | train | ×2 | 26/22/22 | 31.8 | 0.637 | -0.279 | INSUFFICIENT_EVIDENCE | -3166.53 | 6163.75 / 9.809 | 87.29 / 17 |
| 15m | BREAKOUT_RETEST | BASE | SHORT | train | ×2 | 60/45/45 | 33.3 | 0.630 | -0.252 | [-0.615; 0.035] | -7345.18 | 9217.70 / 14.344 | 188.48 / 33 |
| 15m | BREAKOUT_RETEST | STRICT | LONG | train | ×2 | 24/21/21 | 33.3 | 0.683 | -0.282 | INSUFFICIENT_EVIDENCE | -2577.27 | 5574.48 / 9.595 | 81.41 / 16 |
| 15m | BREAKOUT_RETEST | STRICT | SHORT | train | ×2 | 47/35/35 | 37.1 | 0.720 | -0.186 | [-0.668; 0.181] | -4194.27 | 5093.79 / 7.871 | 147.87 / 26 |
| 15m | MOMENTUM_EXPANSION | BASE | LONG | train | ×2 | 95/85/85 | 21.2 | 0.257 | -0.779 | [-1.029; -0.544] | -25896.10 | 25982.92 / 66.542 | 279.19 / 38 |
| 15m | MOMENTUM_EXPANSION | BASE | SHORT | train | ×2 | 137/123/123 | 24.4 | 0.327 | -0.727 | [-0.896; -0.559] | -33641.80 | 33641.80 / 89.370 | 290.92 / 48 |
| 15m | MOMENTUM_EXPANSION | STRICT | LONG | train | ×2 | 74/70/70 | 22.9 | 0.257 | -0.757 | [-1.024; -0.465] | -21082.27 | 21169.10 / 53.289 | 234.80 / 32 |
| 15m | MOMENTUM_EXPANSION | STRICT | SHORT | train | ×2 | 96/89/89 | 24.7 | 0.313 | -0.724 | [-0.970; -0.474] | -23182.90 | 23182.90 / 64.397 | 224.57 / 37 |
| 15m | MEAN_REVERSION | BASE | LONG | train | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | MEAN_REVERSION | BASE | SHORT | train | ×2 | 1/1/1 | 0.0 | 0.000 | -0.743 | INSUFFICIENT_EVIDENCE | -354.55 | 354.55 / 0.743 | 11.95 / 1 |
| 15m | MEAN_REVERSION | STRICT | LONG | train | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | MEAN_REVERSION | STRICT | SHORT | train | ×2 | 1/1/1 | 0.0 | 0.000 | -0.685 | INSUFFICIENT_EVIDENCE | -336.11 | 336.11 / 0.685 | 11.95 / 1 |
| 15m | LIQUIDITY_SWEEP | BASE | LONG | train | ×2 | 26/26/26 | 30.8 | 0.347 | -0.266 | INSUFFICIENT_EVIDENCE | -7309.88 | 8626.38 / 10.644 | 143.06 / 19 |
| 15m | LIQUIDITY_SWEEP | BASE | SHORT | train | ×2 | 25/24/24 | 33.3 | 0.603 | -0.337 | INSUFFICIENT_EVIDENCE | -3730.93 | 8349.01 / 14.741 | 90.10 / 16 |
| 15m | LIQUIDITY_SWEEP | STRICT | LONG | train | ×2 | 24/24/24 | 33.3 | 0.395 | -0.177 | INSUFFICIENT_EVIDENCE | -5945.80 | 7262.30 / 7.974 | 143.06 / 19 |
| 15m | LIQUIDITY_SWEEP | STRICT | SHORT | train | ×2 | 23/22/22 | 31.8 | 0.525 | -0.384 | INSUFFICIENT_EVIDENCE | -4192.01 | 7771.48 / 13.442 | 83.01 / 15 |
| 15m | RANGE_REJECTION | BASE | LONG | train | ×2 | 1/1/1 | 0.0 | 0.000 | -1.547 | INSUFFICIENT_EVIDENCE | -338.86 | 338.86 / 1.547 | 0.00 / 0 |
| 15m | RANGE_REJECTION | BASE | SHORT | train | ×2 | 2/1/1 | 100.0 | — | 2.077 | INSUFFICIENT_EVIDENCE | 753.82 | 0.00 / 0.000 | 0.00 / 0 |
| 15m | RANGE_REJECTION | STRICT | LONG | train | ×2 | 1/1/1 | 0.0 | 0.000 | -1.547 | INSUFFICIENT_EVIDENCE | -338.86 | 338.86 / 1.547 | 0.00 / 0 |
| 15m | RANGE_REJECTION | STRICT | SHORT | train | ×2 | 1/1/1 | 100.0 | — | 2.074 | INSUFFICIENT_EVIDENCE | 751.33 | 0.00 / 0.000 | 0.00 / 0 |
| 15m | TREND_PULLBACK | BASE | LONG | validation | ×1 | 21/20/20 | 20.0 | 0.486 | -0.521 | INSUFFICIENT_EVIDENCE | -6027.91 | 7256.10 / 10.819 | 86.51 / 15 |
| 15m | TREND_PULLBACK | BASE | SHORT | validation | ×1 | 23/20/20 | 25.0 | 0.306 | -0.629 | INSUFFICIENT_EVIDENCE | -9148.42 | 9148.42 / 12.579 | 93.59 / 16 |
| 15m | TREND_PULLBACK | STRICT | LONG | validation | ×1 | 6/6/6 | 16.7 | 0.486 | -0.596 | INSUFFICIENT_EVIDENCE | -2065.71 | 3182.88 / 4.639 | 23.53 / 4 |
| 15m | TREND_PULLBACK | STRICT | SHORT | validation | ×1 | 5/5/5 | 20.0 | 0.051 | -0.966 | INSUFFICIENT_EVIDENCE | -3658.73 | 3658.73 / 4.829 | 26.20 / 5 |
| 15m | BREAKOUT_RETEST | BASE | LONG | validation | ×1 | 11/10/10 | 20.0 | 0.013 | -0.801 | INSUFFICIENT_EVIDENCE | -10113.78 | 10193.42 / 8.116 | 29.57 / 6 |
| 15m | BREAKOUT_RETEST | BASE | SHORT | validation | ×1 | 12/10/10 | 40.0 | 1.101 | 0.040 | INSUFFICIENT_EVIDENCE | 574.16 | 2935.92 / 2.565 | 36.57 / 7 |
| 15m | BREAKOUT_RETEST | STRICT | LONG | validation | ×1 | 8/8/8 | 25.0 | 0.018 | -0.710 | INSUFFICIENT_EVIDENCE | -7277.73 | 7357.37 / 5.788 | 23.32 / 5 |
| 15m | BREAKOUT_RETEST | STRICT | SHORT | validation | ×1 | 10/9/9 | 44.4 | 1.292 | 0.087 | INSUFFICIENT_EVIDENCE | 1567.13 | 2935.92 / 2.345 | 31.93 / 6 |
| 15m | MOMENTUM_EXPANSION | BASE | LONG | validation | ×1 | 38/34/34 | 32.4 | 0.587 | -0.276 | [-0.609; 0.095] | -5317.32 | 8218.44 / 14.933 | 69.11 / 11 |
| 15m | MOMENTUM_EXPANSION | BASE | SHORT | validation | ×1 | 47/43/43 | 23.3 | 0.493 | -0.456 | [-0.828; -0.084] | -12424.26 | 13003.73 / 20.699 | 99.76 / 17 |
| 15m | MOMENTUM_EXPANSION | STRICT | LONG | validation | ×1 | 24/22/22 | 45.5 | 0.959 | 0.005 | INSUFFICIENT_EVIDENCE | -273.06 | 3270.47 / 5.710 | 55.75 / 9 |
| 15m | MOMENTUM_EXPANSION | STRICT | SHORT | validation | ×1 | 26/23/23 | 26.1 | 0.693 | -0.195 | INSUFFICIENT_EVIDENCE | -3456.73 | 4951.15 / 8.274 | 62.01 / 11 |
| 15m | MEAN_REVERSION | BASE | LONG | validation | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | MEAN_REVERSION | BASE | SHORT | validation | ×1 | 1/1/1 | 0.0 | 0.000 | -0.366 | INSUFFICIENT_EVIDENCE | -261.92 | 261.92 / 0.366 | 5.72 / 1 |
| 15m | MEAN_REVERSION | STRICT | LONG | validation | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | MEAN_REVERSION | STRICT | SHORT | validation | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | LIQUIDITY_SWEEP | BASE | LONG | validation | ×1 | 6/6/6 | 50.0 | 0.710 | -0.180 | INSUFFICIENT_EVIDENCE | -1206.70 | 2601.93 / 2.342 | 22.91 / 4 |
| 15m | LIQUIDITY_SWEEP | BASE | SHORT | validation | ×1 | 3/3/3 | 33.3 | 0.176 | -0.696 | INSUFFICIENT_EVIDENCE | -2118.41 | 2571.50 / 2.371 | 19.87 / 3 |
| 15m | LIQUIDITY_SWEEP | STRICT | LONG | validation | ×1 | 6/6/6 | 50.0 | 0.710 | -0.180 | INSUFFICIENT_EVIDENCE | -1206.70 | 2601.93 / 2.342 | 22.91 / 4 |
| 15m | LIQUIDITY_SWEEP | STRICT | SHORT | validation | ×1 | 3/3/3 | 33.3 | 0.176 | -0.696 | INSUFFICIENT_EVIDENCE | -2118.41 | 2571.50 / 2.371 | 19.87 / 3 |
| 15m | RANGE_REJECTION | BASE | LONG | validation | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | RANGE_REJECTION | BASE | SHORT | validation | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | RANGE_REJECTION | STRICT | LONG | validation | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | RANGE_REJECTION | STRICT | SHORT | validation | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | TREND_PULLBACK | BASE | LONG | validation | ×1.5 | 21/20/20 | 20.0 | 0.402 | -0.671 | INSUFFICIENT_EVIDENCE | -7928.68 | 8430.06 / 13.426 | 129.77 / 15 |
| 15m | TREND_PULLBACK | BASE | SHORT | validation | ×1.5 | 23/20/20 | 25.0 | 0.241 | -0.760 | INSUFFICIENT_EVIDENCE | -11048.20 | 11048.20 / 15.200 | 140.38 / 16 |
| 15m | TREND_PULLBACK | STRICT | LONG | validation | ×1.5 | 6/6/6 | 16.7 | 0.413 | -0.732 | INSUFFICIENT_EVIDENCE | -2647.60 | 3596.17 / 5.238 | 35.29 / 4 |
| 15m | TREND_PULLBACK | STRICT | SHORT | validation | ×1.5 | 5/5/5 | 20.0 | 0.022 | -1.088 | INSUFFICIENT_EVIDENCE | -4086.02 | 4086.02 / 5.441 | 39.30 / 5 |
| 15m | BREAKOUT_RETEST | BASE | LONG | validation | ×1.5 | 11/10/10 | 10.0 | 0.003 | -0.870 | INSUFFICIENT_EVIDENCE | -10930.73 | 10964.24 / 8.744 | 44.35 / 6 |
| 15m | BREAKOUT_RETEST | BASE | SHORT | validation | ×1.5 | 12/10/10 | 40.0 | 0.955 | -0.032 | INSUFFICIENT_EVIDENCE | -283.19 | 3315.63 / 3.063 | 54.85 / 7 |
| 15m | BREAKOUT_RETEST | STRICT | LONG | validation | ×1.5 | 8/8/8 | 12.5 | 0.004 | -0.776 | INSUFFICIENT_EVIDENCE | -7895.46 | 7928.97 / 6.252 | 34.98 / 5 |
| 15m | BREAKOUT_RETEST | STRICT | SHORT | validation | ×1.5 | 10/9/9 | 44.4 | 1.136 | 0.016 | INSUFFICIENT_EVIDENCE | 788.46 | 3151.80 / 2.653 | 47.89 / 6 |
| 15m | MOMENTUM_EXPANSION | BASE | LONG | validation | ×1.5 | 38/34/34 | 29.4 | 0.441 | -0.436 | [-0.795; -0.033] | -8387.76 | 10573.84 / 19.048 | 103.66 / 11 |
| 15m | MOMENTUM_EXPANSION | BASE | SHORT | validation | ×1.5 | 47/43/43 | 23.3 | 0.407 | -0.600 | [-0.994; -0.208] | -16264.11 | 16554.43 / 26.034 | 149.65 / 17 |
| 15m | MOMENTUM_EXPANSION | STRICT | LONG | validation | ×1.5 | 24/22/22 | 40.9 | 0.706 | -0.152 | INSUFFICIENT_EVIDENCE | -2291.60 | 4477.68 / 7.554 | 83.63 / 9 |
| 15m | MOMENTUM_EXPANSION | STRICT | SHORT | validation | ×1.5 | 26/23/23 | 26.1 | 0.571 | -0.342 | INSUFFICIENT_EVIDENCE | -5503.12 | 6825.68 / 11.133 | 93.02 / 11 |
| 15m | MEAN_REVERSION | BASE | LONG | validation | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | MEAN_REVERSION | BASE | SHORT | validation | ×1.5 | 1/1/1 | 0.0 | 0.000 | -0.498 | INSUFFICIENT_EVIDENCE | -356.43 | 356.43 / 0.498 | 8.59 / 1 |
| 15m | MEAN_REVERSION | STRICT | LONG | validation | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | MEAN_REVERSION | STRICT | SHORT | validation | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | LIQUIDITY_SWEEP | BASE | LONG | validation | ×1.5 | 6/6/6 | 50.0 | 0.604 | -0.258 | INSUFFICIENT_EVIDENCE | -1771.99 | 2789.93 / 2.513 | 34.37 / 4 |
| 15m | LIQUIDITY_SWEEP | BASE | SHORT | validation | ×1.5 | 3/3/3 | 33.3 | 0.121 | -0.782 | INSUFFICIENT_EVIDENCE | -2437.37 | 2772.55 / 2.556 | 29.81 / 3 |
| 15m | LIQUIDITY_SWEEP | STRICT | LONG | validation | ×1.5 | 6/6/6 | 50.0 | 0.604 | -0.258 | INSUFFICIENT_EVIDENCE | -1771.99 | 2789.93 / 2.513 | 34.37 / 4 |
| 15m | LIQUIDITY_SWEEP | STRICT | SHORT | validation | ×1.5 | 3/3/3 | 33.3 | 0.121 | -0.782 | INSUFFICIENT_EVIDENCE | -2437.37 | 2772.55 / 2.556 | 29.81 / 3 |
| 15m | RANGE_REJECTION | BASE | LONG | validation | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | RANGE_REJECTION | BASE | SHORT | validation | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | RANGE_REJECTION | STRICT | LONG | validation | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | RANGE_REJECTION | STRICT | SHORT | validation | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | TREND_PULLBACK | BASE | LONG | validation | ×2 | 21/20/20 | 20.0 | 0.334 | -0.822 | INSUFFICIENT_EVIDENCE | -9829.52 | 9882.06 / 16.437 | 173.03 / 15 |
| 15m | TREND_PULLBACK | BASE | SHORT | validation | ×2 | 23/20/20 | 20.0 | 0.187 | -0.891 | INSUFFICIENT_EVIDENCE | -12947.92 | 12947.92 / 17.821 | 187.18 / 16 |
| 15m | TREND_PULLBACK | STRICT | LONG | validation | ×2 | 6/6/6 | 16.7 | 0.354 | -0.869 | INSUFFICIENT_EVIDENCE | -3229.52 | 4009.48 / 5.837 | 47.05 / 4 |
| 15m | TREND_PULLBACK | STRICT | SHORT | validation | ×2 | 5/5/5 | 0.0 | 0.000 | -1.211 | INSUFFICIENT_EVIDENCE | -4513.30 | 4513.30 / 6.054 | 52.40 / 5 |
| 15m | BREAKOUT_RETEST | BASE | LONG | validation | ×2 | 11/10/10 | 0.0 | 0.000 | -0.939 | INSUFFICIENT_EVIDENCE | -11747.71 | 11747.71 / 9.390 | 59.14 / 6 |
| 15m | BREAKOUT_RETEST | BASE | SHORT | validation | ×2 | 12/10/10 | 40.0 | 0.831 | -0.105 | INSUFFICIENT_EVIDENCE | -1140.52 | 3797.95 / 3.561 | 73.14 / 7 |
| 15m | BREAKOUT_RETEST | STRICT | LONG | validation | ×2 | 8/8/8 | 0.0 | 0.000 | -0.842 | INSUFFICIENT_EVIDENCE | -8513.21 | 8513.21 / 6.733 | 46.64 / 5 |
| 15m | BREAKOUT_RETEST | STRICT | SHORT | validation | ×2 | 10/9/9 | 44.4 | 1.002 | -0.054 | INSUFFICIENT_EVIDENCE | 9.81 | 3367.68 / 3.078 | 63.86 / 6 |
| 15m | MOMENTUM_EXPANSION | BASE | LONG | validation | ×2 | 38/34/34 | 26.5 | 0.336 | -0.596 | [-0.948; -0.213] | -11458.28 | 13102.94 / 23.303 | 138.21 / 11 |
| 15m | MOMENTUM_EXPANSION | BASE | SHORT | validation | ×2 | 47/43/43 | 20.9 | 0.338 | -0.744 | [-1.180; -0.385] | -20103.80 | 20104.99 / 32.000 | 199.53 / 17 |
| 15m | MOMENTUM_EXPANSION | STRICT | LONG | validation | ×2 | 24/22/22 | 36.4 | 0.525 | -0.308 | INSUFFICIENT_EVIDENCE | -4310.19 | 5954.85 / 9.806 | 111.50 / 9 |
| 15m | MOMENTUM_EXPANSION | STRICT | SHORT | validation | ×2 | 26/23/23 | 26.1 | 0.475 | -0.489 | INSUFFICIENT_EVIDENCE | -7549.43 | 8700.15 / 13.992 | 124.03 / 11 |
| 15m | MEAN_REVERSION | BASE | LONG | validation | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | MEAN_REVERSION | BASE | SHORT | validation | ×2 | 1/1/1 | 0.0 | 0.000 | -0.631 | INSUFFICIENT_EVIDENCE | -450.93 | 450.93 / 0.631 | 11.45 / 1 |
| 15m | MEAN_REVERSION | STRICT | LONG | validation | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | MEAN_REVERSION | STRICT | SHORT | validation | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | LIQUIDITY_SWEEP | BASE | LONG | validation | ×2 | 6/6/6 | 50.0 | 0.510 | -0.336 | INSUFFICIENT_EVIDENCE | -2337.30 | 2977.95 / 2.684 | 45.83 / 4 |
| 15m | LIQUIDITY_SWEEP | BASE | SHORT | validation | ×2 | 3/3/3 | 33.3 | 0.073 | -0.868 | INSUFFICIENT_EVIDENCE | -2756.31 | 2973.59 / 2.741 | 39.74 / 3 |
| 15m | LIQUIDITY_SWEEP | STRICT | LONG | validation | ×2 | 6/6/6 | 50.0 | 0.510 | -0.336 | INSUFFICIENT_EVIDENCE | -2337.30 | 2977.95 / 2.684 | 45.83 / 4 |
| 15m | LIQUIDITY_SWEEP | STRICT | SHORT | validation | ×2 | 3/3/3 | 33.3 | 0.073 | -0.868 | INSUFFICIENT_EVIDENCE | -2756.31 | 2973.59 / 2.741 | 39.74 / 3 |
| 15m | RANGE_REJECTION | BASE | LONG | validation | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | RANGE_REJECTION | BASE | SHORT | validation | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | RANGE_REJECTION | STRICT | LONG | validation | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | RANGE_REJECTION | STRICT | SHORT | validation | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | TREND_PULLBACK | BASE | LONG | test | ×1 | 15/15/15 | 33.3 | 0.437 | -0.363 | INSUFFICIENT_EVIDENCE | -7783.55 | 11411.94 / 9.968 | 70.84 / 8 |
| 15m | TREND_PULLBACK | BASE | SHORT | test | ×1 | 12/11/11 | 9.1 | 0.249 | -0.788 | INSUFFICIENT_EVIDENCE | -9829.65 | 9829.65 / 8.670 | 63.37 / 7 |
| 15m | TREND_PULLBACK | STRICT | LONG | test | ×1 | 2/2/2 | 0.0 | 0.000 | -1.309 | INSUFFICIENT_EVIDENCE | -2305.53 | 2305.53 / 2.617 | 0.00 / 0 |
| 15m | TREND_PULLBACK | STRICT | SHORT | test | ×1 | 4/4/4 | 0.0 | 0.000 | -1.337 | INSUFFICIENT_EVIDENCE | -4733.99 | 4733.99 / 5.349 | 28.31 / 3 |
| 15m | BREAKOUT_RETEST | BASE | LONG | test | ×1 | 7/6/6 | 50.0 | 8.476 | 0.563 | INSUFFICIENT_EVIDENCE | 6003.83 | 501.21 / 0.332 | 42.57 / 5 |
| 15m | BREAKOUT_RETEST | BASE | SHORT | test | ×1 | 13/12/12 | 50.0 | 1.422 | 0.114 | INSUFFICIENT_EVIDENCE | 3815.39 | 3291.95 / 2.183 | 70.97 / 8 |
| 15m | BREAKOUT_RETEST | STRICT | LONG | test | ×1 | 6/5/5 | 40.0 | 7.855 | 0.643 | INSUFFICIENT_EVIDENCE | 5504.88 | 501.21 / 0.332 | 32.29 / 4 |
| 15m | BREAKOUT_RETEST | STRICT | SHORT | test | ×1 | 13/12/12 | 50.0 | 1.422 | 0.114 | INSUFFICIENT_EVIDENCE | 3815.39 | 3291.95 / 2.183 | 70.97 / 8 |
| 15m | MOMENTUM_EXPANSION | BASE | LONG | test | ×1 | 38/30/30 | 40.0 | 0.625 | -0.225 | [-0.855; 0.393] | -8244.67 | 15493.32 / 15.524 | 146.67 / 16 |
| 15m | MOMENTUM_EXPANSION | BASE | SHORT | test | ×1 | 42/35/35 | 28.6 | 0.602 | -0.388 | [-0.829; 0.143] | -10981.10 | 10981.10 / 13.592 | 122.02 / 14 |
| 15m | MOMENTUM_EXPANSION | STRICT | LONG | test | ×1 | 28/22/22 | 45.5 | 0.881 | -0.079 | INSUFFICIENT_EVIDENCE | -1513.66 | 6593.95 / 8.305 | 117.70 / 13 |
| 15m | MOMENTUM_EXPANSION | STRICT | SHORT | test | ×1 | 30/26/26 | 26.9 | 0.551 | -0.478 | INSUFFICIENT_EVIDENCE | -10457.55 | 10457.55 / 12.423 | 95.12 / 11 |
| 15m | MEAN_REVERSION | BASE | LONG | test | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | MEAN_REVERSION | BASE | SHORT | test | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | MEAN_REVERSION | STRICT | LONG | test | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | MEAN_REVERSION | STRICT | SHORT | test | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | LIQUIDITY_SWEEP | BASE | LONG | test | ×1 | 10/10/10 | 40.0 | 0.870 | -0.088 | INSUFFICIENT_EVIDENCE | -1210.24 | 6076.68 / 3.528 | 55.46 / 6 |
| 15m | LIQUIDITY_SWEEP | BASE | SHORT | test | ×1 | 1/1/1 | 0.0 | 0.000 | -0.576 | INSUFFICIENT_EVIDENCE | -1922.97 | 1922.97 / 0.576 | 7.85 / 1 |
| 15m | LIQUIDITY_SWEEP | STRICT | LONG | test | ×1 | 9/9/9 | 44.4 | 1.101 | 0.032 | INSUFFICIENT_EVIDENCE | 741.99 | 4124.45 / 2.361 | 55.46 / 6 |
| 15m | LIQUIDITY_SWEEP | STRICT | SHORT | test | ×1 | 1/1/1 | 0.0 | 0.000 | -0.576 | INSUFFICIENT_EVIDENCE | -1922.97 | 1922.97 / 0.576 | 7.85 / 1 |
| 15m | RANGE_REJECTION | BASE | LONG | test | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | RANGE_REJECTION | BASE | SHORT | test | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | RANGE_REJECTION | STRICT | LONG | test | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | RANGE_REJECTION | STRICT | SHORT | test | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | TREND_PULLBACK | BASE | LONG | test | ×1.5 | 15/15/15 | 33.3 | 0.349 | -0.500 | INSUFFICIENT_EVIDENCE | -9860.18 | 13033.88 / 11.527 | 106.26 / 8 |
| 15m | TREND_PULLBACK | BASE | SHORT | test | ×1.5 | 12/11/11 | 9.1 | 0.215 | -0.906 | INSUFFICIENT_EVIDENCE | -11394.87 | 11394.87 / 9.963 | 95.05 / 7 |
| 15m | TREND_PULLBACK | STRICT | LONG | test | ×1.5 | 2/2/2 | 0.0 | 0.000 | -1.463 | INSUFFICIENT_EVIDENCE | -2573.71 | 2573.71 / 2.926 | 0.00 / 0 |
| 15m | TREND_PULLBACK | STRICT | SHORT | test | ×1.5 | 4/4/4 | 0.0 | 0.000 | -1.506 | INSUFFICIENT_EVIDENCE | -5329.07 | 5329.07 / 6.023 | 42.46 / 3 |
| 15m | BREAKOUT_RETEST | BASE | LONG | test | ×1.5 | 7/6/6 | 50.0 | 5.353 | 0.492 | INSUFFICIENT_EVIDENCE | 5189.65 | 623.26 / 0.413 | 63.85 / 5 |
| 15m | BREAKOUT_RETEST | BASE | SHORT | test | ×1.5 | 13/12/12 | 50.0 | 1.217 | 0.029 | INSUFFICIENT_EVIDENCE | 2138.01 | 3683.68 / 2.443 | 106.46 / 8 |
| 15m | BREAKOUT_RETEST | STRICT | LONG | test | ×1.5 | 6/5/5 | 40.0 | 5.076 | 0.569 | INSUFFICIENT_EVIDENCE | 4859.39 | 623.26 / 0.413 | 48.44 / 4 |
| 15m | BREAKOUT_RETEST | STRICT | SHORT | test | ×1.5 | 13/12/12 | 50.0 | 1.217 | 0.029 | INSUFFICIENT_EVIDENCE | 2138.01 | 3683.68 / 2.443 | 106.46 / 8 |
| 15m | MOMENTUM_EXPANSION | BASE | LONG | test | ×1.5 | 38/30/30 | 30.0 | 0.496 | -0.379 | [-1.043; 0.249] | -12575.17 | 19330.38 / 19.544 | 220.01 / 16 |
| 15m | MOMENTUM_EXPANSION | BASE | SHORT | test | ×1.5 | 42/35/35 | 28.6 | 0.490 | -0.533 | [-0.918; 0.002] | -15820.50 | 15820.50 / 18.672 | 183.03 / 14 |
| 15m | MOMENTUM_EXPANSION | STRICT | LONG | test | ×1.5 | 28/22/22 | 31.8 | 0.685 | -0.240 | INSUFFICIENT_EVIDENCE | -4630.67 | 9352.57 / 11.381 | 176.55 / 13 |
| 15m | MOMENTUM_EXPANSION | STRICT | SHORT | test | ×1.5 | 30/26/26 | 26.9 | 0.458 | -0.620 | INSUFFICIENT_EVIDENCE | -14006.83 | 14006.83 / 16.120 | 142.68 / 11 |
| 15m | MEAN_REVERSION | BASE | LONG | test | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | MEAN_REVERSION | BASE | SHORT | test | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | MEAN_REVERSION | STRICT | LONG | test | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | MEAN_REVERSION | STRICT | SHORT | test | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | LIQUIDITY_SWEEP | BASE | LONG | test | ×1.5 | 10/10/10 | 40.0 | 0.734 | -0.164 | INSUFFICIENT_EVIDENCE | -2703.27 | 6971.99 / 3.853 | 83.19 / 6 |
| 15m | LIQUIDITY_SWEEP | BASE | SHORT | test | ×1.5 | 1/1/1 | 0.0 | 0.000 | -0.615 | INSUFFICIENT_EVIDENCE | -2053.21 | 2053.21 / 0.615 | 11.77 / 1 |
| 15m | LIQUIDITY_SWEEP | STRICT | LONG | test | ×1.5 | 9/9/9 | 44.4 | 0.924 | -0.043 | INSUFFICIENT_EVIDENCE | -611.56 | 4880.28 / 2.603 | 83.19 / 6 |
| 15m | LIQUIDITY_SWEEP | STRICT | SHORT | test | ×1.5 | 1/1/1 | 0.0 | 0.000 | -0.615 | INSUFFICIENT_EVIDENCE | -2053.21 | 2053.21 / 0.615 | 11.77 / 1 |
| 15m | RANGE_REJECTION | BASE | LONG | test | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | RANGE_REJECTION | BASE | SHORT | test | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | RANGE_REJECTION | STRICT | LONG | test | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | RANGE_REJECTION | STRICT | SHORT | test | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | TREND_PULLBACK | BASE | LONG | test | ×2 | 15/15/15 | 26.7 | 0.277 | -0.636 | INSUFFICIENT_EVIDENCE | -11936.89 | 14688.53 / 13.112 | 141.68 / 8 |
| 15m | TREND_PULLBACK | BASE | SHORT | test | ×2 | 12/11/11 | 9.1 | 0.188 | -1.023 | INSUFFICIENT_EVIDENCE | -12960.03 | 12960.03 / 11.256 | 126.73 / 7 |
| 15m | TREND_PULLBACK | STRICT | LONG | test | ×2 | 2/2/2 | 0.0 | 0.000 | -1.617 | INSUFFICIENT_EVIDENCE | -2841.91 | 2841.91 / 3.234 | 0.00 / 0 |
| 15m | TREND_PULLBACK | STRICT | SHORT | test | ×2 | 4/4/4 | 0.0 | 0.000 | -1.674 | INSUFFICIENT_EVIDENCE | -5924.12 | 5924.12 / 6.697 | 56.61 / 3 |
| 15m | BREAKOUT_RETEST | BASE | LONG | test | ×2 | 7/6/6 | 50.0 | 3.767 | 0.421 | INSUFFICIENT_EVIDENCE | 4375.47 | 836.14 / 0.493 | 85.13 / 5 |
| 15m | BREAKOUT_RETEST | BASE | SHORT | test | ×2 | 13/12/12 | 41.7 | 1.043 | -0.055 | INSUFFICIENT_EVIDENCE | 460.67 | 4075.40 / 2.703 | 141.94 / 8 |
| 15m | BREAKOUT_RETEST | STRICT | LONG | test | ×2 | 6/5/5 | 40.0 | 3.665 | 0.494 | INSUFFICIENT_EVIDENCE | 4213.89 | 836.14 / 0.493 | 64.58 / 4 |
| 15m | BREAKOUT_RETEST | STRICT | SHORT | test | ×2 | 13/12/12 | 41.7 | 1.043 | -0.055 | INSUFFICIENT_EVIDENCE | 460.67 | 4075.40 / 2.703 | 141.94 / 8 |
| 15m | MOMENTUM_EXPANSION | BASE | LONG | test | ×2 | 38/30/30 | 26.7 | 0.400 | -0.533 | [-1.221; 0.063] | -16905.81 | 23167.57 / 23.564 | 293.35 / 16 |
| 15m | MOMENTUM_EXPANSION | BASE | SHORT | test | ×2 | 42/35/35 | 28.6 | 0.399 | -0.679 | [-1.083; -0.174] | -20659.73 | 20659.73 / 23.752 | 244.04 / 14 |
| 15m | MOMENTUM_EXPANSION | STRICT | LONG | test | ×2 | 28/22/22 | 27.3 | 0.544 | -0.401 | INSUFFICIENT_EVIDENCE | -7747.77 | 12111.26 / 14.456 | 235.40 / 13 |
| 15m | MOMENTUM_EXPANSION | STRICT | SHORT | test | ×2 | 30/26/26 | 26.9 | 0.381 | -0.762 | INSUFFICIENT_EVIDENCE | -17555.97 | 17555.97 / 19.816 | 190.23 / 11 |
| 15m | MEAN_REVERSION | BASE | LONG | test | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | MEAN_REVERSION | BASE | SHORT | test | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | MEAN_REVERSION | STRICT | LONG | test | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | MEAN_REVERSION | STRICT | SHORT | test | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | LIQUIDITY_SWEEP | BASE | LONG | test | ×2 | 10/10/10 | 40.0 | 0.620 | -0.240 | INSUFFICIENT_EVIDENCE | -4196.32 | 7867.32 / 4.291 | 110.91 / 6 |
| 15m | LIQUIDITY_SWEEP | BASE | SHORT | test | ×2 | 1/1/1 | 0.0 | 0.000 | -0.654 | INSUFFICIENT_EVIDENCE | -2183.45 | 2183.45 / 0.654 | 15.69 / 1 |
| 15m | LIQUIDITY_SWEEP | STRICT | LONG | test | ×2 | 9/9/9 | 44.4 | 0.777 | -0.119 | INSUFFICIENT_EVIDENCE | -1965.14 | 5636.13 / 2.958 | 110.91 / 6 |
| 15m | LIQUIDITY_SWEEP | STRICT | SHORT | test | ×2 | 1/1/1 | 0.0 | 0.000 | -0.654 | INSUFFICIENT_EVIDENCE | -2183.45 | 2183.45 / 0.654 | 15.69 / 1 |
| 15m | RANGE_REJECTION | BASE | LONG | test | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | RANGE_REJECTION | BASE | SHORT | test | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | RANGE_REJECTION | STRICT | LONG | test | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | RANGE_REJECTION | STRICT | SHORT | test | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | TREND_PULLBACK | BASE | LONG | final | ×1 | 7/7/7 | 28.6 | 0.305 | -0.456 | INSUFFICIENT_EVIDENCE | -3712.30 | 4167.79 / 3.818 | 16.02 / 3 |
| 15m | TREND_PULLBACK | BASE | SHORT | final | ×1 | 21/18/18 | 50.0 | 1.243 | 0.084 | INSUFFICIENT_EVIDENCE | 2268.36 | 4948.09 / 3.736 | 137.80 / 20 |
| 15m | TREND_PULLBACK | STRICT | LONG | final | ×1 | 1/1/1 | 0.0 | 0.000 | -1.352 | INSUFFICIENT_EVIDENCE | -821.33 | 821.33 / 1.352 | 6.73 / 1 |
| 15m | TREND_PULLBACK | STRICT | SHORT | final | ×1 | 4/4/4 | 25.0 | 0.794 | -0.273 | INSUFFICIENT_EVIDENCE | -574.77 | 1963.50 / 2.501 | 33.20 / 3 |
| 15m | BREAKOUT_RETEST | BASE | LONG | final | ×1 | 5/5/5 | 40.0 | 1.039 | 0.052 | INSUFFICIENT_EVIDENCE | 153.05 | 2392.77 / 1.172 | 21.04 / 3 |
| 15m | BREAKOUT_RETEST | BASE | SHORT | final | ×1 | 8/7/7 | 42.9 | 1.037 | 0.190 | INSUFFICIENT_EVIDENCE | 241.70 | 4854.94 / 1.315 | 38.28 / 5 |
| 15m | BREAKOUT_RETEST | STRICT | LONG | final | ×1 | 4/4/4 | 50.0 | 1.230 | 0.183 | INSUFFICIENT_EVIDENCE | 764.06 | 2392.77 / 1.113 | 13.98 / 2 |
| 15m | BREAKOUT_RETEST | STRICT | SHORT | final | ×1 | 7/6/6 | 33.3 | 0.512 | -0.092 | INSUFFICIENT_EVIDENCE | -3150.89 | 4854.94 / 1.362 | 31.98 / 4 |
| 15m | MOMENTUM_EXPANSION | BASE | LONG | final | ×1 | 23/19/19 | 21.1 | 0.421 | -0.464 | INSUFFICIENT_EVIDENCE | -6797.40 | 6797.40 / 9.333 | 99.44 / 13 |
| 15m | MOMENTUM_EXPANSION | BASE | SHORT | final | ×1 | 57/45/45 | 44.4 | 0.791 | -0.128 | [-0.496; 0.147] | -4740.30 | 7525.98 / 8.341 | 135.54 / 19 |
| 15m | MOMENTUM_EXPANSION | STRICT | LONG | final | ×1 | 20/17/17 | 23.5 | 0.511 | -0.365 | INSUFFICIENT_EVIDENCE | -4718.38 | 5515.13 / 8.004 | 93.39 / 12 |
| 15m | MOMENTUM_EXPANSION | STRICT | SHORT | final | ×1 | 48/39/39 | 46.2 | 0.815 | -0.128 | [-0.538; 0.227] | -3446.73 | 4780.26 / 6.725 | 101.10 / 15 |
| 15m | MEAN_REVERSION | BASE | LONG | final | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | MEAN_REVERSION | BASE | SHORT | final | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | MEAN_REVERSION | STRICT | LONG | final | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | MEAN_REVERSION | STRICT | SHORT | final | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | LIQUIDITY_SWEEP | BASE | LONG | final | ×1 | 7/7/7 | 14.3 | 0.240 | -0.598 | INSUFFICIENT_EVIDENCE | -6743.21 | 6960.89 / 4.614 | 23.04 / 2 |
| 15m | LIQUIDITY_SWEEP | BASE | SHORT | final | ×1 | 2/2/2 | 0.0 | 0.000 | -0.682 | INSUFFICIENT_EVIDENCE | -1859.17 | 1859.17 / 1.364 | 6.33 / 1 |
| 15m | LIQUIDITY_SWEEP | STRICT | LONG | final | ×1 | 6/6/6 | 16.7 | 0.292 | -0.506 | INSUFFICIENT_EVIDENCE | -5145.96 | 5363.64 / 3.465 | 23.04 / 2 |
| 15m | LIQUIDITY_SWEEP | STRICT | SHORT | final | ×1 | 2/2/2 | 0.0 | 0.000 | -0.682 | INSUFFICIENT_EVIDENCE | -1859.17 | 1859.17 / 1.364 | 6.33 / 1 |
| 15m | RANGE_REJECTION | BASE | LONG | final | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | RANGE_REJECTION | BASE | SHORT | final | ×1 | 2/1/1 | 100.0 | — | 0.367 | INSUFFICIENT_EVIDENCE | 230.05 | 0.00 / 0.000 | 7.65 / 1 |
| 15m | RANGE_REJECTION | STRICT | LONG | final | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | RANGE_REJECTION | STRICT | SHORT | final | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | TREND_PULLBACK | BASE | LONG | final | ×1.5 | 7/7/7 | 28.6 | 0.233 | -0.598 | INSUFFICIENT_EVIDENCE | -4592.45 | 4886.64 / 4.367 | 27.74 / 3 |
| 15m | TREND_PULLBACK | BASE | SHORT | final | ×1.5 | 21/18/18 | 44.4 | 0.998 | -0.053 | INSUFFICIENT_EVIDENCE | -16.13 | 6029.34 / 5.051 | 214.82 / 20 |
| 15m | TREND_PULLBACK | STRICT | LONG | final | ×1.5 | 1/1/1 | 0.0 | 0.000 | -1.528 | INSUFFICIENT_EVIDENCE | -928.20 | 928.20 / 1.528 | 10.09 / 1 |
| 15m | TREND_PULLBACK | STRICT | SHORT | final | ×1.5 | 4/4/4 | 25.0 | 0.645 | -0.421 | INSUFFICIENT_EVIDENCE | -1122.61 | 2146.42 / 2.752 | 49.80 / 3 |
| 15m | BREAKOUT_RETEST | BASE | LONG | final | ×1.5 | 5/5/5 | 40.0 | 0.895 | -0.026 | INSUFFICIENT_EVIDENCE | -452.30 | 2514.06 / 1.346 | 31.72 / 3 |
| 15m | BREAKOUT_RETEST | BASE | SHORT | final | ×1.5 | 8/7/7 | 42.9 | 0.906 | 0.119 | INSUFFICIENT_EVIDENCE | -654.88 | 5027.70 / 1.489 | 57.42 / 5 |
| 15m | BREAKOUT_RETEST | STRICT | LONG | final | ×1.5 | 4/4/4 | 50.0 | 1.077 | 0.108 | INSUFFICIENT_EVIDENCE | 274.22 | 2514.06 / 1.169 | 21.14 / 2 |
| 15m | BREAKOUT_RETEST | STRICT | SHORT | final | ×1.5 | 7/6/6 | 33.3 | 0.434 | -0.166 | INSUFFICIENT_EVIDENCE | -3945.15 | 5027.70 / 1.601 | 47.96 / 4 |
| 15m | MOMENTUM_EXPANSION | BASE | LONG | final | ×1.5 | 23/19/19 | 15.8 | 0.335 | -0.619 | INSUFFICIENT_EVIDENCE | -9081.70 | 9081.70 / 11.769 | 149.16 / 13 |
| 15m | MOMENTUM_EXPANSION | BASE | SHORT | final | ×1.5 | 57/45/45 | 37.8 | 0.604 | -0.283 | [-0.657; 0.007] | -10222.46 | 11466.49 / 13.902 | 207.36 / 19 |
| 15m | MOMENTUM_EXPANSION | STRICT | LONG | final | ×1.5 | 20/17/17 | 17.6 | 0.404 | -0.521 | INSUFFICIENT_EVIDENCE | -6765.13 | 6765.13 / 9.104 | 140.08 / 12 |
| 15m | MOMENTUM_EXPANSION | STRICT | SHORT | final | ×1.5 | 48/39/39 | 38.5 | 0.619 | -0.283 | [-0.678; 0.061] | -8131.22 | 8517.14 / 11.370 | 155.70 / 15 |
| 15m | MEAN_REVERSION | BASE | LONG | final | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | MEAN_REVERSION | BASE | SHORT | final | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | MEAN_REVERSION | STRICT | LONG | final | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | MEAN_REVERSION | STRICT | SHORT | final | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | LIQUIDITY_SWEEP | BASE | LONG | final | ×1.5 | 7/7/7 | 14.3 | 0.212 | -0.675 | INSUFFICIENT_EVIDENCE | -7520.26 | 7520.26 / 4.921 | 34.57 / 2 |
| 15m | LIQUIDITY_SWEEP | BASE | SHORT | final | ×1.5 | 2/2/2 | 0.0 | 0.000 | -0.759 | INSUFFICIENT_EVIDENCE | -2074.78 | 2074.78 / 1.519 | 9.50 / 1 |
| 15m | LIQUIDITY_SWEEP | STRICT | LONG | final | ×1.5 | 6/6/6 | 16.7 | 0.258 | -0.584 | INSUFFICIENT_EVIDENCE | -5819.59 | 5819.59 / 3.698 | 34.57 / 2 |
| 15m | LIQUIDITY_SWEEP | STRICT | SHORT | final | ×1.5 | 2/2/2 | 0.0 | 0.000 | -0.759 | INSUFFICIENT_EVIDENCE | -2074.78 | 2074.78 / 1.519 | 9.50 / 1 |
| 15m | RANGE_REJECTION | BASE | LONG | final | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | RANGE_REJECTION | BASE | SHORT | final | ×1.5 | 2/1/1 | 100.0 | — | 0.166 | INSUFFICIENT_EVIDENCE | 104.12 | 0.00 / 0.000 | 11.47 / 1 |
| 15m | RANGE_REJECTION | STRICT | LONG | final | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | RANGE_REJECTION | STRICT | SHORT | final | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | TREND_PULLBACK | BASE | LONG | final | ×2 | 7/7/7 | 28.6 | 0.176 | -0.740 | INSUFFICIENT_EVIDENCE | -5472.62 | 5639.64 / 5.281 | 39.46 / 3 |
| 15m | TREND_PULLBACK | BASE | SHORT | final | ×2 | 21/18/18 | 38.9 | 0.751 | -0.252 | INSUFFICIENT_EVIDENCE | -3151.87 | 7961.88 / 7.475 | 308.08 / 20 |
| 15m | TREND_PULLBACK | STRICT | LONG | final | ×2 | 1/1/1 | 0.0 | 0.000 | -1.704 | INSUFFICIENT_EVIDENCE | -1035.08 | 1035.08 / 1.704 | 13.45 / 1 |
| 15m | TREND_PULLBACK | STRICT | SHORT | final | ×2 | 4/4/4 | 25.0 | 0.528 | -0.569 | INSUFFICIENT_EVIDENCE | -1670.44 | 2329.34 / 3.002 | 66.40 / 3 |
| 15m | BREAKOUT_RETEST | BASE | LONG | final | ×2 | 5/5/5 | 40.0 | 0.772 | -0.103 | INSUFFICIENT_EVIDENCE | -1057.66 | 2859.47 / 1.579 | 42.41 / 3 |
| 15m | BREAKOUT_RETEST | BASE | SHORT | final | ×2 | 8/7/7 | 42.9 | 0.792 | 0.048 | INSUFFICIENT_EVIDENCE | -1551.44 | 5200.45 / 1.664 | 76.56 / 5 |
| 15m | BREAKOUT_RETEST | STRICT | LONG | final | ×2 | 4/4/4 | 50.0 | 0.943 | 0.033 | INSUFFICIENT_EVIDENCE | -215.63 | 2635.35 / 1.226 | 28.30 / 2 |
| 15m | BREAKOUT_RETEST | STRICT | SHORT | final | ×2 | 7/6/6 | 33.3 | 0.366 | -0.240 | INSUFFICIENT_EVIDENCE | -4739.39 | 5200.45 / 1.840 | 63.95 / 4 |
| 15m | MOMENTUM_EXPANSION | BASE | LONG | final | ×2 | 23/19/19 | 15.8 | 0.272 | -0.775 | INSUFFICIENT_EVIDENCE | -11366.07 | 11366.07 / 14.726 | 198.88 / 13 |
| 15m | MOMENTUM_EXPANSION | BASE | SHORT | final | ×2 | 57/45/45 | 35.6 | 0.464 | -0.438 | [-0.814; -0.139] | -15704.48 | 15911.04 / 19.893 | 279.17 / 19 |
| 15m | MOMENTUM_EXPANSION | STRICT | LONG | final | ×2 | 20/17/17 | 17.6 | 0.325 | -0.677 | INSUFFICIENT_EVIDENCE | -8811.93 | 8811.93 / 11.513 | 186.77 / 12 |
| 15m | MOMENTUM_EXPANSION | STRICT | SHORT | final | ×2 | 48/39/39 | 35.9 | 0.472 | -0.438 | [-0.864; -0.079] | -12815.58 | 13022.14 / 17.252 | 210.29 / 15 |
| 15m | MEAN_REVERSION | BASE | LONG | final | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | MEAN_REVERSION | BASE | SHORT | final | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | MEAN_REVERSION | STRICT | LONG | final | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | MEAN_REVERSION | STRICT | SHORT | final | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | LIQUIDITY_SWEEP | BASE | LONG | final | ×2 | 7/7/7 | 14.3 | 0.189 | -0.753 | INSUFFICIENT_EVIDENCE | -8297.34 | 8297.34 / 5.268 | 46.09 / 2 |
| 15m | LIQUIDITY_SWEEP | BASE | SHORT | final | ×2 | 2/2/2 | 0.0 | 0.000 | -0.837 | INSUFFICIENT_EVIDENCE | -2290.38 | 2290.38 / 1.674 | 12.67 / 1 |
| 15m | LIQUIDITY_SWEEP | STRICT | LONG | final | ×2 | 6/6/6 | 16.7 | 0.229 | -0.662 | INSUFFICIENT_EVIDENCE | -6493.25 | 6493.25 / 3.970 | 46.09 / 2 |
| 15m | LIQUIDITY_SWEEP | STRICT | SHORT | final | ×2 | 2/2/2 | 0.0 | 0.000 | -0.837 | INSUFFICIENT_EVIDENCE | -2290.38 | 2290.38 / 1.674 | 12.67 / 1 |
| 15m | RANGE_REJECTION | BASE | LONG | final | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | RANGE_REJECTION | BASE | SHORT | final | ×2 | 2/1/1 | 0.0 | 0.000 | -0.035 | INSUFFICIENT_EVIDENCE | -21.80 | 21.80 / 0.035 | 15.30 / 1 |
| 15m | RANGE_REJECTION | STRICT | LONG | final | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 15m | RANGE_REJECTION | STRICT | SHORT | final | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | TREND_PULLBACK | BASE | LONG | train | ×1 | 23/19/19 | 42.1 | 1.269 | 0.115 | INSUFFICIENT_EVIDENCE | 1779.66 | 2011.63 / 3.656 | 160.98 / 52 |
| 1h | TREND_PULLBACK | BASE | SHORT | train | ×1 | 39/34/34 | 20.6 | 0.521 | -0.480 | [-0.859; -0.100] | -9095.51 | 10625.41 / 16.314 | 286.39 / 99 |
| 1h | TREND_PULLBACK | STRICT | LONG | train | ×1 | 6/6/6 | 50.0 | 0.637 | -0.150 | INSUFFICIENT_EVIDENCE | -721.88 | 1583.55 / 2.272 | 69.50 / 23 |
| 1h | TREND_PULLBACK | STRICT | SHORT | train | ×1 | 5/5/5 | 20.0 | 0.346 | -0.470 | INSUFFICIENT_EVIDENCE | -1407.40 | 1900.02 / 3.380 | 29.36 / 15 |
| 1h | BREAKOUT_RETEST | BASE | LONG | train | ×1 | 36/34/34 | 23.5 | 0.376 | -0.391 | [-0.703; -0.068] | -13215.94 | 13215.94 / 13.295 | 310.65 / 88 |
| 1h | BREAKOUT_RETEST | BASE | SHORT | train | ×1 | 48/38/38 | 39.5 | 1.278 | 0.104 | [-0.309; 0.510] | 5433.59 | 5572.08 / 4.584 | 323.11 / 87 |
| 1h | BREAKOUT_RETEST | STRICT | LONG | train | ×1 | 29/27/27 | 22.2 | 0.421 | -0.356 | INSUFFICIENT_EVIDENCE | -9516.49 | 11264.09 / 11.311 | 235.64 / 65 |
| 1h | BREAKOUT_RETEST | STRICT | SHORT | train | ×1 | 42/35/35 | 37.1 | 1.251 | 0.062 | [-0.392; 0.460] | 4643.37 | 5572.08 / 4.690 | 295.90 / 79 |
| 1h | MOMENTUM_EXPANSION | BASE | LONG | train | ×1 | 70/57/57 | 43.9 | 1.144 | 0.103 | [-0.248; 0.477] | 2732.92 | 6847.19 / 8.254 | 380.24 / 106 |
| 1h | MOMENTUM_EXPANSION | BASE | SHORT | train | ×1 | 93/75/75 | 42.7 | 1.061 | 0.062 | [-0.220; 0.355] | 1770.71 | 6565.01 / 8.721 | 433.99 / 126 |
| 1h | MOMENTUM_EXPANSION | STRICT | LONG | train | ×1 | 46/39/39 | 43.6 | 1.157 | 0.090 | [-0.358; 0.613] | 1820.86 | 3132.01 / 5.875 | 197.31 / 62 |
| 1h | MOMENTUM_EXPANSION | STRICT | SHORT | train | ×1 | 55/48/48 | 43.8 | 1.163 | 0.064 | [-0.316; 0.438] | 2621.62 | 6872.49 / 9.523 | 251.86 / 73 |
| 1h | MEAN_REVERSION | BASE | LONG | train | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | MEAN_REVERSION | BASE | SHORT | train | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | MEAN_REVERSION | STRICT | LONG | train | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | MEAN_REVERSION | STRICT | SHORT | train | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | LIQUIDITY_SWEEP | BASE | LONG | train | ×1 | 34/34/34 | 38.2 | 0.741 | -0.145 | [-0.462; 0.212] | -4647.26 | 10089.25 / 10.531 | 279.15 / 78 |
| 1h | LIQUIDITY_SWEEP | BASE | SHORT | train | ×1 | 32/32/32 | 34.4 | 0.777 | -0.129 | [-0.534; 0.263] | -3069.27 | 5626.91 / 6.466 | 228.24 / 74 |
| 1h | LIQUIDITY_SWEEP | STRICT | LONG | train | ×1 | 27/27/27 | 33.3 | 0.456 | -0.314 | INSUFFICIENT_EVIDENCE | -8329.91 | 10144.68 / 10.731 | 214.22 / 61 |
| 1h | LIQUIDITY_SWEEP | STRICT | SHORT | train | ×1 | 24/24/24 | 33.3 | 0.878 | -0.114 | INSUFFICIENT_EVIDENCE | -1143.09 | 3030.51 / 4.111 | 187.58 / 59 |
| 1h | RANGE_REJECTION | BASE | LONG | train | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | RANGE_REJECTION | BASE | SHORT | train | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | RANGE_REJECTION | STRICT | LONG | train | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | RANGE_REJECTION | STRICT | SHORT | train | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | TREND_PULLBACK | BASE | LONG | train | ×1.5 | 23/19/19 | 36.8 | 1.111 | 0.019 | INSUFFICIENT_EVIDENCE | 797.94 | 2303.77 / 4.356 | 241.47 / 52 |
| 1h | TREND_PULLBACK | BASE | SHORT | train | ×1.5 | 39/34/34 | 20.6 | 0.470 | -0.566 | [-0.952; -0.207] | -10780.40 | 11875.77 / 19.260 | 429.58 / 99 |
| 1h | TREND_PULLBACK | STRICT | LONG | train | ×1.5 | 6/6/6 | 33.3 | 0.527 | -0.244 | INSUFFICIENT_EVIDENCE | -1022.83 | 1703.33 / 2.459 | 104.25 / 23 |
| 1h | TREND_PULLBACK | STRICT | SHORT | train | ×1.5 | 5/5/5 | 20.0 | 0.312 | -0.555 | INSUFFICIENT_EVIDENCE | -1570.60 | 2002.70 / 3.571 | 44.04 / 15 |
| 1h | BREAKOUT_RETEST | BASE | LONG | train | ×1.5 | 36/34/34 | 23.5 | 0.329 | -0.465 | [-0.783; -0.135] | -15323.27 | 15323.27 / 15.821 | 465.97 / 88 |
| 1h | BREAKOUT_RETEST | BASE | SHORT | train | ×1.5 | 48/38/38 | 39.5 | 1.151 | 0.036 | [-0.358; 0.430] | 3156.60 | 6249.08 / 5.125 | 484.67 / 87 |
| 1h | BREAKOUT_RETEST | STRICT | LONG | train | ×1.5 | 29/27/27 | 22.2 | 0.371 | -0.432 | INSUFFICIENT_EVIDENCE | -11193.55 | 12296.70 / 12.431 | 353.46 / 65 |
| 1h | BREAKOUT_RETEST | STRICT | SHORT | train | ×1.5 | 42/35/35 | 37.1 | 1.127 | -0.006 | [-0.441; 0.399] | 2514.15 | 6249.08 / 5.343 | 443.85 / 79 |
| 1h | MOMENTUM_EXPANSION | BASE | LONG | train | ×1.5 | 70/57/57 | 42.1 | 0.978 | -0.007 | [-0.347; 0.346] | -461.13 | 7550.22 / 10.979 | 570.36 / 106 |
| 1h | MOMENTUM_EXPANSION | BASE | SHORT | train | ×1.5 | 93/75/75 | 40.0 | 0.923 | -0.045 | [-0.329; 0.234] | -2422.26 | 7848.43 / 9.884 | 650.99 / 126 |
| 1h | MOMENTUM_EXPANSION | STRICT | LONG | train | ×1.5 | 46/39/39 | 41.0 | 0.992 | -0.025 | [-0.536; 0.448] | -104.71 | 3883.71 / 7.592 | 295.97 / 62 |
| 1h | MOMENTUM_EXPANSION | STRICT | SHORT | train | ×1.5 | 55/48/48 | 39.6 | 1.001 | -0.051 | [-0.479; 0.312] | 24.67 | 7400.45 / 10.283 | 377.80 / 73 |
| 1h | MEAN_REVERSION | BASE | LONG | train | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | MEAN_REVERSION | BASE | SHORT | train | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | MEAN_REVERSION | STRICT | LONG | train | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | MEAN_REVERSION | STRICT | SHORT | train | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | LIQUIDITY_SWEEP | BASE | LONG | train | ×1.5 | 34/34/34 | 38.2 | 0.653 | -0.216 | [-0.533; 0.141] | -6687.39 | 11629.96 / 12.236 | 418.73 / 78 |
| 1h | LIQUIDITY_SWEEP | BASE | SHORT | train | ×1.5 | 32/32/32 | 31.2 | 0.567 | -0.271 | [-0.596; 0.072] | -6557.93 | 6557.93 / 8.674 | 365.66 / 78 |
| 1h | LIQUIDITY_SWEEP | STRICT | LONG | train | ×1.5 | 27/27/27 | 33.3 | 0.397 | -0.385 | INSUFFICIENT_EVIDENCE | -9916.97 | 11377.91 / 12.035 | 321.34 / 61 |
| 1h | LIQUIDITY_SWEEP | STRICT | SHORT | train | ×1.5 | 24/24/24 | 29.2 | 0.596 | -0.280 | INSUFFICIENT_EVIDENCE | -4239.96 | 4628.13 / 7.068 | 304.67 / 63 |
| 1h | RANGE_REJECTION | BASE | LONG | train | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | RANGE_REJECTION | BASE | SHORT | train | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | RANGE_REJECTION | STRICT | LONG | train | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | RANGE_REJECTION | STRICT | SHORT | train | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | TREND_PULLBACK | BASE | LONG | train | ×2 | 23/19/19 | 36.8 | 0.976 | -0.077 | INSUFFICIENT_EVIDENCE | -183.82 | 2657.50 / 5.451 | 321.96 / 52 |
| 1h | TREND_PULLBACK | BASE | SHORT | train | ×2 | 39/34/34 | 20.6 | 0.426 | -0.653 | [-1.005; -0.280] | -12455.81 | 13116.66 / 22.197 | 563.35 / 98 |
| 1h | TREND_PULLBACK | STRICT | LONG | train | ×2 | 6/6/6 | 33.3 | 0.435 | -0.337 | INSUFFICIENT_EVIDENCE | -1323.79 | 1831.03 / 2.659 | 139.00 / 23 |
| 1h | TREND_PULLBACK | STRICT | SHORT | train | ×2 | 5/5/5 | 20.0 | 0.281 | -0.641 | INSUFFICIENT_EVIDENCE | -1733.79 | 2105.38 / 3.761 | 58.72 / 15 |
| 1h | BREAKOUT_RETEST | BASE | LONG | train | ×2 | 36/34/34 | 23.5 | 0.288 | -0.540 | [-0.850; -0.183] | -17430.68 | 17430.68 / 18.346 | 621.29 / 88 |
| 1h | BREAKOUT_RETEST | BASE | SHORT | train | ×2 | 48/38/38 | 39.5 | 1.040 | -0.031 | [-0.450; 0.388] | 879.70 | 6926.06 / 5.667 | 646.23 / 87 |
| 1h | BREAKOUT_RETEST | STRICT | LONG | train | ×2 | 29/27/27 | 22.2 | 0.327 | -0.508 | INSUFFICIENT_EVIDENCE | -12870.67 | 13747.60 / 13.723 | 471.28 / 65 |
| 1h | BREAKOUT_RETEST | STRICT | SHORT | train | ×2 | 42/35/35 | 37.1 | 1.018 | -0.074 | [-0.491; 0.307] | 385.01 | 6926.06 / 5.997 | 591.80 / 79 |
| 1h | MOMENTUM_EXPANSION | BASE | LONG | train | ×2 | 70/57/57 | 42.1 | 0.838 | -0.118 | [-0.479; 0.235] | -3655.28 | 8262.88 / 14.663 | 760.48 / 106 |
| 1h | MOMENTUM_EXPANSION | BASE | SHORT | train | ×2 | 93/75/75 | 38.7 | 0.805 | -0.151 | [-0.400; 0.146] | -6615.09 | 9131.80 / 11.910 | 867.98 / 126 |
| 1h | MOMENTUM_EXPANSION | STRICT | LONG | train | ×2 | 46/39/39 | 41.0 | 0.853 | -0.140 | [-0.652; 0.375] | -2030.34 | 4997.63 / 9.598 | 394.62 / 62 |
| 1h | MOMENTUM_EXPANSION | STRICT | SHORT | train | ×2 | 55/48/48 | 37.5 | 0.865 | -0.166 | [-0.580; 0.208] | -2572.19 | 7928.38 / 13.151 | 503.73 / 73 |
| 1h | MEAN_REVERSION | BASE | LONG | train | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | MEAN_REVERSION | BASE | SHORT | train | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | MEAN_REVERSION | STRICT | LONG | train | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | MEAN_REVERSION | STRICT | SHORT | train | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | LIQUIDITY_SWEEP | BASE | LONG | train | ×2 | 34/34/34 | 32.4 | 0.577 | -0.288 | [-0.623; 0.087] | -8727.58 | 13201.95 / 14.004 | 558.30 / 78 |
| 1h | LIQUIDITY_SWEEP | BASE | SHORT | train | ×2 | 32/32/32 | 28.1 | 0.497 | -0.346 | [-0.677; 0.000] | -8227.86 | 8227.86 / 11.066 | 487.54 / 78 |
| 1h | LIQUIDITY_SWEEP | STRICT | LONG | train | ×2 | 27/27/27 | 25.9 | 0.347 | -0.455 | INSUFFICIENT_EVIDENCE | -11504.08 | 12642.42 / 13.401 | 428.45 / 61 |
| 1h | LIQUIDITY_SWEEP | STRICT | SHORT | train | ×2 | 24/24/24 | 25.0 | 0.517 | -0.357 | INSUFFICIENT_EVIDENCE | -5518.12 | 5803.52 / 8.827 | 406.22 / 63 |
| 1h | RANGE_REJECTION | BASE | LONG | train | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | RANGE_REJECTION | BASE | SHORT | train | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | RANGE_REJECTION | STRICT | LONG | train | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | RANGE_REJECTION | STRICT | SHORT | train | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | TREND_PULLBACK | BASE | LONG | validation | ×1 | 18/17/17 | 35.3 | 0.739 | -0.198 | INSUFFICIENT_EVIDENCE | -2554.99 | 5915.09 / 8.179 | 322.21 / 60 |
| 1h | TREND_PULLBACK | BASE | SHORT | validation | ×1 | 22/16/16 | 12.5 | 0.277 | -0.593 | INSUFFICIENT_EVIDENCE | -14351.71 | 16985.25 / 12.092 | 345.43 / 57 |
| 1h | TREND_PULLBACK | STRICT | LONG | validation | ×1 | 4/4/4 | 25.0 | 0.099 | -0.663 | INSUFFICIENT_EVIDENCE | -3019.40 | 3351.88 / 3.655 | 80.05 / 16 |
| 1h | TREND_PULLBACK | STRICT | SHORT | validation | ×1 | 5/5/5 | 0.0 | 0.000 | -0.909 | INSUFFICIENT_EVIDENCE | -4560.99 | 4560.99 / 4.544 | 106.53 / 17 |
| 1h | BREAKOUT_RETEST | BASE | LONG | validation | ×1 | 20/17/17 | 47.1 | 0.899 | 0.080 | INSUFFICIENT_EVIDENCE | -1084.71 | 7053.24 / 4.020 | 257.29 / 45 |
| 1h | BREAKOUT_RETEST | BASE | SHORT | validation | ×1 | 17/17/17 | 23.5 | 0.788 | -0.253 | INSUFFICIENT_EVIDENCE | -3252.53 | 9839.13 / 6.352 | 225.25 / 38 |
| 1h | BREAKOUT_RETEST | STRICT | LONG | validation | ×1 | 10/8/8 | 62.5 | 1.583 | 0.428 | INSUFFICIENT_EVIDENCE | 2656.29 | 2427.04 / 1.597 | 105.60 / 19 |
| 1h | BREAKOUT_RETEST | STRICT | SHORT | validation | ×1 | 14/14/14 | 14.3 | 0.540 | -0.489 | INSUFFICIENT_EVIDENCE | -6302.21 | 10351.23 / 7.054 | 201.65 / 34 |
| 1h | MOMENTUM_EXPANSION | BASE | LONG | validation | ×1 | 47/42/42 | 45.2 | 1.379 | 0.072 | [-0.308; 0.440] | 6659.69 | 3350.28 / 6.672 | 414.46 / 75 |
| 1h | MOMENTUM_EXPANSION | BASE | SHORT | validation | ×1 | 36/34/34 | 11.8 | 0.164 | -0.738 | [-1.003; -0.447] | -22462.17 | 23911.14 / 27.297 | 355.91 / 63 |
| 1h | MOMENTUM_EXPANSION | STRICT | LONG | validation | ×1 | 32/30/30 | 46.7 | 1.398 | 0.097 | [-0.402; 0.629] | 5131.27 | 2865.57 / 5.387 | 296.76 / 53 |
| 1h | MOMENTUM_EXPANSION | STRICT | SHORT | validation | ×1 | 20/19/19 | 10.5 | 0.059 | -0.788 | INSUFFICIENT_EVIDENCE | -12631.55 | 13422.11 / 17.180 | 187.60 / 34 |
| 1h | MEAN_REVERSION | BASE | LONG | validation | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | MEAN_REVERSION | BASE | SHORT | validation | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | MEAN_REVERSION | STRICT | LONG | validation | ×1 | 1/1/1 | 0.0 | 0.000 | -1.246 | INSUFFICIENT_EVIDENCE | -1078.37 | 1078.37 / 1.246 | 6.68 / 1 |
| 1h | MEAN_REVERSION | STRICT | SHORT | validation | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | LIQUIDITY_SWEEP | BASE | LONG | validation | ×1 | 19/19/19 | 42.1 | 0.679 | -0.245 | INSUFFICIENT_EVIDENCE | -4928.39 | 8583.25 / 6.124 | 290.53 / 45 |
| 1h | LIQUIDITY_SWEEP | BASE | SHORT | validation | ×1 | 15/13/13 | 7.7 | 0.165 | -0.598 | INSUFFICIENT_EVIDENCE | -10965.32 | 10965.32 / 7.776 | 232.42 / 38 |
| 1h | LIQUIDITY_SWEEP | STRICT | LONG | validation | ×1 | 14/14/14 | 50.0 | 1.205 | -0.037 | INSUFFICIENT_EVIDENCE | 1646.88 | 3664.11 / 3.065 | 243.69 / 38 |
| 1h | LIQUIDITY_SWEEP | STRICT | SHORT | validation | ×1 | 11/10/10 | 0.0 | 0.000 | -0.812 | INSUFFICIENT_EVIDENCE | -11355.59 | 11355.59 / 8.123 | 172.65 / 28 |
| 1h | RANGE_REJECTION | BASE | LONG | validation | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | RANGE_REJECTION | BASE | SHORT | validation | ×1 | 3/1/1 | 100.0 | — | 0.897 | INSUFFICIENT_EVIDENCE | 1195.93 | 0.00 / 0.000 | 17.00 / 3 |
| 1h | RANGE_REJECTION | STRICT | LONG | validation | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | RANGE_REJECTION | STRICT | SHORT | validation | ×1 | 3/1/1 | 100.0 | — | 0.897 | INSUFFICIENT_EVIDENCE | 1195.93 | 0.00 / 0.000 | 17.00 / 3 |
| 1h | TREND_PULLBACK | BASE | LONG | validation | ×1.5 | 18/17/17 | 35.3 | 0.615 | -0.313 | INSUFFICIENT_EVIDENCE | -4162.62 | 6931.10 / 9.412 | 483.32 / 60 |
| 1h | TREND_PULLBACK | BASE | SHORT | validation | ×1.5 | 22/16/16 | 12.5 | 0.250 | -0.678 | INSUFFICIENT_EVIDENCE | -15999.34 | 18260.17 / 13.101 | 518.15 / 57 |
| 1h | TREND_PULLBACK | STRICT | LONG | validation | ×1.5 | 4/4/4 | 25.0 | 0.073 | -0.796 | INSUFFICIENT_EVIDENCE | -3389.07 | 3654.43 / 3.983 | 120.07 / 16 |
| 1h | TREND_PULLBACK | STRICT | SHORT | validation | ×1.5 | 5/5/5 | 0.0 | 0.000 | -1.003 | INSUFFICIENT_EVIDENCE | -5078.38 | 5078.38 / 5.017 | 159.80 / 17 |
| 1h | BREAKOUT_RETEST | BASE | LONG | validation | ×1.5 | 20/16/16 | 50.0 | 0.934 | 0.078 | INSUFFICIENT_EVIDENCE | -628.65 | 6012.00 / 3.601 | 364.79 / 42 |
| 1h | BREAKOUT_RETEST | BASE | SHORT | validation | ×1.5 | 17/17/17 | 23.5 | 0.703 | -0.328 | INSUFFICIENT_EVIDENCE | -4924.90 | 10928.73 / 7.150 | 337.88 / 38 |
| 1h | BREAKOUT_RETEST | STRICT | LONG | validation | ×1.5 | 10/8/8 | 62.5 | 1.397 | 0.353 | INSUFFICIENT_EVIDENCE | 1921.49 | 2613.32 / 1.741 | 158.40 / 19 |
| 1h | BREAKOUT_RETEST | STRICT | SHORT | validation | ×1.5 | 14/14/14 | 14.3 | 0.483 | -0.564 | INSUFFICIENT_EVIDENCE | -7681.77 | 11251.61 / 7.895 | 302.48 / 34 |
| 1h | MOMENTUM_EXPANSION | BASE | LONG | validation | ×1.5 | 47/42/42 | 45.2 | 1.146 | -0.060 | [-0.435; 0.363] | 2854.90 | 3904.29 / 7.505 | 621.70 / 75 |
| 1h | MOMENTUM_EXPANSION | BASE | SHORT | validation | ×1.5 | 36/34/34 | 8.8 | 0.140 | -0.858 | [-1.117; -0.558] | -25618.38 | 26767.22 / 31.038 | 533.86 / 63 |
| 1h | MOMENTUM_EXPANSION | STRICT | LONG | validation | ×1.5 | 32/30/30 | 46.7 | 1.169 | -0.031 | [-0.482; 0.484] | 2403.43 | 3243.99 / 6.077 | 445.15 / 53 |
| 1h | MOMENTUM_EXPANSION | STRICT | SHORT | validation | ×1.5 | 20/19/19 | 5.3 | 0.047 | -0.919 | INSUFFICIENT_EVIDENCE | -14403.13 | 15084.23 / 19.320 | 281.40 / 34 |
| 1h | MEAN_REVERSION | BASE | LONG | validation | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | MEAN_REVERSION | BASE | SHORT | validation | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | MEAN_REVERSION | STRICT | LONG | validation | ×1.5 | 1/1/1 | 0.0 | 0.000 | -1.369 | INSUFFICIENT_EVIDENCE | -1184.88 | 1184.88 / 1.369 | 10.02 / 1 |
| 1h | MEAN_REVERSION | STRICT | SHORT | validation | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | LIQUIDITY_SWEEP | BASE | LONG | validation | ×1.5 | 19/19/19 | 42.1 | 0.576 | -0.316 | INSUFFICIENT_EVIDENCE | -6963.53 | 9662.75 / 6.768 | 435.80 / 45 |
| 1h | LIQUIDITY_SWEEP | BASE | SHORT | validation | ×1.5 | 15/13/13 | 7.7 | 0.144 | -0.668 | INSUFFICIENT_EVIDENCE | -12296.18 | 12296.18 / 8.684 | 348.63 / 38 |
| 1h | LIQUIDITY_SWEEP | STRICT | LONG | validation | ×1.5 | 14/14/14 | 50.0 | 1.016 | -0.108 | INSUFFICIENT_EVIDENCE | 143.04 | 4079.36 / 3.410 | 365.53 / 38 |
| 1h | LIQUIDITY_SWEEP | STRICT | SHORT | validation | ×1.5 | 11/10/10 | 0.0 | 0.000 | -0.877 | INSUFFICIENT_EVIDENCE | -12371.39 | 12371.39 / 8.768 | 258.97 / 28 |
| 1h | RANGE_REJECTION | BASE | LONG | validation | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | RANGE_REJECTION | BASE | SHORT | validation | ×1.5 | 3/1/1 | 100.0 | — | 0.824 | INSUFFICIENT_EVIDENCE | 1098.15 | 0.00 / 0.000 | 25.50 / 3 |
| 1h | RANGE_REJECTION | STRICT | LONG | validation | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | RANGE_REJECTION | STRICT | SHORT | validation | ×1.5 | 3/1/1 | 100.0 | — | 0.824 | INSUFFICIENT_EVIDENCE | 1098.15 | 0.00 / 0.000 | 25.50 / 3 |
| 1h | TREND_PULLBACK | BASE | LONG | validation | ×2 | 18/17/17 | 35.3 | 0.513 | -0.427 | INSUFFICIENT_EVIDENCE | -5770.31 | 8110.76 / 10.645 | 644.43 / 60 |
| 1h | TREND_PULLBACK | BASE | SHORT | validation | ×2 | 22/16/16 | 12.5 | 0.226 | -0.762 | INSUFFICIENT_EVIDENCE | -17646.92 | 19535.06 / 14.110 | 690.87 / 57 |
| 1h | TREND_PULLBACK | STRICT | LONG | validation | ×2 | 4/4/4 | 25.0 | 0.050 | -0.928 | INSUFFICIENT_EVIDENCE | -3758.75 | 3957.00 / 4.311 | 160.09 / 16 |
| 1h | TREND_PULLBACK | STRICT | SHORT | validation | ×2 | 5/5/5 | 0.0 | 0.000 | -1.098 | INSUFFICIENT_EVIDENCE | -5595.76 | 5595.76 / 5.490 | 213.07 / 17 |
| 1h | BREAKOUT_RETEST | BASE | LONG | validation | ×2 | 20/16/16 | 43.8 | 0.792 | 0.003 | INSUFFICIENT_EVIDENCE | -2151.00 | 6949.16 / 4.268 | 486.38 / 42 |
| 1h | BREAKOUT_RETEST | BASE | SHORT | validation | ×2 | 17/17/17 | 23.5 | 0.629 | -0.402 | INSUFFICIENT_EVIDENCE | -6597.21 | 12018.31 / 7.948 | 450.51 / 38 |
| 1h | BREAKOUT_RETEST | STRICT | LONG | validation | ×2 | 10/8/8 | 62.5 | 1.232 | 0.278 | INSUFFICIENT_EVIDENCE | 1186.68 | 3003.91 / 1.885 | 211.20 / 19 |
| 1h | BREAKOUT_RETEST | STRICT | SHORT | validation | ×2 | 14/14/14 | 14.3 | 0.434 | -0.639 | INSUFFICIENT_EVIDENCE | -9061.29 | 12151.97 / 8.941 | 403.31 / 34 |
| 1h | MOMENTUM_EXPANSION | BASE | LONG | validation | ×2 | 47/42/42 | 42.9 | 0.956 | -0.193 | [-0.599; 0.220] | -950.02 | 4458.33 / 8.997 | 828.93 / 75 |
| 1h | MOMENTUM_EXPANSION | BASE | SHORT | validation | ×2 | 36/34/34 | 8.8 | 0.120 | -0.979 | [-1.251; -0.670] | -28774.48 | 29623.20 / 34.779 | 711.82 / 63 |
| 1h | MOMENTUM_EXPANSION | STRICT | LONG | validation | ×2 | 32/30/30 | 43.3 | 0.979 | -0.159 | [-0.619; 0.375] | -324.49 | 3718.25 / 6.767 | 593.53 / 53 |
| 1h | MOMENTUM_EXPANSION | STRICT | SHORT | validation | ×2 | 20/19/19 | 5.3 | 0.039 | -1.051 | INSUFFICIENT_EVIDENCE | -16174.66 | 16746.29 / 21.460 | 375.19 / 34 |
| 1h | MEAN_REVERSION | BASE | LONG | validation | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | MEAN_REVERSION | BASE | SHORT | validation | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | MEAN_REVERSION | STRICT | LONG | validation | ×2 | 1/1/1 | 0.0 | 0.000 | -1.492 | INSUFFICIENT_EVIDENCE | -1291.40 | 1291.40 / 1.492 | 13.36 / 1 |
| 1h | MEAN_REVERSION | STRICT | SHORT | validation | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | LIQUIDITY_SWEEP | BASE | LONG | validation | ×2 | 19/19/19 | 42.1 | 0.487 | -0.387 | INSUFFICIENT_EVIDENCE | -8998.71 | 10742.28 / 7.412 | 581.07 / 45 |
| 1h | LIQUIDITY_SWEEP | BASE | SHORT | validation | ×2 | 15/13/13 | 7.7 | 0.126 | -0.738 | INSUFFICIENT_EVIDENCE | -13627.01 | 13627.01 / 9.592 | 464.84 / 38 |
| 1h | LIQUIDITY_SWEEP | STRICT | LONG | validation | ×2 | 14/14/14 | 50.0 | 0.856 | -0.180 | INSUFFICIENT_EVIDENCE | -1360.84 | 4521.45 / 3.756 | 487.37 / 38 |
| 1h | LIQUIDITY_SWEEP | STRICT | SHORT | validation | ×2 | 11/10/10 | 0.0 | 0.000 | -0.941 | INSUFFICIENT_EVIDENCE | -13387.18 | 13387.18 / 9.413 | 345.30 / 28 |
| 1h | RANGE_REJECTION | BASE | LONG | validation | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | RANGE_REJECTION | BASE | SHORT | validation | ×2 | 3/1/1 | 100.0 | — | 0.751 | INSUFFICIENT_EVIDENCE | 1000.37 | 0.00 / 0.000 | 34.00 / 3 |
| 1h | RANGE_REJECTION | STRICT | LONG | validation | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | RANGE_REJECTION | STRICT | SHORT | validation | ×2 | 3/1/1 | 100.0 | — | 0.751 | INSUFFICIENT_EVIDENCE | 1000.37 | 0.00 / 0.000 | 34.00 / 3 |
| 1h | TREND_PULLBACK | BASE | LONG | test | ×1 | 17/15/15 | 40.0 | 1.028 | 0.037 | INSUFFICIENT_EVIDENCE | 444.88 | 10625.04 / 5.453 | 392.18 / 41 |
| 1h | TREND_PULLBACK | BASE | SHORT | test | ×1 | 16/15/15 | 13.3 | 0.190 | -0.569 | INSUFFICIENT_EVIDENCE | -18923.49 | 18923.49 / 9.623 | 452.33 / 44 |
| 1h | TREND_PULLBACK | STRICT | LONG | test | ×1 | 6/5/5 | 40.0 | 1.664 | 0.305 | INSUFFICIENT_EVIDENCE | 3899.60 | 5876.59 / 3.169 | 126.02 / 13 |
| 1h | TREND_PULLBACK | STRICT | SHORT | test | ×1 | 2/2/2 | 0.0 | 0.000 | -0.099 | INSUFFICIENT_EVIDENCE | -702.34 | 702.34 / 0.199 | 127.06 / 12 |
| 1h | BREAKOUT_RETEST | BASE | LONG | test | ×1 | 7/7/7 | 42.9 | 0.879 | 0.105 | INSUFFICIENT_EVIDENCE | -1070.16 | 6086.87 / 2.250 | 151.27 / 16 |
| 1h | BREAKOUT_RETEST | BASE | SHORT | test | ×1 | 13/13/13 | 30.8 | 0.572 | -0.310 | INSUFFICIENT_EVIDENCE | -9318.32 | 18787.26 / 8.648 | 220.97 / 24 |
| 1h | BREAKOUT_RETEST | STRICT | LONG | test | ×1 | 7/7/7 | 42.9 | 0.879 | 0.105 | INSUFFICIENT_EVIDENCE | -1070.16 | 6086.87 / 2.250 | 151.27 / 16 |
| 1h | BREAKOUT_RETEST | STRICT | SHORT | test | ×1 | 11/11/11 | 27.3 | 0.466 | -0.432 | INSUFFICIENT_EVIDENCE | -10033.24 | 18787.26 / 8.648 | 200.71 / 22 |
| 1h | MOMENTUM_EXPANSION | BASE | LONG | test | ×1 | 52/41/41 | 29.3 | 0.549 | -0.376 | [-0.771; 0.024] | -18621.55 | 22672.97 / 18.601 | 728.43 / 76 |
| 1h | MOMENTUM_EXPANSION | BASE | SHORT | test | ×1 | 47/38/38 | 31.6 | 0.476 | -0.332 | [-0.798; 0.254] | -21700.14 | 23189.82 / 15.930 | 509.33 / 53 |
| 1h | MOMENTUM_EXPANSION | STRICT | LONG | test | ×1 | 42/35/35 | 22.9 | 0.418 | -0.537 | [-0.843; -0.189] | -23259.86 | 27300.07 / 21.961 | 564.03 / 59 |
| 1h | MOMENTUM_EXPANSION | STRICT | SHORT | test | ×1 | 38/31/31 | 32.3 | 0.525 | -0.321 | [-0.829; 0.365] | -14794.84 | 16284.52 / 13.428 | 440.93 / 45 |
| 1h | MEAN_REVERSION | BASE | LONG | test | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | MEAN_REVERSION | BASE | SHORT | test | ×1 | 1/1/1 | 100.0 | — | 0.976 | INSUFFICIENT_EVIDENCE | 2121.25 | 0.00 / 0.000 | 30.02 / 3 |
| 1h | MEAN_REVERSION | STRICT | LONG | test | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | MEAN_REVERSION | STRICT | SHORT | test | ×1 | 1/1/1 | 100.0 | — | 1.803 | INSUFFICIENT_EVIDENCE | 3664.73 | 0.00 / 0.000 | 0.00 / 0 |
| 1h | LIQUIDITY_SWEEP | BASE | LONG | test | ×1 | 14/13/13 | 30.8 | 0.482 | -0.512 | INSUFFICIENT_EVIDENCE | -10940.27 | 13779.44 / 6.862 | 296.10 / 34 |
| 1h | LIQUIDITY_SWEEP | BASE | SHORT | test | ×1 | 7/7/7 | 57.1 | 1.856 | 0.125 | INSUFFICIENT_EVIDENCE | 3689.37 | 1892.06 / 1.163 | 168.08 / 19 |
| 1h | LIQUIDITY_SWEEP | STRICT | LONG | test | ×1 | 13/13/13 | 38.5 | 0.751 | -0.283 | INSUFFICIENT_EVIDENCE | -4588.32 | 7530.19 / 3.887 | 287.75 / 33 |
| 1h | LIQUIDITY_SWEEP | STRICT | SHORT | test | ×1 | 7/7/7 | 57.1 | 1.856 | 0.125 | INSUFFICIENT_EVIDENCE | 3689.37 | 1892.06 / 1.163 | 168.08 / 19 |
| 1h | RANGE_REJECTION | BASE | LONG | test | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | RANGE_REJECTION | BASE | SHORT | test | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | RANGE_REJECTION | STRICT | LONG | test | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | RANGE_REJECTION | STRICT | SHORT | test | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | TREND_PULLBACK | BASE | LONG | test | ×1.5 | 17/15/15 | 40.0 | 0.882 | -0.069 | INSUFFICIENT_EVIDENCE | -2094.38 | 12168.35 / 5.964 | 588.27 / 41 |
| 1h | TREND_PULLBACK | BASE | SHORT | test | ×1.5 | 16/15/15 | 13.3 | 0.161 | -0.673 | INSUFFICIENT_EVIDENCE | -21507.50 | 21507.50 / 10.425 | 678.50 / 44 |
| 1h | TREND_PULLBACK | STRICT | LONG | test | ×1.5 | 6/5/5 | 40.0 | 1.476 | 0.212 | INSUFFICIENT_EVIDENCE | 3055.83 | 6419.43 / 3.476 | 189.03 / 13 |
| 1h | TREND_PULLBACK | STRICT | SHORT | test | ×1.5 | 2/2/2 | 0.0 | 0.000 | -0.179 | INSUFFICIENT_EVIDENCE | -1103.02 | 1103.02 / 0.358 | 190.59 / 12 |
| 1h | BREAKOUT_RETEST | BASE | LONG | test | ×1.5 | 7/7/7 | 42.9 | 0.773 | 0.035 | INSUFFICIENT_EVIDENCE | -2151.19 | 6548.50 / 2.450 | 226.90 / 16 |
| 1h | BREAKOUT_RETEST | BASE | SHORT | test | ×1.5 | 13/13/13 | 30.8 | 0.513 | -0.377 | INSUFFICIENT_EVIDENCE | -11220.70 | 19894.15 / 9.179 | 331.45 / 24 |
| 1h | BREAKOUT_RETEST | STRICT | LONG | test | ×1.5 | 7/7/7 | 42.9 | 0.773 | 0.035 | INSUFFICIENT_EVIDENCE | -2151.19 | 6548.50 / 2.450 | 226.90 / 16 |
| 1h | BREAKOUT_RETEST | STRICT | SHORT | test | ×1.5 | 11/11/11 | 27.3 | 0.416 | -0.499 | INSUFFICIENT_EVIDENCE | -11623.84 | 19894.15 / 9.179 | 301.07 / 22 |
| 1h | MOMENTUM_EXPANSION | BASE | LONG | test | ×1.5 | 52/41/41 | 24.4 | 0.455 | -0.512 | [-0.906; -0.108] | -25125.87 | 28566.80 / 23.517 | 1092.65 / 76 |
| 1h | MOMENTUM_EXPANSION | BASE | SHORT | test | ×1.5 | 47/38/38 | 26.3 | 0.396 | -0.462 | [-0.879; 0.092] | -27558.99 | 28945.99 / 19.620 | 764.00 / 53 |
| 1h | MOMENTUM_EXPANSION | STRICT | LONG | test | ×1.5 | 42/35/35 | 20.0 | 0.350 | -0.669 | [-0.976; -0.308] | -28784.47 | 32333.59 / 26.059 | 846.04 / 59 |
| 1h | MOMENTUM_EXPANSION | STRICT | SHORT | test | ×1.5 | 38/31/31 | 25.8 | 0.434 | -0.458 | [-0.986; 0.280] | -19679.39 | 21066.39 / 16.254 | 661.40 / 45 |
| 1h | MEAN_REVERSION | BASE | LONG | test | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | MEAN_REVERSION | BASE | SHORT | test | ×1.5 | 1/1/1 | 100.0 | — | 0.896 | INSUFFICIENT_EVIDENCE | 1946.53 | 0.00 / 0.000 | 45.03 / 3 |
| 1h | MEAN_REVERSION | STRICT | LONG | test | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | MEAN_REVERSION | STRICT | SHORT | test | ×1.5 | 1/1/1 | 100.0 | — | 1.734 | INSUFFICIENT_EVIDENCE | 3524.60 | 0.00 / 0.000 | 0.00 / 0 |
| 1h | LIQUIDITY_SWEEP | BASE | LONG | test | ×1.5 | 14/13/13 | 30.8 | 0.426 | -0.583 | INSUFFICIENT_EVIDENCE | -12872.46 | 14613.82 / 7.676 | 444.15 / 34 |
| 1h | LIQUIDITY_SWEEP | BASE | SHORT | test | ×1.5 | 7/7/7 | 57.1 | 1.558 | 0.049 | INSUFFICIENT_EVIDENCE | 2641.55 | 2022.70 / 1.245 | 252.12 / 19 |
| 1h | LIQUIDITY_SWEEP | STRICT | LONG | test | ×1.5 | 13/13/13 | 38.5 | 0.668 | -0.355 | INSUFFICIENT_EVIDENCE | -6519.98 | 8261.34 / 4.713 | 431.63 / 33 |
| 1h | LIQUIDITY_SWEEP | STRICT | SHORT | test | ×1.5 | 7/7/7 | 57.1 | 1.558 | 0.049 | INSUFFICIENT_EVIDENCE | 2641.55 | 2022.70 / 1.245 | 252.12 / 19 |
| 1h | RANGE_REJECTION | BASE | LONG | test | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | RANGE_REJECTION | BASE | SHORT | test | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | RANGE_REJECTION | STRICT | LONG | test | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | RANGE_REJECTION | STRICT | SHORT | test | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | TREND_PULLBACK | BASE | LONG | test | ×2 | 17/15/15 | 33.3 | 0.761 | -0.175 | INSUFFICIENT_EVIDENCE | -4633.74 | 13854.67 / 6.923 | 784.36 / 41 |
| 1h | TREND_PULLBACK | BASE | SHORT | test | ×2 | 16/15/15 | 13.3 | 0.136 | -0.777 | INSUFFICIENT_EVIDENCE | -24091.43 | 24091.43 / 11.660 | 904.67 / 44 |
| 1h | TREND_PULLBACK | STRICT | LONG | test | ×2 | 6/5/5 | 40.0 | 1.318 | 0.120 | INSUFFICIENT_EVIDENCE | 2212.03 | 6962.28 / 3.784 | 252.05 / 13 |
| 1h | TREND_PULLBACK | STRICT | SHORT | test | ×2 | 2/2/2 | 0.0 | 0.000 | -0.259 | INSUFFICIENT_EVIDENCE | -1503.69 | 1503.69 / 0.517 | 254.12 / 12 |
| 1h | BREAKOUT_RETEST | BASE | LONG | test | ×2 | 7/7/7 | 42.9 | 0.680 | -0.036 | INSUFFICIENT_EVIDENCE | -3232.26 | 7010.15 / 2.650 | 302.54 / 16 |
| 1h | BREAKOUT_RETEST | BASE | SHORT | test | ×2 | 13/13/13 | 30.8 | 0.459 | -0.444 | INSUFFICIENT_EVIDENCE | -13123.02 | 21001.01 / 9.710 | 441.94 / 24 |
| 1h | BREAKOUT_RETEST | STRICT | LONG | test | ×2 | 7/7/7 | 42.9 | 0.680 | -0.036 | INSUFFICIENT_EVIDENCE | -3232.26 | 7010.15 / 2.650 | 302.54 / 16 |
| 1h | BREAKOUT_RETEST | STRICT | SHORT | test | ×2 | 11/11/11 | 27.3 | 0.371 | -0.566 | INSUFFICIENT_EVIDENCE | -13214.40 | 21001.01 / 9.710 | 401.43 / 22 |
| 1h | MOMENTUM_EXPANSION | BASE | LONG | test | ×2 | 52/41/41 | 24.4 | 0.379 | -0.649 | [-1.027; -0.227] | -31630.42 | 34460.84 / 28.530 | 1456.86 / 76 |
| 1h | MOMENTUM_EXPANSION | BASE | SHORT | test | ×2 | 47/38/38 | 26.3 | 0.332 | -0.593 | [-1.002; 0.010] | -33417.62 | 34701.96 / 24.441 | 1018.67 / 53 |
| 1h | MOMENTUM_EXPANSION | STRICT | LONG | test | ×2 | 42/35/35 | 20.0 | 0.296 | -0.801 | [-1.096; -0.392] | -34309.30 | 37367.31 / 30.158 | 1128.06 / 59 |
| 1h | MOMENTUM_EXPANSION | STRICT | SHORT | test | ×2 | 38/31/31 | 25.8 | 0.361 | -0.595 | [-1.082; 0.083] | -24563.75 | 25848.09 / 20.351 | 881.86 / 45 |
| 1h | MEAN_REVERSION | BASE | LONG | test | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | MEAN_REVERSION | BASE | SHORT | test | ×2 | 1/1/1 | 100.0 | — | 0.815 | INSUFFICIENT_EVIDENCE | 1771.81 | 0.00 / 0.000 | 60.04 / 3 |
| 1h | MEAN_REVERSION | STRICT | LONG | test | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | MEAN_REVERSION | STRICT | SHORT | test | ×2 | 1/1/1 | 100.0 | — | 1.665 | INSUFFICIENT_EVIDENCE | 3384.48 | 0.00 / 0.000 | 0.00 / 0 |
| 1h | LIQUIDITY_SWEEP | BASE | LONG | test | ×2 | 14/13/13 | 23.1 | 0.380 | -0.653 | INSUFFICIENT_EVIDENCE | -14804.72 | 15448.24 / 8.499 | 592.21 / 34 |
| 1h | LIQUIDITY_SWEEP | BASE | SHORT | test | ×2 | 7/7/7 | 42.9 | 1.306 | -0.028 | INSUFFICIENT_EVIDENCE | 1593.76 | 2201.14 / 1.344 | 336.16 / 19 |
| 1h | LIQUIDITY_SWEEP | STRICT | LONG | test | ×2 | 13/13/13 | 30.8 | 0.596 | -0.426 | INSUFFICIENT_EVIDENCE | -8451.71 | 9095.23 / 5.548 | 575.51 / 33 |
| 1h | LIQUIDITY_SWEEP | STRICT | SHORT | test | ×2 | 7/7/7 | 42.9 | 1.306 | -0.028 | INSUFFICIENT_EVIDENCE | 1593.76 | 2201.14 / 1.344 | 336.16 / 19 |
| 1h | RANGE_REJECTION | BASE | LONG | test | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | RANGE_REJECTION | BASE | SHORT | test | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | RANGE_REJECTION | STRICT | LONG | test | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | RANGE_REJECTION | STRICT | SHORT | test | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | TREND_PULLBACK | BASE | LONG | final | ×1 | 13/11/11 | 27.3 | 0.423 | -0.387 | INSUFFICIENT_EVIDENCE | -6917.78 | 6917.78 / 4.525 | 248.66 / 31 |
| 1h | TREND_PULLBACK | BASE | SHORT | final | ×1 | 16/13/13 | 30.8 | 0.631 | -0.158 | INSUFFICIENT_EVIDENCE | -4731.40 | 5410.95 / 3.403 | 175.34 / 30 |
| 1h | TREND_PULLBACK | STRICT | LONG | final | ×1 | 1/1/1 | 0.0 | 0.000 | -1.319 | INSUFFICIENT_EVIDENCE | -1244.80 | 1244.80 / 1.319 | 18.30 / 2 |
| 1h | TREND_PULLBACK | STRICT | SHORT | final | ×1 | 2/2/2 | 0.0 | 0.000 | -0.576 | INSUFFICIENT_EVIDENCE | -1502.10 | 1502.10 / 1.152 | -43.51 / 0 |
| 1h | BREAKOUT_RETEST | BASE | LONG | final | ×1 | 14/13/13 | 38.5 | 0.432 | -0.326 | INSUFFICIENT_EVIDENCE | -9097.23 | 9097.23 / 4.484 | 225.90 / 24 |
| 1h | BREAKOUT_RETEST | BASE | SHORT | final | ×1 | 24/19/19 | 57.9 | 2.155 | 0.254 | INSUFFICIENT_EVIDENCE | 13833.08 | 6193.11 / 3.425 | 408.90 / 52 |
| 1h | BREAKOUT_RETEST | STRICT | LONG | final | ×1 | 11/10/10 | 30.0 | 0.453 | -0.325 | INSUFFICIENT_EVIDENCE | -7820.57 | 8897.53 / 4.628 | 141.83 / 12 |
| 1h | BREAKOUT_RETEST | STRICT | SHORT | final | ×1 | 23/19/19 | 57.9 | 2.155 | 0.254 | INSUFFICIENT_EVIDENCE | 13833.08 | 6193.11 / 3.425 | 408.90 / 52 |
| 1h | MOMENTUM_EXPANSION | BASE | LONG | final | ×1 | 39/34/34 | 44.1 | 1.017 | 0.092 | [-0.345; 0.527] | 348.24 | 7625.54 / 7.334 | 389.43 / 49 |
| 1h | MOMENTUM_EXPANSION | BASE | SHORT | final | ×1 | 54/43/43 | 44.2 | 1.612 | 0.100 | [-0.487; 0.626] | 15933.07 | 9377.24 / 11.846 | 617.87 / 81 |
| 1h | MOMENTUM_EXPANSION | STRICT | LONG | final | ×1 | 28/25/25 | 44.0 | 1.184 | 0.201 | INSUFFICIENT_EVIDENCE | 2709.05 | 7273.93 / 5.723 | 240.25 / 32 |
| 1h | MOMENTUM_EXPANSION | STRICT | SHORT | final | ×1 | 47/41/41 | 43.9 | 1.647 | 0.104 | [-0.498; 0.691] | 16329.87 | 9779.33 / 12.352 | 567.97 / 75 |
| 1h | MEAN_REVERSION | BASE | LONG | final | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | MEAN_REVERSION | BASE | SHORT | final | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | MEAN_REVERSION | STRICT | LONG | final | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | MEAN_REVERSION | STRICT | SHORT | final | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | LIQUIDITY_SWEEP | BASE | LONG | final | ×1 | 7/7/7 | 42.9 | 1.498 | 0.019 | INSUFFICIENT_EVIDENCE | 3532.89 | 3487.08 / 1.969 | 94.97 / 10 |
| 1h | LIQUIDITY_SWEEP | BASE | SHORT | final | ×1 | 8/8/8 | 25.0 | 0.308 | -0.436 | INSUFFICIENT_EVIDENCE | -4691.39 | 4691.39 / 3.487 | 208.09 / 27 |
| 1h | LIQUIDITY_SWEEP | STRICT | LONG | final | ×1 | 6/6/6 | 50.0 | 2.148 | 0.207 | INSUFFICIENT_EVIDENCE | 5677.86 | 2227.56 / 1.161 | 94.97 / 10 |
| 1h | LIQUIDITY_SWEEP | STRICT | SHORT | final | ×1 | 7/7/7 | 28.6 | 0.414 | -0.331 | INSUFFICIENT_EVIDENCE | -2952.30 | 4012.60 / 3.003 | 200.16 / 26 |
| 1h | RANGE_REJECTION | BASE | LONG | final | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | RANGE_REJECTION | BASE | SHORT | final | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | RANGE_REJECTION | STRICT | LONG | final | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | RANGE_REJECTION | STRICT | SHORT | final | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | TREND_PULLBACK | BASE | LONG | final | ×1.5 | 13/11/11 | 27.3 | 0.359 | -0.500 | INSUFFICIENT_EVIDENCE | -8423.29 | 8423.29 / 5.499 | 372.99 / 31 |
| 1h | TREND_PULLBACK | BASE | SHORT | final | ×1.5 | 16/13/13 | 30.8 | 0.538 | -0.267 | INSUFFICIENT_EVIDENCE | -6500.08 | 6500.08 / 4.134 | 296.29 / 30 |
| 1h | TREND_PULLBACK | STRICT | LONG | final | ×1.5 | 1/1/1 | 0.0 | 0.000 | -1.479 | INSUFFICIENT_EVIDENCE | -1395.42 | 1395.42 / 1.479 | 27.46 / 2 |
| 1h | TREND_PULLBACK | STRICT | SHORT | final | ×1.5 | 2/2/2 | 0.0 | 0.000 | -0.677 | INSUFFICIENT_EVIDENCE | -1757.63 | 1757.63 / 1.353 | -42.47 / 0 |
| 1h | BREAKOUT_RETEST | BASE | LONG | final | ×1.5 | 14/13/13 | 30.8 | 0.372 | -0.398 | INSUFFICIENT_EVIDENCE | -10824.10 | 10824.10 / 5.171 | 342.55 / 24 |
| 1h | BREAKOUT_RETEST | BASE | SHORT | final | ×1.5 | 24/19/19 | 57.9 | 1.863 | 0.181 | INSUFFICIENT_EVIDENCE | 11232.68 | 6522.06 / 3.638 | 613.35 / 52 |
| 1h | BREAKOUT_RETEST | STRICT | LONG | final | ×1.5 | 11/10/10 | 30.0 | 0.400 | -0.401 | INSUFFICIENT_EVIDENCE | -9178.73 | 9489.91 / 4.942 | 216.45 / 12 |
| 1h | BREAKOUT_RETEST | STRICT | SHORT | final | ×1.5 | 23/19/19 | 57.9 | 1.863 | 0.181 | INSUFFICIENT_EVIDENCE | 11232.68 | 6522.06 / 3.638 | 613.35 / 52 |
| 1h | MOMENTUM_EXPANSION | BASE | LONG | final | ×1.5 | 39/34/34 | 38.2 | 0.828 | -0.043 | [-0.505; 0.412] | -4031.37 | 10464.13 / 8.711 | 588.73 / 49 |
| 1h | MOMENTUM_EXPANSION | BASE | SHORT | final | ×1.5 | 54/43/43 | 39.5 | 1.351 | -0.028 | [-0.615; 0.572] | 10253.77 | 12142.48 / 15.152 | 941.09 / 81 |
| 1h | MOMENTUM_EXPANSION | STRICT | LONG | final | ×1.5 | 28/25/25 | 40.0 | 0.971 | 0.070 | INSUFFICIENT_EVIDENCE | -483.11 | 8767.09 / 6.959 | 364.97 / 32 |
| 1h | MOMENTUM_EXPANSION | STRICT | SHORT | final | ×1.5 | 47/41/41 | 39.0 | 1.387 | -0.024 | [-0.681; 0.562] | 10942.87 | 12414.92 / 15.494 | 866.23 / 75 |
| 1h | MEAN_REVERSION | BASE | LONG | final | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | MEAN_REVERSION | BASE | SHORT | final | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | MEAN_REVERSION | STRICT | LONG | final | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | MEAN_REVERSION | STRICT | SHORT | final | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | LIQUIDITY_SWEEP | BASE | LONG | final | ×1.5 | 7/7/7 | 42.9 | 1.354 | -0.042 | INSUFFICIENT_EVIDENCE | 2685.77 | 3894.16 / 2.152 | 142.46 / 10 |
| 1h | LIQUIDITY_SWEEP | BASE | SHORT | final | ×1.5 | 8/8/8 | 25.0 | 0.241 | -0.521 | INSUFFICIENT_EVIDENCE | -5759.54 | 5759.54 / 4.165 | 312.13 / 27 |
| 1h | LIQUIDITY_SWEEP | STRICT | LONG | final | ×1.5 | 6/6/6 | 50.0 | 1.925 | 0.143 | INSUFFICIENT_EVIDENCE | 4932.06 | 2382.20 / 1.242 | 142.46 / 10 |
| 1h | LIQUIDITY_SWEEP | STRICT | SHORT | final | ×1.5 | 7/7/7 | 28.6 | 0.320 | -0.416 | INSUFFICIENT_EVIDENCE | -3894.79 | 4374.18 / 3.270 | 300.23 / 26 |
| 1h | RANGE_REJECTION | BASE | LONG | final | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | RANGE_REJECTION | BASE | SHORT | final | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | RANGE_REJECTION | STRICT | LONG | final | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | RANGE_REJECTION | STRICT | SHORT | final | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | TREND_PULLBACK | BASE | LONG | final | ×2 | 13/11/11 | 18.2 | 0.310 | -0.613 | INSUFFICIENT_EVIDENCE | -9928.86 | 9928.86 / 6.746 | 497.32 / 31 |
| 1h | TREND_PULLBACK | BASE | SHORT | final | ×2 | 16/13/13 | 30.8 | 0.460 | -0.375 | INSUFFICIENT_EVIDENCE | -8268.70 | 8268.70 / 4.881 | 417.25 / 30 |
| 1h | TREND_PULLBACK | STRICT | LONG | final | ×2 | 1/1/1 | 0.0 | 0.000 | -1.639 | INSUFFICIENT_EVIDENCE | -1546.06 | 1546.06 / 1.639 | 36.61 / 2 |
| 1h | TREND_PULLBACK | STRICT | SHORT | final | ×2 | 2/2/2 | 0.0 | 0.000 | -0.777 | INSUFFICIENT_EVIDENCE | -2013.17 | 2013.17 / 1.554 | -41.43 / 0 |
| 1h | BREAKOUT_RETEST | BASE | LONG | final | ×2 | 14/13/13 | 30.8 | 0.320 | -0.469 | INSUFFICIENT_EVIDENCE | -12551.02 | 12551.02 / 6.102 | 459.20 / 24 |
| 1h | BREAKOUT_RETEST | BASE | SHORT | final | ×2 | 24/19/19 | 52.6 | 1.610 | 0.108 | INSUFFICIENT_EVIDENCE | 8632.35 | 6851.00 / 3.851 | 817.80 / 52 |
| 1h | BREAKOUT_RETEST | STRICT | LONG | final | ×2 | 11/10/10 | 30.0 | 0.353 | -0.477 | INSUFFICIENT_EVIDENCE | -10536.94 | 10536.94 / 5.255 | 291.07 / 12 |
| 1h | BREAKOUT_RETEST | STRICT | SHORT | final | ×2 | 23/19/19 | 52.6 | 1.610 | 0.108 | INSUFFICIENT_EVIDENCE | 8632.35 | 6851.00 / 3.851 | 817.80 / 52 |
| 1h | MOMENTUM_EXPANSION | BASE | LONG | final | ×2 | 39/34/34 | 38.2 | 0.678 | -0.178 | [-0.591; 0.241] | -8411.12 | 13866.38 / 11.747 | 788.03 / 49 |
| 1h | MOMENTUM_EXPANSION | BASE | SHORT | final | ×2 | 54/43/43 | 39.5 | 1.141 | -0.156 | [-0.757; 0.414] | 4574.65 | 14907.66 / 18.517 | 1264.30 / 81 |
| 1h | MOMENTUM_EXPANSION | STRICT | LONG | final | ×2 | 28/25/25 | 40.0 | 0.801 | -0.060 | INSUFFICIENT_EVIDENCE | -3675.38 | 10260.29 / 8.196 | 489.68 / 32 |
| 1h | MOMENTUM_EXPANSION | STRICT | SHORT | final | ×2 | 47/41/41 | 39.0 | 1.177 | -0.153 | [-0.744; 0.433] | 5556.05 | 15050.44 / 18.697 | 1164.50 / 75 |
| 1h | MEAN_REVERSION | BASE | LONG | final | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | MEAN_REVERSION | BASE | SHORT | final | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | MEAN_REVERSION | STRICT | LONG | final | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | MEAN_REVERSION | STRICT | SHORT | final | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | LIQUIDITY_SWEEP | BASE | LONG | final | ×2 | 7/7/7 | 42.9 | 1.228 | -0.104 | INSUFFICIENT_EVIDENCE | 1838.62 | 4301.27 / 2.335 | 189.95 / 10 |
| 1h | LIQUIDITY_SWEEP | BASE | SHORT | final | ×2 | 8/8/8 | 25.0 | 0.188 | -0.605 | INSUFFICIENT_EVIDENCE | -6827.67 | 6827.67 / 4.843 | 416.17 / 27 |
| 1h | LIQUIDITY_SWEEP | STRICT | LONG | final | ×2 | 6/6/6 | 50.0 | 1.732 | 0.080 | INSUFFICIENT_EVIDENCE | 4186.25 | 2536.85 / 1.322 | 189.95 / 10 |
| 1h | LIQUIDITY_SWEEP | STRICT | SHORT | final | ×2 | 7/7/7 | 28.6 | 0.246 | -0.501 | INSUFFICIENT_EVIDENCE | -4837.26 | 4837.26 / 3.537 | 400.31 / 26 |
| 1h | RANGE_REJECTION | BASE | LONG | final | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | RANGE_REJECTION | BASE | SHORT | final | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | RANGE_REJECTION | STRICT | LONG | final | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 1h | RANGE_REJECTION | STRICT | SHORT | final | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | TREND_PULLBACK | BASE | LONG | train | ×1 | 8/6/6 | 33.3 | 0.248 | -0.560 | INSUFFICIENT_EVIDENCE | -3013.54 | 4004.81 / 4.520 | 298.70 / 81 |
| 4h | TREND_PULLBACK | BASE | SHORT | train | ×1 | 24/19/19 | 21.1 | 0.337 | -0.557 | INSUFFICIENT_EVIDENCE | -11992.20 | 11992.20 / 10.577 | 640.17 / 222 |
| 4h | TREND_PULLBACK | STRICT | LONG | train | ×1 | 3/2/2 | 50.0 | 0.303 | -0.523 | INSUFFICIENT_EVIDENCE | -667.16 | 957.20 / 1.122 | 166.33 / 29 |
| 4h | TREND_PULLBACK | STRICT | SHORT | train | ×1 | 4/4/4 | 0.0 | 0.000 | -1.155 | INSUFFICIENT_EVIDENCE | -4392.53 | 4392.53 / 4.618 | 36.74 / 13 |
| 4h | BREAKOUT_RETEST | BASE | LONG | train | ×1 | 22/18/18 | 38.9 | 0.595 | -0.048 | INSUFFICIENT_EVIDENCE | -6943.42 | 11056.91 / 7.320 | 547.08 / 168 |
| 4h | BREAKOUT_RETEST | BASE | SHORT | train | ×1 | 20/16/16 | 81.2 | 7.269 | 0.912 | INSUFFICIENT_EVIDENCE | 21323.12 | 1518.93 / 1.110 | 512.05 / 162 |
| 4h | BREAKOUT_RETEST | STRICT | LONG | train | ×1 | 13/11/11 | 36.4 | 0.670 | -0.081 | INSUFFICIENT_EVIDENCE | -3205.59 | 6190.69 / 4.375 | 362.25 / 117 |
| 4h | BREAKOUT_RETEST | STRICT | SHORT | train | ×1 | 15/12/12 | 83.3 | 7.364 | 0.806 | INSUFFICIENT_EVIDENCE | 14804.20 | 1518.93 / 1.110 | 439.12 / 143 |
| 4h | MOMENTUM_EXPANSION | BASE | LONG | train | ×1 | 9/8/8 | 25.0 | 0.689 | -0.477 | INSUFFICIENT_EVIDENCE | -1744.10 | 2781.84 / 5.027 | 170.62 / 44 |
| 4h | MOMENTUM_EXPANSION | BASE | SHORT | train | ×1 | 25/19/19 | 36.8 | 0.969 | 0.003 | INSUFFICIENT_EVIDENCE | -463.25 | 5697.60 / 5.689 | 410.42 / 122 |
| 4h | MOMENTUM_EXPANSION | STRICT | LONG | train | ×1 | 6/5/5 | 40.0 | 2.371 | -0.083 | INSUFFICIENT_EVIDENCE | 2234.86 | 1629.92 / 3.619 | 100.87 / 32 |
| 4h | MOMENTUM_EXPANSION | STRICT | SHORT | train | ×1 | 9/9/9 | 22.2 | 0.462 | -0.557 | INSUFFICIENT_EVIDENCE | -4339.15 | 4868.17 / 6.292 | 209.39 / 59 |
| 4h | MEAN_REVERSION | BASE | LONG | train | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | MEAN_REVERSION | BASE | SHORT | train | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | MEAN_REVERSION | STRICT | LONG | train | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | MEAN_REVERSION | STRICT | SHORT | train | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | LIQUIDITY_SWEEP | BASE | LONG | train | ×1 | 22/22/22 | 36.4 | 0.623 | -0.108 | INSUFFICIENT_EVIDENCE | -7568.80 | 10711.12 / 7.894 | 458.50 / 152 |
| 4h | LIQUIDITY_SWEEP | BASE | SHORT | train | ×1 | 15/13/13 | 23.1 | 0.529 | -0.506 | INSUFFICIENT_EVIDENCE | -5073.26 | 9916.34 / 9.216 | 361.03 / 106 |
| 4h | LIQUIDITY_SWEEP | STRICT | LONG | train | ×1 | 13/13/13 | 46.2 | 0.758 | 0.187 | INSUFFICIENT_EVIDENCE | -2755.82 | 8846.18 / 4.671 | 322.08 / 106 |
| 4h | LIQUIDITY_SWEEP | STRICT | SHORT | train | ×1 | 11/10/10 | 20.0 | 0.593 | -0.518 | INSUFFICIENT_EVIDENCE | -3780.43 | 8623.51 / 7.820 | 223.08 / 71 |
| 4h | RANGE_REJECTION | BASE | LONG | train | ×1 | 2/1/1 | 100.0 | — | 1.821 | INSUFFICIENT_EVIDENCE | 3263.25 | 0.00 / 0.000 | 30.37 / 5 |
| 4h | RANGE_REJECTION | BASE | SHORT | train | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | RANGE_REJECTION | STRICT | LONG | train | ×1 | 1/1/1 | 100.0 | — | 1.845 | INSUFFICIENT_EVIDENCE | 3253.05 | 0.00 / 0.000 | 18.53 / 3 |
| 4h | RANGE_REJECTION | STRICT | SHORT | train | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | TREND_PULLBACK | BASE | LONG | train | ×1.5 | 8/6/6 | 33.3 | 0.179 | -0.626 | INSUFFICIENT_EVIDENCE | -3476.90 | 4233.05 / 4.780 | 448.05 / 81 |
| 4h | TREND_PULLBACK | BASE | SHORT | train | ×1.5 | 24/19/19 | 21.1 | 0.301 | -0.623 | INSUFFICIENT_EVIDENCE | -13247.61 | 13247.61 / 11.829 | 960.25 / 222 |
| 4h | TREND_PULLBACK | STRICT | LONG | train | ×1.5 | 3/2/2 | 50.0 | 0.113 | -0.576 | INSUFFICIENT_EVIDENCE | -894.88 | 1009.19 / 1.183 | 249.50 / 29 |
| 4h | TREND_PULLBACK | STRICT | SHORT | train | ×1.5 | 4/4/4 | 0.0 | 0.000 | -1.232 | INSUFFICIENT_EVIDENCE | -4578.36 | 4578.36 / 4.927 | 55.11 / 13 |
| 4h | BREAKOUT_RETEST | BASE | LONG | train | ×1.5 | 22/18/18 | 38.9 | 0.546 | -0.102 | INSUFFICIENT_EVIDENCE | -8147.49 | 11937.75 / 7.858 | 820.62 / 168 |
| 4h | BREAKOUT_RETEST | BASE | SHORT | train | ×1.5 | 20/16/16 | 81.2 | 6.721 | 0.861 | INSUFFICIENT_EVIDENCE | 20300.60 | 1594.01 / 1.165 | 768.08 / 162 |
| 4h | BREAKOUT_RETEST | STRICT | LONG | train | ×1.5 | 13/11/11 | 36.4 | 0.617 | -0.137 | INSUFFICIENT_EVIDENCE | -3913.52 | 6442.46 / 4.562 | 543.37 / 117 |
| 4h | BREAKOUT_RETEST | STRICT | SHORT | train | ×1.5 | 15/12/12 | 83.3 | 6.758 | 0.752 | INSUFFICIENT_EVIDENCE | 14018.50 | 1594.01 / 1.165 | 658.68 / 143 |
| 4h | MOMENTUM_EXPANSION | BASE | LONG | train | ×1.5 | 9/8/8 | 25.0 | 0.622 | -0.557 | INSUFFICIENT_EVIDENCE | -2262.12 | 3074.29 / 5.524 | 255.92 / 44 |
| 4h | MOMENTUM_EXPANSION | BASE | SHORT | train | ×1.5 | 25/19/19 | 36.8 | 0.895 | -0.065 | INSUFFICIENT_EVIDENCE | -1637.37 | 6071.46 / 6.255 | 615.63 / 122 |
| 4h | MOMENTUM_EXPANSION | STRICT | LONG | train | ×1.5 | 6/5/5 | 40.0 | 2.107 | -0.171 | INSUFFICIENT_EVIDENCE | 1953.12 | 1764.92 / 3.928 | 151.31 / 32 |
| 4h | MOMENTUM_EXPANSION | STRICT | SHORT | train | ×1.5 | 9/9/9 | 22.2 | 0.420 | -0.625 | INSUFFICIENT_EVIDENCE | -4904.25 | 5245.38 / 6.798 | 314.09 / 59 |
| 4h | MEAN_REVERSION | BASE | LONG | train | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | MEAN_REVERSION | BASE | SHORT | train | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | MEAN_REVERSION | STRICT | LONG | train | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | MEAN_REVERSION | STRICT | SHORT | train | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | LIQUIDITY_SWEEP | BASE | LONG | train | ×1.5 | 22/22/22 | 36.4 | 0.574 | -0.163 | INSUFFICIENT_EVIDENCE | -8932.80 | 11761.20 / 8.627 | 687.75 / 152 |
| 4h | LIQUIDITY_SWEEP | BASE | SHORT | train | ×1.5 | 15/13/13 | 23.1 | 0.480 | -0.564 | INSUFFICIENT_EVIDENCE | -5890.30 | 10538.90 / 9.793 | 541.54 / 106 |
| 4h | LIQUIDITY_SWEEP | STRICT | LONG | train | ×1.5 | 13/13/13 | 46.2 | 0.700 | 0.132 | INSUFFICIENT_EVIDENCE | -3585.28 | 9204.16 / 5.005 | 483.13 / 106 |
| 4h | LIQUIDITY_SWEEP | STRICT | SHORT | train | ×1.5 | 11/10/10 | 20.0 | 0.551 | -0.577 | INSUFFICIENT_EVIDENCE | -4361.80 | 9010.40 / 8.230 | 334.62 / 71 |
| 4h | RANGE_REJECTION | BASE | LONG | train | ×1.5 | 2/1/1 | 100.0 | — | 1.761 | INSUFFICIENT_EVIDENCE | 3154.25 | 0.00 / 0.000 | 45.55 / 5 |
| 4h | RANGE_REJECTION | BASE | SHORT | train | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | RANGE_REJECTION | STRICT | LONG | train | ×1.5 | 1/1/1 | 100.0 | — | 1.787 | INSUFFICIENT_EVIDENCE | 3149.95 | 0.00 / 0.000 | 27.80 / 3 |
| 4h | RANGE_REJECTION | STRICT | SHORT | train | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | TREND_PULLBACK | BASE | LONG | train | ×2 | 8/6/6 | 16.7 | 0.129 | -0.692 | INSUFFICIENT_EVIDENCE | -3940.26 | 4461.30 / 5.040 | 597.40 / 81 |
| 4h | TREND_PULLBACK | BASE | SHORT | train | ×2 | 24/19/19 | 21.1 | 0.269 | -0.688 | INSUFFICIENT_EVIDENCE | -14502.98 | 14502.98 / 13.080 | 1280.33 / 222 |
| 4h | TREND_PULLBACK | STRICT | LONG | train | ×2 | 3/2/2 | 0.0 | 0.000 | -0.630 | INSUFFICIENT_EVIDENCE | -1122.59 | 1122.59 / 1.260 | 332.67 / 29 |
| 4h | TREND_PULLBACK | STRICT | SHORT | train | ×2 | 4/4/4 | 0.0 | 0.000 | -1.309 | INSUFFICIENT_EVIDENCE | -4764.19 | 4764.19 / 5.237 | 73.48 / 13 |
| 4h | BREAKOUT_RETEST | BASE | LONG | train | ×2 | 22/18/18 | 38.9 | 0.500 | -0.157 | INSUFFICIENT_EVIDENCE | -9369.55 | 12836.57 / 8.406 | 1112.10 / 170 |
| 4h | BREAKOUT_RETEST | BASE | SHORT | train | ×2 | 20/16/16 | 68.8 | 6.186 | 0.810 | INSUFFICIENT_EVIDENCE | 19278.12 | 1669.09 / 1.226 | 1024.11 / 162 |
| 4h | BREAKOUT_RETEST | STRICT | LONG | train | ×2 | 13/11/11 | 36.4 | 0.567 | -0.193 | INSUFFICIENT_EVIDENCE | -4639.42 | 6694.24 / 4.749 | 742.44 / 119 |
| 4h | BREAKOUT_RETEST | STRICT | SHORT | train | ×2 | 15/12/12 | 66.7 | 6.160 | 0.699 | INSUFFICIENT_EVIDENCE | 13232.81 | 1669.09 / 1.226 | 878.24 / 143 |
| 4h | MOMENTUM_EXPANSION | BASE | LONG | train | ×2 | 9/8/8 | 25.0 | 0.562 | -0.637 | INSUFFICIENT_EVIDENCE | -2780.17 | 3366.75 / 6.020 | 341.23 / 44 |
| 4h | MOMENTUM_EXPANSION | BASE | SHORT | train | ×2 | 25/19/19 | 36.8 | 0.827 | -0.134 | INSUFFICIENT_EVIDENCE | -2811.46 | 6445.31 / 6.820 | 820.84 / 122 |
| 4h | MOMENTUM_EXPANSION | STRICT | LONG | train | ×2 | 6/5/5 | 40.0 | 1.880 | -0.259 | INSUFFICIENT_EVIDENCE | 1671.37 | 1899.92 / 4.238 | 201.74 / 32 |
| 4h | MOMENTUM_EXPANSION | STRICT | SHORT | train | ×2 | 9/9/9 | 22.2 | 0.382 | -0.693 | INSUFFICIENT_EVIDENCE | -5469.34 | 5622.58 / 7.304 | 418.79 / 59 |
| 4h | MEAN_REVERSION | BASE | LONG | train | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | MEAN_REVERSION | BASE | SHORT | train | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | MEAN_REVERSION | STRICT | LONG | train | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | MEAN_REVERSION | STRICT | SHORT | train | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | LIQUIDITY_SWEEP | BASE | LONG | train | ×2 | 22/22/22 | 36.4 | 0.530 | -0.218 | INSUFFICIENT_EVIDENCE | -10296.85 | 12811.33 / 9.361 | 917.00 / 152 |
| 4h | LIQUIDITY_SWEEP | BASE | SHORT | train | ×2 | 15/13/13 | 15.4 | 0.437 | -0.623 | INSUFFICIENT_EVIDENCE | -6707.31 | 11161.44 / 10.369 | 722.06 / 106 |
| 4h | LIQUIDITY_SWEEP | STRICT | LONG | train | ×2 | 13/13/13 | 46.2 | 0.647 | 0.077 | INSUFFICIENT_EVIDENCE | -4414.77 | 9562.15 / 5.339 | 644.17 / 106 |
| 4h | LIQUIDITY_SWEEP | STRICT | SHORT | train | ×2 | 11/10/10 | 20.0 | 0.513 | -0.636 | INSUFFICIENT_EVIDENCE | -4943.14 | 9397.27 / 8.640 | 446.17 / 71 |
| 4h | RANGE_REJECTION | BASE | LONG | train | ×2 | 2/1/1 | 100.0 | — | 1.700 | INSUFFICIENT_EVIDENCE | 3045.24 | 0.00 / 0.000 | 60.74 / 5 |
| 4h | RANGE_REJECTION | BASE | SHORT | train | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | RANGE_REJECTION | STRICT | LONG | train | ×2 | 1/1/1 | 100.0 | — | 1.729 | INSUFFICIENT_EVIDENCE | 3046.84 | 0.00 / 0.000 | 37.07 / 3 |
| 4h | RANGE_REJECTION | STRICT | SHORT | train | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | TREND_PULLBACK | BASE | LONG | validation | ×1 | 12/9/9 | 11.1 | 0.096 | -0.732 | INSUFFICIENT_EVIDENCE | -16437.01 | 16437.01 / 6.599 | 279.47 / 55 |
| 4h | TREND_PULLBACK | BASE | SHORT | validation | ×1 | 3/3/3 | 100.0 | — | 2.287 | INSUFFICIENT_EVIDENCE | 13035.24 | 0.00 / 0.000 | 265.61 / 44 |
| 4h | TREND_PULLBACK | STRICT | LONG | validation | ×1 | 5/4/4 | 0.0 | 0.000 | -1.083 | INSUFFICIENT_EVIDENCE | -12706.37 | 12706.37 / 4.334 | 146.94 / 22 |
| 4h | TREND_PULLBACK | STRICT | SHORT | validation | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | BREAKOUT_RETEST | BASE | LONG | validation | ×1 | 15/10/10 | 60.0 | 1.687 | 0.392 | INSUFFICIENT_EVIDENCE | 5890.21 | 2913.15 / 1.122 | 428.06 / 87 |
| 4h | BREAKOUT_RETEST | BASE | SHORT | validation | ×1 | 8/6/6 | 50.0 | 5.281 | 0.720 | INSUFFICIENT_EVIDENCE | 7599.63 | 1696.19 / 1.275 | 264.23 / 52 |
| 4h | BREAKOUT_RETEST | STRICT | LONG | validation | ×1 | 10/9/9 | 66.7 | 2.458 | 0.490 | INSUFFICIENT_EVIDENCE | 8715.41 | 2913.15 / 1.122 | 493.66 / 97 |
| 4h | BREAKOUT_RETEST | STRICT | SHORT | validation | ×1 | 5/4/4 | 50.0 | 3.923 | 0.639 | INSUFFICIENT_EVIDENCE | 4202.53 | 1437.97 / 1.181 | 173.16 / 32 |
| 4h | MOMENTUM_EXPANSION | BASE | LONG | validation | ×1 | 15/12/12 | 50.0 | 0.989 | 0.179 | INSUFFICIENT_EVIDENCE | -88.32 | 4032.27 / 2.980 | 611.91 / 116 |
| 4h | MOMENTUM_EXPANSION | BASE | SHORT | validation | ×1 | 11/9/9 | 33.3 | 0.559 | -0.224 | INSUFFICIENT_EVIDENCE | -5776.84 | 8506.66 / 4.538 | 226.15 / 47 |
| 4h | MOMENTUM_EXPANSION | STRICT | LONG | validation | ×1 | 8/7/7 | 57.1 | 1.179 | 0.511 | INSUFFICIENT_EVIDENCE | 893.21 | 4020.03 / 2.293 | 302.55 / 58 |
| 4h | MOMENTUM_EXPANSION | STRICT | SHORT | validation | ×1 | 4/4/4 | 0.0 | 0.000 | -0.981 | INSUFFICIENT_EVIDENCE | -5048.77 | 5048.77 / 3.924 | 89.92 / 22 |
| 4h | MEAN_REVERSION | BASE | LONG | validation | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | MEAN_REVERSION | BASE | SHORT | validation | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | MEAN_REVERSION | STRICT | LONG | validation | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | MEAN_REVERSION | STRICT | SHORT | validation | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | LIQUIDITY_SWEEP | BASE | LONG | validation | ×1 | 8/8/8 | 12.5 | 0.256 | -0.747 | INSUFFICIENT_EVIDENCE | -10375.01 | 12110.70 / 6.718 | 220.23 / 36 |
| 4h | LIQUIDITY_SWEEP | BASE | SHORT | validation | ×1 | 7/7/7 | 14.3 | 0.457 | -0.430 | INSUFFICIENT_EVIDENCE | -5729.50 | 7032.93 / 3.012 | 371.84 / 62 |
| 4h | LIQUIDITY_SWEEP | STRICT | LONG | validation | ×1 | 3/3/3 | 0.0 | 0.000 | -1.110 | INSUFFICIENT_EVIDENCE | -6238.95 | 6238.95 / 3.331 | 43.17 / 7 |
| 4h | LIQUIDITY_SWEEP | STRICT | SHORT | validation | ×1 | 6/6/6 | 16.7 | 0.668 | -0.320 | INSUFFICIENT_EVIDENCE | -2397.90 | 3701.33 / 2.191 | 309.47 / 53 |
| 4h | RANGE_REJECTION | BASE | LONG | validation | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | RANGE_REJECTION | BASE | SHORT | validation | ×1 | 1/1/1 | 0.0 | 0.000 | -1.160 | INSUFFICIENT_EVIDENCE | -1402.58 | 1402.58 / 1.160 | 6.14 / 1 |
| 4h | RANGE_REJECTION | STRICT | LONG | validation | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | RANGE_REJECTION | STRICT | SHORT | validation | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | TREND_PULLBACK | BASE | LONG | validation | ×1.5 | 12/9/9 | 11.1 | 0.087 | -0.792 | INSUFFICIENT_EVIDENCE | -17269.03 | 17269.03 / 7.128 | 419.21 / 55 |
| 4h | TREND_PULLBACK | BASE | SHORT | validation | ×1.5 | 3/3/3 | 100.0 | — | 2.213 | INSUFFICIENT_EVIDENCE | 12621.63 | 0.00 / 0.000 | 398.42 / 44 |
| 4h | TREND_PULLBACK | STRICT | LONG | validation | ×1.5 | 5/4/4 | 0.0 | 0.000 | -1.125 | INSUFFICIENT_EVIDENCE | -13169.08 | 13169.08 / 4.501 | 220.41 / 22 |
| 4h | TREND_PULLBACK | STRICT | SHORT | validation | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | BREAKOUT_RETEST | BASE | LONG | validation | ×1.5 | 15/10/10 | 60.0 | 1.547 | 0.336 | INSUFFICIENT_EVIDENCE | 4896.12 | 3011.87 / 1.182 | 642.09 / 87 |
| 4h | BREAKOUT_RETEST | BASE | SHORT | validation | ×1.5 | 8/6/6 | 50.0 | 4.298 | 0.659 | INSUFFICIENT_EVIDENCE | 6963.46 | 1885.61 / 1.387 | 396.35 / 52 |
| 4h | BREAKOUT_RETEST | STRICT | LONG | validation | ×1.5 | 10/9/9 | 66.7 | 2.248 | 0.433 | INSUFFICIENT_EVIDENCE | 7781.98 | 3011.87 / 1.182 | 740.49 / 97 |
| 4h | BREAKOUT_RETEST | STRICT | SHORT | validation | ×1.5 | 5/4/4 | 50.0 | 3.259 | 0.570 | INSUFFICIENT_EVIDENCE | 3771.62 | 1669.39 / 1.325 | 259.75 / 32 |
| 4h | MOMENTUM_EXPANSION | BASE | LONG | validation | ×1.5 | 15/12/12 | 41.7 | 0.851 | 0.095 | INSUFFICIENT_EVIDENCE | -1343.59 | 4754.46 / 3.520 | 917.86 / 116 |
| 4h | MOMENTUM_EXPANSION | BASE | SHORT | validation | ×1.5 | 11/9/9 | 22.2 | 0.517 | -0.297 | INSUFFICIENT_EVIDENCE | -6660.14 | 9184.56 / 4.912 | 339.23 / 47 |
| 4h | MOMENTUM_EXPANSION | STRICT | LONG | validation | ×1.5 | 8/7/7 | 57.1 | 1.044 | 0.428 | INSUFFICIENT_EVIDENCE | 230.49 | 4276.61 / 2.440 | 453.83 / 58 |
| 4h | MOMENTUM_EXPANSION | STRICT | SHORT | validation | ×1.5 | 4/4/4 | 0.0 | 0.000 | -1.067 | INSUFFICIENT_EVIDENCE | -5402.12 | 5402.12 / 4.267 | 134.88 / 22 |
| 4h | MEAN_REVERSION | BASE | LONG | validation | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | MEAN_REVERSION | BASE | SHORT | validation | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | MEAN_REVERSION | STRICT | LONG | validation | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | MEAN_REVERSION | STRICT | SHORT | validation | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | LIQUIDITY_SWEEP | BASE | LONG | validation | ×1.5 | 8/8/8 | 12.5 | 0.236 | -0.809 | INSUFFICIENT_EVIDENCE | -11231.09 | 12739.12 / 7.078 | 330.34 / 36 |
| 4h | LIQUIDITY_SWEEP | BASE | SHORT | validation | ×1.5 | 7/7/7 | 14.3 | 0.421 | -0.484 | INSUFFICIENT_EVIDENCE | -6524.69 | 7603.26 / 3.385 | 557.76 / 62 |
| 4h | LIQUIDITY_SWEEP | STRICT | LONG | validation | ×1.5 | 3/3/3 | 0.0 | 0.000 | -1.166 | INSUFFICIENT_EVIDENCE | -6536.46 | 6536.46 / 3.497 | 64.75 / 7 |
| 4h | LIQUIDITY_SWEEP | STRICT | SHORT | validation | ×1.5 | 6/6/6 | 16.7 | 0.608 | -0.375 | INSUFFICIENT_EVIDENCE | -3054.77 | 4133.34 / 2.287 | 464.21 / 53 |
| 4h | RANGE_REJECTION | BASE | LONG | validation | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | RANGE_REJECTION | BASE | SHORT | validation | ×1.5 | 1/1/1 | 0.0 | 0.000 | -1.240 | INSUFFICIENT_EVIDENCE | -1499.34 | 1499.34 / 1.240 | 9.21 / 1 |
| 4h | RANGE_REJECTION | STRICT | LONG | validation | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | RANGE_REJECTION | STRICT | SHORT | validation | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | TREND_PULLBACK | BASE | LONG | validation | ×2 | 12/9/9 | 11.1 | 0.080 | -0.852 | INSUFFICIENT_EVIDENCE | -18101.08 | 18101.08 / 7.670 | 558.94 / 55 |
| 4h | TREND_PULLBACK | BASE | SHORT | validation | ×2 | 3/3/3 | 100.0 | — | 2.138 | INSUFFICIENT_EVIDENCE | 12208.04 | 0.00 / 0.000 | 531.23 / 44 |
| 4h | TREND_PULLBACK | STRICT | LONG | validation | ×2 | 5/4/4 | 0.0 | 0.000 | -1.167 | INSUFFICIENT_EVIDENCE | -13631.81 | 13631.81 / 4.668 | 293.88 / 22 |
| 4h | TREND_PULLBACK | STRICT | SHORT | validation | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | BREAKOUT_RETEST | BASE | LONG | validation | ×2 | 15/10/10 | 60.0 | 1.419 | 0.280 | INSUFFICIENT_EVIDENCE | 3902.00 | 3110.60 / 1.243 | 856.12 / 87 |
| 4h | BREAKOUT_RETEST | BASE | SHORT | validation | ×2 | 8/6/6 | 50.0 | 3.585 | 0.597 | INSUFFICIENT_EVIDENCE | 6327.30 | 2075.04 / 1.500 | 528.47 / 52 |
| 4h | BREAKOUT_RETEST | STRICT | LONG | validation | ×2 | 10/9/9 | 66.7 | 2.055 | 0.376 | INSUFFICIENT_EVIDENCE | 6848.53 | 3110.60 / 1.243 | 987.32 / 97 |
| 4h | BREAKOUT_RETEST | STRICT | SHORT | validation | ×2 | 5/4/4 | 50.0 | 2.758 | 0.501 | INSUFFICIENT_EVIDENCE | 3340.73 | 1900.81 / 1.469 | 346.33 / 32 |
| 4h | MOMENTUM_EXPANSION | BASE | LONG | validation | ×2 | 15/12/12 | 41.7 | 0.734 | 0.011 | INSUFFICIENT_EVIDENCE | -2598.88 | 5504.93 / 4.158 | 1223.82 / 116 |
| 4h | MOMENTUM_EXPANSION | BASE | SHORT | validation | ×2 | 11/9/9 | 22.2 | 0.479 | -0.370 | INSUFFICIENT_EVIDENCE | -7543.41 | 9875.58 / 5.316 | 452.31 / 47 |
| 4h | MOMENTUM_EXPANSION | STRICT | LONG | validation | ×2 | 8/7/7 | 57.1 | 0.923 | 0.344 | INSUFFICIENT_EVIDENCE | -432.24 | 4533.20 / 2.587 | 605.10 / 58 |
| 4h | MOMENTUM_EXPANSION | STRICT | SHORT | validation | ×2 | 4/4/4 | 0.0 | 0.000 | -1.152 | INSUFFICIENT_EVIDENCE | -5755.46 | 5755.46 / 4.609 | 179.84 / 22 |
| 4h | MEAN_REVERSION | BASE | LONG | validation | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | MEAN_REVERSION | BASE | SHORT | validation | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | MEAN_REVERSION | STRICT | LONG | validation | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | MEAN_REVERSION | STRICT | SHORT | validation | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | LIQUIDITY_SWEEP | BASE | LONG | validation | ×2 | 8/8/8 | 12.5 | 0.217 | -0.870 | INSUFFICIENT_EVIDENCE | -12087.20 | 13367.56 / 7.437 | 440.45 / 36 |
| 4h | LIQUIDITY_SWEEP | BASE | SHORT | validation | ×2 | 7/7/7 | 14.3 | 0.389 | -0.537 | INSUFFICIENT_EVIDENCE | -7319.86 | 8173.59 / 3.759 | 743.68 / 62 |
| 4h | LIQUIDITY_SWEEP | STRICT | LONG | validation | ×2 | 3/3/3 | 0.0 | 0.000 | -1.221 | INSUFFICIENT_EVIDENCE | -6833.99 | 6833.99 / 3.662 | 86.33 / 7 |
| 4h | LIQUIDITY_SWEEP | STRICT | SHORT | validation | ×2 | 6/6/6 | 16.7 | 0.556 | -0.430 | INSUFFICIENT_EVIDENCE | -3711.62 | 4565.35 / 2.578 | 618.95 / 53 |
| 4h | RANGE_REJECTION | BASE | LONG | validation | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | RANGE_REJECTION | BASE | SHORT | validation | ×2 | 1/1/1 | 0.0 | 0.000 | -1.320 | INSUFFICIENT_EVIDENCE | -1596.09 | 1596.09 / 1.320 | 12.28 / 1 |
| 4h | RANGE_REJECTION | STRICT | LONG | validation | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | RANGE_REJECTION | STRICT | SHORT | validation | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | TREND_PULLBACK | BASE | LONG | test | ×1 | 4/3/3 | 66.7 | 7.047 | 1.176 | INSUFFICIENT_EVIDENCE | 14200.65 | 2348.21 / 1.221 | 308.02 / 30 |
| 4h | TREND_PULLBACK | BASE | SHORT | test | ×1 | 2/2/2 | 0.0 | 0.000 | -1.092 | INSUFFICIENT_EVIDENCE | -8447.85 | 8447.85 / 2.184 | 137.65 / 15 |
| 4h | TREND_PULLBACK | STRICT | LONG | test | ×1 | 1/1/1 | 100.0 | — | 2.385 | INSUFFICIENT_EVIDENCE | 9141.85 | 0.00 / 0.000 | 115.31 / 11 |
| 4h | TREND_PULLBACK | STRICT | SHORT | test | ×1 | 1/1/1 | 0.0 | 0.000 | -1.124 | INSUFFICIENT_EVIDENCE | -3704.85 | 3704.85 / 1.124 | 113.88 / 12 |
| 4h | BREAKOUT_RETEST | BASE | LONG | test | ×1 | 7/6/6 | 16.7 | 0.107 | -0.708 | INSUFFICIENT_EVIDENCE | -18186.06 | 20354.12 / 5.542 | 336.12 / 39 |
| 4h | BREAKOUT_RETEST | BASE | SHORT | test | ×1 | 8/8/8 | 12.5 | 0.283 | -0.582 | INSUFFICIENT_EVIDENCE | -12207.80 | 15121.36 / 5.309 | 829.27 / 89 |
| 4h | BREAKOUT_RETEST | STRICT | LONG | test | ×1 | 6/5/5 | 20.0 | 0.126 | -0.619 | INSUFFICIENT_EVIDENCE | -14998.27 | 17166.33 / 4.388 | 248.44 / 31 |
| 4h | BREAKOUT_RETEST | STRICT | SHORT | test | ×1 | 7/7/7 | 0.0 | 0.000 | -0.927 | INSUFFICIENT_EVIDENCE | -17033.89 | 17033.89 / 6.490 | 677.77 / 73 |
| 4h | MOMENTUM_EXPANSION | BASE | LONG | test | ×1 | 16/14/14 | 50.0 | 1.539 | 0.396 | INSUFFICIENT_EVIDENCE | 9088.16 | 8696.61 / 4.899 | 796.89 / 75 |
| 4h | MOMENTUM_EXPANSION | BASE | SHORT | test | ×1 | 9/8/8 | 25.0 | 0.309 | -0.429 | INSUFFICIENT_EVIDENCE | -12858.92 | 14750.44 / 4.512 | 332.50 / 31 |
| 4h | MOMENTUM_EXPANSION | STRICT | LONG | test | ×1 | 14/13/13 | 53.8 | 2.075 | 0.509 | INSUFFICIENT_EVIDENCE | 13445.16 | 8696.61 / 4.899 | 778.43 / 73 |
| 4h | MOMENTUM_EXPANSION | STRICT | SHORT | test | ×1 | 8/7/7 | 28.6 | 0.365 | -0.320 | INSUFFICIENT_EVIDENCE | -10022.27 | 11913.79 / 4.512 | 229.58 / 22 |
| 4h | MEAN_REVERSION | BASE | LONG | test | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | MEAN_REVERSION | BASE | SHORT | test | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | MEAN_REVERSION | STRICT | LONG | test | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | MEAN_REVERSION | STRICT | SHORT | test | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | LIQUIDITY_SWEEP | BASE | LONG | test | ×1 | 10/10/10 | 50.0 | 1.405 | 0.181 | INSUFFICIENT_EVIDENCE | 6435.54 | 12654.72 / 4.473 | 637.83 / 68 |
| 4h | LIQUIDITY_SWEEP | BASE | SHORT | test | ×1 | 2/2/2 | 50.0 | 1.664 | 0.014 | INSUFFICIENT_EVIDENCE | 1356.71 | 2043.52 / 1.123 | 162.00 / 17 |
| 4h | LIQUIDITY_SWEEP | STRICT | LONG | test | ×1 | 8/8/8 | 50.0 | 1.349 | 0.136 | INSUFFICIENT_EVIDENCE | 4521.12 | 9723.19 / 3.327 | 514.49 / 55 |
| 4h | LIQUIDITY_SWEEP | STRICT | SHORT | test | ×1 | 2/2/2 | 50.0 | 1.664 | 0.014 | INSUFFICIENT_EVIDENCE | 1356.71 | 2043.52 / 1.123 | 162.00 / 17 |
| 4h | RANGE_REJECTION | BASE | LONG | test | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | RANGE_REJECTION | BASE | SHORT | test | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | RANGE_REJECTION | STRICT | LONG | test | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | RANGE_REJECTION | STRICT | SHORT | test | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | TREND_PULLBACK | BASE | LONG | test | ×1.5 | 4/3/3 | 66.7 | 6.293 | 1.097 | INSUFFICIENT_EVIDENCE | 13553.08 | 2560.40 / 1.331 | 462.03 / 30 |
| 4h | TREND_PULLBACK | BASE | SHORT | test | ×1.5 | 2/2/2 | 0.0 | 0.000 | -1.138 | INSUFFICIENT_EVIDENCE | -8786.78 | 8786.78 / 2.276 | 206.47 / 15 |
| 4h | TREND_PULLBACK | STRICT | LONG | test | ×1.5 | 1/1/1 | 100.0 | — | 2.327 | INSUFFICIENT_EVIDENCE | 8921.41 | 0.00 / 0.000 | 172.96 / 11 |
| 4h | TREND_PULLBACK | STRICT | SHORT | test | ×1.5 | 1/1/1 | 0.0 | 0.000 | -1.186 | INSUFFICIENT_EVIDENCE | -3909.48 | 3909.48 / 1.186 | 170.83 / 12 |
| 4h | BREAKOUT_RETEST | BASE | LONG | test | ×1.5 | 7/6/6 | 16.7 | 0.094 | -0.770 | INSUFFICIENT_EVIDENCE | -19228.23 | 21231.33 / 5.813 | 504.17 / 39 |
| 4h | BREAKOUT_RETEST | BASE | SHORT | test | ×1.5 | 8/8/8 | 12.5 | 0.250 | -0.660 | INSUFFICIENT_EVIDENCE | -13842.98 | 16390.83 / 5.759 | 1243.90 / 89 |
| 4h | BREAKOUT_RETEST | STRICT | LONG | test | ×1.5 | 6/5/5 | 20.0 | 0.112 | -0.677 | INSUFFICIENT_EVIDENCE | -15827.80 | 17830.90 / 4.582 | 372.66 / 31 |
| 4h | BREAKOUT_RETEST | STRICT | SHORT | test | ×1.5 | 7/7/7 | 0.0 | 0.000 | -1.004 | INSUFFICIENT_EVIDENCE | -18449.90 | 18449.90 / 7.031 | 1016.65 / 73 |
| 4h | MOMENTUM_EXPANSION | BASE | LONG | test | ×1.5 | 16/14/14 | 50.0 | 1.358 | 0.292 | INSUFFICIENT_EVIDENCE | 6476.38 | 9451.08 / 5.348 | 1195.33 / 75 |
| 4h | MOMENTUM_EXPANSION | BASE | SHORT | test | ×1.5 | 9/8/8 | 25.0 | 0.273 | -0.506 | INSUFFICIENT_EVIDENCE | -14236.36 | 15876.59 / 4.942 | 498.74 / 31 |
| 4h | MOMENTUM_EXPANSION | STRICT | LONG | test | ×1.5 | 14/13/13 | 53.8 | 1.808 | 0.400 | INSUFFICIENT_EVIDENCE | 10983.13 | 9451.08 / 5.348 | 1167.65 / 73 |
| 4h | MOMENTUM_EXPANSION | STRICT | SHORT | test | ×1.5 | 8/7/7 | 28.6 | 0.324 | -0.394 | INSUFFICIENT_EVIDENCE | -11170.90 | 12811.13 / 4.768 | 344.37 / 22 |
| 4h | MEAN_REVERSION | BASE | LONG | test | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | MEAN_REVERSION | BASE | SHORT | test | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | MEAN_REVERSION | STRICT | LONG | test | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | MEAN_REVERSION | STRICT | SHORT | test | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | LIQUIDITY_SWEEP | BASE | LONG | test | ×1.5 | 10/10/10 | 50.0 | 1.279 | 0.122 | INSUFFICIENT_EVIDENCE | 4660.67 | 13318.94 / 4.710 | 956.75 / 68 |
| 4h | LIQUIDITY_SWEEP | BASE | SHORT | test | ×1.5 | 2/2/2 | 50.0 | 1.471 | -0.056 | INSUFFICIENT_EVIDENCE | 1014.44 | 2155.55 / 1.185 | 243.00 / 17 |
| 4h | LIQUIDITY_SWEEP | STRICT | LONG | test | ×1.5 | 8/8/8 | 50.0 | 1.228 | 0.078 | INSUFFICIENT_EVIDENCE | 3099.38 | 10199.88 / 3.490 | 771.74 / 55 |
| 4h | LIQUIDITY_SWEEP | STRICT | SHORT | test | ×1.5 | 2/2/2 | 50.0 | 1.471 | -0.056 | INSUFFICIENT_EVIDENCE | 1014.44 | 2155.55 / 1.185 | 243.00 / 17 |
| 4h | RANGE_REJECTION | BASE | LONG | test | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | RANGE_REJECTION | BASE | SHORT | test | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | RANGE_REJECTION | STRICT | LONG | test | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | RANGE_REJECTION | STRICT | SHORT | test | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | TREND_PULLBACK | BASE | LONG | test | ×2 | 4/3/3 | 66.7 | 5.655 | 1.018 | INSUFFICIENT_EVIDENCE | 12905.49 | 2772.60 / 1.441 | 616.04 / 30 |
| 4h | TREND_PULLBACK | BASE | SHORT | test | ×2 | 2/2/2 | 0.0 | 0.000 | -1.184 | INSUFFICIENT_EVIDENCE | -9125.70 | 9125.70 / 2.368 | 275.30 / 15 |
| 4h | TREND_PULLBACK | STRICT | LONG | test | ×2 | 1/1/1 | 100.0 | — | 2.270 | INSUFFICIENT_EVIDENCE | 8700.95 | 0.00 / 0.000 | 230.61 / 11 |
| 4h | TREND_PULLBACK | STRICT | SHORT | test | ×2 | 1/1/1 | 0.0 | 0.000 | -1.248 | INSUFFICIENT_EVIDENCE | -4114.11 | 4114.11 / 1.248 | 227.77 / 12 |
| 4h | BREAKOUT_RETEST | BASE | LONG | test | ×2 | 7/6/6 | 16.7 | 0.083 | -0.831 | INSUFFICIENT_EVIDENCE | -20270.45 | 22108.57 / 6.084 | 672.23 / 39 |
| 4h | BREAKOUT_RETEST | BASE | SHORT | test | ×2 | 8/8/8 | 12.5 | 0.221 | -0.738 | INSUFFICIENT_EVIDENCE | -15478.11 | 17660.28 / 6.209 | 1658.54 / 89 |
| 4h | BREAKOUT_RETEST | STRICT | LONG | test | ×2 | 6/5/5 | 20.0 | 0.099 | -0.736 | INSUFFICIENT_EVIDENCE | -16657.37 | 18495.49 / 4.776 | 496.88 / 31 |
| 4h | BREAKOUT_RETEST | STRICT | SHORT | test | ×2 | 7/7/7 | 0.0 | 0.000 | -1.082 | INSUFFICIENT_EVIDENCE | -19865.88 | 19865.88 / 7.571 | 1355.54 / 73 |
| 4h | MOMENTUM_EXPANSION | BASE | LONG | test | ×2 | 16/14/14 | 50.0 | 1.200 | 0.189 | INSUFFICIENT_EVIDENCE | 3864.51 | 10205.60 / 5.797 | 1593.78 / 75 |
| 4h | MOMENTUM_EXPANSION | BASE | SHORT | test | ×2 | 9/8/8 | 25.0 | 0.240 | -0.583 | INSUFFICIENT_EVIDENCE | -15613.75 | 17002.69 / 5.423 | 664.99 / 31 |
| 4h | MOMENTUM_EXPANSION | STRICT | LONG | test | ×2 | 14/13/13 | 53.8 | 1.581 | 0.292 | INSUFFICIENT_EVIDENCE | 8521.02 | 10205.60 / 5.797 | 1556.86 / 73 |
| 4h | MOMENTUM_EXPANSION | STRICT | SHORT | test | ×2 | 8/7/7 | 28.6 | 0.286 | -0.469 | INSUFFICIENT_EVIDENCE | -12319.49 | 13708.44 / 5.024 | 459.15 / 22 |
| 4h | MEAN_REVERSION | BASE | LONG | test | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | MEAN_REVERSION | BASE | SHORT | test | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | MEAN_REVERSION | STRICT | LONG | test | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | MEAN_REVERSION | STRICT | SHORT | test | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | LIQUIDITY_SWEEP | BASE | LONG | test | ×2 | 10/10/10 | 50.0 | 1.165 | 0.062 | INSUFFICIENT_EVIDENCE | 2885.76 | 13983.20 / 4.947 | 1275.67 / 68 |
| 4h | LIQUIDITY_SWEEP | BASE | SHORT | test | ×2 | 2/2/2 | 50.0 | 1.296 | -0.126 | INSUFFICIENT_EVIDENCE | 672.18 | 2267.59 / 1.246 | 324.00 / 17 |
| 4h | LIQUIDITY_SWEEP | STRICT | LONG | test | ×2 | 8/8/8 | 50.0 | 1.118 | 0.021 | INSUFFICIENT_EVIDENCE | 1677.60 | 10676.59 / 3.653 | 1028.98 / 55 |
| 4h | LIQUIDITY_SWEEP | STRICT | SHORT | test | ×2 | 2/2/2 | 50.0 | 1.296 | -0.126 | INSUFFICIENT_EVIDENCE | 672.18 | 2267.59 / 1.246 | 324.00 / 17 |
| 4h | RANGE_REJECTION | BASE | LONG | test | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | RANGE_REJECTION | BASE | SHORT | test | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | RANGE_REJECTION | STRICT | LONG | test | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | RANGE_REJECTION | STRICT | SHORT | test | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | TREND_PULLBACK | BASE | LONG | final | ×1 | 7/5/5 | 20.0 | 0.282 | -0.562 | INSUFFICIENT_EVIDENCE | -4752.59 | 6619.97 / 3.528 | 579.98 / 72 |
| 4h | TREND_PULLBACK | BASE | SHORT | final | ×1 | 7/6/6 | 16.7 | 0.184 | -0.544 | INSUFFICIENT_EVIDENCE | -15496.70 | 17610.48 / 4.449 | 560.84 / 67 |
| 4h | TREND_PULLBACK | STRICT | LONG | final | ×1 | 2/2/2 | 50.0 | 0.779 | -0.226 | INSUFFICIENT_EVIDENCE | -528.91 | 2396.29 / 1.171 | 335.12 / 47 |
| 4h | TREND_PULLBACK | STRICT | SHORT | final | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | BREAKOUT_RETEST | BASE | LONG | final | ×1 | 12/9/9 | 22.2 | 0.244 | -0.570 | INSUFFICIENT_EVIDENCE | -15107.38 | 15107.38 / 5.132 | 594.65 / 59 |
| 4h | BREAKOUT_RETEST | BASE | SHORT | final | ×1 | 17/15/15 | 53.3 | 1.559 | 0.305 | INSUFFICIENT_EVIDENCE | 13339.43 | 7469.04 / 2.148 | 1296.86 / 144 |
| 4h | BREAKOUT_RETEST | STRICT | LONG | final | ×1 | 9/8/8 | 25.0 | 0.265 | -0.549 | INSUFFICIENT_EVIDENCE | -13525.45 | 14108.53 / 4.448 | 461.58 / 42 |
| 4h | BREAKOUT_RETEST | STRICT | SHORT | final | ×1 | 13/11/11 | 36.4 | 0.875 | -0.110 | INSUFFICIENT_EVIDENCE | -2986.89 | 15356.59 / 4.813 | 1020.15 / 105 |
| 4h | MOMENTUM_EXPANSION | BASE | LONG | final | ×1 | 12/12/12 | 25.0 | 0.547 | -0.338 | INSUFFICIENT_EVIDENCE | -8722.07 | 12626.06 / 6.295 | 550.31 / 60 |
| 4h | MOMENTUM_EXPANSION | BASE | SHORT | final | ×1 | 22/17/17 | 29.4 | 1.064 | -0.023 | INSUFFICIENT_EVIDENCE | 1548.34 | 14593.63 / 7.523 | 873.10 / 105 |
| 4h | MOMENTUM_EXPANSION | STRICT | LONG | final | ×1 | 9/9/9 | 33.3 | 0.783 | -0.054 | INSUFFICIENT_EVIDENCE | -2913.71 | 6817.71 / 2.724 | 400.55 / 45 |
| 4h | MOMENTUM_EXPANSION | STRICT | SHORT | final | ×1 | 16/12/12 | 41.7 | 2.052 | 0.441 | INSUFFICIENT_EVIDENCE | 13125.37 | 6341.83 / 3.044 | 741.97 / 88 |
| 4h | MEAN_REVERSION | BASE | LONG | final | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | MEAN_REVERSION | BASE | SHORT | final | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | MEAN_REVERSION | STRICT | LONG | final | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | MEAN_REVERSION | STRICT | SHORT | final | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | LIQUIDITY_SWEEP | BASE | LONG | final | ×1 | 12/11/11 | 54.5 | 1.498 | 0.357 | INSUFFICIENT_EVIDENCE | 8484.40 | 4180.70 / 1.152 | 910.20 / 98 |
| 4h | LIQUIDITY_SWEEP | BASE | SHORT | final | ×1 | 5/5/5 | 40.0 | 0.886 | -0.022 | INSUFFICIENT_EVIDENCE | -794.11 | 5209.71 / 2.229 | 96.91 / 27 |
| 4h | LIQUIDITY_SWEEP | STRICT | LONG | final | ×1 | 12/11/11 | 54.5 | 1.498 | 0.357 | INSUFFICIENT_EVIDENCE | 8484.40 | 4180.70 / 1.152 | 910.20 / 98 |
| 4h | LIQUIDITY_SWEEP | STRICT | SHORT | final | ×1 | 4/4/4 | 50.0 | 1.400 | 0.249 | INSUFFICIENT_EVIDENCE | 1771.92 | 2643.68 / 1.164 | 62.18 / 22 |
| 4h | RANGE_REJECTION | BASE | LONG | final | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | RANGE_REJECTION | BASE | SHORT | final | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | RANGE_REJECTION | STRICT | LONG | final | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | RANGE_REJECTION | STRICT | SHORT | final | ×1 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | TREND_PULLBACK | BASE | LONG | final | ×1.5 | 7/5/5 | 20.0 | 0.227 | -0.645 | INSUFFICIENT_EVIDENCE | -5634.11 | 7286.73 / 3.862 | 869.97 / 72 |
| 4h | TREND_PULLBACK | BASE | SHORT | final | ×1.5 | 7/6/6 | 16.7 | 0.170 | -0.608 | INSUFFICIENT_EVIDENCE | -16530.12 | 18429.56 / 4.673 | 844.37 / 67 |
| 4h | TREND_PULLBACK | STRICT | LONG | final | ×1.5 | 2/2/2 | 50.0 | 0.643 | -0.310 | INSUFFICIENT_EVIDENCE | -918.87 | 2571.49 / 1.257 | 502.67 / 47 |
| 4h | TREND_PULLBACK | STRICT | SHORT | final | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | BREAKOUT_RETEST | BASE | LONG | final | ×1.5 | 12/9/9 | 22.2 | 0.215 | -0.636 | INSUFFICIENT_EVIDENCE | -16564.57 | 16564.57 / 5.724 | 895.67 / 59 |
| 4h | BREAKOUT_RETEST | BASE | SHORT | final | ×1.5 | 17/15/15 | 53.3 | 1.428 | 0.250 | INSUFFICIENT_EVIDENCE | 10701.84 | 7689.48 / 2.222 | 1945.29 / 144 |
| 4h | BREAKOUT_RETEST | STRICT | LONG | final | ×1.5 | 9/8/8 | 25.0 | 0.235 | -0.612 | INSUFFICIENT_EVIDENCE | -14792.31 | 14792.96 / 4.895 | 696.07 / 42 |
| 4h | BREAKOUT_RETEST | STRICT | SHORT | final | ×1.5 | 13/11/11 | 36.4 | 0.798 | -0.163 | INSUFFICIENT_EVIDENCE | -5060.70 | 16069.67 / 5.047 | 1530.22 / 105 |
| 4h | MOMENTUM_EXPANSION | BASE | LONG | final | ×1.5 | 12/12/12 | 25.0 | 0.484 | -0.430 | INSUFFICIENT_EVIDENCE | -10603.75 | 14281.48 / 7.265 | 825.46 / 60 |
| 4h | MOMENTUM_EXPANSION | BASE | SHORT | final | ×1.5 | 22/17/17 | 29.4 | 0.960 | -0.099 | INSUFFICIENT_EVIDENCE | -1036.66 | 15997.80 / 8.366 | 1283.08 / 102 |
| 4h | MOMENTUM_EXPANSION | STRICT | LONG | final | ×1.5 | 9/9/9 | 33.3 | 0.697 | -0.144 | INSUFFICIENT_EVIDENCE | -4322.20 | 7999.92 / 3.409 | 600.83 / 45 |
| 4h | MOMENTUM_EXPANSION | STRICT | SHORT | final | ×1.5 | 16/12/12 | 41.7 | 1.825 | 0.360 | INSUFFICIENT_EVIDENCE | 11179.88 | 7297.58 / 3.553 | 1117.03 / 88 |
| 4h | MEAN_REVERSION | BASE | LONG | final | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | MEAN_REVERSION | BASE | SHORT | final | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | MEAN_REVERSION | STRICT | LONG | final | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | MEAN_REVERSION | STRICT | SHORT | final | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | LIQUIDITY_SWEEP | BASE | LONG | final | ×1.5 | 12/11/11 | 54.5 | 1.369 | 0.296 | INSUFFICIENT_EVIDENCE | 6589.05 | 4361.44 / 1.227 | 1365.30 / 98 |
| 4h | LIQUIDITY_SWEEP | BASE | SHORT | final | ×1.5 | 5/5/5 | 40.0 | 0.804 | -0.089 | INSUFFICIENT_EVIDENCE | -1447.18 | 5477.40 / 2.343 | 190.84 / 27 |
| 4h | LIQUIDITY_SWEEP | STRICT | LONG | final | ×1.5 | 12/11/11 | 54.5 | 1.369 | 0.296 | INSUFFICIENT_EVIDENCE | 6589.05 | 4361.44 / 1.227 | 1365.30 / 98 |
| 4h | LIQUIDITY_SWEEP | STRICT | SHORT | final | ×1.5 | 4/4/4 | 50.0 | 1.265 | 0.180 | INSUFFICIENT_EVIDENCE | 1244.77 | 2785.44 / 1.246 | 138.76 / 22 |
| 4h | RANGE_REJECTION | BASE | LONG | final | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | RANGE_REJECTION | BASE | SHORT | final | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | RANGE_REJECTION | STRICT | LONG | final | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | RANGE_REJECTION | STRICT | SHORT | final | ×1.5 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | TREND_PULLBACK | BASE | LONG | final | ×2 | 7/5/5 | 20.0 | 0.181 | -0.729 | INSUFFICIENT_EVIDENCE | -6515.64 | 7953.50 / 4.197 | 1159.96 / 72 |
| 4h | TREND_PULLBACK | BASE | SHORT | final | ×2 | 7/6/6 | 16.7 | 0.157 | -0.672 | INSUFFICIENT_EVIDENCE | -17563.51 | 19248.61 / 4.898 | 1127.90 / 67 |
| 4h | TREND_PULLBACK | STRICT | LONG | final | ×2 | 2/2/2 | 50.0 | 0.523 | -0.394 | INSUFFICIENT_EVIDENCE | -1308.85 | 2746.71 / 1.343 | 670.23 / 47 |
| 4h | TREND_PULLBACK | STRICT | SHORT | final | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | BREAKOUT_RETEST | BASE | LONG | final | ×2 | 12/9/9 | 22.2 | 0.190 | -0.702 | INSUFFICIENT_EVIDENCE | -18021.80 | 18021.80 / 6.316 | 1196.69 / 59 |
| 4h | BREAKOUT_RETEST | BASE | SHORT | final | ×2 | 17/15/15 | 46.7 | 1.307 | 0.195 | INSUFFICIENT_EVIDENCE | 8064.34 | 8005.65 / 2.338 | 2593.72 / 144 |
| 4h | BREAKOUT_RETEST | STRICT | LONG | final | ×2 | 9/8/8 | 25.0 | 0.208 | -0.675 | INSUFFICIENT_EVIDENCE | -16059.22 | 16059.22 / 5.399 | 930.55 / 42 |
| 4h | BREAKOUT_RETEST | STRICT | SHORT | final | ×2 | 13/11/11 | 36.4 | 0.727 | -0.216 | INSUFFICIENT_EVIDENCE | -7134.45 | 16782.72 / 5.282 | 2040.29 / 105 |
| 4h | MOMENTUM_EXPANSION | BASE | LONG | final | ×2 | 12/12/12 | 25.0 | 0.429 | -0.521 | INSUFFICIENT_EVIDENCE | -12485.51 | 15936.96 / 8.236 | 1100.62 / 60 |
| 4h | MOMENTUM_EXPANSION | BASE | SHORT | final | ×2 | 22/17/17 | 29.4 | 0.868 | -0.176 | INSUFFICIENT_EVIDENCE | -3642.00 | 17422.35 / 9.219 | 1713.50 / 102 |
| 4h | MOMENTUM_EXPANSION | STRICT | LONG | final | ×2 | 9/9/9 | 33.3 | 0.620 | -0.235 | INSUFFICIENT_EVIDENCE | -5730.74 | 9182.19 / 4.094 | 801.11 / 45 |
| 4h | MOMENTUM_EXPANSION | STRICT | SHORT | final | ×2 | 16/12/12 | 41.7 | 1.631 | 0.279 | INSUFFICIENT_EVIDENCE | 9234.43 | 8253.30 / 4.135 | 1492.10 / 88 |
| 4h | MEAN_REVERSION | BASE | LONG | final | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | MEAN_REVERSION | BASE | SHORT | final | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | MEAN_REVERSION | STRICT | LONG | final | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | MEAN_REVERSION | STRICT | SHORT | final | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | LIQUIDITY_SWEEP | BASE | LONG | final | ×2 | 12/11/11 | 54.5 | 1.251 | 0.236 | INSUFFICIENT_EVIDENCE | 4693.64 | 4542.19 / 1.303 | 1820.39 / 98 |
| 4h | LIQUIDITY_SWEEP | BASE | SHORT | final | ×2 | 5/5/5 | 40.0 | 0.730 | -0.156 | INSUFFICIENT_EVIDENCE | -2100.23 | 5745.09 / 2.458 | 284.78 / 27 |
| 4h | LIQUIDITY_SWEEP | STRICT | LONG | final | ×2 | 12/11/11 | 54.5 | 1.251 | 0.236 | INSUFFICIENT_EVIDENCE | 4693.64 | 4542.19 / 1.303 | 1820.39 / 98 |
| 4h | LIQUIDITY_SWEEP | STRICT | SHORT | final | ×2 | 4/4/4 | 50.0 | 1.145 | 0.110 | INSUFFICIENT_EVIDENCE | 717.65 | 2927.21 / 1.328 | 215.34 / 22 |
| 4h | RANGE_REJECTION | BASE | LONG | final | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | RANGE_REJECTION | BASE | SHORT | final | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | RANGE_REJECTION | STRICT | LONG | final | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
| 4h | RANGE_REJECTION | STRICT | SHORT | final | ×2 | 0/0/0 | — | — | — | INSUFFICIENT_EVIDENCE | — | — / — | 0.00 / 0 |
