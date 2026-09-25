"""Generate a Three.js codebase and proxy video directly from text."""
import argparse
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--prompt")
    inputs.add_argument("--prompt-file", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    prompt = (args.prompt_file.expanduser().read_text(encoding="utf-8")
              if args.prompt_file else args.prompt).strip()
    if not prompt:
        parser.error("The prompt must not be empty.")
    from cvm.program import generate
    output = args.output.expanduser().resolve()
    generate(prompt, output)
    print(f"Three.js codebase: {output / 'case'}")
    print(f"Three.js video: {output / 'proxy.mp4'}")


if __name__ == "__main__":
    main()
