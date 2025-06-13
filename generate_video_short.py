import json
from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips, concatenate_audioclips, ColorClip, TextClip, CompositeVideoClip
from PIL import Image
import numpy as np
import os

from generate_audio import AUDIO_OUTPUT_DIR
from generate_list import LIST_OUTPUT_DIR

VIDEO_OUTPUT_DIR = "outputs/video_output"
TITLED_IMAGE_OUTPUT_DIR = "outputs/titled_image_output"

def generate_video_short():
    """
    Generate a vertical video suitable for YouTube Shorts by combining titled images and audio files based on JSON input.
    Each item will:
    - Start with a 0.2 second delay before audio begins
    - Have a 0.5 second delay after audio ends before next item
    - Display on a white background with title text below
    - Maintain 9:16 aspect ratio (1080x1920) for YouTube Shorts
    - Include a smooth zoom effect on the images
    """

    json_path = f"{LIST_OUTPUT_DIR}/list_items.json"
    output_path = f"{VIDEO_OUTPUT_DIR}/final_video_short.mp4"
    image_dir = f"{TITLED_IMAGE_OUTPUT_DIR}"
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
        image_file = os.path.join(image_dir, f"item_{item_number}_short.png")
        audio_file = os.path.join(audio_dir, f"item_{item_number}.mp3")
        
        # Load image using PIL first
        pil_image = Image.open(image_file)
        
        # Convert PIL Image to numpy array
        image_array = np.array(pil_image)
        
        # Load audio clip
        audio_clip = AudioFileClip(audio_file)
        
        # Calculate total duration including delays
        total_duration = 0.2 + audio_clip.duration + 0.5
        
        # Create image clip from numpy array and set duration
        image_clip = ImageClip(image_array).set_duration(total_duration)
        
        # Create a white background clip (1080x1920 for vertical video)
        bg_clip = ColorClip(size=(1080, 1920), color=(255, 255, 255))
        bg_clip = bg_clip.set_duration(total_duration)
        
        # Add zoom effect using resize
        def zoom_effect(t):
            # Start at 1.0 and zoom to 1.2 over the duration
            zoom_factor = 1.0 + (0.2 * t / total_duration)
            return zoom_factor
        
        # Apply the zoom effect using the newer PIL resampling method
        def resize_with_zoom(get_frame, t):
            frame = get_frame(t)
            zoom = zoom_effect(t)
            h, w = frame.shape[:2]
            new_h, new_w = int(h * zoom), int(w * zoom)
            pil_image = Image.fromarray(frame)
            resized = pil_image.resize((new_w, new_h), Image.Resampling.LANCZOS)
            return np.array(resized)
        
        # Apply the resize effect
        image_clip = image_clip.fl(lambda gf, t: resize_with_zoom(gf, t))
        
        # Position the image in the center
        image_clip = image_clip.set_position("center")
        
        # Composite all elements
        video_clip = CompositeVideoClip([
            bg_clip,
            image_clip
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
    generate_video_short() 