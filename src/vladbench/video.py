"""MP4 transport for annotation-selected frame sequences.

Start from ``MediaCache.lossless``. Only the selected frames are fetched. FPS is
a synthetic spacing, not a claim about source capture time. Artifacts are
content-addressed so every model in a condition sends byte-identical video for
the same question.
"""
from __future__ import annotations

import hashlib
from io import BytesIO
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import time
from urllib.error import HTTPError
from urllib.request import urlopen

from PIL import Image

from .requests import digest

LOSSLESS_LABEL = "libx264rgb-crf0-fps1-v1"
COMPRESSED_LABEL = "libx264-crf18-yuv420p-fps1-v1"
LOSSLESS_CODEC = ["-c:v", "libx264rgb", "-crf", "0", "-preset", "fast"]
LOSSY_CODEC = ["-an", "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", "-pix_fmt", "yuv420p"]


def transient(error: Exception) -> bool:
    if isinstance(error, HTTPError):
        return error.code in (408, 409, 429) or error.code >= 500
    return isinstance(error, (TimeoutError, OSError))


def fetch(url: str, max_attempts: int = 4) -> bytes:
    for attempt in range(max_attempts):
        try:
            with urlopen(url, timeout=60) as response:
                return response.read()
        except (HTTPError, TimeoutError, OSError) as error:
            if not transient(error) or attempt + 1 == max_attempts:
                raise
        time.sleep(min(2 ** attempt, 8))
    raise AssertionError("unreachable")


def as_jpeg(image: Image.Image, raw: bytes) -> tuple[bytes, str]:
    if image.format == "JPEG":
        return raw, "none"
    buf = BytesIO()
    image.convert("RGB").save(buf, format="JPEG", quality=100, subsampling=0)
    return buf.getvalue(), "JPEG quality=100 subsampling=0"


def fetch_frames(urls: list[str]) -> list[dict]:
    """Fetch annotation-selected frames in order; JPEG-convert non-JPEG sources."""
    frames, size = [], None
    for url in urls:
        raw = fetch(url)
        image = Image.open(BytesIO(raw))
        if size is not None and image.size != size:
            raise ValueError("Sequence frames have inconsistent dimensions")
        size = image.size
        sent, conversion = as_jpeg(image, raw)
        frames.append({"url": url, "bytes": sent, "source_sha256": hashlib.sha256(raw).hexdigest(),
                       "sent_sha256": hashlib.sha256(sent).hexdigest(), "dimensions": list(size), "conversion": conversion})
    return frames


def ffmpeg(inputs: list[str], codec: list[str], output: Path) -> bytes:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", *inputs, *codec, "-movflags", "+faststart", str(output)], check=True)
    return output.read_bytes()


def encode_mp4(jpeg_frames: list[bytes], *, fps: int = 1) -> bytes:
    with tempfile.TemporaryDirectory() as folder:
        for index, frame in enumerate(jpeg_frames):
            (Path(folder) / f"{index:04d}.jpg").write_bytes(frame)
        return ffmpeg(["-framerate", str(fps), "-i", str(Path(folder) / "%04d.jpg")], LOSSLESS_CODEC, Path(folder) / "sequence.mp4")


def lossless_receipt(frames: list[dict], encoded: list[bytes], label: str, data: bytes, fps: int) -> dict:
    return {
        "frames": [{k: v for k, v in f.items() if k != "bytes"} for f in frames], "fps": float(fps),
        "timing_basis": "synthetic equal spacing; source timing unverified",
        "frame_selection": "all annotation-selected frames, original order", "transport": "MP4 video_url",
        "encoding": "ffmpeg libx264rgb crf=0; synthetic 1 FPS", "encoding_key": label,
        "original_frame_count": len(frames), "encoded_frame_count": len(encoded),
        "encoded_sha256": hashlib.sha256(data).hexdigest(),
    }


class MediaCache:
    """Content-addressed MP4 artifacts shared by every model in a condition."""

    def __init__(self, folder: Path, fps: int = 1):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.fps = fps
        self.guard = threading.Lock()
        self.locks: dict[str, threading.Lock] = {}

    def lock(self, key: str) -> threading.Lock:
        with self.guard:
            return self.locks.setdefault(key, threading.Lock())

    def paths(self, key: str) -> tuple[Path, Path]:
        return self.folder / (key + ".mp4"), self.folder / (key + ".json")

    def store(self, key: str, data: bytes, receipt: dict) -> None:
        video_path, receipt_path = self.paths(key)
        temporary = video_path.with_suffix(".tmp")
        temporary.write_bytes(data)
        temporary.replace(video_path)
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")

    def load(self, key: str) -> tuple[Path, bytes, dict] | None:
        video_path, receipt_path = self.paths(key)
        if not (video_path.exists() and receipt_path.exists()):
            return None
        video, receipt = video_path.read_bytes(), json.loads(receipt_path.read_text())
        if hashlib.sha256(video).hexdigest() != receipt["encoded_sha256"]:
            raise ValueError(f"Cached video checksum mismatch: {video_path.name}")
        return video_path, video, receipt

    def encode_lossless(self, image_urls: list[str]) -> tuple[bytes, dict]:
        frames = fetch_frames(image_urls)
        encoded = [f["bytes"] for f in frames]
        data = encode_mp4(encoded, fps=self.fps)
        return data, lossless_receipt(frames, encoded, LOSSLESS_LABEL, data, self.fps)

    def lossless(self, image_urls: list[str]) -> tuple[Path, bytes, dict]:
        key = digest({"urls": image_urls, "encoding": LOSSLESS_LABEL})
        with self.lock(key):
            cached = self.load(key)
            if cached is None:
                self.store(key, *self.encode_lossless(image_urls))
                cached = self.load(key)
            if cached is None:
                raise RuntimeError(f"Video cache write failed for {key}")
            return cached

    def encode_compressed(self, source_path: Path, source_receipt: dict) -> tuple[bytes, dict]:
        with tempfile.TemporaryDirectory() as folder:
            data = ffmpeg(["-i", str(source_path)], LOSSY_CODEC, Path(folder) / "sequence.mp4")
        receipt = dict(source_receipt, encoding="ffmpeg libx264 crf=18 yuv420p; synthetic 1 FPS", encoding_key=COMPRESSED_LABEL,
                       encoded_sha256=hashlib.sha256(data).hexdigest(), source_encoded_sha256=source_receipt["encoded_sha256"],
                       provider_size_fallback=True)
        return data, receipt

    def compressed(self, image_urls: list[str], source_path: Path, source_receipt: dict) -> tuple[Path, bytes, dict]:
        key = digest({"urls": image_urls, "encoding": COMPRESSED_LABEL})
        with self.lock(key):
            cached = self.load(key)
            if cached is None:
                self.store(key, *self.encode_compressed(source_path, source_receipt))
                cached = self.load(key)
            if cached is None:
                raise RuntimeError(f"Video cache write failed for {key}")
            return cached
