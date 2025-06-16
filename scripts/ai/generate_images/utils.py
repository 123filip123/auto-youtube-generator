
import base64
import os
from pathlib import Path
from tenacity import retry, stop_after_attempt, wait_exponential
from utils.open_ai_client import get_open_ai_client

MAX_RETRIES = 3
DELAY_BETWEEN_REQUESTS = 5  # seconds


@retry(stop=stop_after_attempt(MAX_RETRIES), wait=wait_exponential(multiplier=1, min=4, max=10))
def generate_image(prompt: str, output_dir: str, filename: str) -> str:
    """
    Generate an image using OpenAI's image generation API and save it to the specified directory.
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
            quality="low"
        )
        
        image_bytes = base64.b64decode(response.data[0].b64_json)

        image_path = os.path.join(output_dir, f"{filename}.png")
        with open(image_path, "wb") as f:
            f.write(image_bytes)
        
        return image_path
    except Exception as e:
        print(f"Error generating image with prompt '{prompt}': {str(e)}")
        raise  # Re-raise the exception to be handled by the retry decorator