import tempfile
import unittest
from pathlib import Path

from spherex_pipeline.database import Database
from spherex_pipeline.filenames import parse_level2_filename
from spherex_pipeline.models import RemoteObject


def remote(key: str, *, etag: str = "etag-1", size: int = 100) -> RemoteObject:
    return RemoteObject(
        bucket="test-bucket",
        key=key,
        size_bytes=size,
        etag=etag,
        last_modified="2026-01-01T00:00:00+00:00",
        storage_class="STANDARD",
        checksum_algorithms=None,
        parsed=parse_level2_filename(key),
    )


KEY1 = (
    "qr2/level2/2025W17_4B/l2b-v20-2025-240/2/"
    "level2_2025W17_4B_0001_1D2_spx_l2b-v20-2025-240.fits"
)
KEY2 = (
    "qr2/level2/2025W17_4B/l2b-v20-2025-240/3/"
    "level2_2025W17_4B_0002_2D3_spx_l2b-v20-2025-240.fits"
)


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temporary.name) / "test.sqlite3")
        self.database.initialize()

    def tearDown(self):
        self.temporary.cleanup()

    def scan(self, objects):
        scan_id = self.database.start_scan("test-bucket", "qr2/level2/")
        return self.database.sync_objects(
            scan_id, "test-bucket", "qr2/level2/", objects
        )

    def test_new_updated_and_removed_objects(self):
        first = self.scan([remote(KEY1), remote(KEY2)])
        self.assertEqual(first, {"listed": 2, "new": 2, "updated": 0, "removed": 0})

        for key in (KEY1, KEY2):
            self.database.set_download_status(
                bucket="test-bucket",
                key=key,
                remote_size_bytes=100,
                remote_etag="etag-1",
                remote_last_modified="2026-01-01T00:00:00+00:00",
                local_path=f"/data/{key}",
                status="completed",
                bytes_downloaded=100,
                verified=True,
            )

        second = self.scan([remote(KEY1, etag="etag-2", size=101)])
        self.assertEqual(second, {"listed": 1, "new": 0, "updated": 1, "removed": 1})
        rows = self.database.current_objects("test-bucket", "2025W17_4B")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["etag"], "etag-2")
        self.assertEqual(self.database.get_download("test-bucket", KEY1)["status"], "stale")
        self.assertEqual(
            self.database.get_download("test-bucket", KEY2)["status"], "remote_missing"
        )


if __name__ == "__main__":
    unittest.main()
