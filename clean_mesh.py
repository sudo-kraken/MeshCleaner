import trimesh
import os
import glob
import argparse
import logging
from tqdm import tqdm

def setup_logging(verbose=False):
    """Configure logging based on verbosity level."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format='%(levelname)s: %(message)s')

def select_main_component(components, method='first'):
    """
    Select the main component using a specified method.
    
    Args:
        components: List of mesh components
        method: 'first' or 'ratio'
          - 'first': returns the first mesh in the list (which is usually the model)
          - 'ratio': returns the component with the lowest surface area to volume ratio
                    (supports tend to be slender, hence a higher ratio)
    
    Returns:
        The selected mesh component
    """
    if method == 'first':
        return components[0]
    elif method == 'ratio':
        best_comp = None
        best_ratio = float('inf')
        for comp in components:
            vol = comp.volume if comp.volume > 1e-6 else 1e-6  # avoid division by zero
            ratio = comp.area / vol
            if ratio < best_ratio:
                best_ratio = ratio
                best_comp = comp
        return best_comp
    else:
        # Default to first if method is not recognised
        return components[0]

def process_file(input_file, output_file, method='first'):
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
        mesh = trimesh.load(input_file)
        components = mesh.split(only_watertight=False)
        
        if len(components) > 1:
            logging.debug(f"Found {len(components)} components in {os.path.basename(input_file)}")
            processed_mesh = select_main_component(components, method=method)
        else:
            logging.debug(f"Only one component found in {os.path.basename(input_file)}")
            processed_mesh = mesh

        processed_mesh.export(output_file)
        return True
    except Exception as e:
        logging.error(f"Error processing {input_file}: {str(e)}")
        return False

def main():
    """Main function to process 3D models by removing support structures."""
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Process 3D models to remove support structures.')
    parser.add_argument('--input', '-i', 
                      type=str, 
                      required=True,
                      help='Input directory containing STL files')
    parser.add_argument('--output', '-o', 
                      type=str, 
                      required=True,
                      help='Output directory for processed files')
    parser.add_argument('--method', '-m',
                      type=str,
                      choices=['first', 'ratio'],
                      default='first',
                      help='Method to select main component (default: first)')
    parser.add_argument('--formats', '-f',
                      type=str,
                      default="stl",
                      help='Comma-separated list of file formats to process (default: stl)')
    parser.add_argument('--verbose', '-v',
                      action='store_true',
                      help='Enable verbose output')
    
    args = parser.parse_args()
    
    # Set up logging
    setup_logging(args.verbose)
    
    # Validate input directory
    if not os.path.exists(args.input):
        logging.error(f"Input directory '{args.input}' does not exist")
        return 1
    
    # Create the output directory if it doesn't exist
    if not os.path.exists(args.output):
        os.makedirs(args.output)
        logging.info(f"Created output directory: {args.output}")

    # Parse file formats
    formats = [f.strip() for f in args.formats.split(',')]
    files = []
    for fmt in formats:
        pattern = os.path.join(args.input, f"*.{fmt}")
        files.extend(glob.glob(pattern))
    
    if not files:
        logging.warning(f"No files found in '{args.input}' with formats: {formats}")
        return 0
        
    logging.info(f"Found {len(files)} files to process")
    
    # Process all files
    success_count = 0
    for file in tqdm(files, desc="Processing files"):
        filename = os.path.basename(file)
        output_file = os.path.join(args.output, filename)
        
        if process_file(file, output_file, method=args.method):
            success_count += 1
            logging.debug(f"Successfully processed: {filename}")
    
    logging.info(f"Processing complete: {success_count}/{len(files)} files processed successfully")
    return 0

if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)
