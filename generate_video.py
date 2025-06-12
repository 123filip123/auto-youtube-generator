import json
from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips, concatenate_audioclips, ColorClip, TextClip, CompositeVideoClip
from PIL import Image
import numpy as np
import os

from generate_audio import AUDIO_OUTPUT_DIR
from generate_image import IMAGE_OUTPUT_DIR
from generate_list import LIST_OUTPUT_DIR

VIDEO_OUTPUT_DIR = "outputs/video_output"

def generate_video():
    """
    Generate a video by combining images and audio files based on JSON input.
    Each item will:
    - Start with a 0.2 second delay before audio begins
    - Have a 0.5 second delay after audio ends before next item
    - Display on a white background with title text below
    """

    json_path = f"{LIST_OUTPUT_DIR}/list_items.json"
    output_path = f"{VIDEO_OUTPUT_DIR}/final_video.mp4"
    image_dir = f"{IMAGE_OUTPUT_DIR}"
    audio_dir = f"{AUDIO_OUTPUT_DIR}"

    # Load the JSON file
    with open(json_path, 'r') as f:
        data = json.load(f)
    
    # List to store all video clips
    video_clips = []
    
    # Process each item in the JSON array
    for i, item in enumerate(data, start=1):
        # Get image and audio filenames using iterator
        item_number = f"{i:02d}"  # This will format numbers as "01", "02", etc.
        image_file = os.path.join(image_dir, f"item_{item_number}.png")
        audio_file = os.path.join(audio_dir, f"item_{item_number}.mp3")
        
        # Load and resize image using PIL first
        pil_image = Image.open(image_file)
        # Calculate new width while maintaining aspect ratio
        aspect_ratio = pil_image.width / pil_image.height
        new_width = int(720 * aspect_ratio)
        pil_image = pil_image.resize((new_width, 720), Image.Resampling.LANCZOS)
        
        # Convert PIL Image to numpy array
        image_array = np.array(pil_image)
        
        # Load audio clip
        audio_clip = AudioFileClip(audio_file)
        
        # Calculate total duration including delays
        total_duration = 0.2 + audio_clip.duration + 0.5
        
        # Create image clip from numpy array and set duration
        image_clip = ImageClip(image_array).set_duration(total_duration)
        
        # Create a white background clip
        bg_clip = ColorClip(size=(1920, 1080), color=(255, 255, 255))
        bg_clip = bg_clip.set_duration(total_duration)
        
        # Create title text clip
        title_clip = TextClip(
            item['title'],
            fontsize=60,
            color='black',
            font='Arial-Bold',
            size=(new_width, None),
            method='caption'
        )
        title_clip = title_clip.set_duration(total_duration)
        
        # Position the image in the upper center, leaving space for the text below
        image_y = (1080 - 720 - 60) // 2  # 60px gap for text
        image_clip = image_clip.set_position(("center", image_y))
        
        # Position the title further below the image
        text_y = image_y + 720 + 60  # 60px gap below image
        title_clip = title_clip.set_position(("center", text_y))
        
        # Composite all elements
        video_clip = CompositeVideoClip([
            bg_clip,
            image_clip,
            title_clip
        ])
        
        # Create a silent audio clip for the initial delay
        initial_delay = AudioFileClip(audio_file).set_duration(0.2).volumex(0)
        
        # Create a silent audio clip for the final delay
        final_delay = AudioFileClip(audio_file).set_duration(0.5).volumex(0)
        
        # Concatenate the audio clips with delays
        combined_audio = concatenate_audioclips([initial_delay, audio_clip, final_delay])
        
        # Set the audio of the video clip
        video_clip = video_clip.set_audio(combined_audio)
        
        # Add to the list of clips
        video_clips.append(video_clip)
    
    # Concatenate all clips sequentially
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
    generate_video()
