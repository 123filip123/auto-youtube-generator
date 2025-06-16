import os
import sys

# Add the project root directory to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.append(project_root)

# Now import and run the generate_images function
from scripts.ai.generate_images.generate_images import generate_images

if __name__ == "__main__":
    generate_images() 