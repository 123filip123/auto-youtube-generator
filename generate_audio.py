import json
import os
import time
from typing import Dict
from tenacity import retry, stop_after_attempt, wait_exponential

from utils.open_ai_client import get_open_ai_client

AUDIO_OUTPUT_DIR = "outputs/audio_output"
MAX_RETRIES = 3
DELAY_BETWEEN_REQUESTS = 5  # seconds

@retry(stop=stop_after_attempt(MAX_RETRIES), wait=wait_exponential(multiplier=1, min=4, max=10))
def generate_audio_for_item(i: int, item: Dict):
    """
    Generate audio for a single item using OpenAI's Text-to-Speech API.
    
    Args:
        i (int): Index of the item
        item (Dict): Dictionary containing title and description
    """
    try:
        # Combine title and description with a pause
        text = f"{item['title']}. {item['description']}"

        client = get_open_ai_client()
                
        # Generate audio using OpenAI's TTS API
        response = client.audio.speech.create(
            model="tts-1",
            voice="ash",
            instructions="Speak in a engaging tone that would be informative and interesting for a youtube video. Use a professional, conversational style.",
            input=text
        )
                
        # Generate filename
        filename = f"item_{i:02d}.mp3"
        filepath = os.path.join(AUDIO_OUTPUT_DIR, filename)
                
        # Save the audio file using streaming response
        with open(filepath, 'wb') as f:
            for chunk in response.iter_bytes():
                f.write(chunk)

        print(f"Generated audio for item {i}: {item['title']}")
        return True
    except Exception as e:
        print(f"Error generating audio for item {i}: {str(e)}")
        raise  # Re-raise the exception to be handled by the retry decorator

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
        

# Main function
if __name__ == "__main__":
    # Example usage
    from generate_list import generate_list
    
    topic = input("Enter a topic for your video: ")
    items_json = generate_list(topic)
    generate_audio_for_items(items_json)
