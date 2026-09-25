"""Generate a MiniMax-H3 video from explicit proxy, reference image, and text inputs."""
import argparse
from pathlib import Path

from cvm import KEEP_STEPS, SEED, STEPS


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--code-video", type=Path, required=True)
    parser.add_argument("--reference-image", type=Path, required=True)
    text = parser.add_mutually_exclusive_group(required=True)
    text.add_argument("--prompt")
    text.add_argument("--prompt-file", type=Path)
    parser.add_argument("--model-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--keep-steps", type=int, default=KEEP_STEPS)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--text-device", default="cuda:1")
    parser.add_argument("--generation-device", default="cuda:0")
    args = parser.parse_args(argv)
    if not 0 <= args.keep_steps <= STEPS:
        parser.error(f"--keep-steps must be between 0 and {STEPS}.")
    proxy = args.code_video.expanduser().resolve()
    reference = args.reference_image.expanduser().resolve()
    model = args.model_root.expanduser().resolve()
    output = args.output.expanduser().resolve()
    for path in (proxy, reference):
        if not path.is_file():
            parser.error(f"Input does not exist: {path}")
    if not model.is_dir():
        parser.error(f"Checkpoint directory does not exist: {model}")
    if output.exists():
        parser.error(f"Refusing to overwrite {output}")
    prompt = (args.prompt_file.expanduser().read_text(encoding="utf-8")
              if args.prompt_file else args.prompt).strip()
    if not prompt:
        parser.error("The prompt must not be empty.")
    from cvm.video import generate
    generate(proxy, reference, prompt, model, output, seed=args.seed,
             keep_steps=args.keep_steps, text_device=args.text_device,
             generation_device=args.generation_device)
    print(f"Generated video: {output}")


if __name__ == "__main__":
    main()
