"""Download and verify the pinned public MiniMax-H3 checkpoint components."""
import argparse
import hashlib
import json
from pathlib import Path

MANIFEST = Path(__file__).resolve().parent / "configs" / "h3_checkpoint.json"


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def localize_index(source, output, spec):
    if sha256(source) != spec["modular_index_sha256"]:
        raise ValueError("The upstream modular index differs from the pinned snapshot.")
    config = json.loads(source.read_text())
    for entry in config.values():
        if isinstance(entry, list) and len(entry) == 3 and isinstance(entry[2], dict):
            if entry[2]["pretrained_model_name_or_path"] != spec["repo"]:
                raise ValueError("Unexpected external component in the model index.")
            entry[2]["pretrained_model_name_or_path"] = str(output.resolve())
    target = output / "modular_model_index.json"
    target.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n")


def verify_index(output, spec):
    config = json.loads((output / "modular_model_index.json").read_text())
    for entry in config.values():
        if isinstance(entry, list) and len(entry) == 3 and isinstance(entry[2], dict):
            path = entry[2]["pretrained_model_name_or_path"]
            if Path(path).resolve() != output.resolve():
                raise ValueError("A model component is not bound to this local checkpoint.")
            entry[2]["pretrained_model_name_or_path"] = spec["repo"]
    digest = hashlib.sha256(json.dumps(config, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if digest != spec["normalized_index_sha256"]:
        raise ValueError("The localized model index changes more than component paths.")


def verify_files(output, spec):
    verify_index(output, spec)
    for name, expected in spec["files_sha256"].items():
        if sha256(output / name) != expected:
            raise ValueError(f"Checkpoint file differs from the pinned manifest: {name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("models/MiniMax-H3-ref2va"))
    parser.add_argument("--verify", action="store_true", help="Hash all downloaded files; reads about 210 GB")
    parser.add_argument("--verify-only", action="store_true", help="Check an existing local checkpoint, without downloads")
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    spec = json.loads(MANIFEST.read_text())
    if args.verify_only:
        verify_files(output, spec)
        print("All checkpoint hashes match the pinned manifest.")
        return
    from huggingface_hub import hf_hub_download, snapshot_download
    output.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        spec["repo"], revision=spec["revision"], local_dir=output, token=False,
        allow_patterns=[*spec["files_sha256"], "LICENSE"],
    )
    # Read the immutable cached upstream index, never an already localized copy.
    source = Path(hf_hub_download(spec["repo"], "modular_model_index.json",
                                 revision=spec["revision"], token=False))
    localize_index(source, output, spec)
    verify_index(output, spec)
    if args.verify:
        verify_files(output, spec)
        print("All checkpoint hashes match the pinned manifest.")
    else:
        print("Pinned checkpoint downloaded; use --verify-only for full content hashing.")
    print(output)


if __name__ == "__main__":
    main()
