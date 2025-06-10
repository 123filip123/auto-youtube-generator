import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def generate_list(prompt_topic: str):
    num_items: int = 10
    system_msg = "You are a helpful assistant that generates a list of interesting facts, places, or concepts."
    user_msg = (
        f"Give me a list of {num_items} items for a YouTube video on the topic: '{prompt_topic}'. "
        f"Each item should have a short, catchy **title** and a 4-5 sentence **description** that is informative and intriguing. "
        f"Return the output in JSON format as a list of items like this: "
        f"[{{'title': '...', 'description': '...'}}, ...]"
    )

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg}
        ],
        temperature=0.7
    )

    return response.choices[0].message.content

# --- Example usage ---
if __name__ == "__main__":
    topic = input("Enter a topic for your video: ")
    result = generate_list(topic)
    print("\nGenerated Items:\n")
    print(result)

