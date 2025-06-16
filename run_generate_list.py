import os
import sys

# Add the project root directory to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.append(project_root)

# Now import and run the generate_list function
from scripts.ai.generate_list.generate_list import generate_list

if __name__ == "__main__":
    generate_list() 