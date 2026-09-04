import pytest

import config
from utils.timing import count_sentences, shot_count, speaking_seconds, word_budget


@pytest.mark.parametrize(
    "narration, expected",
    [
        ("", 0),
        ("   ", 0),
        ("No terminal punctuation", 1),
        ("One sentence.", 1),
        ("Hello. World!", 2),
        ("Wait... what?", 2),
        ("Really?! Yes.", 2),
    ],
)
def test_count_sentences(narration, expected):
    assert count_sentences(narration) == expected


def test_speaking_seconds_includes_a_pause_per_sentence():
    # 30 words over two sentences: 30/3.15 speaking + 2*1.6 pause.
    narration = " ".join(["word"] * 29) + ". Done."
    expected = 30 / config.NARRATION_WORDS_PER_SECOND + 2 * config.NARRATION_SENTENCE_PAUSE_SECONDS
    assert speaking_seconds(narration) == pytest.approx(expected)


def test_shot_count_divides_speaking_time_by_seconds_per_image():
    # 30 words, 2 sentences -> 12.72s -> 12.72/2.5 = 5.09 -> 5 shots.
    narration = " ".join(["word"] * 29) + ". Done."
    assert shot_count(narration) == 5


def test_shot_count_is_at_least_one():
    assert shot_count("Hi.") == 1
    assert shot_count("") == 1


def test_word_budget_accounts_for_the_inter_sentence_pause():
    # The naive figure is 85 * 3.15 = 268, which renders as ~118 seconds.
    assert word_budget(85) == 193
    assert word_budget(85) < 85 * config.NARRATION_WORDS_PER_SECOND


def test_word_budget_scales_with_target():
    assert word_budget(170) == 2 * word_budget(85) or word_budget(170) > word_budget(85)


def test_shot_count_reads_config_at_call_time(monkeypatch):
    narration = " ".join(["word"] * 29) + ". Done."
    monkeypatch.setattr(config, "SECONDS_PER_IMAGE", 5.0)
    assert shot_count(narration) == 3
