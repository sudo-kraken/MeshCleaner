<div align="center">
<img src="docs/assets/logo.png" align="center" width="144px" height="144px"/>

### MeshCleaner

_A Python utility for removing support structures from 3D model files. It detects connected components in a mesh and keeps the primary model while discarding probable supports._
</div>

<div align="center">

[![Python](https://img.shields.io/python/required-version-toml?tomlFilePath=https%3A%2F%2Fraw.githubusercontent.com%2Fsudo-kraken%2FMeshCleaner%2Fmain%2Fpyproject.toml&logo=python&logoColor=yellow&color=3776AB&style=for-the-badge)](https://github.com/sudo-kraken/MeshCleaner/blob/main/pyproject.toml)

</div>

<div align="center">

[![OpenSSF Scorecard](https://img.shields.io/ossf-scorecard/github.com/sudo-kraken/MeshCleaner?label=openssf%20scorecard&style=for-the-badge)](https://scorecard.dev/viewer/?uri=github.com/sudo-kraken/MeshCleaner)

</div>

## Contents

- [Overview](#overview)
- [Architecture at a glance](#architecture-at-a-glance)
- [Features](#features)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
  - [Using uv recommended](#using-uv-recommended)
  - [Alternative pip](#alternative-pip)
- [Usage](#usage)
  - [CLI](#cli)
  - [Python module](#python-module)
  - [Options](#options)
  - [Examples](#examples)
- [Library usage](#library-usage)
- [Production notes](#production-notes)
- [Development](#development)
  - [Run tests](#run-tests)
  - [Linting](#linting)
  - [Lock file management](#lock-file-management)
  - [Export pinned requirements](#export-pinned-requirements)
- [GitHub Actions](#github-actions)
- [Troubleshooting](#troubleshooting)
- [Licence](#licence)
- [Security](#security)
- [Contributing](#contributing)
- [Support](#support)

## Overview

MeshCleaner automatically separates likely support structures from the main model component in common mesh formats. It provides a simple command line interface, batch processing and a small Python library for embedding in other tools.

## Architecture at a glance

- Python package with console entry point `meshcleaner`
- Component detection using `trimesh` connected components and `networkx` helpers
- Two selection strategies:
  - `first` selects the first (often largest or primary) component
  - `ratio` selects the component with the lowest surface area to volume ratio
- Batch processing pipeline for directories
- Designed to be installed and run via `uv` for reproducible environments

## Features

- Automatically detects and separates the main model from support structures
- Multiple component selection methods:
  - `first` select first component usually the model
  - `ratio` select component with lowest surface area to volume ratio
- Batch processing of multiple files
- Supports STL, OBJ and PLY
- Ships as a CLI via `uv` with the `meshcleaner` entry point

## Prerequisites

- Python 3.9 or newer
- The following Python libraries are installed automatically during setup:
  - `trimesh`, `numpy`, `tqdm`, `networkx`

## Installation

### Using uv recommended

```bash
git clone https://github.com/sudo-kraken/MeshCleaner.git
cd MeshCleaner

# Install the project and base runtime dependencies
uv sync

# If you also want developer tools such as pytest and ruff
uv sync --extra dev
```

This project is configured as a package, so the console script `meshcleaner` is installed into the virtual environment.

### Alternative pip

If you prefer `pip` and a traditional requirements file:

```bash
pip install -r requirements.txt
```

The `requirements.txt` can be generated from the lock when needed:

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

## Production notes

- Use `ratio` when your model has large smooth surfaces compared to sparse supports. Use `first` when components are already ordered such that the model is first.
- Keep backups of original files if running bulk operations. Write outputs to a separate directory using `-o`.
- For very large meshes, ensure sufficient memory is available. Consider processing formats individually with `-f` to reduce peak usage.
- Verbose mode `-v` helps diagnose component counts and selection decisions.

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

Create or refresh the lock:

```bash
uv lock
```

Recreate after interpreter or index changes:

```bash
uv lock --recreate
```

Upgrade packages within constraints:

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

- `no graph engines available`  
  Install `networkx` which MeshCleaner depends on. It is included in `pyproject.toml` and will be installed by `uv sync`.

- Windows notes  
  On Windows, the console script is installed at `.venv/Scripts/meshcleaner.exe` when the venv is created by uv. Prefer `uv run meshcleaner ...` to avoid path issues.

## Licence

This project is licensed under the MIT Licence. See the [LICENCE](LICENCE) file for details.

## Security

If you discover a security issue, please review and follow the guidance in [SECURITY.md](SECURITY.md), or open a private security-focused issue with minimal details and request a secure contact channel.

## Contributing

Feel free to open issues or submit pull requests if you have suggestions or improvements.  
See [CONTRIBUTING.md](CONTRIBUTING.md)

## Support

Open an [issue](/../../issues) with as much detail as possible, including your environment details and relevant logs or output.
