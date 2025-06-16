import json

from .utils import create_titled_image_short
from utils.output_dirs import IMAGE_OUTPUT_DIR
from utils.output_file_names import get_image_file_name, get_list_items_path, get_titled_image_file_name


def create_titled_images_for_items_short(items_json: str):
    """
    Generate titled images for each item in the JSON list, optimized for YouTube Shorts.
    Generates titled images for each prompt in the image_prompts array.
    
    Args:
        items_json (str): JSON string containing list of items with title, description, and image_prompts
    """
    # Parse the JSON string into a list of dictionaries
    items = json.loads(items_json)
    
    image_paths = []
    for i, item in enumerate(items, start=1):
        try:
            # Generate titled images for each prompt in the image_prompts array
            for j, prompt in enumerate(item['image_prompts'], start=1):
                # Get the source image path for this prompt
                source_image_path = f"{IMAGE_OUTPUT_DIR}/{get_image_file_name(i, j)}"
                
                # Generate the titled image
                output_filename = get_titled_image_file_name(i, j)
                image_path = create_titled_image_short(
                    source_image_path,
                    item['title'],
                    output_filename
                )
                image_paths.append(image_path)
                print(f"Generated titled image for Shorts (prompt {j}): {image_path}")
            
        except Exception as e:
            print(f"Failed to generate titled image for item {i}: {str(e)}")
            continue
    
    return image_paths

if __name__ == "__main__":
    # Read the JSON file from the output directory
    json_path = get_list_items_path()
    with open(json_path, 'r') as f:
        items_json = f.read()
    create_titled_images_for_items_short(items_json) 