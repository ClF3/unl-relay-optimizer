import unittest

from relay_vdot_optimizer.vdot import (
    distance_m,
    marginal_distance_m_per_min,
    time_for_distance_min,
    vdot_from_performance,
    velocity_m_per_min,
)


class VdotFormulaTests(unittest.TestCase):
    def test_known_5k_example(self):
        self.assertAlmostEqual(vdot_from_performance(5000, 20), 49.8, delta=0.2)

    def test_distance_is_time_times_velocity(self):
        self.assertAlmostEqual(distance_m(50, 30), 30 * velocity_m_per_min(50, 30))

    def test_marginal_is_positive_for_normal_duration(self):
        self.assertGreater(marginal_distance_m_per_min(50, 60), 0)

    def test_time_for_distance_inverts_distance(self):
        time_min = time_for_distance_min(50, 5000)
        self.assertAlmostEqual(distance_m(50, time_min), 5000, delta=1e-5)


if __name__ == "__main__":
    unittest.main()
