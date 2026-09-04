"""Command-line entry point for the auto YouTube generator."""

import argparse
import sys

from models import InvalidScriptError
from pipeline import PipelineError, run_pipeline
from scripts.ai.generate_prompts.generate_prompts import PromptGenerationError
from scripts.ai.generate_script.generate_script import MIN_TARGET_SECONDS


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a YouTube Shorts video from a topic."
    )
    parser.add_argument("--topic", help="Video topic. Prompted for if omitted.")
    parser.add_argument(
        "--seconds",
        type=int,
        help="Target video length in seconds. Prompted for if omitted.",
    )
    return parser.parse_args(argv)


def prompt_for_topic() -> str:
    while True:
        topic = input("Enter a topic for your video: ").strip()
        if topic:
            return topic
        print("Please enter a topic.")


def prompt_for_target_seconds() -> int:
    while True:
        raw = input("Enter the target length in seconds: ").strip()
        try:
            seconds = int(raw)
        except ValueError:
            print(f"'{raw}' is not a whole number. Try again.")
            continue
        if seconds < MIN_TARGET_SECONDS:
            print(f"Please enter at least {MIN_TARGET_SECONDS} seconds.")
            continue
        return seconds


def main(argv=None) -> int:
    args = parse_args(argv)

    topic = args.topic.strip() if args.topic else prompt_for_topic()
    if args.seconds is not None:
        if args.seconds < MIN_TARGET_SECONDS:
            print(
                f"--seconds must be at least {MIN_TARGET_SECONDS}, "
                f"got {args.seconds}",
                file=sys.stderr,
            )
            return 2
        target_seconds = args.seconds
    else:
        target_seconds = prompt_for_target_seconds()

    try:
        video = run_pipeline(topic, target_seconds)
    except (PipelineError, InvalidScriptError, PromptGenerationError) as exc:
        print(f"\nPipeline failed: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130

    print(f"\nDone: {video}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
