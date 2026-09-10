import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from spherex_pipeline.config import Settings
from spherex_pipeline.database import Database
from spherex_pipeline.downloader import PlanItem, _download_one, safe_local_path


class FakeS3Client:
    def __init__(self, payload: bytes):
        self.payload = payload
        self.request = None

    def get_object(self, **kwargs):
        self.request = kwargs
        return {
            "ETag": '"etag-1"',
            "ContentLength": len(self.payload),
            "Body": io.BytesIO(self.payload),
        }


class DownloaderTests(unittest.TestCase):
    def test_key_maps_below_download_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = safe_local_path(root, "qr2/level2/period/file.fits")
            self.assertEqual(path, root.resolve() / "qr2/level2/period/file.fits")

    def test_parent_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                safe_local_path(Path(directory), "../outside.fits")

    def test_download_uses_etag_condition_and_atomic_final_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = Database(root / "catalog.sqlite3")
            database.initialize()
            payload = b"test-payload"
            fake = FakeS3Client(payload)
            settings = Settings(
                project_root=root,
                bucket="test-bucket",
                region="us-east-1",
                unsigned=True,
                catalog_prefix="qr2/level2/",
                database_path=root / "catalog.sqlite3",
                export_csv_path=root / "export.csv",
                selection_planning_period=None,
                selection_limit=1,
                selection_strategy="first",
                manifest_path=root / "manifest.csv",
                download_root=root / "data",
                workers=1,
                max_attempts=1,
                backoff_seconds=0,
                verify_fits=False,
                sha256=False,
                log_level="INFO",
                log_file=root / "pipeline.log",
            )
            row = {
                "bucket": "test-bucket",
                "key": "qr2/level2/test.fits",
                "size_bytes": len(payload),
                "etag": "etag-1",
                "last_modified": "2026-01-01T00:00:00+00:00",
            }
            target = safe_local_path(settings.download_root, row["key"])
            item = PlanItem(row=row, local_path=target, action="download", reason="test")
            with patch("spherex_pipeline.downloader.make_s3_client", return_value=fake):
                status, _ = _download_one(item, settings, database)
            self.assertEqual(status, "completed")
            self.assertEqual(target.read_bytes(), payload)
            self.assertFalse(target.with_suffix(".fits.part").exists())
            self.assertEqual(fake.request["IfMatch"], '"etag-1"')


if __name__ == "__main__":
    unittest.main()
