"""Ask the model for a list of video items, as guaranteed-valid JSON."""

import config
from models import Item, parse_items
from utils.open_ai_client import get_open_ai_client
from utils.openai_support import with_retry

SYSTEM_MESSAGE = (
    "You are a helpful assistant that generates a list of interesting facts, "
    "places, or concepts, along with creative image prompts. Always ensure all "
    "content is family-friendly and appropriate for all audiences."
)

LIST_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "description": "The generated video items, in presentation order.",
            "items": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Very short subject name, no extra words.",
                    },
                    "description": {
                        "type": "string",
                        "description": "Two informative, intriguing sentences.",
                    },
                    "image_prompts": {
                        "type": "array",
                        "description": "Image generation prompts for this item.",
                        "items": {"type": "string"},
                    },
                },
                "required": ["title", "description", "image_prompts"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}


def _build_user_message(topic: str, num_items: int) -> str:
    prompt_count = config.IMAGE_PROMPTS_PER_ITEM
    return (
        f"Give me a list of {num_items} items for a YouTube video on the topic: "
        f"'{topic}'.\n"
        f"Each item must have:\n"
        f"1. A very short, concise title (just the main subject/name, no "
        f"additional descriptive text)\n"
        f"2. A 2 sentence description that is informative and intriguing\n"
        f"3. Exactly {prompt_count} different image_prompts that would create "
        f"engaging visuals for this item:\n"
        f"   - First prompt: A straightforward, clear representation of the "
        f"item. The prompt should just be the item name.\n"
        f"   - Second prompt: The item in a creative setting. Should be "
        f"hilariously funny and creative.\n"
        f"   - Third prompt: The item in a different style or perspective than "
        f"the first two. Should be a bit more creative and unique.\n"
        f"\n"
        f"IMPORTANT SAFETY GUIDELINES FOR IMAGE PROMPTS:\n"
        f"- All prompts must be family-friendly and appropriate for all "
        f"audiences\n"
        f"- Avoid any content that could be considered violent, graphic, or "
        f"inappropriate\n"
        f"- Do not include prompts that could generate images of weapons, gore, "
        f"or harmful content\n"
        f"- Avoid prompts that could create images with nudity, sexual content, "
        f"or adult themes\n"
        f"- Ensure all prompts are educational, informative, or entertaining in "
        f"a wholesome way\n"
        f"- If the topic involves potentially sensitive subjects, focus on "
        f"positive, educational, or neutral representations\n"
        f"\n"
        f"COPYRIGHT AND INTELLECTUAL PROPERTY GUIDELINES:\n"
        f"- NEVER include copyrighted characters, brands, or intellectual "
        f"property in prompts\n"
        f"- Avoid specific character names like 'Yoda', 'Mickey Mouse', "
        f"'Superman', 'Mario', etc.\n"
        f"- Instead of copyrighted characters, use generic descriptions (e.g., "
        f"'wise green alien mentor' instead of 'Yoda')\n"
        f"- Avoid famous logos, brand names, or trademarked symbols\n"
        f"- Create original, generic descriptions that capture the essence "
        f"without infringing on copyrights\n"
        f"- Focus on visual concepts, emotions, and themes rather than specific "
        f"copyrighted entities\n"
        f"- Use descriptive terms like 'heroic figure', 'wise mentor', 'cute "
        f"animal companion' instead of specific character names"
    )


@with_retry
def _request_items(client, topic: str, num_items: int) -> str | None:
    response = client.chat.completions.create(
        model=config.TEXT_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_MESSAGE},
            {"role": "user", "content": _build_user_message(topic, num_items)},
        ],
        temperature=config.TEXT_TEMPERATURE,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "video_items",
                "strict": True,
                "schema": LIST_JSON_SCHEMA,
            },
        },
    )
    return response.choices[0].message.content


def generate_list(topic: str, num_items: int = 5, *, client=None) -> list[Item]:
    """Generate `num_items` validated items for `topic`.

    Raises `InvalidItemsError` if the model's output does not match the
    expected shape, including a wrong number of image prompts.
    """
    if num_items < 1:
        raise ValueError(f"num_items must be at least 1, got {num_items}")

    client = client or get_open_ai_client()
    content = _request_items(client, topic, num_items)
    return parse_items(content or "")
