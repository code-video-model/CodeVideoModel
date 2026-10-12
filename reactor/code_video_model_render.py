"""CPU-only rendering service for generated JavaScript, isolated from the GPU service.

Run serve in an unprivileged, networkless, resource-limited container with no
credentials, weights or Docker socket. The GPU application speaks HTTP over a
shared Unix socket. Chromium and FFmpeg never execute in the GPU process.
"""

import argparse
import io
import json
import os
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import zipfile
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler
from pathlib import Path, PurePosixPath
from socketserver import UnixStreamServer

LIMIT = 8 * 1024 * 1024
SETTINGS = {"width": 960, "height": 544, "fps": 24, "frames": 124}


def extract_scene(data: bytes, target: Path, source: Path) -> None:
    """Extract text scene modules only; use the trusted renderer and Three.js."""
    if len(data) > LIMIT:
        raise ValueError("Scene ZIP exceeds 8 MiB")
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ValueError("Scene must be a ZIP archive") from exc
    with archive:
        members = archive.infolist()
        if len(members) > 128 or sum(m.file_size for m in members) > LIMIT:
            raise ValueError(
                "Scene has too many files or exceeds the expanded size limit"
            )
        seen = set()
        for member in members:
            name = PurePosixPath(member.filename)
            if (
                name.is_absolute()
                or ".." in name.parts
                or "\\" in member.filename
                or stat.S_ISLNK(member.external_attr >> 16)
            ):
                raise ValueError("Unsafe archive path")
            if member.is_dir():
                continue
            # Export a workspace with just case/. Vendor and settings are server-owned.
            if (
                len(name.parts) < 2
                or name.parts[0] != "case"
                or name.suffix
                not in {".html", ".js", ".mjs", ".css", ".json", ".glsl", ".wgsl"}
            ):
                raise ValueError("ZIP may contain only text files under case/")
            if str(name) in seen:
                raise ValueError("Duplicate archive path")
            seen.add(str(name))
            raw = archive.read(member)
            raw.decode("utf-8")
            path = target / str(name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
    if not (target / "case/index.html").is_file():
        raise ValueError("Scene needs case/index.html")
    (target / "settings.json").write_text(json.dumps(SETTINGS))
    shutil.copytree(source / "vendor", target / "vendor")


class UnixHTTPConnection(HTTPConnection):
    def __init__(self, path):
        super().__init__("localhost", timeout=350)
        self.path = str(path)

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.path)


def render_remote(path: Path, data: bytes) -> bytes:
    if len(data) > LIMIT:
        raise ValueError("Scene ZIP exceeds 8 MiB")
    connection = UnixHTTPConnection(path)
    try:
        connection.request(
            "POST", "/render", body=data, headers={"Content-Type": "application/zip"}
        )
        response = connection.getresponse()
        result = response.read(64 * 1024 * 1024 + 1)
        if response.status != 200:
            raise ValueError(result.decode(errors="replace")[:1000])
        if len(result) > 64 * 1024 * 1024:
            raise ValueError("Renderer output exceeds the limit")
        return result
    finally:
        connection.close()


def serve(path: Path, source: Path) -> None:
    if not Path("/.dockerenv").exists() or os.getuid() == 0:
        raise RuntimeError(
            "Renderer must run as a non-root user inside its isolated container"
        )
    if path.exists():
        raise FileExistsError(
            f"Socket already exists: {path}; check for an active renderer"
        )

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.connection.settimeout(30)
            if self.path != "/render":
                self.send_error(404)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= LIMIT:
                    raise ValueError("Invalid scene length")
                data = self.rfile.read(length)
                if len(data) != length:
                    raise ValueError("Incomplete scene upload")
                with tempfile.TemporaryDirectory() as directory:
                    workspace = Path(directory)
                    extract_scene(data, workspace, source)
                    with tempfile.TemporaryFile() as log:
                        child = subprocess.Popen(
                            [
                                sys.executable,
                                str(source / "inference/render.py"),
                                "video",
                                "--scene",
                                str(workspace),
                            ],
                            stdout=log,
                            stderr=log,
                            start_new_session=True,
                        )
                        try:
                            code = child.wait(timeout=300)
                        except subprocess.TimeoutExpired as exc:
                            raise ValueError(
                                "Scene rendering exceeded 300 seconds"
                            ) from exc
                        finally:
                            # Kill the entire owned browser/encoder group, including orphan descendants.
                            try:
                                os.killpg(child.pid, signal.SIGKILL)
                            except ProcessLookupError:
                                pass
                            child.wait()
                        if code:
                            log.seek(0)
                            print(
                                "Native renderer failed:",
                                repr(log.read(8192).decode(errors="replace")),
                                flush=True,
                            )
                            raise ValueError(
                                "Scene failed the native render contract; check deterministic seek and camera export"
                            )
                    result = (workspace / "case/reconstruction.mp4").read_bytes()
                status = 200
            except (ValueError, OSError, zipfile.BadZipFile, UnicodeError) as exc:
                result, status = str(exc).encode(), 400
            self.send_response(status)
            self.send_header("Content-Length", str(len(result)))
            self.end_headers()
            self.wfile.write(result)

        def log_message(self, format, *args):
            print(format % args, flush=True)

    def stop(signum, frame):
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, stop)
    try:
        with UnixStreamServer(str(path), Handler) as server:
            os.chmod(path, 0o660)
            server.serve_forever()
    finally:
        path.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    serve(args.socket, args.source)
