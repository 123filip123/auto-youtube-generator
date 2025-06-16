import os
import sys

# Add the project root directory to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.append(project_root)

from scripts.non_ai.save_to_generated_data.save_to_generated_data import save_to_generated_data
from utils.output_file_names import get_list_items_path

if __name__ == "__main__":
    # Get the topic from user input
    topic = input("Enter the topic name for the folder (or press Enter to use timestamp): ").strip()
    
    # Save the generated data
    save_to_generated_data(get_list_items_path(), topic if topic else None) 