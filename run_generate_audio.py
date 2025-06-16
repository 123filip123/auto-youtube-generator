import os
import sys

# Add the project root directory to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.append(project_root)

# Now import and run the generate_audio function
from scripts.ai.generate_audios.generate_audio import generate_audio

if __name__ == "__main__":
    generate_audio() 