"""Generate a photorealistic reference from a Three.js video's first frame."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile


def main(argv=None, *, guided=False):
    description = ("Generate a reference image from a Three.js first frame and a text prompt."
                   if guided else __doc__)
    parser = argparse.ArgumentParser(description=description)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--video", type=Path, help="Extract and edit the first decoded frame")
    inputs.add_argument("--first-frame", type=Path, help="Edit an already extracted first-frame image")
    if guided:
        text = parser.add_mutually_exclusive_group(required=True)
        text.add_argument("--prompt", help="Scene intent; exact first-frame alignment is not required")
        text.add_argument("--prompt-file", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    options = {}
    if guided:
        prompt = (args.prompt_file.expanduser().read_text(encoding="utf-8")
                  if args.prompt_file else args.prompt).strip()
        if not prompt:
            parser.error("The prompt must not be empty.")
        options["text_prompt"] = prompt
    source = (args.video or args.first_frame).expanduser().resolve()
    output = args.output.expanduser().resolve()
    if not source.is_file():
        parser.error(f"Input does not exist: {source}")
    if output.exists():
        parser.error(f"Refusing to overwrite {output}")
    if not os.environ.get("OPENROUTER_API_KEY"):
        parser.error("Set OPENROUTER_API_KEY in the environment.")
    from cvm.reference import generate
    if args.first_frame:
        generate(source, output, **options)
    else:
        with tempfile.TemporaryDirectory(prefix="cvm-first-frame-") as temporary:
            frame = Path(temporary) / "first_frame.png"
            subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-i", str(source),
                            "-frames:v", "1", str(frame)], check=True)
            generate(frame, output, **options)
    print(f"Reference image: {output}")


if __name__ == "__main__":
    main()
