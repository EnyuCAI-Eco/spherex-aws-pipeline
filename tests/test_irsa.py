import io
import unittest
from urllib.parse import parse_qs, urlparse

from spherex_pipeline.irsa import (
    build_point_query_url,
    parse_sia_csv,
    query_spherex_point,
)


CSV_RESPONSE = '''s_ra,s_dec,instrument_name,obs_id,access_url,access_estsize,s_region,cloud_access
207.4051,54.1760,SPHEREx-D2,2025W19_2B_0346_4,https://example.test/image.fits,71635,"POLYGON ICRS 1 2 3 4","{""aws"": {""bucket_name"": ""nasa-irsa-spherex"", ""key"": ""qr2/level2/2025W19_2B/l2b-v20-2025-247/2/level2_2025W19_2B_0346_4D2_spx_l2b-v20-2025-247.fits""}}"
'''


class IrsaTests(unittest.TestCase):
    def test_point_query_uses_qr2_and_subpixel_probe(self):
        url = build_point_query_url(210.80225, 54.34894, max_records=25)
        query = parse_qs(urlparse(url).query)
        self.assertEqual(query["COLLECTION"], ["spherex_qr2"])
        self.assertEqual(query["POS"], ["CIRCLE 210.80225 54.34894 1e-05"])
        self.assertEqual(query["MAXREC"], ["25"])

    def test_invalid_coordinates_are_rejected(self):
        with self.assertRaises(ValueError):
            build_point_query_url(360.0, 0.0)
        with self.assertRaises(ValueError):
            build_point_query_url(0.0, -90.1)

    def test_sia_csv_maps_result_to_s3(self):
        match = parse_sia_csv(CSV_RESPONSE)[0]
        self.assertEqual(match.bucket, "nasa-irsa-spherex")
        self.assertTrue(match.key.endswith("_4D2_spx_l2b-v20-2025-247.fits"))
        self.assertEqual(match.detector, 2)
        self.assertEqual(match.estimated_size_bytes, 71635 * 1024)

    def test_query_can_use_injected_transport(self):
        def opener(request, timeout):
            self.assertIn("COLLECTION=spherex_qr2", request.full_url)
            self.assertEqual(timeout, 5.0)
            return io.BytesIO(CSV_RESPONSE.encode("utf-8"))

        matches = query_spherex_point(
            210.80225,
            54.34894,
            timeout=5.0,
            attempts=1,
            opener=opener,
        )
        self.assertEqual(len(matches), 1)


if __name__ == "__main__":
    unittest.main()
