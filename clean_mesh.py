import argparse
import glob
import logging
import os
from collections.abc import Iterable
from pathlib import Path

import trimesh
from tqdm import tqdm


def setup_logging(verbose: bool = False) -> None:
    """Configure logging based on verbosity level."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


def select_main_component(components: Iterable[trimesh.Trimesh], method: str = "first") -> trimesh.Trimesh:
    """
    Select the main component using a specified method.

    Args:
        components: Iterable of mesh components
        method: 'first' or 'ratio'
          - 'first': returns the first mesh in the list (which is usually the model)
          - 'ratio': returns the component with the lowest surface area to volume ratio
                     supports tend to be slender, hence a higher ratio

    Returns:
        The selected mesh component
    """
    components = list(components)
    if not components:
        raise ValueError("No components provided")

    if method == "first":
        return components[0]
    elif method == "ratio":
        best_comp = None
        best_ratio = float("inf")
        for comp in components:
            # guard against zero or tiny volumes
            vol = float(comp.volume) if getattr(comp, "volume", 0.0) and comp.volume > 1e-12 else 1e-12
            ratio = float(comp.area) / vol
            if ratio < best_ratio:
                best_ratio = ratio
                best_comp = comp
        assert best_comp is not None
        return best_comp
    else:
        # Default to first if method is not recognised
        return components[0]


def process_file(
    input_file: os.PathLike[str] | str, output_file: os.PathLike[str] | str, method: str = "first"
) -> bool:
    """
    Process a single 3D file to remove support structures.

    Args:
        input_file: Path to input file
        output_file: Path to output file
        method: Method for selecting the main component

    Returns:
        True if processing was successful, False otherwise
    """
    try:
        input_path = Path(input_file)
        output_path = Path(output_file)

        mesh = trimesh.load(input_path, force="mesh")
        components = list(mesh.split(only_watertight=False))

        if len(components) > 1:
            logging.debug("Found %d components in %s", len(components), input_path.name)
            processed_mesh = select_main_component(components, method=method)
        else:
            logging.debug("Only one component found in %s", input_path.name)
            processed_mesh = mesh

        output_path.parent.mkdir(parents=True, exist_ok=True)
        processed_mesh.export(output_path)
        return True
    except Exception as e:
        logging.error("Error processing %s: %s", input_file, str(e))
        return False


def process_directory(
    input_dir: os.PathLike[str] | str,
    output_dir: os.PathLike[str] | str,
    *,
    formats: Iterable[str] = ("stl",),
    method: str = "first",
    verbose: bool = False,
) -> int:
    """
    Process all meshes in a directory.

    Args:
        input_dir: Directory containing input meshes
        output_dir: Directory to write processed meshes
        formats: Iterable of filename extensions without dot
        method: Component selection method
        verbose: Enable verbose logging

    Returns:
        Number of files successfully processed
    """
    setup_logging(verbose)
    in_dir = Path(input_dir)
    out_dir = Path(output_dir)

    if not in_dir.exists():
        logging.error("Input directory '%s' does not exist", in_dir)
        return 0

    out_dir.mkdir(parents=True, exist_ok=True)

    fmt_list = [f.strip().lstrip(".").lower() for f in formats if f.strip()]
    files: list[Path] = []
    for fmt in fmt_list:
        # keep glob for compatibility with your original script
        files.extend([Path(p) for p in glob.glob(str(in_dir / f"*.{fmt}"))])

    if not files:
        logging.warning("No files found in '%s' with formats: %s", in_dir, fmt_list)
        return 0

    logging.info("Found %d files to process", len(files))

    success_count = 0
    for file in tqdm(files, desc="Processing files"):
        filename = file.name
        output_file = out_dir / filename

        if process_file(file, output_file, method=method):
            success_count += 1
            logging.debug("Successfully processed: %s", filename)

    logging.info(
        "Processing complete: %d/%d files processed successfully",
        success_count,
        len(files),
    )
    return success_count


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI argument parser."""
    parser = argparse.ArgumentParser(description="Process 3D models to remove support structures.")
    parser.add_argument(
        "--input",
        "-i",
        type=str,
        required=True,
        help="Input directory containing STL files",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        required=True,
        help="Output directory for processed files",
    )
    parser.add_argument(
        "--method",
        "-m",
        type=str,
        choices=["first", "ratio"],
        default="first",
        help="Method to select main component (default: first)",
    )
    parser.add_argument(
        "--formats",
        "-f",
        type=str,
        default="stl",
        help="Comma-separated list of file formats to process (default: stl)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Main function to process 3D models by removing support structures."""
    parser = build_parser()
    args = parser.parse_args(argv)

    # Validate input directory
    if not os.path.exists(args.input):
        logging.error("Input directory '%s' does not exist", args.input)
        return 1

    # Create the output directory if it does not exist
    if not os.path.exists(args.output):
        os.makedirs(args.output)
        logging.info("Created output directory: %s", args.output)

    # Parse file formats and run directory processing
    formats = [f.strip() for f in args.formats.split(",")]
    processed = process_directory(
        args.input,
        args.output,
        formats=formats,
        method=args.method,
        verbose=args.verbose,
    )

    # Non zero exit when nothing processed, to match tests
    return 0 if processed > 0 else 1


if __name__ == "__main__":
    exit_code = main()
    raise SystemExit(exit_code)
