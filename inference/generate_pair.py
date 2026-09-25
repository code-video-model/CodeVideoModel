"""Create or continue a paired variant of an existing generated workspace."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
from PIL import Image

from cvm import WIDTH, HEIGHT, FPS, FRAMES, STEPS, KEEP_STEPS, SEED, PROGRAM_MODEL, IMAGE_MODEL, check_video
from cvm import pair


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt-file", type=Path, required=True, help="Complete scene description for variant B")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model-root", type=Path, help="Authorized MiniMax-H3 ref2va checkpoint")
    parser.add_argument("--stage", choices=("all", "program", "image", "video"), default="all",
                        help="Pair stage to run; image/video require an existing Pair workspace")
    parser.add_argument("--anchor", type=Path, help="Anchor A workspace; required when creating a Pair")
    parser.add_argument("--edit-file", type=Path, help="Change from A to B; required when creating a Pair")
    parser.add_argument("--pair-type", choices=pair.TYPES)
    parser.add_argument("--reuse-reference", action="store_true",
                        help="Reuse the anchor image instead of editing it; only for an unchanged first frame")
    parser.add_argument("--keep-steps", type=int, default=KEEP_STEPS)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--text-device", default="cuda:1")
    parser.add_argument("--generation-device", default="cuda:0")
    args = parser.parse_args()
    if not 0 <= args.keep_steps <= STEPS:
        parser.error(f"--keep-steps must be between 0 and {STEPS}.")
    prompt = args.prompt_file.expanduser().read_text(encoding="utf-8").strip()
    if not prompt:
        parser.error("The prompt file is empty.")
    output = args.output.expanduser().resolve()
    anchor = args.anchor.expanduser().resolve() if args.anchor else None
    edit = args.edit_file.expanduser().read_text(encoding="utf-8").strip() if args.edit_file else None
    if edit == "":
        parser.error("The edit file is empty.")
    creating = args.stage in ("all", "program")
    pairing = None
    if creating:
        if anchor is None or edit is None:
            parser.error("generate_pair.py only supports Pair editing. Supply --anchor and --edit-file "
                         "to create a variant; use the standalone inference modules for non-paired generation.")
    else:
        saved = output / "prompt.txt"
        if not saved.is_file() or saved.read_text().strip() != prompt:
            parser.error("This output directory belongs to a different prompt.")
        pairing = pair.load(output)
        if pairing is None:
            parser.error("generate_pair.py only supports Pair workspaces. Create a variant with "
                         "--stage program, --anchor, and --edit-file first.")
        if "variant_files" not in pairing:
            parser.error("Complete the pair's program stage before continuing.")
        for name, value in (("anchor", str(anchor) if anchor else None),
                            ("edit", edit), ("type", args.pair_type)):
            if value is not None and value != pairing[name]:
                parser.error(f"The supplied {name} differs from the saved pair specification.")
    if args.reuse_reference and args.stage not in ("all", "image"):
        parser.error("--reuse-reference requires --stage image/all.")
    if args.stage == "all" and not (anchor / "reference.png").is_file():
        parser.error("Generate the anchor's reference.png before running the complete pair pipeline.")
    if args.stage in ("all", "video") and args.model_root is None:
        parser.error("--model-root is required for video generation.")
    if args.stage in ("all", "video"):
        if not args.model_root.expanduser().is_dir():
            parser.error("The MiniMax-H3 checkpoint directory does not exist.")
        import importlib.util
        if (importlib.util.find_spec("diffusers") is None
                or importlib.util.find_spec("diffusers.modular_pipelines.minimax_h3") is None):
            parser.error("Install the authorized MiniMax-H3-compatible Diffusers backend first.")
    if args.stage in ("all", "image") and not args.reuse_reference and not os.environ.get("OPENROUTER_API_KEY"):
        parser.error("Set OPENROUTER_API_KEY before starting the image stage.")
    if creating:
        from cvm.program import generate
        generate(prompt, output, anchor=anchor, edit=edit, pair_type=args.pair_type or "scene")
        pairing = pair.load(output)
        if pairing is None:
            raise ValueError("The program stage did not produce a Pair workspace.")
    if args.stage in ("all", "image"):
        from cvm.reference import generate
        if (output / "reference.png").exists():
            raise FileExistsError(f"Refusing to overwrite {output / 'reference.png'}")
        check_video(output / "proxy.mp4")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(output / "proxy.mp4"),
                        "-frames:v", "1", str(output / "first_frame.png")], check=True)
        reference = pair.reference_input(output, pairing)
        if args.reuse_reference:
            with (output / "reference.png").open("xb") as stream:
                stream.write(reference.read_bytes())
        else:
            generate(reference, output / "reference.png",
                     edit=pairing["edit"], pair_type=pairing["type"],
                     group_id=Path(pairing["anchor"]).name, variant=output.name)
        pairing["reference_mode"] = "reuse" if args.reuse_reference else "edit"
        pairing["reference_output_sha256"] = pair.digest(output / "reference.png")
        pair.save(output, pairing)
    if args.stage in ("all", "video"):
        from cvm.video import generate
        pairing = pair.load(output)
        if pairing is None or "reference_output_sha256" not in pairing:
            raise ValueError("Complete the pair's image stage before video generation.")
        generate(output / "proxy.mp4", output / "reference.png", prompt,
                 args.model_root.expanduser().resolve(), output / "video.mp4",
                 seed=args.seed, keep_steps=args.keep_steps,
                 text_device=args.text_device, generation_device=args.generation_device)
    artifacts = {}
    for name in (*pair.case_files(output), "proxy.mp4", "reference.png", "video.mp4"):
        path = output / name
        if path.is_file():
            artifacts[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    reference_size = None
    if (output / "reference.png").is_file():
        with Image.open(output / "reference.png") as reference_image:
            reference_size = list(reference_image.size)
    (output / "run.json").write_text(json.dumps({
        "completed_stage": args.stage,
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "models": [PROGRAM_MODEL, IMAGE_MODEL, "MiniMax-H3"],
        "width": WIDTH, "height": HEIGHT, "fps": FPS, "frames": FRAMES,
        "steps": STEPS, "keep_steps": args.keep_steps, "seed": args.seed,
        "image_condition": "Qwen+VAE throughout", "artifacts": artifacts,
        "reference_size": reference_size,
        "pair": pairing,
    }, indent=2), encoding="utf-8")
    print(f"Completed {args.stage}: {output}")


if __name__ == "__main__":
    main()
