"""Deterministic canvas rendering and a five-frame visual review sheet."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import math
import mimetypes
from pathlib import Path
import secrets
import subprocess
import threading
from urllib.parse import unquote, urlsplit

from PIL import Image, ImageDraw, ImageOps
from playwright.sync_api import sync_playwright


def contact_sheet(frames, times, output):
    sheet = Image.new("RGB", (320 * len(frames), 202), "white")
    draw = ImageDraw.Draw(sheet)
    for i, (raw, t) in enumerate(zip(frames, times)):
        with Image.open(io.BytesIO(raw)) as frame:
            thumbnail = ImageOps.contain(frame.convert("RGB"), (320, 180))
        x = 320 * i + (320 - thumbnail.width) // 2
        sheet.paste(thumbnail, (x, 22))
        draw.text((320 * i + 5, 4), f"{t:.3f} s", fill="black")
    sheet.save(output)


def render(scene, mode, requested_times=None):
    scene = scene.resolve()
    settings = json.loads((scene / "settings.json").read_text())
    w, h, fps, count = (settings[k] for k in ("width", "height", "fps", "frames"))
    if any(not isinstance(v, int) or isinstance(v, bool) or v <= 0 for v in (w, h, fps, count)):
        raise ValueError("Rendering settings must be positive integers.")
    indices = sorted({round((count - 1) * f) for f in (0, .25, .5, .75, 1)})
    times = requested_times if requested_times is not None else [i / fps for i in indices]
    if not times or any(not 0 <= t <= (count - 1) / fps for t in times):
        raise ValueError("Preview times must lie within the video.")
    token = secrets.token_urlsafe(24)
    suffixes = {".html", ".js", ".mjs", ".css", ".json", ".glsl", ".wgsl"}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            name = unquote(urlsplit(self.path).path).lstrip("/") or "case/index.html"
            path = (scene / name).resolve()
            allowed = any(path.is_relative_to(scene / directory) for directory in ("case", "vendor"))
            if (self.headers.get("X-Render-Token") != token or not allowed
                    or path.suffix not in suffixes):
                self.send_error(403)
                return
            if not path.is_file() or not path.resolve().is_relative_to(scene):
                self.send_error(404)
                return
            body = path.read_bytes()
            self.send_response(200)
            content_type = "text/javascript" if path.suffix in {".js", ".mjs"} else mimetypes.guess_type(name)[0]
            self.send_header("Content-Type", content_type or "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    temporary = scene / "case/reconstruction.partial.mp4"
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(args=[
                "--disable-dev-shm-usage", "--use-gl=angle",
                "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
            page = browser.new_page(viewport={"width": w, "height": h},
                                    device_scale_factor=1,
                                    extra_http_headers={"X-Render-Token": token})
            origin = f"http://127.0.0.1:{server.server_port}"
            page.route("**/*", lambda route: route.continue_()
                       if route.request.url.startswith(origin + "/") else route.abort())
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(origin + "/case/index.html", wait_until="networkidle")
            if errors:
                raise RuntimeError("; ".join(errors))
            page.wait_for_function(
                "() => typeof window.reconstruction?.seek === 'function' && "
                "typeof window.reconstruction?.pause === 'function'")
            page.evaluate("window.reconstruction.pause()")
            canvas = page.locator("canvas")
            if canvas.count() != 1:
                raise ValueError("The scene must have exactly one canvas.")

            def capture(t):
                page.evaluate("async t => {await window.reconstruction.seek(t);}", t)
                if errors:
                    raise RuntimeError("; ".join(errors))
                raw = canvas.screenshot()
                with Image.open(io.BytesIO(raw)) as image:
                    if image.size != (w, h):
                        raise ValueError("Canvas size differs from the render contract.")
                return raw

            first = capture(0)
            capture((count - 1) / fps)
            if capture(0) != first:
                raise ValueError("seek() is not deterministic when called out of order.")
            if mode == "preview":
                contact_sheet([capture(t) for t in times], times, scene / "preview.png")
                return
            if not page.evaluate("typeof window.reconstruction.getCameraState === 'function'"):
                raise ValueError("Camera trajectory export requires getCameraState().")
            trajectory = []
            proc = subprocess.Popen([
                "ffmpeg", "-v", "error", "-y", "-f", "image2pipe", "-vcodec", "png",
                "-framerate", str(fps), "-i", "pipe:0", "-an", "-c:v", "libx264",
                "-pix_fmt", "yuv420p", "-threads", "1", str(temporary)],
                stdin=subprocess.PIPE)
            try:
                for i in range(count):
                    proc.stdin.write(capture(i / fps))
                    state = page.evaluate("window.reconstruction.getCameraState()")
                    for key, length in (("position", 3), ("quaternion", 4)):
                        values = state.get(key)
                        if (not isinstance(values, list) or len(values) != length
                                or any(isinstance(v, bool) or not isinstance(v, (int, float))
                                       or not math.isfinite(v) for v in values)):
                            raise ValueError(f"Invalid camera {key} at frame {i}.")
                    fov = state.get("fov")
                    if isinstance(fov, bool) or not isinstance(fov, (int, float)) or not 0 < fov < 180:
                        raise ValueError(f"Invalid camera FOV at frame {i}.")
                    trajectory.append({"frame": i, "time": i / fps, "position": state["position"],
                                       "quaternion": state["quaternion"], "fov": fov})
                proc.stdin.close()
                if proc.wait() != 0:
                    raise RuntimeError("FFmpeg failed to encode the proxy.")
            finally:
                if proc.poll() is None:
                    proc.terminate()
                    proc.wait()
            camera = dict(width=w, height=h, fps=fps, frames=count, trajectory=trajectory)
            camera_bytes = json.dumps(camera, indent=2).encode()
            anchor_camera = scene / "anchor/case/camera_trajectory.json"
            if anchor_camera.exists():
                expected = json.loads(anchor_camera.read_text())
                if {key: expected[key] for key in camera} != camera:
                    raise ValueError("The variant changed the anchor camera trajectory.")
                camera_bytes = anchor_camera.read_bytes()
            (scene / "case/camera_trajectory.json").write_bytes(camera_bytes)
            temporary.replace(scene / "case/reconstruction.mp4")
            browser.close()
        encoded = []
        for index in indices:
            encoded.append(subprocess.check_output([
                "ffmpeg", "-v", "error", "-i", str(scene / "case/reconstruction.mp4"),
                "-vf", f"select=eq(n\\,{index})", "-frames:v", "1",
                "-fps_mode", "passthrough", "-f", "image2pipe", "-vcodec", "png", "-"]))
        contact_sheet(encoded, [i / fps for i in indices], scene / "preview.png")
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("preview", "video"))
    parser.add_argument("--scene", type=Path, default=Path.cwd())
    parser.add_argument("--times", help="Comma-separated preview timestamps")
    args = parser.parse_args()
    render(args.scene, args.mode,
           [float(t) for t in args.times.split(",")] if args.times else None)
