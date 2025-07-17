import os
import textwrap
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from pathlib import Path

from utils.output_dirs import TITLED_IMAGE_OUTPUT_DIR

def wrap_text(text, font, max_width):
    """
    Wrap text to fit within a maximum width using the given font.
    
    Args:
        text (str): The text to wrap
        font: The font object to measure text with
        max_width (int): Maximum width in pixels
        
    Returns:
        list: List of text lines
    """
    words = text.split()
    lines = []
    current_line = []
    
    for word in words:
        test_line = ' '.join(current_line + [word])
        bbox = font.getbbox(test_line)
        text_width = bbox[2] - bbox[0]
        
        if text_width <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(' '.join(current_line))
                current_line = [word]
            else:
                # If a single word is too long, break it
                lines.append(word)
                current_line = []
    
    if current_line:
        lines.append(' '.join(current_line))
    
    return lines

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
        
        # Try multiple font options with larger size for better visibility
        font = None
        font_size = 120  # Increased from 80 to 120 for better visibility
        
        # Try different font options in order of preference
        font_options = [
            "arial.ttf",
            "Arial.ttf", 
            "arialbd.ttf",
            "Arial-Bold.ttf",
            "arial-bold.ttf",
        ]
        
        for font_path in font_options:
            try:
                font = ImageFont.truetype(font_path, font_size)
                break
            except (IOError, OSError):
                continue
        
        # If no system fonts work, create a larger default font
        if font is None:
            try:
                # Try to create a larger default font
                font = ImageFont.load_default()
                # Note: Default font size is usually small, but we'll work with what we have
            except:
                # Last resort - create a basic font
                font = ImageFont.load_default()
        
        # Calculate text position and wrap text if needed
        max_text_width = bg_width - 100  # Leave 50px margin on each side
        wrapped_lines = wrap_text(title, font, max_text_width)
        
        # Calculate line height and total text height
        line_height = font_size + 10  # Add some spacing between lines
        total_text_height = len(wrapped_lines) * line_height
        
        # Calculate text position
        text_y = image_y + new_height + 220  # 150px gap below image (increased from 80px)
        
        # Draw each line of text
        for i, line in enumerate(wrapped_lines):
            line_y = text_y + (i * line_height) - (total_text_height // 2)
            draw.text((bg_width//2, line_y), line, fill='black', font=font, anchor="mm")
        
        # Save the final image
        output_path = os.path.join(TITLED_IMAGE_OUTPUT_DIR, output_filename)
        bg_image.save(output_path)
        
        return output_path
    except Exception as e:
        print(f"Error generating titled image for '{title}' from '{image_path}': {str(e)}")
        raise  # Re-raise the exception to be handled by the caller