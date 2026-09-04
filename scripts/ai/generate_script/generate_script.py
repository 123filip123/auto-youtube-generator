"""Ask the model for one narrated script, divided into free-form sections."""

import config
from models import Script, parse_script, with_estimated_timings
from utils.open_ai_client import get_open_ai_client
from utils.openai_support import with_retry
from utils.timing import word_budget

# Anything shorter than this cannot carry a hook and a payoff.
MIN_TARGET_SECONDS = 15

SCRIPT_SYSTEM_MESSAGE = (
    "You are a short-form video writer. You write one continuous spoken "
    "script for a vertical video, divided into labelled sections that build "
    "on each other. Always ensure all content is family-friendly and "
    "appropriate for all audiences."
)

SCRIPT_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {
            "type": "string",
            "description": (
                "The video title: short, concrete, and stating the surprise "
                "rather than teasing it."
            ),
        },
        "sections": {
            "type": "array",
            "description": "The sections of the script, in spoken order.",
            "items": {
                "type": "object",
                "properties": {
                    "label": {
                        "type": "string",
                        "description": (
                            "A short upper-case name for this section's job, "
                            "chosen by you, e.g. HOOK or WAIT, WHAT?"
                        ),
                    },
                    "narration": {
                        "type": "string",
                        "description": (
                            "The spoken prose for this section: one to four "
                            "sentences, read aloud continuously."
                        ),
                    },
                },
                "required": ["label", "narration"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["title", "sections"],
    "additionalProperties": False,
}


def build_script_message(topic: str, target_seconds: int) -> str:
    """The user message for call 1.

    The word budget is pause-corrected — see `utils.timing.word_budget`. Handing
    the model the naive words-per-second figure produces scripts ~40% long.
    """
    budget = word_budget(target_seconds)
    return (
        f"Write the script for a {target_seconds}-second vertical video on: "
        f"'{topic}'.\n"
        f"\n"
        f"Total spoken length must be about {budget} words across all "
        f"sections. This is a spoken-word budget that already accounts for "
        f"the pauses between sentences, so treat it as a hard ceiling.\n"
        f"\n"
        f"STRUCTURE:\n"
        f"- Divide the script into sections. You choose how many and what to "
        f"call them; four to seven works well at this length.\n"
        f"- Give each section a short upper-case label naming its job in the "
        f"video, for example HOOK, SETUP, THE TWIST, or WAIT, WHAT?\n"
        f"- The first section must hook the viewer in one or two sentences. "
        f"The last section must end on a call to action.\n"
        f"- Sections in between carry the argument: set up the situation, "
        f"turn it, give the evidence, land the payoff.\n"
        f"\n"
        f"VOICE:\n"
        f"- Address the viewer directly as 'you'. Write the way a person "
        f"talks, contractions included.\n"
        f"- Open on a concrete, surprising, specific fact. Never open by "
        f"summarising what the video will cover.\n"
        f"- Never write meta narration such as 'in this video we'll explore' "
        f"or 'let's dive in'.\n"
        f"- Prefer specific numbers, names and dates over vague claims.\n"
        f"- Vary sentence length. Short sentences land the turns.\n"
        f"\n"
        f"IMPORTANT SAFETY GUIDELINES:\n"
        f"- All content must be family-friendly and appropriate for all "
        f"audiences\n"
        f"- Avoid any content that could be considered violent, graphic, or "
        f"inappropriate\n"
        f"- Ensure the script is educational, informative, or entertaining in "
        f"a wholesome way\n"
        f"- If the topic involves potentially sensitive subjects, focus on "
        f"positive, educational, or neutral representations\n"
        f"\n"
        f"COPYRIGHT AND INTELLECTUAL PROPERTY GUIDELINES:\n"
        f"- NEVER reference copyrighted characters, brands, or intellectual "
        f"property\n"
        f"- Avoid specific character names like 'Yoda', 'Mickey Mouse', "
        f"'Superman', 'Mario', etc.\n"
        f"- Avoid famous logos, brand names, or trademarked symbols\n"
        f"- Focus on visual concepts, emotions, and themes rather than "
        f"specific copyrighted entities"
    )


@with_retry
def _request_script(client, topic: str, target_seconds: int) -> str | None:
    response = client.chat.completions.create(
        model=config.TEXT_MODEL,
        messages=[
            {"role": "system", "content": SCRIPT_SYSTEM_MESSAGE},
            {"role": "user", "content": build_script_message(topic, target_seconds)},
        ],
        temperature=config.TEXT_TEMPERATURE,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "video_script",
                "strict": True,
                "schema": SCRIPT_JSON_SCHEMA,
            },
        },
    )
    return response.choices[0].message.content


def generate_script(
    topic: str, target_seconds: int | None = None, *, client=None
) -> Script:
    """Write one script for `topic`, roughly `target_seconds` long.

    Raises `InvalidScriptError` if the model's output does not match the
    expected shape. The returned script carries estimated timings; nothing
    consumes them until the archive rewrites them from measured audio.
    """
    target = (
        config.TARGET_VIDEO_SECONDS if target_seconds is None else int(target_seconds)
    )
    if target < MIN_TARGET_SECONDS:
        raise ValueError(
            f"target_seconds must be at least {MIN_TARGET_SECONDS}, got {target}"
        )

    client = client or get_open_ai_client()
    content = _request_script(client, topic, target)
    return with_estimated_timings(parse_script(content or "", topic=topic))
