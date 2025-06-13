import base64
import os
import json
from pathlib import Path
import time
from typing import List
from tenacity import retry, stop_after_attempt, wait_exponential

from utils.helper_functions import clean_json_input
from utils.open_ai_client import get_open_ai_client

LIST_OUTPUT_DIR = "outputs/json_output"
THUMBNAIL_OUTPUT_DIR = "outputs/thumbnail_output"
MAX_RETRIES = 3
DELAY_BETWEEN_REQUESTS = 5  # seconds

def create_thumbnail_prompt(items: List[dict]) -> str:
    """
    Create a well-formatted prompt for thumbnail generation.
    """
    # Create a summary of the items for the prompt
    items_summary = "\n".join([f"- {item['title']}" for item in items[:5]])  # Use first 5 items
    total_items = len(items)
    
    prompt = f"""Create a professional, eye-catching YouTube thumbnail for a video that showcases {total_items} amazing items.
    The video includes these items:
    {items_summary}
    And {total_items - 5} more items...
    
    The thumbnail should be:
    - High contrast and vibrant
    - Include text that's easy to read
    - Have a professional look
    - Be engaging and click-worthy
    - Follow YouTube thumbnail best practices
    - Use a 16:9 aspect ratio
    - Include a collage or montage of elements representing the different items
    - Add a "TOP {total_items}" text to make it more clickable
    - Use bright, eye-catching colors
    - Include a professional-looking border or frame"""
    
    return prompt

@retry(stop=stop_after_attempt(MAX_RETRIES), wait=wait_exponential(multiplier=1, min=4, max=10))
def generate_thumbnail(prompt: str, output_dir: str, filename: str) -> str:
    """
    Generate a thumbnail using DALL-E and save it to the specified directory.
    Returns the path to the saved image.
    """
    # Create the output directory if it doesn't exist
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    try:
        client = get_open_ai_client()

        # Generate the image
        response = client.images.generate(
            model="gpt-image-1",
            prompt=prompt,
            size="1536x1024",  # Closest supported size to 16:9 aspect ratio
            n=1,
        )
        
        image_bytes = base64.b64decode(response.data[0].b64_json)

        image_path = os.path.join(output_dir, f"{filename}.png")
        with open(image_path, "wb") as f:
            f.write(image_bytes)
        
        return image_path
    except Exception as e:
        print(f"Error generating thumbnail with prompt '{prompt}': {str(e)}")
        raise  # Re-raise the exception to be handled by the retry decorator

def generate_youtube_thumbnail() -> str:
    """
    Generate an engaging YouTube thumbnail using DALL-E API based on the list of items.
    
    Args:
        output_path (str): Path where the thumbnail will be saved
        
    Returns:
        str: Path to the generated thumbnail image
    """
    try:
        # Read the list items from JSON file
        json_path = f"{LIST_OUTPUT_DIR}/list_items.json"
        with open(json_path, 'r') as f:
            items = json.load(f)
        
        # Create the prompt
        prompt = create_thumbnail_prompt(items)
        print(f"\nGenerating thumbnail with prompt:\n{prompt}")
        
        # Generate and save the thumbnail
        thumbnail_path = generate_thumbnail(prompt, THUMBNAIL_OUTPUT_DIR, "thumbnail")
        print(f"Successfully generated thumbnail: {thumbnail_path}")
        
        return thumbnail_path
        
    except Exception as e:
        print(f"Failed to generate thumbnail after {MAX_RETRIES} attempts: {str(e)}")
        raise

if __name__ == "__main__":
    try:
        thumbnail_path = generate_youtube_thumbnail()
        print(f"Thumbnail generated successfully at: {thumbnail_path}")
    except Exception as e:
        print(f"An error occurred: {str(e)}")
