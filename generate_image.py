import os
import json
from pathlib import Path
import time

from utils.helper_functions import clean_json_input
from utils.open_ai_client import get_open_ai_client

IMAGE_OUTPUT_DIR = "outputs/image_output"


def create_image_prompt(title: str, description: str) -> str:
    """
    Create a well-formatted prompt for DALL-E image generation.
    """
    # Limit the description to a reasonable length for the prompt
    max_desc_length = 200
    if len(description) > max_desc_length:
        description = description[:max_desc_length] + "..."
    
    return f"Create a professional, high-quality image illustrating: {title}. The image should be visually striking, suitable for a YouTube video and most importantly, it should be a real photo of the subject. Style: cartoonish,modern, clean, and engaging."

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
            model="dall-e-3",
            prompt=prompt,
            size="1024x1024",
            quality="standard",
            n=1,
        )
        
        # Get the image URL
        image_url = response.data[0].url
        
        # Download and save the image
        import requests
        image_path = os.path.join(output_dir, f"{filename}.png")
        response = requests.get(image_url)
        with open(image_path, "wb") as f:
            f.write(response.content)
        
        # Add a small delay to avoid rate limiting
        time.sleep(1)
        
        return image_path
    except Exception as e:
        print(f"Error generating image: {str(e)}")
        raise

def generate_images_for_items(items_json: str) -> list[str]:
    """
    Generate images for each item in the JSON list.
    Returns a list of paths to the generated images.
    """
    # Clean and parse the JSON string into a list of items
    cleaned_json = clean_json_input(items_json)
    items = json.loads(cleaned_json)
    
    image_paths = []
    for i, item in enumerate(items, start=1):
        try:
            # Create a prompt that combines the title and description
            prompt = create_image_prompt(item['title'], item['description'])
            
            # Generate a filename based on the index
            filename = f"item_{i:02d}"
            
            print(f"\nGenerating image for item {i}: {item['title']}")
            print(f"Using prompt: {prompt}")
            
            # Generate and save the image
            image_path = generate_image(prompt, IMAGE_OUTPUT_DIR, filename)
            image_paths.append(image_path)
            print(f"Successfully generated image: {image_path}")
            
        except Exception as e:
            print(f"Failed to generate image for item {i}: {str(e)}")
            continue
    
    return image_paths

if __name__ == "__main__":
    # Example usage
    items_json = input("Paste the JSON output from generate_list.py: ")
    try:
        image_paths = generate_images_for_items(items_json)
        print("\nGenerated Images:")
        for path in image_paths:
            print(f"- {path}")
    except Exception as e:
        print(f"An error occurred: {str(e)}")
