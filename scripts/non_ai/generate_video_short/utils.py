from moviepy.editor import ImageClip, AudioFileClip, concatenate_audioclips, ColorClip, CompositeVideoClip
from PIL import Image
import numpy as np
import os

from utils.output_dirs import AUDIO_OUTPUT_DIR, TITLED_IMAGE_OUTPUT_DIR
from utils.output_file_names import get_audio_file_name, get_titled_image_file_name

def create_background_clip(duration):
    """Create a white background clip with the specified duration."""
    bg_clip = ColorClip(size=(1080, 1920), color=(255, 255, 255))
    return bg_clip.set_duration(duration)

def create_zoom_effect(total_duration):
    """Create a zoom effect function that scales from 1.0 to 1.2 over the duration."""
    def zoom_effect(t):
        zoom_factor = 1.0 + (0.2 * t / (total_duration / 3))
        return zoom_factor
    return zoom_effect

def resize_with_zoom(get_frame, t, zoom_effect):
    """Apply zoom effect to a frame using PIL resampling."""
    frame = get_frame(t)
    zoom = zoom_effect(t)
    h, w = frame.shape[:2]
    new_h, new_w = int(h * zoom), int(w * zoom)
    pil_image = Image.fromarray(frame)
    resized = pil_image.resize((new_w, new_h), Image.Resampling.LANCZOS)
    return np.array(resized)

def create_image_clip(image_path, total_duration, start_time):
    """Create an image clip with zoom effect for the given image."""
    pil_image = Image.open(image_path)
    image_array = np.array(pil_image)
    image_clip = ImageClip(image_array).set_duration(total_duration / 3)
    
    zoom_effect = create_zoom_effect(total_duration)
    image_clip = image_clip.fl(lambda gf, t: resize_with_zoom(gf, t, zoom_effect))
    image_clip = image_clip.set_position("center")
    image_clip = image_clip.set_start(start_time)
    
    return image_clip

def create_audio_with_delays(audio_file):
    """Create audio clip with initial and final delays."""
    audio_clip = AudioFileClip(audio_file)
    initial_delay = AudioFileClip(audio_file).set_duration(0.2).volumex(0)
    final_delay = AudioFileClip(audio_file).set_duration(0.5).volumex(0)
    return concatenate_audioclips([initial_delay, audio_clip, final_delay])

def create_item_video_clip(item_index, total_duration):
    """Create a video clip for a single item with all its images and audio."""
    # Create background
    bg_clip = create_background_clip(total_duration)
    
    # Create image clips
    image_clips = []
    for j in range(1, 4):
        image_file = os.path.join(TITLED_IMAGE_OUTPUT_DIR, get_titled_image_file_name(item_index, j))
        start_time = (j - 1) * (total_duration / 3)
        image_clip = create_image_clip(image_file, total_duration, start_time)
        image_clips.append(image_clip)
    
    # Create composite video
    video_clip = CompositeVideoClip([bg_clip, *image_clips])
    
    # Add audio
    audio_file = os.path.join(AUDIO_OUTPUT_DIR, get_audio_file_name(item_index))
    combined_audio = create_audio_with_delays(audio_file)
    video_clip = video_clip.set_audio(combined_audio)
    
    return video_clip