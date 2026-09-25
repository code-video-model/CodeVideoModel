"""GPT-6 creates a scene or edits an anchor copy through direct visual iteration."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

from . import WIDTH, HEIGHT, FPS, FRAMES, PROGRAM_MODEL, check_video
from . import pair

ROOT = Path(__file__).resolve().parents[1]
RENDERER = ROOT / "inference" / "render.py"


def generate(prompt: str, output: Path, *, anchor: Path | None = None,
             edit: str | None = None, pair_type: str = "scene") -> None:
    if (anchor is None) != (edit is None):
        raise ValueError("Supply both an anchor directory and the requested edit.")
    if anchor is not None:
        anchor = anchor.resolve()
        if output.resolve() == anchor or output.resolve().is_relative_to(anchor) or anchor.is_relative_to(output.resolve()):
            raise ValueError("Anchor and variant directories must be separate and non-nested.")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Program generation needs an empty directory: {output}")
    output.mkdir(parents=True, exist_ok=True)
    (output / "vendor").mkdir()
    (output / "case").mkdir()
    agents = output / ".github/agents"
    agents.mkdir(parents=True)
    shutil.copyfile(ROOT / "prompts/program.agent.md", agents / "video-prompt-threejs.agent.md")
    for name in ("three.module.js", "LICENSE.threejs"):
        shutil.copyfile(ROOT / "vendor" / name, output / "vendor" / name)
    shutil.copyfile(RENDERER, output / "render.py")
    shutil.copyfile(ROOT / "templates/index.html", output / "case/index.html")
    shutil.copyfile(ROOT / "prompts/program.md", output / "AGENTS.md")
    (output / "prompt.txt").write_text(prompt, encoding="utf-8")
    prompt_data = {"prompt": prompt}
    (output / "prompt.json").write_text(json.dumps(prompt_data), encoding="utf-8")
    settings = dict(width=WIDTH, height=HEIGHT, fps=FPS, frames=FRAMES)
    (output / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
    pair_data = None
    if anchor is not None:
        pair_data = pair.prepare(anchor, output, prompt, edit, pair_type)
    prompts = ROOT / "prompts"
    camera = (prompts / "camera_contract.md").read_text()
    task = (prompts / "program_header.md").read_text() + "\n" + (prompts / "program_contract.md").read_text()
    instructions = "No shared seed case is provided; create the group anchor from scratch."
    if pair_data is not None:
        rules = json.loads((prompts / "program_pair.json").read_text())
        instructions = "\n\n".join([
            rules["seed"], rules["guidance"][pair_type], rules["preservation"][pair_type],
            "Read edit.txt for the requested difference. Preserve the immutable "
            "anchor snapshot, pair.json, edit.txt, and prompt data. Before editing, "
            "render the copied scene and save anchor-preview.png for direct comparison.",
        ])
    task = task.replace("@PAIR_INSTRUCTIONS@", instructions).replace("@CAMERA@", camera)
    values = {"WORK": str(output), "ANCHOR": str(output / "anchor"),
              "WIDTH": str(WIDTH), "HEIGHT": str(HEIGHT), "FPS": str(FPS),
              "FRAMES": str(FRAMES), "DURATION": str(FRAMES / FPS),
              "PROMPT_SHA": pair.digest(output / "prompt.txt")}
    for key, value in values.items():
        task = task.replace(f"@{key}@", value)
    (output / "TASK.md").write_text(task, encoding="utf-8")
    locked = {str(p.relative_to(output)): pair.digest(p) for p in
              (output / "AGENTS.md", output / "TASK.md", agents / "video-prompt-threejs.agent.md")}
    subprocess.run([
        "copilot", "-C", str(output), "--model", PROGRAM_MODEL,
        "--agent", "video-prompt-threejs",
        "--reasoning-effort", "xhigh", "--allow-all-tools", "--no-ask-user",
        "--no-remote", "--no-remote-export", "--autopilot", "--prompt",
        f"Read {output / 'AGENTS.md'} and {output / 'TASK.md'}. "
        "Complete only this isolated prompt-to-Three.js task as one "
        "uninterrupted /goal session. No reference video exists. Build, "
        "render, directly inspect generated keyframes/contact sheets against "
        "the prompt, refine, and deliver the fresh Candidate without waiting "
        "for user feedback.",
    ], check=True)
    for name, sha in locked.items():
        if pair.digest(output / name) != sha:
            raise ValueError(f"The agent changed its instructions: {name}")
    if (output / "prompt.txt").read_text() != prompt:
        raise ValueError("The agent changed the target prompt.")
    if json.loads((output / "prompt.json").read_text()) != prompt_data:
        raise ValueError("The agent changed the structured prompt.")
    if pair_data is not None:
        if pair.load(output) != pair_data:
            raise ValueError("The agent changed the pair specification.")
        for name, sha in pair_data["anchor_files"].items():
            if pair.digest(anchor / name) != sha:
                raise ValueError(f"The original anchor changed during generation: {name}")
    if json.loads((output / "settings.json").read_text()) != settings:
        raise ValueError("The agent changed the rendering contract.")
    for name in ("three.module.js", "LICENSE.threejs"):
        if (output / "vendor" / name).read_bytes() != (ROOT / "vendor" / name).read_bytes():
            raise ValueError(f"The agent changed the shared runtime: {name}")
    result = json.loads((output / "result.json").read_text())
    if result.get("status") != "candidate":
        raise ValueError("The agent did not deliver a candidate.")
    pair.case_files(output)
    check_video(output / "case/reconstruction.mp4")
    # Use the trusted renderer, not a possibly modified workspace copy.
    subprocess.run([sys.executable, str(RENDERER), "video",
                    "--scene", str(output)], check=True)
    check_video(output / "case/reconstruction.mp4")
    camera = output / "case/camera_trajectory.json"
    if not camera.is_file():
        raise ValueError("The candidate has no camera trajectory.")
    if pair_data is not None and camera.read_bytes() != (output / "anchor/case/camera_trajectory.json").read_bytes():
        raise ValueError("The variant changed the anchor camera trajectory file.")
    shutil.copyfile(output / "case/reconstruction.mp4", output / "proxy.mp4")
    if pair_data is not None:
        pair_data["variant_files"] = {name: pair.digest(output / name) for name in pair.variant_files(output)}
        pair.save(output, pair_data)
