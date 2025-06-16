import json
import time
from typing import List

from .utils import generate_image
from utils.helper_functions import clean_json_input
from utils.output_dirs import IMAGE_OUTPUT_DIR

MAX_RETRIES = 3
DELAY_BETWEEN_REQUESTS = 5  # seconds


def generate_images(items_json: str) -> List[str]:
    """
    Generate images for each item in the JSON list.
    Generates images for each prompt in the image_prompts array.
    Returns a list of paths to the generated images.
    """
    # Clean and parse the JSON string into a list of items
    cleaned_json = clean_json_input(items_json)
    items = json.loads(cleaned_json)
    
    image_paths = []
    for i, item in enumerate(items, start=1):
        try:
            print(f"\nProcessing item {i}: {item['title']}")
            
            # Generate images for each prompt in the image_prompts array
            for j, prompt in enumerate(item['image_prompts'], start=1):
                print(f"\nGenerating image for prompt {j}:")
                print(f"Using prompt: {prompt}")
                
                # Generate a filename based on the item and prompt index
                filename = f"item_{i:02d}_prompt_{j:02d}"
                
                # Generate and save the image
                image_path = generate_image(prompt, IMAGE_OUTPUT_DIR, filename)
                image_paths.append(image_path)
                print(f"Successfully generated image: {image_path}")
                
                # Add delay between requests to avoid rate limiting
                time.sleep(DELAY_BETWEEN_REQUESTS)
            
        except Exception as e:
            print(f"Failed to generate images for item {i} after {MAX_RETRIES} attempts: {str(e)}")
            print("Continuing with next item...")
            continue
    
    return image_paths

if __name__ == "__main__":
    # Read the JSON file from the output directory
    json_path = f"outputs/json_output/list_items_with_prompts.json"
    with open(json_path, 'r') as f:
        items_json = f.read()
    
    try:
        image_paths = generate_images(items_json)
        print("\nGenerated Images:")
        for path in image_paths:
            print(f"- {path}")
            
    except Exception as e:
        print(f"An error occurred: {str(e)}") 