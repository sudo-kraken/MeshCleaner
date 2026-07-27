from __future__ import annotations

import argparse
import logging
import math
import os
import shutil
import tempfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
import trimesh
from tqdm import tqdm

SELECTION_METHODS = ("largest", "first", "ratio")
SelectionMethod = Literal["largest", "first", "ratio"]
LOGGER = logging.getLogger(__name__)


def setup_logging(verbose: bool = False) -> None:
    """Configure logging based on verbosity level."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")
    LOGGER.setLevel(level)


def _component_area(component: trimesh.Trimesh) -> float:
    """Return a finite component area, or negative infinity when unavailable."""
    try:
        area = float(component.area)
    except (TypeError, ValueError, OverflowError):
        return -math.inf
    return area if math.isfinite(area) and area >= 0 else -math.inf


def _component_ratio(component: trimesh.Trimesh) -> float:
    """Return a valid surface-area-to-volume ratio, or infinity when undefined."""
    area = _component_area(component)
    try:
        volume = abs(float(component.volume))
    except (TypeError, ValueError, OverflowError):
        return math.inf

    if area <= 0 or not math.isfinite(volume) or volume <= 1e-12:
        return math.inf
    return area / volume


def select_main_component(
    components: Iterable[trimesh.Trimesh], method: SelectionMethod = "largest"
) -> trimesh.Trimesh:
    """
    Select a connected component using a specified method.

    Args:
        components: Iterable of mesh components
        method: 'largest', 'first' or 'ratio'
          - 'largest': returns the mesh with the greatest surface area
          - 'first': returns the first mesh reported by Trimesh
          - 'ratio': returns the component with the lowest surface area to volume ratio
                     supports tend to be slender, hence a higher ratio; falls back
                     to 'largest' when all component ratios are undefined

    Returns:
        The selected mesh component
    """
    components = list(components)
    if not components:
        raise ValueError("No components provided")

    if method == "largest":
        selected = max(components, key=_component_area)
        LOGGER.debug(
            "Selected largest component with surface area %.6g",
            _component_area(selected),
        )
        return selected
    if method == "first":
        LOGGER.debug("Selected the first component returned by Trimesh")
        return components[0]
    if method == "ratio":
        ratios = [(_component_ratio(component), component) for component in components]
        best_ratio, selected = min(ratios, key=lambda item: item[0])
        if math.isfinite(best_ratio):
            LOGGER.debug(
                "Selected component with surface-area-to-volume ratio %.6g",
                best_ratio,
            )
            return selected
        selected = max(components, key=_component_area)
        LOGGER.debug(
            "Component ratios were undefined; selected largest component with surface area %.6g",
            _component_area(selected),
        )
        return selected
    raise ValueError(f"Unknown component selection method: {method}")


def _export_data_bytes(data: object) -> bytes:
    """Convert exporter output to bytes."""
    if isinstance(data, str):
        return data.encode("utf-8")
    if isinstance(data, (bytes, bytearray, memoryview)):
        return bytes(data)
    raise TypeError(f"Unsupported mesh export data type: {type(data).__name__}")


def _stage_obj_export(
    mesh: trimesh.Trimesh,
    staged_output: Path,
    output_path: Path,
) -> tuple[Path, Path] | None:
    """Stage an OBJ and place its material assets in a model-specific directory."""
    mtl_name = f"{output_path.stem}.mtl"
    exported = mesh.export(
        file_type="obj",
        return_texture=True,
        write_texture=False,
        mtl_name=mtl_name,
    )
    if not isinstance(exported, tuple) or len(exported) != 2:
        raise TypeError("OBJ exporter did not return mesh and asset data")

    obj_data, assets = exported
    if not isinstance(assets, Mapping):
        raise TypeError("OBJ exporter returned invalid asset data")

    obj_text = _export_data_bytes(obj_data).decode("utf-8")
    if not assets:
        staged_output.write_bytes(obj_text.encode("utf-8"))
        return None
    if mtl_name not in assets:
        raise ValueError("OBJ export produced assets without its material file")

    assets_name = f"{output_path.name}_assets"
    source_reference = f"mtllib {mtl_name}"
    if source_reference not in obj_text.splitlines():
        raise ValueError("OBJ export did not reference its material file")
    obj_text = obj_text.replace(
        source_reference,
        f"mtllib {assets_name}/{mtl_name}",
        1,
    )
    staged_output.write_bytes(obj_text.encode("utf-8"))

    staged_assets = staged_output.parent / assets_name
    staged_assets.mkdir()
    for name, data in assets.items():
        if not isinstance(name, str) or not name or Path(name).name != name or "/" in name or "\\" in name:
            raise ValueError(f"OBJ export produced an unsafe asset name: {name!r}")
        (staged_assets / name).write_bytes(_export_data_bytes(data))

    return staged_assets, output_path.parent / assets_name


def _remove_output_path(path: Path) -> None:
    """Remove a newly published output while rolling back a failed commit."""
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def _preserve_rollback_backups(
    staging_dir: Path,
    backups: list[tuple[Path, Path]],
) -> Path | None:
    """Move unrestored backups outside temporary staging before it is removed."""
    existing = [(backup, destination) for backup, destination in backups if backup.exists() or backup.is_symlink()]
    if not existing:
        return None

    recovery_dir = Path(
        tempfile.mkdtemp(
            dir=staging_dir.parent,
            prefix=".meshcleaner-recovery-",
        )
    )
    recovery_backups = recovery_dir / "backups"
    try:
        os.rename(staging_dir / ".rollback", recovery_backups)
    except OSError:
        shutil.rmtree(recovery_dir, ignore_errors=True)
        return None

    mappings = [f"backups/{backup.name} -> {destination}" for backup, destination in existing]
    try:
        (recovery_dir / "RECOVERY.txt").write_text(
            "Previous outputs that could not be restored automatically:\n" + "\n".join(mappings) + "\n",
            encoding="utf-8",
        )
    except OSError:
        LOGGER.error(
            "Recovery copies were preserved at '%s', but the manifest could not be written",
            recovery_dir,
        )
    return recovery_dir


def _publish_staged_outputs(
    staging_dir: Path,
    publications: list[tuple[Path, Path]],
) -> None:
    """Replace a set of outputs and restore all prior files if any move fails."""
    destination_keys = [os.path.normcase(os.path.abspath(destination)) for _, destination in publications]
    if len(destination_keys) != len(set(destination_keys)):
        raise ValueError("Mesh export produced duplicate output paths")
    if any(not staged.exists() for staged, _ in publications):
        raise ValueError("Mesh export is missing a staged output")

    rollback_dir = staging_dir / ".rollback"
    rollback_dir.mkdir()
    backups: list[tuple[Path, Path]] = []
    published: list[Path] = []
    try:
        for index, (_, destination) in enumerate(publications):
            if destination.exists() or destination.is_symlink():
                backup = rollback_dir / str(index)
                backups.append((backup, destination))
                os.replace(destination, backup)

        for staged, destination in publications:
            published.append(destination)
            os.replace(staged, destination)
    except BaseException as publish_error:
        rollback_errors = []
        for destination in reversed(published):
            try:
                _remove_output_path(destination)
            except OSError as error:
                rollback_errors.append(error)
        for backup, destination in reversed(backups):
            if not backup.exists() and not backup.is_symlink():
                continue
            try:
                os.replace(backup, destination)
            except OSError as error:
                rollback_errors.append(error)

        if rollback_errors:
            recovery_dir = _preserve_rollback_backups(staging_dir, backups)
            recovery_message = (
                f" Recovery copies are available at '{recovery_dir}'." if recovery_dir is not None else ""
            )
            raise RuntimeError(
                f"Failed to publish mesh outputs and could not fully restore the previous outputs.{recovery_message}"
            ) from publish_error
        raise


def _is_same_or_descendant(path: Path, directory: Path) -> bool:
    """Return whether path is the directory itself or is contained by it."""
    try:
        path.relative_to(directory)
    except ValueError:
        return False
    return True


def process_file(
    input_file: os.PathLike[str] | str,
    output_file: os.PathLike[str] | str,
    method: SelectionMethod = "largest",
) -> bool:
    """
    Process a single 3D file by retaining one connected mesh component.

    Args:
        input_file: Path to input file
        output_file: Path to output file
        method: Method for selecting the retained component

    Returns:
        True if processing was successful, False otherwise
    """
    try:
        if method not in SELECTION_METHODS:
            raise ValueError(f"Unknown component selection method: {method}")

        input_path = Path(input_file)
        output_path = Path(output_file)
        if input_path.resolve() == output_path.resolve():
            raise ValueError("Input and output files must be different")

        mesh = trimesh.load(input_path, force="mesh")
        if isinstance(mesh, trimesh.Trimesh):
            if mesh.is_empty:
                raise ValueError("Input mesh contains no geometry")
            if not np.isfinite(mesh.vertices).all():
                raise ValueError("Input mesh contains non-finite vertices")

        components = list(mesh.split(only_watertight=False))

        if len(components) > 1:
            LOGGER.debug("Found %d components in %s", len(components), input_path.name)
            processed_mesh = select_main_component(components, method=method)
        else:
            LOGGER.debug("Only one component found in %s", input_path.name)
            processed_mesh = mesh

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            dir=output_path.parent,
            prefix=f".{output_path.stem}-",
        ) as temporary_directory:
            staging_dir = Path(temporary_directory)
            staged_output = staging_dir / output_path.name
            publications = []
            if output_path.suffix.casefold() == ".obj":
                assets_publication = _stage_obj_export(
                    processed_mesh,
                    staged_output,
                    output_path,
                )
                if assets_publication is not None:
                    publications.append(assets_publication)
            else:
                processed_mesh.export(staged_output)

            if not staged_output.is_file() or staged_output.stat().st_size == 0:
                raise ValueError("Mesh export produced an empty file")

            staged_sidecars = sorted(
                (
                    path
                    for path in staging_dir.iterdir()
                    if path != staged_output and (not publications or path != publications[0][0])
                ),
                key=lambda path: path.name,
            )
            if any(not path.is_file() for path in staged_sidecars):
                raise ValueError("Mesh export produced unsupported nested assets")
            for sidecar in staged_sidecars:
                publications.append((sidecar, output_path.parent / sidecar.name))
            publications.append((staged_output, output_path))

            resolved_input = input_path.resolve()
            if any(
                _is_same_or_descendant(
                    resolved_input,
                    destination.resolve(),
                )
                for _, destination in publications
            ):
                raise ValueError("An output path would replace the input file or one of its parent directories")
            _publish_staged_outputs(staging_dir, publications)
        return True
    except Exception as e:
        LOGGER.error("Error processing %s: %s", input_file, str(e))
        return False


@dataclass(frozen=True)
class _ProcessingResult:
    total: int
    succeeded: int


def _process_directory(
    input_dir: os.PathLike[str] | str,
    output_dir: os.PathLike[str] | str,
    *,
    formats: Iterable[str] | str = ("stl",),
    method: SelectionMethod = "largest",
    verbose: bool = False,
) -> _ProcessingResult:
    LOGGER.setLevel(logging.DEBUG if verbose else logging.INFO)
    in_dir = Path(input_dir)
    out_dir = Path(output_dir)

    if not in_dir.is_dir():
        if in_dir.exists():
            LOGGER.error("Input path '%s' is not a directory", in_dir)
        else:
            LOGGER.error("Input directory '%s' does not exist", in_dir)
        return _ProcessingResult(total=0, succeeded=0)

    if out_dir.exists() and not out_dir.is_dir():
        LOGGER.error("Output path '%s' is not a directory", out_dir)
        return _ProcessingResult(total=0, succeeded=0)

    resolved_input = in_dir.resolve()
    resolved_output = out_dir.resolve()
    if _is_same_or_descendant(
        resolved_input,
        resolved_output,
    ) or _is_same_or_descendant(resolved_output, resolved_input):
        LOGGER.error("Input and output directories must not overlap, to protect source files")
        return _ProcessingResult(total=0, succeeded=0)

    output_exists = out_dir.exists()
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        LOGGER.error("Unable to create output directory '%s': %s", out_dir, e)
        return _ProcessingResult(total=0, succeeded=0)
    if not output_exists:
        LOGGER.info("Created output directory: %s", out_dir)

    if isinstance(formats, str):
        formats = (formats,)
    format_set = {file_format.strip().lstrip(".").casefold() for file_format in formats}
    format_set.discard("")
    fmt_list = sorted(format_set)
    try:
        files = sorted(
            (path for path in in_dir.iterdir() if path.is_file() and path.suffix.lstrip(".").casefold() in format_set),
            key=lambda path: (path.name.casefold(), path.name),
        )
    except OSError as e:
        LOGGER.error("Unable to read input directory '%s': %s", in_dir, e)
        return _ProcessingResult(total=0, succeeded=0)

    if not files:
        LOGGER.warning("No files found in '%s' with formats: %s", in_dir, fmt_list)
        return _ProcessingResult(total=0, succeeded=0)

    LOGGER.info("Found %d files to process", len(files))

    success_count = 0
    for file in tqdm(files, desc="Processing files"):
        filename = file.name
        output_file = out_dir / filename

        if process_file(file, output_file, method=method):
            success_count += 1
            LOGGER.debug("Successfully processed: %s", filename)

    LOGGER.info(
        "Processing complete: %d/%d files processed successfully",
        success_count,
        len(files),
    )
    return _ProcessingResult(total=len(files), succeeded=success_count)


def process_directory(
    input_dir: os.PathLike[str] | str,
    output_dir: os.PathLike[str] | str,
    *,
    formats: Iterable[str] | str = ("stl",),
    method: SelectionMethod = "largest",
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
    result = _process_directory(
        input_dir,
        output_dir,
        formats=formats,
        method=method,
        verbose=verbose,
    )
    return result.succeeded


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI argument parser."""
    parser = argparse.ArgumentParser(description="Keep one connected component from each 3D model.")
    parser.add_argument(
        "--input",
        "-i",
        type=str,
        required=True,
        help="Input directory containing 3D model files",
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
        choices=SELECTION_METHODS,
        default="largest",
        help="Method to select the retained component (default: largest)",
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
    """Process 3D models by retaining one connected component."""
    parser = build_parser()
    args = parser.parse_args(argv)
    setup_logging(args.verbose)

    # Parse file formats and run directory processing
    formats = [f.strip() for f in args.formats.split(",")]
    result = _process_directory(
        args.input,
        args.output,
        formats=formats,
        method=args.method,
        verbose=args.verbose,
    )

    return 0 if result.total > 0 and result.succeeded == result.total else 1


if __name__ == "__main__":
    exit_code = main()
    raise SystemExit(exit_code)
