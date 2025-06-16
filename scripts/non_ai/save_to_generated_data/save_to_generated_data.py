import os
import shutil
from datetime import datetime

def save_to_generated_data(json_path: str, prompt: str = None):
    """
    Save AI-generated content to a separate generated_data folder
    Uses prompt name if provided, otherwise uses timestamp
    """
    # Create folder name based on prompt or timestamp
    if prompt:
        # Clean prompt to be folder-name friendly
        folder_name = "".join(c if c.isalnum() else "_" for c in prompt.lower())
        folder_name = "_".join(folder_name.split())
    else:
        folder_name = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    generated_folder = f"generated_data/{folder_name}"
    
    # Create folder structure
    os.makedirs(f"{generated_folder}/audio", exist_ok=True)
    os.makedirs(f"{generated_folder}/images", exist_ok=True)
    
    # Copy JSON file
    shutil.copy2(json_path, f"{generated_folder}/list_items.json")
    
    # Copy audio files
    for file in os.listdir("outputs/audio_output"):
        if file.endswith(".mp3"):
            shutil.copy2(f"outputs/audio_output/{file}", f"{generated_folder}/audio/{file}")
    
    # Copy image files
    for file in os.listdir("outputs/image_output"):
        if file.endswith(".png"):
            shutil.copy2(f"outputs/image_output/{file}", f"{generated_folder}/images/{file}")
    
    print(f"\nSaved AI-generated content to: {generated_folder}")