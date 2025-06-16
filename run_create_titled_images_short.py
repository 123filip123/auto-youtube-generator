import os
import sys

# Add the project root directory to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.append(project_root)

# Now import and run the create_titled_images_short function
from scripts.non_ai.create_titled_images_short.create_titled_images_short import create_titled_images_short

if __name__ == "__main__":
    create_titled_images_short() 