"""Deepgram pre-recorded adapter.

Turns one Deepgram pre-recorded result (``diarize=true``) into the grouped turns
that :func:`speaker_aware_eval.whos_who.adapters.diarized.build_output` reads.
A turn is a run of consecutive words from one voice. Voice labels are
``SPEAKER_<n>``. A word without an integer ``speaker`` is dropped: with
``diarize=true`` Deepgram gives every word one, so a missing voice means a
malformed entry. (The Scribe adapter differs: Scribe can leave a word without a
voice, and that word joins the current turn.)
"""

from __future__ import annotations

from typing import Any


def _words(payload: Any) -> list[Any]:
    try:
        words = payload["results"]["channels"][0]["alternatives"][0]["words"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError(
            "Deepgram payload needs results.channels[0].alternatives[0].words"
        ) from exc
    if not isinstance(words, list):
        raise ValueError("Deepgram payload words must be a list")
    return words


def to_diarized(payload: dict[str, Any]) -> dict[str, Any]:
    """Return ``{"speaker_turns": [...]}`` for a Deepgram result."""
    turns: list[dict[str, str]] = []
    for word in _words(payload):
        if not isinstance(word, dict):
            continue
        speaker = word.get("speaker")
        if isinstance(speaker, bool) or not isinstance(speaker, int):
            continue
        text = word.get("punctuated_word") or word.get("word")
        if not isinstance(text, str) or not text.strip():
            continue
        label = f"SPEAKER_{speaker}"
        if turns and turns[-1]["speaker"] == label:
            turns[-1]["text"] = f"{turns[-1]['text']} {text.strip()}"
        else:
            turns.append({"speaker": label, "text": text.strip()})
    if not turns:
        raise ValueError("Deepgram payload has no usable words")
    return {"speaker_turns": turns}
