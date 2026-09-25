"""Small, immutable anchor snapshots shared by the two pair-edit stages."""
import hashlib
import json
from pathlib import Path
import shutil

from PIL import Image

from . import WIDTH, HEIGHT, FPS, FRAMES

TYPES = ("scene", "robot", "trajectory")
FILES = ("settings.json", "prompt.txt", "prompt.json")
SOURCE_SUFFIXES = {".js", ".mjs", ".html", ".css", ".json", ".glsl", ".wgsl"}


def case_files(root):
    case = root / "case"
    files = sorted(p for p in case.rglob("*") if p.is_file() and p.suffix in SOURCE_SUFFIXES)
    if not (case / "index.html").is_file() or not any(p.suffix in {".js", ".mjs"} for p in files):
        raise ValueError("An anchor/candidate needs case/index.html and procedural JavaScript.")
    for path in files:
        if path.is_symlink() or not path.resolve().is_relative_to(case.resolve()):
            raise ValueError("Case sources must not point outside the case directory.")
    return tuple(str(p.relative_to(root)) for p in files)


def source_files(root):
    return FILES + case_files(root)


def variant_files(root):
    return ("settings.json", "proxy.mp4") + case_files(root)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(output, data):
    (output / "pair.json").write_text(json.dumps(data, indent=2), encoding="utf-8")


def prepare(anchor, output, prompt, edit, kind):
    anchor, output = anchor.resolve(), output.resolve()
    if anchor == output or anchor.is_relative_to(output) or output.is_relative_to(anchor):
        raise ValueError("Anchor and variant directories must be separate and non-nested.")
    if kind not in TYPES or not isinstance(edit, str) or not edit.strip():
        raise ValueError("Pair editing requires a supported type and a non-empty edit.")
    files = source_files(anchor)
    if "case/camera_trajectory.json" not in files:
        raise ValueError("The anchor must contain its camera trajectory for strict pair editing.")
    for name in files:
        path = anchor / name
        if not path.is_file() or not path.resolve().is_relative_to(anchor):
            raise ValueError(f"Missing or external anchor file: {name}")
    expected = dict(width=WIDTH, height=HEIGHT, fps=FPS, frames=FRAMES)
    if json.loads((anchor / "settings.json").read_text()) != expected:
        raise ValueError("Anchor settings differ from this pipeline's rendering contract.")
    snapshot = output / "anchor"
    snapshot.mkdir()
    for name in files:
        (snapshot / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(anchor / name, snapshot / name)
    for name in case_files(anchor):
        (output / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(snapshot / name, output / name)
    (output / "edit.txt").write_text(edit.strip(), encoding="utf-8")
    data = {
        "anchor": str(anchor), "type": kind, "edit": edit.strip(),
        "target_prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "anchor_files": {name: digest(snapshot / name) for name in files},
    }
    save(output, data)
    return data


def load(output):
    path = output / "pair.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    if data.get("type") not in TYPES or not isinstance(data.get("edit"), str) or not data["edit"].strip():
        raise ValueError("Invalid pair type or edit in pair.json.")
    if set(data["anchor_files"]) != set(source_files(output / "anchor")):
        raise ValueError("Incomplete anchor snapshot.")
    if digest(output / "prompt.txt") != data["target_prompt_sha256"]:
        raise ValueError("The pair's target prompt changed.")
    if json.loads((output / "prompt.json").read_text()).get("prompt") != (output / "prompt.txt").read_text():
        raise ValueError("The pair's structured prompt changed.")
    if (output / "edit.txt").read_text() != data["edit"]:
        raise ValueError("The requested pair edit changed.")
    for name, sha in data["anchor_files"].items():
        if digest(output / "anchor" / name) != sha:
            raise ValueError(f"Anchor snapshot changed: {name}")
    if "variant_files" in data:
        if set(data["variant_files"]) != set(variant_files(output)):
            raise ValueError("Incomplete variant provenance.")
        for name, sha in data["variant_files"].items():
            if digest(output / name) != sha:
                raise ValueError(f"Variant artifact changed: {name}")
    for key, path in (("reference_input_sha256", output / "anchor/reference.png"),
                      ("reference_output_sha256", output / "reference.png")):
        if key in data and digest(path) != data[key]:
            raise ValueError(f"Paired reference changed: {path.name}")
    return data


def reference_input(output, data):
    target = output / "anchor/reference.png"
    if "reference_input_sha256" not in data:
        anchor = Path(data["anchor"])
        for name, sha in data["anchor_files"].items():
            if digest(anchor / name) != sha:
                raise ValueError("The original anchor changed before its reference was bound.")
        source = anchor / "reference.png"
        if not source.is_file() or not source.resolve().is_relative_to(anchor):
            raise ValueError("The anchor reference is missing or outside its directory.")
        with Image.open(source) as image:
            image.verify()
        if target.exists() and digest(target) != digest(source):
            raise ValueError("An unexpected image occupies the anchor snapshot.")
        shutil.copyfile(source, target)
        data["reference_input_sha256"] = digest(target)
        save(output, data)
    if digest(target) != data["reference_input_sha256"]:
        raise ValueError("The bound anchor reference changed.")
    return target
