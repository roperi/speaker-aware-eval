"""Neutral input format for the who's-who scorer.

Both inputs are JSON objects. Any source can be scored once a small adapter converts it
to this shape.

Right answer (human-checked)::

    {
      "conversation_id": "call-001",
      "people": [{"name": "Dana Reyes", "aliases": ["Dana", "Agent"]}],
      "turns": [{"speaker": "Dana Reyes", "text": "Thanks for calling."}]
    }

System output::

    {
      "conversation_id": "call-001",
      "turns": [{"voice": "SPEAKER_00", "speaker": "Dana Reyes", "text": "Thanks for calling."}]
    }

- ``people`` is optional. People who speak in the right answer but are not listed are added.
  In the system output ``people`` is accepted and ignored.
- ``speaker`` in the right answer is the true identity: a name or a role. In the system output
  it is the name or role the system assigned. It may be a placeholder such as
  ``"Unknown Speaker 2"``, empty, or null.
- ``voice`` is the system's anonymous voice ID. It is required in the system output.
- The words, their split into turns and the number of turns may differ between the files.
- Unknown keys are ignored. Both files must carry the same ``conversation_id``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class FormatError(ValueError):
    """Raised when an input file does not follow the neutral format."""


@dataclass(frozen=True)
class Person:
    name: str
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class Turn:
    speaker: str | None
    text: str
    voice: str | None = None


@dataclass(frozen=True)
class Conversation:
    conversation_id: str
    turns: tuple[Turn, ...]
    people: tuple[Person, ...] = field(default_factory=tuple)


def _require_object(data: Any, what: str) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise FormatError(f"{what}: expected a JSON object")
    return data


def _parse_people(data: dict[str, Any], what: str) -> tuple[Person, ...]:
    raw = data.get("people", [])
    if not isinstance(raw, list):
        raise FormatError(f"{what}: 'people' must be a list")
    people = []
    for i, item in enumerate(raw):
        item = _require_object(item, f"{what}: people[{i}]")
        name = item.get("name")
        aliases = item.get("aliases", [])
        if not isinstance(name, str) or not name.strip():
            raise FormatError(f"{what}: people[{i}] needs a non-empty 'name'")
        if not isinstance(aliases, list) or not all(isinstance(a, str) for a in aliases):
            raise FormatError(f"{what}: people[{i}] 'aliases' must be a list of strings")
        people.append(Person(name=name, aliases=tuple(aliases)))
    return tuple(people)


def _parse(data: Any, what: str, *, is_output: bool) -> Conversation:
    data = _require_object(data, what)
    cid = data.get("conversation_id")
    if not isinstance(cid, str) or not cid.strip():
        raise FormatError(f"{what}: 'conversation_id' must be a non-empty string")
    raw_turns = data.get("turns")
    if not isinstance(raw_turns, list) or not raw_turns:
        raise FormatError(f"{what}: 'turns' must be a non-empty list")
    turns = []
    for i, item in enumerate(raw_turns):
        where = f"{what}: turns[{i}]"
        item = _require_object(item, where)
        text = item.get("text")
        if not isinstance(text, str):
            raise FormatError(f"{where} needs a string 'text'")
        speaker = item.get("speaker")
        if is_output:
            voice = item.get("voice")
            if not isinstance(voice, str) or not voice.strip():
                raise FormatError(f"{where} needs a non-empty 'voice'")
            if speaker is not None and not isinstance(speaker, str):
                raise FormatError(f"{where} 'speaker' must be a string or null")
        else:
            voice = None
            if not isinstance(speaker, str) or not speaker.strip():
                raise FormatError(f"{where} needs a non-empty 'speaker'")
        turns.append(Turn(speaker=speaker, text=text, voice=voice))
    return Conversation(
        conversation_id=cid,
        turns=tuple(turns),
        people=() if is_output else _parse_people(data, what),
    )


def parse_truth(data: Any, what: str = "right answer") -> Conversation:
    return _parse(data, what, is_output=False)


def parse_output(data: Any, what: str = "system output") -> Conversation:
    return _parse(data, what, is_output=True)


def _load_json(path: str | Path, what: str) -> Any:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except OSError as exc:
        raise FormatError(f"{what}: cannot read {path}: {exc.strerror or exc}") from exc
    except json.JSONDecodeError as exc:
        raise FormatError(f"{what}: {path} is not valid JSON: {exc}") from exc


def load_truth(path: str | Path) -> Conversation:
    return parse_truth(_load_json(path, "right answer"))


def load_output(path: str | Path) -> Conversation:
    return parse_output(_load_json(path, "system output"))
