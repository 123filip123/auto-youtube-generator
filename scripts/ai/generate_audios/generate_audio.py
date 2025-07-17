import json
import os
import time

from .utils import generate_audio_for_item
from utils.output_dirs import AUDIO_OUTPUT_DIR

MAX_RETRIES = 3
DELAY_BETWEEN_REQUESTS = 5  # seconds



def generate_audio_for_items(items_json: str):
    """
    Generate audio files for each item in the list using OpenAI's Text-to-Speech API.
    Each item will have its title and description spoken in sequence.
    
    Args:
        items_json (str): JSON string containing list of items with title and description
    """
    # Create output directory if it doesn't exist
    os.makedirs(AUDIO_OUTPUT_DIR, exist_ok=True)
    
    try:        
        # Parse the JSON string into a list of dictionaries
        items = json.loads(items_json)
                
        for i, item in enumerate(items, 1):
            try:
                generate_audio_for_item(i, item)
                # Add a small delay between requests to avoid rate limiting
                time.sleep(DELAY_BETWEEN_REQUESTS)
            except Exception as e:
                print(f"Failed to generate audio for item {i} after {MAX_RETRIES} attempts: {str(e)}")
                print("Continuing with next item...")
                continue
    except Exception as e:
        print(f"Error processing items_json: {e}")
        
