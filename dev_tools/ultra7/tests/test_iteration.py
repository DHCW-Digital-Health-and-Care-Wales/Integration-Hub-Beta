import unittest

from ultra7.iteration import apply_iteration
from ultra7.models import IterationSpec


class TestApplyIterationIncrement(unittest.TestCase):
    def test_increments_by_step(self) -> None:
        content = "MSH|...|000001|P|2.5"
        start, end = content.index("000001"), content.index("000001") + len("000001")
        spec = IterationSpec(start=start, end=end, mode="increment", step=1)
        self.assertTrue(apply_iteration(content, spec, 0).endswith("000001|P|2.5"))
        self.assertTrue(apply_iteration(content, spec, 1).endswith("000002|P|2.5"))
        self.assertTrue(apply_iteration(content, spec, 5).endswith("000006|P|2.5"))

    def test_preserves_original_width_by_default(self) -> None:
        content = "ID:007:END"
        spec = IterationSpec(start=3, end=6, mode="increment", step=1)
        result = apply_iteration(content, spec, 2)
        self.assertEqual(result, "ID:009:END")

    def test_custom_pad_width(self) -> None:
        content = "ID:7:END"
        spec = IterationSpec(start=3, end=4, mode="increment", step=1, pad_width=5)
        result = apply_iteration(content, spec, 3)
        self.assertEqual(result, "ID:00010:END")

    def test_non_numeric_original_is_left_unchanged(self) -> None:
        content = "ID:ABC:END"
        spec = IterationSpec(start=3, end=6, mode="increment", step=1)
        self.assertEqual(apply_iteration(content, spec, 4), content)


class TestApplyIterationList(unittest.TestCase):
    def test_cycles_through_values(self) -> None:
        content = "PID|1||PATIENT_A"
        start = content.index("PATIENT_A")
        end = start + len("PATIENT_A")
        spec = IterationSpec(start=start, end=end, mode="list", values=["PATIENT_A", "PATIENT_B", "PATIENT_C"])
        self.assertTrue(apply_iteration(content, spec, 0).endswith("PATIENT_A"))
        self.assertTrue(apply_iteration(content, spec, 1).endswith("PATIENT_B"))
        self.assertTrue(apply_iteration(content, spec, 2).endswith("PATIENT_C"))
        self.assertTrue(apply_iteration(content, spec, 3).endswith("PATIENT_A"))  # wraps around

    def test_empty_values_list_leaves_original(self) -> None:
        content = "PID|1||X"
        spec = IterationSpec(start=7, end=8, mode="list", values=[])
        self.assertEqual(apply_iteration(content, spec, 0), content)


class TestApplyIterationTimestamp(unittest.TestCase):
    def test_replaces_with_formatted_timestamp(self) -> None:
        content = "MSH|...|TS_PLACEHOLDER|..."
        start = content.index("TS_PLACEHOLDER")
        end = start + len("TS_PLACEHOLDER")
        spec = IterationSpec(start=start, end=end, mode="timestamp", timestamp_format="%Y%m%d")
        result = apply_iteration(content, spec, 0)
        self.assertNotIn("TS_PLACEHOLDER", result)
        # Should now contain an 8-digit date in its place.
        replaced = result[start : start + 8]
        self.assertTrue(replaced.isdigit())


class TestApplyIterationBounds(unittest.TestCase):
    def test_out_of_bounds_range_is_ignored(self) -> None:
        content = "short"
        spec = IterationSpec(start=10, end=20, mode="increment")
        self.assertEqual(apply_iteration(content, spec, 3), content)

    def test_inverted_range_is_ignored(self) -> None:
        content = "MSG000001"
        spec = IterationSpec(start=5, end=2, mode="increment")
        self.assertEqual(apply_iteration(content, spec, 1), content)


if __name__ == "__main__":
    unittest.main()
