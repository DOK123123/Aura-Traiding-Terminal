"""Calendar integrity fixtures for offline portfolio uncertainty; no market claims."""
from decimal import Decimal as D
import unittest

from app.lab.models import Bar, Baseline
from scripts.pattern_research import blocked_bootstrap, period_run


DAY = 86400
STEP = 900
START = 1577836800
HYPOTHESIS = dict(id='calendar-fixture', pattern='doji', context='NONE', exit='PCT_2_4')


def cash_segment(start=START, days=70):
    bars = [Bar(start+i*STEP, D(100), D(101), D(99), D(100), D(10))
            for i in range(249+days*96)]
    rows = [None]*249 + [dict(patterns={}) for _ in bars[249:]]
    return bars, rows


class BootstrapCalendarTests(unittest.TestCase):
    def test_sparse_endpoints_do_not_imply_known_flat_calendar(self):
        # Synthetic equity markers, not observed market returns or a backtest.
        curve = [dict(time=0, equity='10000'), dict(time=100*DAY, equity='10000')]
        curve += [dict(time=i*DAY, equity=str(10000+i-100)) for i in range(101, 161)]
        result = blocked_bootstrap(curve, reps=99)
        self.assertEqual(result['status'], 'INCOMPLETE_CALENDAR')
        self.assertEqual(result['missing_days'], 99)
        self.assertIsNone(result['p_value'])
        self.assertNotIn('lower95_mean_daily', result)
        self.assertNotIn('observed_mean_daily', result)

    def test_missing_middle_day_refuses_blocks_even_with_enough_observations(self):
        curve = [dict(time=i*DAY, equity=str(10000+i)) for i in range(100) if i != 50]
        result = blocked_bootstrap(curve, reps=99)
        self.assertEqual(result['status'], 'INCOMPLETE_CALENDAR')
        self.assertEqual(result['missing_days'], 1)
        self.assertIsNone(result['p_value'])

    def test_dense_continuous_result_retains_frozen_seed_arithmetic(self):
        curve = [dict(time=i*DAY, equity=str(10000+i+(i%14)*3)) for i in range(100)]
        result = blocked_bootstrap(curve, reps=99)
        self.assertEqual(result, blocked_bootstrap(curve, reps=99))
        self.assertEqual(result['status'], 'DESCRIPTIVE_DEPENDENT_BLOCKS')
        self.assertEqual(result['days'], 99)
        self.assertEqual(result['block_days'], 14)
        self.assertEqual(result['p_value'], .01)
        # Independent frozen baseline values from the unchanged dense algorithm.
        self.assertEqual(result['lower95_mean_daily'], 60/99)
        self.assertEqual(result['observed_mean_daily'], 102/99)

    def test_observed_no_signal_days_are_retained_as_zero_returns(self):
        part, rows = cash_segment()
        end = part[-1].time+STEP
        result = period_run([(part, rows)], HYPOTHESIS, START, end, Baseline(), STEP)
        curve = result['equity_curve']
        self.assertEqual(result['signals'], 0)
        self.assertEqual(result['trades'], [])
        self.assertTrue(all(D(p['equity']) == 10000 for p in curve))
        observed_times = {part[249].time} | {b.time+STEP for b in part[249:]}
        self.assertTrue(all(p['time'] in observed_times for p in curve))
        self.assertTrue(all(p['time']%DAY == 0 for p in curve[1:-1]))
        bootstrap = blocked_bootstrap(curve, reps=99)
        self.assertEqual(bootstrap['days'], 70)
        self.assertEqual(bootstrap['observed_mean_daily'], 0)
        self.assertEqual(bootstrap['lower95_mean_daily'], 0)
        self.assertEqual(bootstrap['p_value'], 1)

    def test_no_signal_markers_do_not_fill_unobserved_gap(self):
        first = cash_segment(days=35)
        second = cash_segment(start=START+100*DAY, days=35)
        end = second[0][-1].time+STEP
        result = period_run([first, second], HYPOTHESIS, START, end, Baseline(), STEP)
        curve = result['equity_curve']
        gap_start = first[0][-1].time+STEP
        gap_end = second[0][0].time
        self.assertFalse(any(gap_start < p['time'] < gap_end for p in curve))
        self.assertEqual(blocked_bootstrap(curve, reps=99)['status'], 'INCOMPLETE_CALENDAR')

    def test_period_curve_is_unchanged_by_appended_future_bars(self):
        part, rows = cash_segment()
        end = part[-1].time+STEP
        before = period_run([(part, rows)], HYPOTHESIS, START, end, Baseline(), STEP)
        future, future_rows = cash_segment(start=end, days=1)
        after = period_run([(part+future, rows+future_rows)], HYPOTHESIS, START, end, Baseline(), STEP)
        self.assertEqual(before, after)
        self.assertLessEqual(max(p['time'] for p in after['equity_curve']), end)


if __name__ == '__main__':
    unittest.main()
