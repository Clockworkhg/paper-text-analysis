import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.validation import generate_validation_artifacts


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate review templates, validation report, and method text outputs.")
    parser.add_argument("output_dir", help="Pipeline output directory")
    parser.add_argument("--sample-size", type=int, default=50, help="Rows to sample per review sheet")
    args = parser.parse_args()

    paths = generate_validation_artifacts(Path(args.output_dir), sample_size=args.sample_size)
    for name, path in paths.items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
