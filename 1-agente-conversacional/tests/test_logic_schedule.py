import unittest

from app.logic import calculate_schedule


class RouteScheduleLogicTests(unittest.TestCase):
    def test_before_cutoff_moves_to_next_business_day(self) -> None:
        result = calculate_schedule("2026-04-02T16:00:00", cutoff="17:30")
        self.assertEqual(result["scheduled_pickup_date"], "2026-04-03")
        self.assertEqual(result["reason"], "next_business_day_before_cutoff")

    def test_after_cutoff_moves_to_second_business_day(self) -> None:
        result = calculate_schedule("2026-04-02T18:00:00", cutoff="17:30")
        self.assertEqual(result["scheduled_pickup_date"], "2026-04-06")
        self.assertEqual(result["reason"], "second_business_day_after_cutoff")

    def test_friday_before_cutoff_moves_to_monday(self) -> None:
        result = calculate_schedule("2026-04-03T16:00:00", cutoff="17:30")
        self.assertEqual(result["scheduled_pickup_date"], "2026-04-06")
        self.assertEqual(result["reason"], "next_business_day_before_cutoff")

    def test_friday_after_cutoff_moves_to_tuesday(self) -> None:
        result = calculate_schedule("2026-04-03T18:00:00", cutoff="17:30")
        self.assertEqual(result["scheduled_pickup_date"], "2026-04-07")
        self.assertEqual(result["reason"], "second_business_day_after_cutoff")


if __name__ == "__main__":
    unittest.main()
