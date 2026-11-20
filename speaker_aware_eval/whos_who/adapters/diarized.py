"""Diarized system-output adapter.

A diarized transcription service returns anonymous voice labels and text. A
naming step maps each voice label to a person's name. This module turns those two
pieces into the scorer's system-output JSON.

The accepted diarized payload is either the service's ``chunks`` list (each chunk
has ``speaker``, ``timestamp`` and ``text``) or an already grouped
``speaker_turns`` list. Chunks from the same voice with touching timestamps are
merged, matching the private pipeline's transcription contract.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _normalize_naming(naming: dict[str, Any]) -> dict[str, str | None]:
    result: dict[str, str | None] = {}
    for voice, name in naming.items():
        if not isinstance(voice, str) or not voice.strip():
            continue
        if name is None:
            result[voice] = None
            continue
        if not isinstance(name, str):
            raise ValueError(f"naming for {voice!r} must be a string or null")
        cleaned = name.strip()
        result[voice] = cleaned or None
    return result


def parse_naming(naming: dict[str, Any] | str | Path) -> dict[str, str | None]:
    """Accept a naming map or a JSON file path and return a normalized map."""
    if isinstance(naming, (str, Path)):
        try:
            with open(naming, encoding="utf-8") as handle:
                naming = json.load(handle)
        except OSError as exc:
            raise ValueError(f"cannot read {naming}: {exc.strerror or exc}") from exc
        except json.JSONDecodeError as exc:
            raise ValueError(f"{naming} is not valid JSON: {exc}") from exc
    if not isinstance(naming, dict):
        raise ValueError("naming result must be a JSON object mapping voice labels to names")
    return _normalize_naming(naming)


def _turns_from_chunks(chunks: Iterable[Any]) -> list[dict[str, Any]]:
    turns: list[dict[str, Any]] = []
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        speaker = chunk.get("speaker")
        text = chunk.get("text")
        timestamp = chunk.get("timestamp")
        if not isinstance(speaker, str) or not speaker.strip():
            continue
        if not isinstance(text, str) or not text.strip():
            continue
        if not isinstance(timestamp, list) or len(timestamp) < 2:
            continue
        start = _as_float(timestamp[0])
        end = _as_float(timestamp[1])
        if start is None or end is None or end < start:
            continue
        if turns and turns[-1]["speaker"] == speaker and turns[-1]["end"] == start:
            turns[-1]["end"] = end
            turns[-1]["text"] = f"{turns[-1]['text']} {text.strip()}".strip()
            continue
        turns.append({"speaker": speaker, "start": start, "end": end, "text": text.strip()})
    return turns


def _turns_from_speaker_turns(speaker_turns: Iterable[Any]) -> list[dict[str, Any]]:
    turns: list[dict[str, Any]] = []
    for turn in speaker_turns:
        if not isinstance(turn, dict):
            continue
        speaker = turn.get("speaker")
        text = turn.get("text")
        if not isinstance(speaker, str) or not speaker.strip():
            continue
        if not isinstance(text, str) or not text.strip():
            continue
        turns.append({"speaker": speaker, "text": text.strip()})
    return turns


def group_diarized_turns(diarized: dict[str, Any]) -> list[dict[str, Any]]:
    """Return grouped turns from a diarized payload.

    Prefers an explicit ``speaker_turns`` list; otherwise groups ``chunks``.
    Raises ``ValueError`` when neither yields a turn.
    """
    if not isinstance(diarized, dict):
        raise ValueError("diarized payload must be a JSON object")
    speaker_turns = diarized.get("speaker_turns")
    if isinstance(speaker_turns, list) and speaker_turns:
        turns = _turns_from_speaker_turns(speaker_turns)
    else:
        chunks = diarized.get("chunks")
        if not isinstance(chunks, list):
            raise ValueError("diarized payload needs a 'chunks' or 'speaker_turns' list")
        turns = _turns_from_chunks(chunks)
    if not turns:
        raise ValueError("diarized payload has no usable turns")
    return turns


def build_output(
    diarized: dict[str, Any],
    naming: dict[str, Any] | str | Path,
    *,
    conversation_id: str,
) -> dict[str, Any]:
    """Build system-output JSON from a diarized payload and a naming result."""
    if not isinstance(conversation_id, str) or not conversation_id.strip():
        raise ValueError("conversation_id is required")
    names = parse_naming(naming)
    turns = group_diarized_turns(diarized)
    return {
        "conversation_id": conversation_id,
        "turns": [
            {
                "voice": turn["speaker"],
                "speaker": names.get(turn["speaker"]),
                "text": turn["text"],
            }
            for turn in turns
        ],
    }


def load_output(
    diarized_path: str | Path,
    naming_path: str | Path,
    *,
    conversation_id: str,
) -> dict[str, Any]:
    """Load a diarized payload from a file and build system-output JSON."""
    try:
        with open(diarized_path, encoding="utf-8") as handle:
            diarized = json.load(handle)
    except OSError as exc:
        raise ValueError(f"cannot read {diarized_path}: {exc.strerror or exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{diarized_path} is not valid JSON: {exc}") from exc
    return build_output(diarized, naming_path, conversation_id=conversation_id)
