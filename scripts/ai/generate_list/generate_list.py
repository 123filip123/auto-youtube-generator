from utils.helper_functions import clean_json_input
from utils.open_ai_client import get_open_ai_client
import os

from utils.output_dirs import JSON_OUTPUT_DIR



def generate_list(prompt_topic: str):
    num_items: int = 5
    system_msg = "You are a helpful assistant that generates a list of interesting facts, places, or concepts, along with creative image prompts."
    user_msg = (
        f"Give me a list of {num_items} items for a YouTube video on the topic: '{prompt_topic}'. "
        f"Each item should have:\n"
        f"1. A very short, concise **title** (just the main subject/name, no additional descriptive text)\n"
        f"2. A 2 sentence **description** that is informative and intriguing\n"
        f"3. Three different **image_prompts** that would create engaging visuals for this item:\n"
        f"   - First prompt: A straightforward, clear representation of the item. The prompt should just be the item name.\n"
        f"   - Second prompt: The item in an creative setting.\n"
        f"   - Third prompt: The item in a different style or perspective\n"
        f"Return the output in JSON format as a list of items like this: "
        f"[{{'title': '...', 'description': '...', 'image_prompts': ['...', '...', '...']}}, ...]"
    )

    client = get_open_ai_client()

    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg}
        ],
        temperature=0.7
    )

    content = response.choices[0].message.content

    # Clean the JSON input
    content = clean_json_input(content)
    
    # Create outputs directory if it doesn't exist
    os.makedirs(JSON_OUTPUT_DIR, exist_ok=True)
    
    # Save the JSON response to a file
    filename = f"{JSON_OUTPUT_DIR}/list_items_with_prompts.json"
    with open(filename, 'w') as f:
        f.write(content)

    print("\nGenerated Items with Image Prompts:\n")
    print(f"Content: {content}")
    
    return content


# Main function
if __name__ == "__main__":
    topic = input("Enter a topic for your video: ")
    result = generate_list(topic)
    print("\nGenerated Items with Image Prompts:\n")
    print(result)
