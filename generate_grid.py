import os
from PIL import Image
from pathlib import Path
import math
import shutil

TITLED_IMAGE_OUTPUT_DIR = "outputs/titled_image_output"
GRID_OUTPUT_DIR = "outputs/grid_output"

def clear_cache():
    """
    Clear only the grid and titled image output directories.
    """
    directories = [
        TITLED_IMAGE_OUTPUT_DIR,
        GRID_OUTPUT_DIR
    ]
    
    for directory in directories:
        if os.path.exists(directory):
            print(f"Removing directory: {directory}")
            shutil.rmtree(directory)
    
    print("Grid and titled image cache cleared successfully")

def generate_grid_image():
    """
    Generate a grid image containing all titled images.
    The grid will be arranged in a way that maintains aspect ratio and equal spacing.
    """
    # Create output directory if it doesn't exist
    Path(GRID_OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    
    # Get all titled images
    image_files = sorted([f for f in os.listdir(TITLED_IMAGE_OUTPUT_DIR) if f.endswith('.png')])
    
    if not image_files:
        print("No titled images found to create grid")
        return None
    
    # Calculate grid dimensions
    num_images = len(image_files)
    grid_cols = math.ceil(math.sqrt(num_images))
    grid_rows = math.ceil(num_images / grid_cols)
    
    # Load first image to get dimensions
    first_image = Image.open(os.path.join(TITLED_IMAGE_OUTPUT_DIR, image_files[0]))
    img_width, img_height = first_image.size
    
    # Calculate grid dimensions with padding
    padding = 20  # pixels of padding between images
    grid_width = (img_width * grid_cols) + (padding * (grid_cols - 1))
    grid_height = (img_height * grid_rows) + (padding * (grid_rows - 1))
    
    # Create a white background for the grid
    grid_image = Image.new('RGB', (grid_width, grid_height), (255, 255, 255))
    
    # Place each image in the grid
    for idx, image_file in enumerate(image_files):
        print(f"Processing image {idx} of {len(image_files)}")
        row = idx // grid_cols
        col = idx % grid_cols
        
        # Calculate position
        x = col * (img_width + padding)
        y = row * (img_height + padding)
        
        # Load and paste image
        img = Image.open(os.path.join(TITLED_IMAGE_OUTPUT_DIR, image_file))
        grid_image.paste(img, (x, y))
    
    # Save the grid image
    output_path = os.path.join(GRID_OUTPUT_DIR, "grid_image.png")
    grid_image.save(output_path)
    print(f"Generated grid image: {output_path}")
    
    return output_path

if __name__ == "__main__":
    generate_grid_image() 