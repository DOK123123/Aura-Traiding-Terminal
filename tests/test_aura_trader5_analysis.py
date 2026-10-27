"""Isolated Aura Trader 5 calculation tests."""
import unittest

from app.aura_trader5_analysis import Candle, atr, ema, fibonacci_levels, risk_plan, rsi


class TestManualAnalysis(unittest.TestCase):
    def test_ema_constant(self):
        self.assertEqual(ema([42.0] * 30, 20), 42.0)
        self.assertIsNone(ema([1.0], 20))

    def test_rsi_extremes_and_flat(self):
        self.assertEqual(rsi([float(i) for i in range(20)]), 100.0)
        self.assertEqual(rsi([float(20-i) for i in range(20)]), 0.0)
        self.assertEqual(rsi([10.0] * 20), 50.0)

    def test_atr_constant_range(self):
        candles = [Candle(11.0, 9.0, 10.0) for _ in range(20)]
        self.assertAlmostEqual(atr(candles), 2.0)

    def test_fibonacci(self):
        up = fibonacci_levels(100.0, 200.0, "up")
        down = fibonacci_levels(100.0, 200.0, "down")
        self.assertAlmostEqual(up["0.618"], 138.2)
        self.assertAlmostEqual(down["0.618"], 161.8)

    def test_risk_plan(self):
        plan = risk_plan(100.0, 95.0, 110.0, "long", 10000.0, 1.0)
        self.assertAlmostEqual(plan["risk_budget_usdt"], 100.0)
        self.assertAlmostEqual(plan["estimated_loss_usdt"], 100.0)
        self.assertGreater(plan["estimated_rr_after_costs"], 1.0)
        self.assertLess(plan["estimated_rr_after_costs"], 2.0)

    def test_invalid_side_and_prices(self):
        with self.assertRaises(ValueError):
            risk_plan(100, 105, 110, "long", 10000)
        with self.assertRaises(ValueError):
            atr([Candle(9, 11, 10)])


if __name__ == "__main__":
    unittest.main()
