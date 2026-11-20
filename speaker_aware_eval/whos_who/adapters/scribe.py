"""ElevenLabs Scribe v2 adapter (the output returned by the Replicate model).

Turns one Scribe result (``diarize: true``) into the grouped turns that
:func:`speaker_aware_eval.whos_who.adapters.diarized.build_output` reads. Only
entries of type ``word`` carry text; audio events and spacing are dropped. A
word without a voice stays in the current turn, or is dropped before any voice
has been seen. Voice labels are ``SPEAKER_<n>`` where ``<n>`` is the number in
Scribe's ``speaker_<n>`` id, or the id itself when it has no number.
"""

from __future__ import annotations

import re
from typing import Any

_NUMBERED = re.compile(r"^speaker_(\d+)$")


def _label(speaker_id: str) -> str:
    match = _NUMBERED.match(speaker_id.strip())
    return f"SPEAKER_{match.group(1)}" if match else f"SPEAKER_{speaker_id.strip()}"


def to_diarized(payload: dict[str, Any]) -> dict[str, Any]:
    """Return ``{"speaker_turns": [...]}`` for a Scribe v2 result."""
    words = payload.get("words") if isinstance(payload, dict) else None
    if not isinstance(words, list):
        raise ValueError("Scribe payload needs a 'words' list")
    turns: list[dict[str, str]] = []
    for word in words:
        if not isinstance(word, dict) or word.get("type") != "word":
            continue
        text = word.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        speaker_id = word.get("speaker_id")
        if isinstance(speaker_id, str) and speaker_id.strip():
            label = _label(speaker_id)
        elif turns:
            label = turns[-1]["speaker"]
        else:
            continue
        if turns and turns[-1]["speaker"] == label:
            turns[-1]["text"] = f"{turns[-1]['text']} {text.strip()}"
        else:
            turns.append({"speaker": label, "text": text.strip()})
    if not turns:
        raise ValueError("Scribe payload has no usable words")
    return {"speaker_turns": turns}
