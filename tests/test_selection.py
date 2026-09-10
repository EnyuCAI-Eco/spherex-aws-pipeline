import unittest

from spherex_pipeline.selection import _stratified


class SelectionTests(unittest.TestCase):
    def test_stratified_selection_covers_all_detectors(self):
        candidates = []
        for observation in range(1, 5):
            for detector in range(1, 7):
                candidates.append(
                    {
                        "key": f"key-{observation:02d}-{detector}",
                        "detector": detector,
                        "small_slew_counter": observation,
                        "observation_id": f"obs-{observation}",
                        "processing_date": "2025-240",
                    }
                )
        selected = _stratified(candidates, 10)
        self.assertEqual(len(selected), 10)
        self.assertEqual({row["detector"] for row in selected}, set(range(1, 7)))
        self.assertEqual({row["small_slew_counter"] for row in selected}, {1, 2, 3, 4})


if __name__ == "__main__":
    unittest.main()
