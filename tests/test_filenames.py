import unittest

from spherex_pipeline.filenames import parse_level2_filename


class FilenameTests(unittest.TestCase):
    def test_official_level2_example(self):
        parsed = parse_level2_filename(
            "level2_2025W22_2B_0001_1D3_spx_l2b-v4-2025-152.fits"
        )
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.planning_period, "2025W22_2B")
        self.assertEqual(parsed.large_slew_counter, "0001")
        self.assertEqual(parsed.small_slew_counter, 1)
        self.assertEqual(parsed.detector, 3)
        self.assertEqual(parsed.observation_id, "2025W22_2B_0001.1")
        self.assertEqual(parsed.pipeline_level, "l2b")
        self.assertEqual(parsed.pipeline_version, "v4")
        self.assertEqual(parsed.processing_date, "2025-152")

    def test_full_s3_key(self):
        parsed = parse_level2_filename(
            "qr2/level2/2025W17_4B/l2b-v20-2025-240/2/"
            "level2_2025W17_4B_0001_1D2_spx_l2b-v20-2025-240.fits"
        )
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.detector, 2)

    def test_non_level2_name_does_not_parse(self):
        self.assertIsNone(parse_level2_filename("README.txt"))


if __name__ == "__main__":
    unittest.main()
