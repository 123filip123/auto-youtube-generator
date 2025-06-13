import json
from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips, concatenate_audioclips, ColorClip, TextClip, CompositeVideoClip
from PIL import Image
import numpy as np
import os
import re

from generate_audio import AUDIO_OUTPUT_DIR
from generate_list import LIST_OUTPUT_DIR

VIDEO_OUTPUT_DIR = "outputs/video_output"
TITLED_IMAGE_OUTPUT_DIR = "outputs/titled_image_output"

def split_into_sentences(text: str) -> list:
    """
    Split text into sentences using regex.
    Handles common sentence endings (.!?) and preserves abbreviations.
    """
    # Split on sentence endings followed by space or end of string
    sentences = re.split(r'(?<=[.!?])\s+', text)
    # Filter out empty sentences and strip whitespace
    return [s.strip() for s in sentences if s.strip()]

def generate_video_v2():
    """
    Generate a video by combining titled images and audio files based on JSON input.
    Each item will:
    - Show full description image for first 1.5 seconds
    - Then show sentence-specific images for equal durations for the rest of the audio
    - Have a 0.5 second delay after audio ends before next item
    """

    json_path = f"{LIST_OUTPUT_DIR}/list_items.json"
    output_path = f"{VIDEO_OUTPUT_DIR}/final_video.mp4"
    image_dir = f"{TITLED_IMAGE_OUTPUT_DIR}"
    audio_dir = f"{AUDIO_OUTPUT_DIR}"

    # Load the JSON file
    with open(json_path, 'r') as f:
        data = json.load(f)
    
    # List to store all video clips
    video_clips = []
    
    # Process each item in the JSON array
    for i, item in enumerate(data, start=1):
        item_number = f"{i:02d}"  # Format numbers as "01", "02", etc.
        
        # Get the full description image
        full_image_file = os.path.join(image_dir, f"item_{item_number}_full.png")
        
        # Get audio file
        audio_file = os.path.join(audio_dir, f"item_{item_number}.mp3")
        audio_clip = AudioFileClip(audio_file)
        
        # Calculate durations
        full_image_duration = 3.0  # Show full image for 3 seconds
        remaining_duration = audio_clip.duration - full_image_duration
        final_delay = 0.5  # Delay after audio ends
        
        # Split description into sentences to know how many sentence images we have
        sentences = split_into_sentences(item['description'])
        num_sentences = len(sentences)
        
        # Calculate duration for each sentence image
        sentence_duration = remaining_duration / num_sentences if num_sentences > 0 else 0
        
        # Create clips list for this item
        item_clips = []
        
        # Add full description image clip
        pil_image = Image.open(full_image_file)
        aspect_ratio = pil_image.width / pil_image.height
        new_width = int(720 * aspect_ratio)
        pil_image = pil_image.resize((new_width, 720), Image.Resampling.LANCZOS)
        image_array = np.array(pil_image)
        
        full_image_clip = ImageClip(image_array).set_duration(full_image_duration)
        full_image_clip = full_image_clip.set_position("center")
        
        # Create white background for full image
        bg_clip = ColorClip(size=(1920, 1080), color=(255, 255, 255))
        bg_clip = bg_clip.set_duration(full_image_duration)
        
        # Composite full image clip
        full_clip = CompositeVideoClip([bg_clip, full_image_clip])
        item_clips.append(full_clip)
        
        # Add sentence-specific image clips
        for j in range(1, num_sentences + 1):
            sentence_image_file = os.path.join(image_dir, f"item_{item_number}_sentence_{j:02d}.png")
            
            # Load and resize sentence image
            pil_image = Image.open(sentence_image_file)
            aspect_ratio = pil_image.width / pil_image.height
            new_width = int(720 * aspect_ratio)
            pil_image = pil_image.resize((new_width, 720), Image.Resampling.LANCZOS)
            image_array = np.array(pil_image)
            
            # Create sentence image clip
            sentence_image_clip = ImageClip(image_array).set_duration(sentence_duration)
            sentence_image_clip = sentence_image_clip.set_position("center")
            
            # Create white background for sentence image
            bg_clip = ColorClip(size=(1920, 1080), color=(255, 255, 255))
            bg_clip = bg_clip.set_duration(sentence_duration)
            
            # Composite sentence image clip
            sentence_clip = CompositeVideoClip([bg_clip, sentence_image_clip])
            item_clips.append(sentence_clip)
        
        # For the final delay, use the last sentence image instead of a blank screen
        if num_sentences > 0:
            last_sentence_image_file = os.path.join(image_dir, f"item_{item_number}_sentence_{num_sentences:02d}.png")
            pil_image = Image.open(last_sentence_image_file)
            aspect_ratio = pil_image.width / pil_image.height
            new_width = int(720 * aspect_ratio)
            pil_image = pil_image.resize((new_width, 720), Image.Resampling.LANCZOS)
            image_array = np.array(pil_image)
            
            # Create final delay clip with the last image
            final_image_clip = ImageClip(image_array).set_duration(final_delay)
            final_image_clip = final_image_clip.set_position("center")
            
            # Create white background for final delay
            bg_clip = ColorClip(size=(1920, 1080), color=(255, 255, 255))
            bg_clip = bg_clip.set_duration(final_delay)
            
            # Composite final delay clip
            delay_clip = CompositeVideoClip([bg_clip, final_image_clip])
        else:
            # If there are no sentences, use the full image for the delay
            delay_clip = full_clip.set_duration(final_delay)
        
        item_clips.append(delay_clip)
        
        # Concatenate all clips for this item
        item_video = concatenate_videoclips(item_clips)
        
        # Set the audio for the entire item
        item_video = item_video.set_audio(audio_clip)
        
        # Add to the list of clips
        video_clips.append(item_video)
    
    # Concatenate all item clips
    final_clip = concatenate_videoclips(video_clips)
    
    # Write the final video
    final_clip.write_videofile(
        output_path,
        fps=24,
        codec='libx264',
        audio_codec='aac'
    )
    
    # Close all clips to free up resources
    final_clip.close()
    for clip in video_clips:
        clip.close()

if __name__ == "__main__":
    # Example usage
    generate_video_v2() 