"""Frames in, byte-identical MP4 out; runs the real ffmpeg on tiny images."""
from email.message import Message
from io import BytesIO
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from urllib.error import HTTPError

from vladbench.video import MediaCache, fetch, fetch_frames, transient


def png(color):
    buf = BytesIO()
    Image.new("RGB", (8, 8), color).save(buf, format="PNG")
    return buf.getvalue()


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not installed")
class VideoTests(unittest.TestCase):
    def test_frames_are_converted_in_order_and_cached_by_content(self):
        with tempfile.TemporaryDirectory() as tmp, patch("vladbench.video.urlopen", side_effect=lambda *a, **k: BytesIO(png("red"))):
            cache = MediaCache(Path(tmp))
            urls = ["https://example.test/a.png", "https://example.test/b.png"]
            path, video, receipt = cache.lossless(urls)
            self.assertTrue(video.startswith(b"\x00\x00\x00") and path.exists())
            self.assertEqual([f["url"] for f in receipt["frames"]], urls)
            self.assertEqual(receipt["frames"][0]["conversion"], "JPEG quality=100 subsampling=0")
            self.assertEqual((receipt["original_frame_count"], receipt["encoded_frame_count"]), (2, 2))
            again = cache.lossless(urls)
            self.assertEqual(again[1], video)

    def test_single_frame_sequences_encode_one_frame(self):
        with tempfile.TemporaryDirectory() as tmp, patch("vladbench.video.urlopen", side_effect=lambda *a, **k: BytesIO(png("blue"))):
            receipt = MediaCache(Path(tmp)).lossless(["https://example.test/one.png"])[2]
            self.assertEqual((receipt["original_frame_count"], receipt["encoded_frame_count"]), (1, 1))

    def test_compressed_fallback_is_lossy_and_traceable_to_its_source(self):
        with tempfile.TemporaryDirectory() as tmp, patch("vladbench.video.urlopen", side_effect=lambda *a, **k: BytesIO(png("green"))):
            cache = MediaCache(Path(tmp))
            urls = ["https://example.test/a.png", "https://example.test/b.png"]
            path, video, receipt = cache.lossless(urls)
            small_path, small, small_receipt = cache.compressed(urls, path, receipt)
            self.assertNotEqual(small, video)
            self.assertTrue(small_receipt["provider_size_fallback"])
            self.assertEqual(small_receipt["source_encoded_sha256"], receipt["encoded_sha256"])
            self.assertEqual(cache.compressed(urls, path, receipt)[1], small)
            (small_path).write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                cache.compressed(urls, path, receipt)

    def test_fetch_retries_transient_errors_only(self):
        rate_limited = HTTPError("u", 429, "slow", Message(), BytesIO())
        forbidden = HTTPError("u", 403, "no", Message(), BytesIO())
        self.assertTrue(transient(rate_limited) and transient(TimeoutError()) and transient(ConnectionResetError()))
        self.assertFalse(transient(forbidden))
        with patch("vladbench.video.urlopen", side_effect=[rate_limited, BytesIO(b"ok")]), patch("vladbench.video.time.sleep") as sleep:
            self.assertEqual(fetch("https://example.test/a"), b"ok")
        sleep.assert_called_once_with(1)
        with patch("vladbench.video.urlopen", side_effect=[forbidden]), self.assertRaises(HTTPError):
            fetch("https://example.test/a")
        with patch("vladbench.video.urlopen", side_effect=[rate_limited] * 2), patch("vladbench.video.time.sleep"), self.assertRaises(HTTPError):
            fetch("https://example.test/a", max_attempts=2)

    def test_fetch_rejects_inconsistent_dimensions(self):
        big = BytesIO()
        Image.new("RGB", (9, 9), "red").save(big, format="PNG")
        with patch("vladbench.video.urlopen", side_effect=[BytesIO(png("red")), BytesIO(big.getvalue())]):
            with self.assertRaisesRegex(ValueError, "inconsistent"):
                fetch_frames(["https://example.test/a", "https://example.test/b"])


if __name__ == "__main__":
    unittest.main()
