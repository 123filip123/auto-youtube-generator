from utils.output_dirs import JSON_OUTPUT_DIR, VIDEO_OUTPUT_DIR


def get_image_file_name(item_number: int, prompt_number: int):
    return f"item_{item_number:02d}_prompt_{prompt_number:02d}.png"

def get_audio_file_name(item_number: int):
    return f"item_{item_number:02d}.mp3"

def get_video_file_name():
    return f"final_video_short.mp4"

def get_titled_image_file_name(item_number: int, prompt_number: int):
    return f"item_{item_number:02d}_prompt_{prompt_number:02d}_short.png"

def get_list_items_path():
    return f"{JSON_OUTPUT_DIR}/list_items_with_prompts.json"

def get_video_output_path():
    return f"{VIDEO_OUTPUT_DIR}/final_video_short.mp4"