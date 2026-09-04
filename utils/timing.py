"""Turn narration text into the timings the pipeline plans against.

Every duration here is derived, never authored: the model writes prose to a
word budget and these functions decide how long it takes to speak and
therefore how many images ride over it.

The inter-sentence pause is what makes this non-obvious. The voice leaves
~1.6s of silence after every sentence whatever the sentence says, so two
paragraphs of equal word count but different sentence counts have materially
different runtimes. Ignoring that term under-counts shots and overshoots the
target length.
"""

import re

import config

# A run of consecutive terminators is one sentence end, so "Wait..." costs
# one pause rather than three.
_SENTENCE_END = re.compile(r"[.!?]+")


def count_sentences(narration: str) -> int:
    """How many sentence-ending pauses the voice will take.

    Non-empty narration written without terminal punctuation is still one
    spoken sentence, so the floor is 1.
    """
    text = narration.strip()
    if not text:
        return 0
    return max(1, len(_SENTENCE_END.findall(text)))


def speaking_seconds(narration: str) -> float:
    """How long `narration` takes to speak aloud, pauses included."""
    words = len(narration.split())
    return (
        words / config.NARRATION_WORDS_PER_SECOND
        + count_sentences(narration) * config.NARRATION_SENTENCE_PAUSE_SECONDS
    )


def shot_count(narration: str) -> int:
    """How many images ride over `narration`. Always at least one."""
    return max(1, round(speaking_seconds(narration) / config.SECONDS_PER_IMAGE))


def word_budget(target_seconds: float, avg_words_per_sentence: int = 13) -> int:
    """The total spoken-word budget for a script of `target_seconds`.

    The naive figure — target times words-per-second — ignores the pause and
    overshoots badly: 85 seconds budgets 268 words that way, which renders as
    roughly 118 seconds. Costing a whole sentence, speech plus pause, and
    dividing gives ~193 instead.
    """
    seconds_per_sentence = (
        avg_words_per_sentence / config.NARRATION_WORDS_PER_SECOND
        + config.NARRATION_SENTENCE_PAUSE_SECONDS
    )
    return round(target_seconds / seconds_per_sentence * avg_words_per_sentence)
