"""Which of an item's images actually exist, and the frames it will show.

An image can fail (the safety system may reject its prompt), so an item can
end up with fewer pictures than prompts, or none. The titled-image and video
stages both read this module, so they always agree on an item's frames.
"""

from pathlib import Path

from utils.paths import image_path, titled_image_path


def usable(path: Path) -> bool:
    """A file is usable if it exists and is not empty."""
    return path.exists() and path.stat().st_size > 0


def available_prompt_numbers(item_number: int, prompt_count: int) -> list[int]:
    """The prompt numbers, in order, whose generated image is usable."""
    return [
        prompt_number
        for prompt_number in range(1, prompt_count + 1)
        if usable(image_path(item_number, prompt_number))
    ]


def has_images(item_number: int, prompt_count: int) -> bool:
    return bool(available_prompt_numbers(item_number, prompt_count))


def item_frame_paths(item_number: int, prompt_count: int) -> list[Path]:
    """The titled frames an item plays, in order.

    One frame per usable image. An item with no usable images gets a single
    question-mark placeholder, stored where its first frame would be.
    """
    numbers = available_prompt_numbers(item_number, prompt_count) or [1]
    return [titled_image_path(item_number, number) for number in numbers]
