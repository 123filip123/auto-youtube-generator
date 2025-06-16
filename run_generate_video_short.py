import os
import sys

# Add the project root directory to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.append(project_root)

# Now import and run the generate_video_short function
from scripts.non_ai.generate_video_short.generate_video_short import generate_video_short

if __name__ == "__main__":
    generate_video_short() 