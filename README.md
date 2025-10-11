# MeshCleaner

A Python utility for removing support structures from 3D model files. It detects connected components in a mesh and keeps the primary model while discarding probable supports

## Features

- Automatically detects and separates the main model from support structures
- Multiple component selection methods:
  - `first`: Select first component (usually the model)
  - `ratio`: Select component with lowest surface area to volume ratio
- Batch processing of multiple files
- Supports common mesh formats such as STL, OBJ and PLY
- Ship as a CLI installed via `uv` with a `meshcleaner` entry point

## Requirements

- Python 3.9 or newer
- `trimesh`, `numpy`, `tqdm`, `networkx`

These are installed automatically using the steps below.

## Installation

### Using uv (recommended)

```bash
git clone https://github.com/sudo-kraken/MeshCleaner.git
cd MeshCleaner

# Install the project and base runtime dependencies
uv sync

# If you also want developer tools such as pytest and ruff
uv sync --extra dev
```

This project is configured as a package, so the console script `meshcleaner` is installed into the virtual environment.

### Alternative: pip

If you prefer `pip` and a traditional requirements file:

```bash
pip install -r requirements.txt
```

Note: the `requirements.txt` can be generated from the lock when needed:

```bash
uv export --format requirements-txt --output requirements.txt
```

## Usage

You can run MeshCleaner either as a CLI entry point or as a Python module.

### CLI

```bash
# Using uv
uv run meshcleaner -i INPUT_DIR -o OUTPUT_DIR [options]

# Once the venv is active, you can also call the script directly
meshcleaner -i INPUT_DIR -o OUTPUT_DIR [options]
```

### Python module

```bash
uv run python -m clean_mesh -i INPUT_DIR -o OUTPUT_DIR [options]
```

### Options

- `-i, --input`    Input directory containing 3D model files. Required.
- `-o, --output`   Output directory for processed files. Required.
- `-m, --method`   Component selection method. One of `first` or `ratio`. Default is `first`.
- `-f, --formats`  Comma separated list of file formats to process. Default is `stl`.
- `-v, --verbose`  Enable verbose logging.

### Examples

Process all STL files in a directory using default settings:
```bash
uv run meshcleaner -i "./models" -o "./cleaned"
```

Process multiple file formats and use the ratio method:
```bash
uv run meshcleaner -i "./models" -o "./cleaned" -m ratio -f "stl,obj,ply"
```

## Library usage

You can import functions if you want to call MeshCleaner from another project:

```python
from clean_mesh import process_file, process_directory, select_main_component

# Single file
process_file("input.stl", "output.stl", method="ratio")

# Whole directory
process_directory("input_dir", "output_dir", formats=["stl", "obj"], method="first", verbose=True)
```

## Development

### Run tests

```bash
# Ensure dev tools are installed
uv sync --extra dev

# Run tests and coverage
uv run pytest -q
```

There is an optional integration test that looks for a `test.stl` file in the repository root. If it is not present the test is skipped.

### Linting

```bash
uv run ruff check .
uv run ruff format .
```

### Lock file management

- Create or refresh the lock:
  ```bash
  uv lock
  ```

- Recreate after interpreter or index changes:
  ```bash
  uv lock --recreate
  ```

- Upgrade packages within constraints:
  ```bash
  uv lock --upgrade
  uv lock --upgrade-package trimesh
  ```

### Export pinned requirements

```bash
uv export --format requirements-txt --output requirements.txt
```

## GitHub Actions

This repository includes a workflow that checks `uv.lock` freshness on Renovate pull requests. It validates that `uv.lock` is consistent with `pyproject.toml` and fails the PR if not.

## Troubleshooting

- `no graph engines available`: install `networkx` which MeshCleaner depends on. It is included in `pyproject.toml` and will be installed by `uv sync`.
- On Windows, the console script is installed at `.venv/Scripts/meshcleaner.exe` when the venv is created by uv. Prefer `uv run meshcleaner ...` to avoid path issues.
