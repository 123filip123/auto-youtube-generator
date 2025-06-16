import json
from moviepy.editor import AudioFileClip, concatenate_videoclips
import os

from scripts.non_ai.generate_video_short.utils import create_item_video_clip
from utils.output_dirs import AUDIO_OUTPUT_DIR, VIDEO_OUTPUT_DIR
from utils.output_file_names import get_audio_file_name, get_list_items_path, get_video_output_path


def generate_video_short():
    """
    Generate a vertical video suitable for YouTube Shorts by combining titled images and audio files based on JSON input.
    Each item will:
    - Start with a 0.2 second delay before audio begins
    - Have a 0.5 second delay after audio ends before next item
    - Display all three images for the item, evenly distributed during the duration
    - Maintain 9:16 aspect ratio (1080x1920) for YouTube Shorts
    - Include a smooth zoom effect on the images
    """
    # Setup paths and create output directory
    json_path = get_list_items_path()
    output_path = get_video_output_path()
    os.makedirs(VIDEO_OUTPUT_DIR, exist_ok=True)
    
    # Load data
    with open(json_path, 'r') as f:
        data = json.load(f)
    
    # Process each item
    video_clips = []
    for i, item in enumerate(data, start=1):
        audio_file = os.path.join(AUDIO_OUTPUT_DIR, get_audio_file_name(i))
        audio_clip = AudioFileClip(audio_file)
        total_duration = 0.2 + audio_clip.duration + 0.5
        
        video_clip = create_item_video_clip(i, total_duration)
        video_clips.append(video_clip)
    
    # Create final video
    final_clip = concatenate_videoclips(video_clips)
    
    # Write the final video
    final_clip.write_videofile(
        output_path,
        fps=24,
        codec='libx264',
        audio_codec='aac'
    )
    
    # Cleanup
    final_clip.close()
    for clip in video_clips:
        clip.close()

if __name__ == "__main__":
    generate_video_short() 