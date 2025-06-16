import os
from typing import Dict
from tenacity import retry, stop_after_attempt, wait_exponential
from utils.open_ai_client import get_open_ai_client
from utils.output_dirs import AUDIO_OUTPUT_DIR

MAX_RETRIES = 3

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