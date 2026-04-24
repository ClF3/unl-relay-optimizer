import unittest

from relay_vdot_optimizer.optimizers import (
    optimize_concave,
    optimize_distance_search,
    optimize_search,
)


class OptimizerTests(unittest.TestCase):
    def test_concave_identical_runners_split_evenly(self):
        result = optimize_concave([50, 50], 60)
        times = [allocation.time_min for allocation in result.allocations]
        self.assertAlmostEqual(times[0], 30, delta=1e-5)
        self.assertAlmostEqual(times[1], 30, delta=1e-5)
        self.assertAlmostEqual(sum(times), 60, delta=1e-5)

    def test_concave_stronger_runner_gets_more_time(self):
        result = optimize_concave([60, 40], 60)
        self.assertGreater(result.allocations[0].time_min, result.allocations[1].time_min)

    def test_search_uses_exact_number_of_units(self):
        result = optimize_search([55, 50, 45], 30, unit_sec=60)
        total_minutes = sum(allocation.time_min for allocation in result.allocations)
        self.assertAlmostEqual(total_minutes, 30)
        self.assertEqual(result.details["time_units"], 30)

    def test_search_rejects_non_integer_unit_count(self):
        with self.assertRaises(ValueError):
            optimize_search([50, 45], 10, unit_sec=45)

    def test_distance_search_returns_completed_units_under_time_limit(self):
        result = optimize_distance_search([55, 50, 45], 30, unit_m=400)
        used_time = sum(allocation.time_min for allocation in result.allocations)
        self.assertLessEqual(used_time, 30 + 1e-7)
        self.assertAlmostEqual(
            result.total_distance_m,
            result.details["distance_units"] * result.details["unit_m"],
        )
        self.assertEqual(result.total_distance_m % 400, 0)


if __name__ == "__main__":
    unittest.main()
