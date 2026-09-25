"""Evaluate Structure, Style and Quality with Qwen through OpenRouter."""
import argparse
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, required=True, help="Generated video to evaluate")
    parser.add_argument("--code-video", type=Path, required=True, help="Three.js structure and motion reference")
    parser.add_argument("--reference-image", type=Path, required=True, help="Appearance reference")
    text = parser.add_mutually_exclusive_group(required=True)
    text.add_argument("--prompt")
    text.add_argument("--prompt-file", type=Path)
    parser.add_argument("--output", type=Path, required=True, help="Directory for scores, evidence and responses")
    parser.add_argument("--dry-run", action="store_true", help="Prepare all inputs without sending API requests")
    args = parser.parse_args(argv)
    prompt = (args.prompt_file.expanduser().read_text(encoding="utf-8")
              if args.prompt_file else args.prompt).strip()
    if not prompt:
        parser.error("The prompt must not be empty.")
    from cvm.evaluation import evaluate
    result = evaluate(args.video, args.code_video, args.reference_image,
                      prompt, args.output, dry_run=args.dry_run)
    if result is not None:
        print(f"Evaluation: {args.output.expanduser().resolve() / 'scores.json'}")


if __name__ == "__main__":
    main()
