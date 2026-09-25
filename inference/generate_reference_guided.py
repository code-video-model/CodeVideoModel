"""Generate a reference image from a Three.js first frame and a text prompt."""
from .generate_reference import main as reference_main


def main(argv=None):
    reference_main(argv, guided=True)


if __name__ == "__main__":
    main()
