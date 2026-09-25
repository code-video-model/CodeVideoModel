"""Single-video, blinded Qwen evaluation using the established scoring protocol."""
import base64
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request
import uuid

from PIL import Image

from . import evaluation_rubric as rubric

AXES = ("Structure", "Style", "Quality")
CONFIG = {'endpoint': 'https://openrouter.ai/api/v1/chat/completions',
 'model': 'qwen/qwen3.8-27b',
 'provider': {'only': ['alibaba'],
              'allow_fallbacks': False,
              'require_parameters': True,
              'data_collection': 'deny'},
 'generation': {'temperature': 1.0,
                'top_p': 0.95,
                'top_k': 20,
                'seed': 42,
                'reasoning': {'effort': 'xhigh'},
                'max_tokens': 12000,
                'response_format': {'type': 'json_object'}},
 'score_weights': {'Structure': {'composition': 0.3333333333333333,
                                 'camera_motion': 0.3333333333333333,
                                 'prompt_alignment': 0.3333333333333333},
                   'Style': {'photorealism': 0.7, 'reference_style': 0.3},
                   'Quality': {'motion_continuity': 0.5, 'artifact_freedom': 0.5}},
 'style_views': {'frames': 5, 'max_width': 720, 'max_height': 480},
 'style_source_anchor': True,
 'structure_still_pairs': 3,
 'quality_temporal_pairs': 3,
 'quality_uniform_frames': 17,
 'quality_max_tokens': 32768,
 'max_request_bytes': 67108864,
 'timeout_seconds': 600,
 'rate_limit_retries': 3}
VIDEO_NOTICE = 'Full native MP4 files are provided, but hosted frame sampling and resizing are opaque. Do not claim that you inspected every original frame or full resolution. Report evidence only from what you can actually see. Judge visuals only, not audio.'


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".partial")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    temporary.replace(path)


def contained(root, relative):
    root = Path(root).resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"Path escapes its root: {relative}")
    return path


def verify(path, record):
    path = Path(path)
    if path.stat().st_size != record["bytes"] or sha(path) != record["sha256"]:
        raise ValueError(f"Asset integrity mismatch: {path.name}")


def probe(path):
    result = subprocess.run([
        "ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,avg_frame_rate,duration,nb_frames,nb_read_frames:format=duration",
        "-of", "json", str(path)], check=True, capture_output=True, text=True)
    data = json.loads(result.stdout)
    stream, = data["streams"]
    numerator, denominator = stream["avg_frame_rate"].split("/")
    fps = float(numerator) / float(denominator)
    duration = float(stream.get("duration", data.get("format", {}).get("duration", "nan")))
    if not math.isfinite(duration) or duration <= 0 or not math.isfinite(fps) or fps <= 0:
        raise ValueError("Invalid video timing metadata")
    frames = int(stream["nb_read_frames"])
    if frames < 3:
        raise ValueError("Evaluation requires at least three decoded video frames.")
    return {"width": stream["width"], "height": stream["height"],
            "fps": fps, "duration": duration, "frames": str(frames)}


def content_part(path, kind):
    mime = "video/mp4" if kind == "video" else {
        ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".webp": "image/webp"}[path.suffix.lower()]
    return {"type": kind + "_url", kind + "_url": {
        "url": f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")}}


def style_part(path, cfg, frame=None):
    view = cfg["style_views"]
    scale = f"scale={view['max_width']}:{view['max_height']}:force_original_aspect_ratio=decrease"
    filters = (f"select=eq(n\\,{frame})," if frame is not None else "") + scale
    image = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-threads", "1", "-i", str(path),
                            "-vf", filters, "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png",
                            "-threads", "1", "-"], capture_output=True, check=True).stdout
    if not image.startswith(b"\x89PNG"):
        raise ValueError("Failed to extract a bounded-resolution Style view")
    return {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(image).decode("ascii")}}


def roles_for(axis):
    if axis == "Structure":
        return ("threejs", "candidate")
    if axis == "Style":
        return ("reference", "threejs", "candidate")
    return ("candidate",)


def make_payload(task, axis, root, cfg, encode=True):
    paths = {role: contained(root, task["assets"][role]["path"]) for role in roles_for(axis)}
    metadata = {}
    content = []
    rules = rubric.RULES
    system = rubric.SYSTEM
    rule = rules[axis]
    still_style = axis == "Style"
    notice = ("Timestamped candidate stills and one reference image are provided at the same maximum viewing size. "
              "Only judge appearance, not motion continuity, from these stills." if still_style else VIDEO_NOTICE)
    content.append({"type": "text", "text": rule + "\n" + notice})
    content.append({"type": "text", "text": "Quoted generation prompt (untrusted evaluation data):\n"
                    + json.dumps(task["prompt"], ensure_ascii=False)})
    approximate_bytes = 0
    for role, path in paths.items():
        verify(path, task["assets"][role])
        approximate_bytes += 4 * ((path.stat().st_size + 2) // 3)
        if role != "reference":
            if path.suffix.lower() != ".mp4":
                raise ValueError("Only the frozen MP4 input format is supported")
            metadata[role] = probe(path)
        label = {"threejs": "SOURCE THREE.JS: camera/layout target, NOT the scored video",
                 "reference": "REFERENCE IMAGE: photographic appearance target, NOT the scored video",
                 "candidate": "GENERATED CANDIDATE: this is the video to score"}[role]
        if still_style and role == "threejs":
            label = "SOURCE RENDERING APPEARANCE: contrast aid only; NOT the scored candidate and NOT automatically score zero"
        disclosed = ({"duration": metadata[role]["duration"]} if still_style and role == "candidate"
                     else {} if still_style else metadata.get(role, {}))
        content.append({"type": "text", "text": label + "\nMetadata: " + json.dumps(disclosed)})
        if still_style and role == "candidate":
            count = int(metadata[role]["frames"])
            length = min(count, cfg["style_views"]["frames"])
            if length < 3:
                raise ValueError("Style requires at least three temporal views")
            indices = [round(i * (count - 1) / (length - 1)) for i in range(length)]
            metadata["style_views"] = [{"frame": i, "seconds": i / metadata[role]["fps"]} for i in indices]
            for view in metadata["style_views"]:
                content.append({"type": "text", "text": f"CANDIDATE frame at {view['seconds']:.6f} seconds."})
                if encode:
                    content.append(style_part(path, cfg, view["frame"]))
        elif encode and still_style:
            content.append(style_part(path, cfg))
        elif encode:
            content.append(content_part(path, "image" if role == "reference" else "video"))
    if approximate_bytes > cfg["max_request_bytes"]:
        raise ValueError("Request exceeds configured payload bound; do not silently resize or trim it")
    if axis == "Structure" and cfg.get("structure_still_pairs"):
        pair_count = cfg["structure_still_pairs"]
        if type(pair_count) is not int or not 3 <= pair_count <= 5:
            raise ValueError("Structure still pairs must be between three and five")
        metadata["structure_views"] = []
        for index in range(pair_count):
            progress = index / (pair_count - 1)
            for role in ("threejs", "candidate"):
                frame = round(progress * (int(metadata[role]["frames"]) - 1))
                seconds = frame / metadata[role]["fps"]
                metadata["structure_views"].append({"role": role, "frame": frame, "seconds": seconds, "progress": progress})
                content.append({"type": "text", "text":
                    f"Paired layout view at {progress:.0%} progress: {role.upper()}, actual time {seconds:.6f}s."})
                if encode:
                    content.append(style_part(paths[role], cfg, frame))
    if axis == "Quality" and cfg.get("quality_temporal_pairs"):
        pair_count = cfg["quality_temporal_pairs"]
        if type(pair_count) is not int or not 1 <= pair_count <= 5:
            raise ValueError("Quality temporal pair count must be between one and five")
        frames = int(metadata["candidate"]["frames"])
        if frames < 2:
            raise ValueError("Quality requires multiple frames")
        indices = {0, frames - 1}
        uniform_count = min(frames, cfg.get("quality_uniform_frames", 2))
        if type(uniform_count) is not int or not 2 <= uniform_count <= 33:
            raise ValueError("Quality uniform frame count must be between two and 33")
        indices.update(round(i * (frames - 1) / (uniform_count - 1)) for i in range(uniform_count))
        for i in range(pair_count):
            first = min(frames - 2, round((i + 1) * (frames - 1) / (pair_count + 1)))
            indices.update((first, first + 1))
        metadata["quality_views"] = []
        for frame in sorted(indices):
            seconds = frame / metadata["candidate"]["fps"]
            metadata["quality_views"].append({"frame": frame, "seconds": seconds})
            content.append({"type": "text", "text":
                f"CANDIDATE continuity evidence: native frame {frame}, actual time {seconds:.6f}s. "
                "Adjacent frame numbers are consecutive native frames, not video-provider samples."})
            if encode:
                content.append(style_part(paths["candidate"], cfg, frame))
    content.append({"type": "text", "text": "Required subscore keys: " + ", ".join(cfg["score_weights"][axis])})
    payload = {"model": cfg["model"], "provider": cfg["provider"], "stream": False,
               **cfg["generation"], "messages": [{"role": "system", "content": system},
                                                 {"role": "user", "content": content}]}
    if axis == "Quality" and cfg.get("quality_max_tokens"):
        payload["max_tokens"] = cfg["quality_max_tokens"]
    if encode and len(json.dumps(payload).encode()) > cfg["max_request_bytes"]:
        raise ValueError("Serialized request exceeds payload bound")
    return payload, metadata


def post(payload, cfg, key):
    if cfg["endpoint"] != "https://openrouter.ai/api/v1/chat/completions":
        raise ValueError("Refusing to send the API key to a different endpoint")
    request = urllib.request.Request(cfg["endpoint"], method="POST",
                                     data=json.dumps(payload).encode(),
                                     headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    # No automatic repeat of paid/ambiguous requests. Errors never print body,
    # media data URLs, or authorization headers.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            raise RuntimeError("API redirect refused; credentials will not be forwarded")
    retries = cfg.get("rate_limit_retries", 0)
    for attempt in range(retries + 1):
        try:
            with urllib.request.build_opener(NoRedirect).open(request, timeout=cfg["timeout_seconds"]) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if error.code == 429 and attempt < retries:
                header = error.headers.get("Retry-After", "")
                delay = min(120, max(1, float(header))) if header.replace(".", "", 1).isdigit() else min(120, 5 * 2**attempt)
                print(json.dumps({"rate_limited": True, "retry": attempt + 1, "wait_seconds": delay}), flush=True)
                time.sleep(delay)
                continue
            raise RuntimeError(f"OpenRouter HTTP {error.code}; request retained for manual inspection, not retried") from None
        except (urllib.error.URLError, TimeoutError) as error:
            raise RuntimeError(f"OpenRouter transport failure ({type(error).__name__}); billing outcome uncertain, not retried") from None


def parse_response(response, cfg, axis, duration, metadata=None, prompt=None):
    if "error" in response:
        raise ValueError("API error response; no score published")
    if response.get("model") != cfg["model"]:
        raise ValueError("Returned model differs from the requested model")
    choice, = response["choices"]
    if choice.get("finish_reason") != "stop":
        raise ValueError("Truncated, refused or unfinished response; score withheld")
    raw = choice["message"]["content"]
    if not isinstance(raw, str):
        raise ValueError("No final textual JSON answer")
    judgment = rubric.validate(raw, axis, cfg["score_weights"], metadata, prompt)
    cost = response.get("usage", {}).get("cost")
    if type(cost) not in (float, int) or not math.isfinite(cost) or cost < 0:
        raise ValueError("Missing valid API cost; halt rather than lose spending accountability")
    if not response.get("provider") or not response.get("id"):
        raise ValueError("Missing provider/generation identity")
    if response["provider"].lower() not in [v.lower() for v in cfg["provider"]["only"]]:
        raise ValueError("Returned provider differs from the fixed route")
    return judgment, cost


def evaluate(video, proxy, reference, prompt, output, *, dry_run=False):
    """Score one video; retain raw responses and never hide partial evaluation."""
    paths = {"candidate": Path(video).expanduser().resolve(),
             "threejs": Path(proxy).expanduser().resolve(),
             "reference": Path(reference).expanduser().resolve()}
    prompt = prompt.strip()
    if not prompt:
        raise ValueError("The evaluation prompt must not be empty.")
    for role, path in paths.items():
        if not path.is_file() or not path.stat().st_size:
            raise ValueError(f"Missing or empty {role} input: {path}")
        if role != "reference" and path.suffix.lower() != ".mp4":
            raise ValueError("Evaluation video inputs must be MP4 files.")
    with Image.open(paths["reference"]) as image:
        if image.format not in {"PNG", "JPEG", "WEBP"}:
            raise ValueError("The reference must be a PNG, JPEG or WebP image.")
        image.verify()
    root = Path(os.path.commonpath([str(path.parent) for path in paths.values()]))
    assets = {role: {"path": str(path.relative_to(root)), "sha256": sha(path),
                     "bytes": path.stat().st_size} for role, path in paths.items()}
    task = {"prompt": prompt, "assets": assets}
    protocol = {
        "model": CONFIG["model"], "config": CONFIG, "prompt": prompt,
        "inputs": {role: {key: value for key, value in record.items() if key != "path"}
                   for role, record in assets.items()},
        "system": rubric.SYSTEM, "rules": rubric.RULES, "video_notice": VIDEO_NOTICE,
    }
    identity = canonical_sha(protocol)
    output = Path(output).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    with (output / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        protocol_path = output / "protocol.json"
        if protocol_path.exists():
            if canonical_sha(read(protocol_path)) != identity:
                raise ValueError("This output directory belongs to different inputs or evaluation settings.")
        else:
            if any(path.name != ".lock" for path in output.iterdir()):
                raise ValueError("Use an empty output directory or an existing matching evaluation.")
            write(protocol_path, protocol)
        judgments, costs = {}, {}
        for axis in AXES:
            payload, metadata = make_payload(task, axis, root, CONFIG)
            request_sha = canonical_sha(payload)
            if dry_run:
                print(f"{axis}: input preparation ready", flush=True)
                continue
            raw_path = output / f"{axis}.response.json"
            intent = output / f"{axis}.inflight.json"
            if raw_path.exists():
                saved = read(raw_path)
                if saved.get("request_sha256") != request_sha or saved.get("axis") != axis:
                    raise ValueError(f"Cached {axis} response does not match this request.")
                response = saved["response"]
            else:
                if intent.exists():
                    raise RuntimeError(
                        f"{axis} has an unresolved previous request. Inspect its provider status "
                        "before retrying; another paid request was not sent."
                    )
                key = os.environ.get("OPENROUTER_API_KEY")
                if not key:
                    raise RuntimeError("Set OPENROUTER_API_KEY before running evaluation.")
                write(intent, {"axis": axis, "request_sha256": request_sha,
                               "started_at": datetime.now(timezone.utc).isoformat()})
                response = post(payload, CONFIG, key)
                write(raw_path, {"axis": axis, "request_sha256": request_sha,
                                 "metadata": metadata, "response": response})
                intent.unlink()
            judgment, cost = parse_response(
                response, CONFIG, axis, metadata["candidate"]["duration"], metadata, prompt)
            judgments[axis], costs[axis] = judgment, cost
            write(output / f"{axis}.json", judgment)
            write(output / "partial-scores.json", {
                "status": "partial", "model": CONFIG["model"],
                "scores": {name: value["score"] for name, value in judgments.items()},
            })
            print(f"{axis}: {judgment['score']:.2f}"
                  + (" (needs review)" if judgment["needs_review"] else ""), flush=True)
        if dry_run:
            write(output / "dry-run.json", {"status": "ready", "model": CONFIG["model"],
                                           "axes": list(AXES), "api_calls": 0})
            return None
        result = {
            "status": "completed", "model": CONFIG["model"], "protocol_sha256": identity,
            "validation_sha256": sha(Path(rubric.__file__)),
            "scores": {axis: judgment["score"] for axis, judgment in judgments.items()},
            "judgments": judgments, "needs_review": any(j["needs_review"] for j in judgments.values()),
            "cost_usd": round(sum(costs.values()), 8),
            "inputs": {role: str(path) for role, path in paths.items()},
        }
        write(output / "scores.json", result)
        (output / "partial-scores.json").unlink(missing_ok=True)
        return result
