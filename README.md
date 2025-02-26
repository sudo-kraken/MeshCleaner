# MeshCleaner

A Python tool for removing support structures from 3D model files. This utility helps in post-processing 3D prints by identifying and removing support structures, keeping only the main model.

## Features

- Automatically detects and separates the main model from support structures
- Multiple component selection methods:
  - `first`: Select first component (usually the model)
  - `ratio`: Select component with lowest surface area to volume ratio
- Processes multiple files in batch
- Supports various file formats

## Installation

1. Clone the repository:
   ```
   git clone https://github.com/sudo-kraken/MeshCleaner.git
   cd MeshCleaner
   ```

2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

## Usage

```
python clean_mesh.py -i INPUT_DIR -o OUTPUT_DIR [options]
```

### Options

- `-i, --input`: Input directory containing 3D model files (required)
- `-o, --output`: Output directory for processed files (required)
- `-m, --method`: Method to select main component (`first` or `ratio`, default: `first`)
- `-f, --formats`: Comma-separated list of file formats to process (default: `stl`)
- `-v, --verbose`: Enable verbose output

### Examples

Process all STL files in a directory using default settings:
```py
python clean_mesh.py -i "input_folder" -o "output_folder"
```

Process multiple file formats and use ratio method:
```py
python clean_mesh.py -i "input_folder" -o "output_folder" -m ratio -f "stl,obj"
```