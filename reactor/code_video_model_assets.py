"""Resolve immutable source, native weights and bounded upload validation."""

import json
import subprocess
import tempfile
from pathlib import Path

import yaml

SOURCE_REVISION = "5f3bdc665246ca19861853144b7639495c510118"


def prepare_assets(config_path: Path | None, weights_root: Path) -> dict:
    config = yaml.safe_load(config_path.read_text()) if config_path else {}
    config = config or {}
    base = config_path.parent if config_path else Path.cwd()

    def path(key, default):
        value = Path(config.get(key, default)).expanduser()
        return value.resolve() if value.is_absolute() else (base / value).resolve()

    root = Path(weights_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    # An upstream checkout already contains cvm; Cookbook resolves one pinned checkout.
    adjacent = base.parent
    source = path(
        "source",
        adjacent if (adjacent / "cvm/video.py").is_file() else root / "CodeVideoModel",
    )
    if not source.exists():
        subprocess.run(
            [
                "git",
                "clone",
                "https://github.com/code-video-model/CodeVideoModel.git",
                str(source),
            ],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(source), "checkout", "--detach", SOURCE_REVISION],
            check=True,
        )
    if not (source / "cvm/video.py").is_file():
        raise ValueError(f"Missing CVM source: {source}")
    if source == root / "CodeVideoModel":
        revision = subprocess.check_output(
            ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
        ).strip()
        if revision != SOURCE_REVISION:
            raise ValueError(
                "Cached CVM source has a different revision; use a separate cache "
                "or explicitly configure source for your own checkout."
            )
    weights = path("weights", root / "MiniMax-H3-ref2va")
    if not (weights / "modular_model_index.json").is_file():
        import sys

        subprocess.run(
            [sys.executable, str(source / "download_h3.py"), "--output", str(weights)],
            check=True,
        )
    scratch = path("scratch", root / "scratch")
    scratch.mkdir(parents=True, exist_ok=True)
    return {
        "source": source,
        "weights": weights,
        "scratch": scratch,
        "render_socket": path("render_socket", root / "render/renderer.sock"),
        "text_device": config.get("text_device", "cuda:1"),
        "device": config.get("device", "cuda:0"),
    }


def validate_proxy(data: bytes, scratch: Path) -> None:
    if not data or len(data) > 64 * 1024 * 1024:
        raise ValueError("Proxy must be nonempty and <=64 MiB")
    with tempfile.TemporaryDirectory(dir=scratch) as directory:
        file = Path(directory) / "proxy.mp4"
        file.write_bytes(data)
        try:
            probe = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-count_frames",
                    "-show_streams",
                    "-of",
                    "json",
                    str(file),
                ],
                capture_output=True,
                timeout=30,
                check=True,
            )
            streams = json.loads(probe.stdout)["streams"]
            if len(streams) != 1:
                raise ValueError(
                    "Proxy must have exactly one video stream and no audio"
                )
            s = streams[0]
            from fractions import Fraction

            if (
                s["codec_type"],
                s["codec_name"],
                s["pix_fmt"],
                s["width"],
                s["height"],
                int(s["nb_read_frames"]),
                Fraction(s["avg_frame_rate"]),
            ) != ("video", "h264", "yuv420p", 960, 544, 124, 24):
                raise ValueError(
                    "Expected H.264/yuv420p, 960x544, 124 frames at 24 FPS, without audio"
                )
        except (subprocess.SubprocessError, KeyError, json.JSONDecodeError) as exc:
            raise ValueError("Invalid or undecodable proxy video") from exc
