from utils.helper_functions import clean_json_input
from utils.open_ai_client import get_open_ai_client
import os

LIST_OUTPUT_DIR = "outputs/json_output"


def generate_list(prompt_topic: str):
    num_items: int = 10
    system_msg = "You are a helpful assistant that generates a list of interesting facts, places, or concepts."
    user_msg = (
        f"Give me a list of {num_items} items for a YouTube video on the topic: '{prompt_topic}'. "
        f"Each item should have a very short, concise **title** (just the main subject/name, no additional descriptive text) "
        f"and a 2 sentence **description** that is informative and intriguing. "
        f"Return the output in JSON format as a list of items like this: "
        f"[{{'title': '...', 'description': '...'}}, ...]"
    )

    client = get_open_ai_client()

    response = client.chat.completions.create(
        model="gpt-4o",
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
    os.makedirs(LIST_OUTPUT_DIR, exist_ok=True)
    
    # Save the JSON response to a file
    filename = f"{LIST_OUTPUT_DIR}/list_items.json"
    with open(filename, 'w') as f:
        f.write(content)

    print("\nGenerated Items:\n")
    print(f"Content: {content}")
    
    return content


# Main function
if __name__ == "__main__":
    topic = input("Enter a topic for your video: ")
    result = generate_list(topic)
    print("\nGenerated Items:\n")
    print(result)

