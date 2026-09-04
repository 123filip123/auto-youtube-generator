"""Ask the model for a list of video items, as guaranteed-valid JSON."""

import config
from models import Item, parse_items
from utils.open_ai_client import get_open_ai_client
from utils.openai_support import with_retry

SYSTEM_MESSAGE = (
    "You are a storyboard writer. For each subject you write a short narrated "
    "story and the sequence of simple line drawings that illustrates it, where "
    "each drawing continues the one before it. Always ensure all content is "
    "family-friendly and appropriate for all audiences."
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
                    "style": {
                        "type": "string",
                        "description": (
                            "The recurring figure(s) and setting for this "
                            "item's drawings, described concretely enough to "
                            "be redrawn identically every time."
                        ),
                    },
                    "beats": {
                        "type": "array",
                        "description": "The story beats, in narration order.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "narration": {
                                    "type": "string",
                                    "description": "One spoken sentence.",
                                },
                                "prompt": {
                                    "type": "string",
                                    "description": (
                                        "The drawing for this sentence, as a "
                                        "continuation of the previous one."
                                    ),
                                },
                            },
                            "required": ["narration", "prompt"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["title", "style", "beats"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}


# Below this a "sentence" stops being one. The budget clamps rather than
# going negative when SECONDS_PER_FRAME is set under the pause floor.
_MIN_WORDS_PER_BEAT = 4


def words_per_beat() -> int:
    """The spoken-word budget for one frame.

    Only the speaking part of a frame buys words — the inter-sentence pause
    is spent whatever the sentence says. Read at call time so a per-run
    override of any of the three constants applies.
    """
    speaking = config.SECONDS_PER_FRAME - config.NARRATION_SENTENCE_PAUSE_SECONDS
    return max(
        _MIN_WORDS_PER_BEAT,
        round(speaking * config.NARRATION_WORDS_PER_SECOND),
    )


def _build_user_message(topic: str, num_items: int) -> str:
    beat_count = config.IMAGE_PROMPTS_PER_ITEM
    word_budget = words_per_beat()
    return (
        f"Give me a list of {num_items} items for a YouTube video on the topic: "
        f"'{topic}'.\n"
        f"Each item is a tiny narrated story told through a sequence of simple "
        f"line drawings. Every item must have:\n"
        f"1. A very short, concise title (just the main subject/name, no "
        f"additional descriptive text)\n"
        f"2. A 'style' line naming the recurring figure(s) and setting for this "
        f"item — their build, hair, clothing, props and surroundings, and the "
        f"colour of each — described concretely enough that an illustrator "
        f"could redraw them identically in every frame. Name a distinct, "
        f"vivid colour for each element and avoid white, grey and black: the "
        f"colours carry the picture, and they must not change from one frame "
        f"to the next. Describe only what is drawn; do not name a medium or "
        f"an art style.\n"
        f"3. Exactly {beat_count} beats, in order. Each beat has:\n"
        f"   - 'narration': one short sentence of the spoken script, about "
        f"{word_budget} words, so it is spoken in roughly the time its frame "
        f"is on screen. Read in order, the {beat_count} sentences must flow as "
        f"continuous, informative, intriguing prose about the item.\n"
        f"   - 'prompt': what the drawing shows at that moment, written as a "
        f"continuation of the previous drawing. Keep the same figure and the "
        f"same setting, and change or add exactly one thing per beat. Refer "
        f"back explicitly, for example 'the same scientist, now beside the "
        f"apparatus'.\n"
        f"The first beat establishes the subject alone. Each later beat adds "
        f"the element its sentence introduces, so the drawings track the "
        f"narration as it plays.\n"
        f"\n"
        f"DRAWING CONSTRAINTS:\n"
        f"- The drawings are plain black outline sketches with stick-figure "
        f"people. Describe simple shapes, poses and objects only.\n"
        f"- Never ask for text, letters, numbers or labels in a drawing.\n"
        f"- Colours are solid flat fills inside the outlines. Never ask for "
        f"shading, gradients, texture or photographic detail.\n"
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
    expected shape, including a wrong number of story beats.
    """
    if num_items < 1:
        raise ValueError(f"num_items must be at least 1, got {num_items}")

    client = client or get_open_ai_client()
    content = _request_items(client, topic, num_items)
    # Read the count now, not at import time, so a per-run override applies.
    return parse_items(content or "", expected_prompts=config.IMAGE_PROMPTS_PER_ITEM)
