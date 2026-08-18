"""Command-line entry point for the auto YouTube generator."""

import argparse
import sys

from models import InvalidItemsError
from pipeline import PipelineError, run_pipeline


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a YouTube Shorts video from a topic."
    )
    parser.add_argument("--topic", help="Video topic. Prompted for if omitted.")
    parser.add_argument(
        "--items", type=int, help="Number of items. Prompted for if omitted."
    )
    return parser.parse_args(argv)


def prompt_for_topic() -> str:
    while True:
        topic = input("Enter a topic for your video: ").strip()
        if topic:
            return topic
        print("Please enter a topic.")


def prompt_for_item_count() -> int:
    while True:
        raw = input("Enter the number of items for your video: ").strip()
        try:
            count = int(raw)
        except ValueError:
            print(f"'{raw}' is not a whole number. Try again.")
            continue
        if count < 1:
            print("Please enter a number of at least 1.")
            continue
        return count


def main(argv=None) -> int:
    args = parse_args(argv)

    topic = args.topic.strip() if args.topic else prompt_for_topic()
    if args.items is not None:
        if args.items < 1:
            print(f"--items must be at least 1, got {args.items}", file=sys.stderr)
            return 2
        num_items = args.items
    else:
        num_items = prompt_for_item_count()

    try:
        video = run_pipeline(topic, num_items)
    except (PipelineError, InvalidItemsError) as exc:
        print(f"\nPipeline failed: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130

    print(f"\nDone: {video}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
