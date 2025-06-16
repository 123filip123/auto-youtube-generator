import os
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from pathlib import Path

from utils.output_dirs import TITLED_IMAGE_OUTPUT_DIR

def create_titled_image_short(image_path: str, title: str, output_filename: str):
    """
    Create an image with a title below it, matching the YouTube Shorts video layout.
    The background will be a blurred version of the source image.
    
    Args:
        image_path (str): Path to the source image
        title (str): Title text to add below the image
        output_filename (str): Name of the output file (without extension)
    """
    try:
        # Create output directory if it doesn't exist
        Path(TITLED_IMAGE_OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
        
        # Load and resize image
        pil_image = Image.open(image_path)
        aspect_ratio = pil_image.width / pil_image.height
        new_height = int(1080 * aspect_ratio)
        pil_image = pil_image.resize((1080, new_height), Image.Resampling.LANCZOS)
        
        # Create background dimensions (1080x1920 for vertical video)
        bg_width = 1080
        bg_height = 1920
        
        # Create blurred background from the source image
        bg_image = Image.open(image_path)
        bg_image = bg_image.resize((bg_width, bg_height), Image.Resampling.LANCZOS)
        bg_image = bg_image.filter(ImageFilter.GaussianBlur(radius=90))
        
        # Add a semi-transparent white overlay to ensure text readability
        overlay = Image.new('RGBA', (bg_width, bg_height), (255, 255, 255, 128))
        bg_image = Image.alpha_composite(bg_image.convert('RGBA'), overlay)
        bg_image = bg_image.convert('RGB')
        
        # Calculate positions
        image_y = (bg_height - new_height - 80) // 2  # 80px gap for text
        image_x = (bg_width - 1080) // 2
        
        # Paste the image onto the background
        bg_image.paste(pil_image, (image_x, image_y))
        
        # Add title text
        draw = ImageDraw.Draw(bg_image)
        try:
            font = ImageFont.truetype("Arial Bold", 80)  # Larger font for vertical format
        except IOError:
            # Fallback to default font if Arial Bold is not available
            font = ImageFont.load_default()
        
        # Calculate text position
        text_y = image_y + new_height + 80  # 80px gap below image
        
        # Draw text
        draw.text((bg_width//2, text_y), title, fill='black', font=font, anchor="mm")
        
        # Save the final image
        output_path = os.path.join(TITLED_IMAGE_OUTPUT_DIR, output_filename)
        bg_image.save(output_path)
        
        return output_path
    except Exception as e:
        print(f"Error generating titled image for '{title}' from '{image_path}': {str(e)}")
        raise  # Re-raise the exception to be handled by the caller