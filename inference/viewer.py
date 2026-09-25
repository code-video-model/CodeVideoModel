"""Browse a generated Three.js workspace with playback, source, and world inspection."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import secrets
from urllib.parse import unquote, urlsplit

ASSETS = Path(__file__).resolve().parents[1] / "assets" / "viewer"
SOURCE_SUFFIXES = {".html", ".js", ".mjs", ".css", ".json", ".glsl", ".wgsl"}


def scene_file(root, name):
    relative = Path(name)
    if (relative.is_absolute() or not relative.parts
            or relative.parts[0] not in {"case", "vendor"}
            or any(part.startswith(".") for part in relative.parts)):
        return None
    path = (root / relative).resolve()
    if (not path.is_relative_to(root)
            or not path.is_relative_to(root / relative.parts[0])
            or path.suffix not in SOURCE_SUFFIXES or not path.is_file()):
        return None
    return path


def create_server(scene, port=8000):
    scene = Path(scene).expanduser().resolve()
    settings = json.loads((scene / "settings.json").read_text())
    for key in ("width", "height", "fps", "frames"):
        value = settings[key]
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"Scene setting {key} must be a positive integer.")
    for name in ("case/index.html", "vendor/three.module.js"):
        if scene_file(scene, name) is None:
            raise ValueError(f"Workspace is missing a local {name}.")
    config = dict(title=scene.name, **{key: settings[key] for key in ("width", "height", "fps", "frames")})
    token = secrets.token_urlsafe(24)
    prefix = f"/{token}/"
    assets = {path.name: path for path in ASSETS.iterdir() if path.is_file()}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            hosts = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
            url = unquote(urlsplit(self.path).path)
            if self.headers.get("Host") not in hosts or not url.startswith(prefix):
                self.send_error(403)
                return
            name = url[len(prefix):]
            if not name:
                path = assets["index.html"]
                body = path.read_bytes()
            elif name == "_viewer/config.json":
                path = Path("config.json")
                sources = sorted(
                    str(source.relative_to(scene)).replace("\\", "/")
                    for source in (scene / "case").rglob("*")
                    if scene_file(scene, str(source.relative_to(scene))) is not None
                )
                body = json.dumps(dict(config, sources=sources)).encode()
            elif name == "_viewer/three.js":
                path = scene_file(scene, "vendor/three.module.js")
                body = path.read_bytes()
            elif name.startswith("_viewer/") and name[8:] in assets:
                path = assets[name[8:]]
                body = path.read_bytes()
            elif name.startswith("_viewer/source/"):
                path = scene_file(scene, name[len("_viewer/source/"):])
                if path is None:
                    self.send_error(404)
                    return
                body = path.read_bytes()
            else:
                path = scene_file(scene, name)
                if path is None:
                    self.send_error(404)
                    return
                body = path.read_bytes()
                if name == "vendor/three.module.js":
                    body = assets["three-bridge.js"].read_bytes()
                elif name == "case/index.html":
                    # Install the clock/error bridge before any generated scene scripts.
                    html = body.decode("utf-8")
                    bridge = f'<script src="{prefix}_viewer/host.js"></script>'
                    if html.lstrip().lower().startswith("<!doctype"):
                        end = html.index(">") + 1
                        html = html[:end] + bridge + html[end:]
                    else:
                        html = "<!doctype html>" + bridge + html
                    body = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", (
                "text/javascript" if path.suffix in {".js", ".mjs"}
                else mimetypes.guess_type(str(path))[0] or "text/plain") + "; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy",
                             "default-src 'self'; script-src 'self' 'unsafe-inline'; "
                             "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
                             "connect-src 'self'; frame-ancestors 'self'; object-src 'none'")
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.viewer_url = f"http://127.0.0.1:{server.server_port}{prefix}"
    return server


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene", type=Path, required=True, help="Workspace containing settings.json and case/")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error("--port must be between 0 and 65535.")
    try:
        server = create_server(args.scene, args.port)
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))
    print(f"Open {server.viewer_url}\nPress Ctrl+C to stop. Only open trusted scene code.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
