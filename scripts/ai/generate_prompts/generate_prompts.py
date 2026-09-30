"""Turn a finished script into a style sheet and one image prompt per shot.

This call sees the whole script at once, which is the point: it lets the model
plan a visual arc across the video and author a style sheet that serves every
section rather than only the first.
"""

import json
from dataclasses import replace
from typing import Sequence

import config
from models import Script
from utils.open_ai_client import get_open_ai_client
from utils.openai_support import temperature_kwargs, with_retry
from utils.timing import shot_count


class PromptGenerationError(RuntimeError):
    """The model failed to return usable prompts for every section."""


PROMPTS_SYSTEM_MESSAGE = (
    "You are a storyboard artist. Given a narrated script, you design the "
    "sequence of simple line drawings that illustrates it. Always ensure all "
    "content is family-friendly and appropriate for all audiences."
)

PROMPTS_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "style": {
            "type": "string",
            "description": (
                "The recurring figure(s) and setting for the whole video, "
                "described concretely enough to be redrawn identically in "
                "every frame, naming a distinct vivid colour for each "
                "element. When the script names a real subject, name it here "
                "too and describe its likeness."
            ),
        },
        "sections": {
            "type": "array",
            "description": (
                "One entry per script section, in the same order as given."
            ),
            "items": {
                "type": "object",
                "properties": {
                    "label": {
                        "type": "string",
                        "description": "The section's label, echoed back.",
                    },
                    "prompts": {
                        "type": "array",
                        "description": "The drawings for this section, in order.",
                        "items": {"type": "string"},
                    },
                },
                "required": ["label", "prompts"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["style", "sections"],
    "additionalProperties": False,
}


def shot_budgets(script: Script) -> list[int]:
    """How many shots each section's narration earns."""
    return [shot_count(section.narration) for section in script.sections]


def build_prompts_message(script: Script, budgets: Sequence[int]) -> str:
    """The user message for call 2: the whole script plus each shot budget."""
    listing = "\n\n".join(
        f"SECTION {position} — {section.label} — {budget} drawing(s)\n"
        f"{section.narration}"
        for position, (section, budget) in enumerate(
            zip(script.sections, budgets), start=1
        )
    )
    return (
        f"Here is the full script for a vertical video titled "
        f"'{script.title}'. Design the drawings for it.\n"
        f"\n"
        f"{listing}\n"
        f"\n"
        f"Return one entry per section, in this exact order, with the number "
        f"of drawings shown above for each.\n"
        f"\n"
        f"FIRST, write the 'style' sheet: the recurring figure(s) and setting "
        f"for the whole video — their build, hair, clothing, props and "
        f"surroundings, and the colour of each — described concretely enough "
        f"that an illustrator could redraw them identically in every frame. "
        f"Name a distinct, vivid colour for each invented element and "
        f"avoid white, grey and black. A named real subject outranks that "
        f"rule: give their skin, hair and signature clothing their actual "
        f"colours, whatever those are. Describe only what is drawn; do not "
        f"name a medium or an art style. The style sheet is the ONLY thing "
        f"that carries a character's look from one section to the next, so "
        f"it must be specific enough to survive on its own.\n"
        f"\n"
        f"THEN write the prompts. How they chain matters:\n"
        f"- The FIRST drawing of every section is generated from its text "
        f"alone, so it must be self-contained and establish the whole scene, "
        f"naming any real subject and asking for their likeness again. "
        f"Never begin a section's first prompt with a back-reference.\n"
        f"- Every LATER drawing in a section is generated as a continuation "
        f"of the drawing immediately before it, so write it as a change: "
        f"keep the same figure and setting and alter or add exactly one "
        f"thing, referring back explicitly, for example 'the same wolf, now "
        f"stepping toward the firelight'.\n"
        f"- Drawings never chain across a section boundary. Each section is a "
        f"fresh visual start.\n"
        f"\n"
        f"DRAWING CONSTRAINTS:\n"
        f"- The drawings are plain black outline sketches with simply drawn "
        f"people. Describe simple shapes, poses and objects, plus the few "
        f"features that make a person recognisable.\n"
        f"- Never ask for text, letters, numbers or labels in a drawing.\n"
        f"- Colours are solid flat fills inside the outlines. Never ask for "
        f"shading, gradients, texture or photographic detail.\n"
        f"\n"
        f"IMPORTANT SAFETY GUIDELINES FOR IMAGE PROMPTS:\n"
        f"- All prompts must be family-friendly and appropriate for all "
        f"audiences\n"
        f"- Do not include prompts that could generate images of weapons, "
        f"gore, or harmful content\n"
        f"- Avoid prompts that could create images with nudity, sexual "
        f"content, or adult themes\n"
        f"\n"
        f"DRAWING A NAMED SUBJECT:\n"
        f"- When the script names a specific person, character or thing, "
        f"draw that subject itself. Never substitute an anonymous stand-in.\n"
        f"- Name the subject in the style sheet and describe what makes it "
        f"recognisable at a glance: skin tone, hair length, shape and "
        f"colour, facial hair, glasses or headwear, and the clothing it is "
        f"known for.\n"
        f"- Say it in the prompts as well as the style sheet — write 'drawn "
        f"in the likeness of <name>' rather than trusting the description to "
        f"speak for itself.\n"
        f"- That description is what actually carries the resemblance, so "
        f"make it specific enough that the subject would be recognised from "
        f"the drawing alone."
    )


@with_retry
def _request_prompts(client, message: str) -> str | None:
    response = client.chat.completions.create(
        model=config.TEXT_MODEL,
        messages=[
            {"role": "system", "content": PROMPTS_SYSTEM_MESSAGE},
            {"role": "user", "content": message},
        ],
        **temperature_kwargs(),
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "storyboard_prompts",
                "strict": True,
                "schema": PROMPTS_JSON_SCHEMA,
            },
        },
    )
    return response.choices[0].message.content


def _decode_sections(content: str | None) -> tuple[str, list[list[str]]]:
    """Pull the style sheet and per-section prompt lists out of a response."""
    try:
        payload = json.loads(content or "")
    except json.JSONDecodeError as exc:
        raise PromptGenerationError(f"prompt output was not valid JSON: {exc}") from exc

    raw_sections = payload.get("sections")
    if not isinstance(raw_sections, list):
        raise PromptGenerationError("prompt output has no 'sections' list")

    prompt_lists: list[list[str]] = []
    for entry in raw_sections:
        raw = entry.get("prompts") if isinstance(entry, dict) else None
        prompt_lists.append(
            [p.strip() for p in raw if isinstance(p, str) and p.strip()]
            if isinstance(raw, list)
            else []
        )
    return str(payload.get("style") or "").strip(), prompt_lists


def _empty_positions(script: Script, prompt_lists: Sequence[Sequence[str]]) -> list[int]:
    """1-based positions of sections that came back with nothing usable.

    A short-but-non-empty section is NOT reported: we set the budget
    ourselves and assembly divides measured audio by the actual shot count,
    so an off-budget section still yields a correct video.
    """
    if len(prompt_lists) != len(script.sections):
        return list(range(1, len(script.sections) + 1))
    return [
        position
        for position, prompts in enumerate(prompt_lists, start=1)
        if not prompts
    ]


def generate_prompts(script: Script, *, client=None) -> Script:
    """Fill `script` with a global style sheet and one prompt per shot.

    Prompt counts that differ from the budget are honoured, not corrected.
    A section that comes back empty triggers exactly one repair call.
    """
    client = client or get_open_ai_client()
    budgets = shot_budgets(script)
    message = build_prompts_message(script, budgets)

    style, prompt_lists = _decode_sections(_request_prompts(client, message))
    missing = _empty_positions(script, prompt_lists)

    if missing:
        listing = ", ".join(str(position) for position in missing)
        repair = (
            f"{message}\n\n"
            f"Your previous answer returned no drawings for section(s) "
            f"{listing}. Return ALL {len(script.sections)} sections in order, "
            f"each with at least one drawing."
        )
        style, prompt_lists = _decode_sections(_request_prompts(client, repair))
        missing = _empty_positions(script, prompt_lists)
        if missing:
            listing = ", ".join(f"section {position}" for position in missing)
            raise PromptGenerationError(
                f"the model returned no drawings for {listing} twice; "
                f"refusing to generate a section with no visuals"
            )

    filled = tuple(
        replace(section, prompts=tuple(prompts))
        for section, prompts in zip(script.sections, prompt_lists)
    )
    return replace(script, style=style, sections=filled)
