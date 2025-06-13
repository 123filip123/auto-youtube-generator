import base64
import os
import json
from pathlib import Path
import time
from typing import List
import re
from tenacity import retry, stop_after_attempt, wait_exponential

from utils.helper_functions import clean_json_input
from utils.open_ai_client import get_open_ai_client

IMAGE_OUTPUT_DIR = "outputs/image_output"
MAX_RETRIES = 3
DELAY_BETWEEN_REQUESTS = 5  # seconds

def split_into_sentences(text: str) -> List[str]:
    """
    Split text into sentences using regex.
    Handles common sentence endings (.!?) and preserves abbreviations.
    """
    # Split on sentence endings followed by space or end of string
    sentences = re.split(r'(?<=[.!?])\s+', text)
    # Filter out empty sentences and strip whitespace
    return [s.strip() for s in sentences if s.strip()]

def create_image_prompt(title: str, description: str, is_full_description: bool = False) -> str:
    """
    Create a well-formatted prompt for DALL-E image generation.
    """
    # Limit the description to a reasonable length for the prompt
    max_length = 200
    if len(description) > max_length:
        description = description[:max_length] + "..."

    if is_full_description:
        prompt = f"Create a realistic, high-quality photograph that visually represents: {title}. {description} The image should be a pure photograph with no text, no captions, and no watermarks. Style: photorealistic"
    else:
        prompt = f"Create a realistic, high-quality photograph that visually represents: {title}. {description} The image should be a pure photograph with no text, no captions, and no watermarks. Style: photorealistic"
    
    return prompt

@retry(stop=stop_after_attempt(MAX_RETRIES), wait=wait_exponential(multiplier=1, min=4, max=10))
def generate_image(prompt: str, output_dir: str, filename: str) -> str:
    """
    Generate an image using DALL-E and save it to the specified directory.
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
            size="1024x1024",
            n=1,
        )
        
        image_bytes = base64.b64decode(response.data[0].b64_json)

        image_path = os.path.join(output_dir, f"{filename}.png")
        with open(image_path, "wb") as f:
            f.write(image_bytes)
        
        return image_path
    except Exception as e:
        print(f"Error generating image with prompt '{prompt}': {str(e)}")
        raise  # Re-raise the exception to be handled by the retry decorator

def generate_images_for_items_v2(items_json: str) -> List[str]:
    """
    Generate images for each item in the JSON list.
    First generates one image for the full description, then generates images for each sentence.
    Returns a list of paths to the generated images.
    """
    # Clean and parse the JSON string into a list of items
    cleaned_json = clean_json_input(items_json)
    items = json.loads(cleaned_json)
    
    image_paths = []
    for i, item in enumerate(items, start=1):
        try:
            print(f"\nProcessing item {i}: {item['title']}")
            
            # First, generate one image for the full description
            print("\nGenerating full description image:")
            full_prompt = create_image_prompt(item['title'], item['description'], is_full_description=True)
            print(f"Using prompt: {full_prompt}")
            
            full_filename = f"item_{i:02d}_full"
            full_image_path = generate_image(full_prompt, IMAGE_OUTPUT_DIR, full_filename)
            image_paths.append(full_image_path)
            print(f"Successfully generated full description image: {full_image_path}")
            
            # Add delay between requests
            time.sleep(DELAY_BETWEEN_REQUESTS)
            
            # Then, generate images for each sentence
            sentences = split_into_sentences(item['description'])
            print(f"\nFound {len(sentences)} sentences in description")
            
            for j, sentence in enumerate(sentences, start=1):
                # Create a prompt for this sentence
                prompt = create_image_prompt(item['title'], sentence)
                
                # Generate a filename based on the item and sentence index
                filename = f"item_{i:02d}_sentence_{j:02d}"
                
                print(f"\nGenerating image for sentence {j}:")
                print(f"Using prompt: {prompt}")
                
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
    # Example usage with predefined JSON
    items_json = '''[
  {
    "title": "Venus Flytrap",
    "description": "This carnivorous plant snaps shut on unsuspecting insects that wander into its trap-like leaves. Its ability to count touches before closing makes it a cunning predator of the plant world."
  }
]'''
    try:
        image_paths = generate_images_for_items_v2(items_json)
        print("\nGenerated Images:")
        for path in image_paths:
            print(f"- {path}")
    except Exception as e:
        print(f"An error occurred: {str(e)}") 