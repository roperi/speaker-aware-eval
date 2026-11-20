"""Make a right-answer file from a plain-text transcript.

Write one turn per line as ``Name: what they said``. Blank lines are ignored. The speaker is
the text before the first colon that is followed by whitespace, so a colon inside the words
("Dana: it closes at 10:30") is fine. A turn that runs over several lines must be joined by
hand.

Command line::

    python -m speaker_aware_eval.whos_who.reference call.txt --id call-001 \\
        --alias "Dana Reyes=Dana,Agent" > truth.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .formats import FormatError, parse_truth

__all__ = ["reference_from_file", "reference_from_text", "main"]

MAX_NAME_LENGTH = 60
_LINE = re.compile(rf"^(?P<name>[^:]{{1,{MAX_NAME_LENGTH}}}):\s+(?P<text>\S.*)$")


def _key(name: str) -> str:
    """Names that differ only in case or spacing are the same person."""
    return " ".join(name.split()).casefold()


def _turns(text: str) -> list[tuple[str, str]]:
    turns = []
    # Split on real line breaks only: str.splitlines() also splits on U+2028, U+0085 and others.
    lines = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for number, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line:
            continue
        match = _LINE.match(line)
        if match is None or not match["name"].strip():
            raise FormatError(f"line {number}: no speaker; write 'Name: text' (got: {line!r})")
        turns.append((" ".join(match["name"].split()), match["text"]))
    if not turns:
        raise FormatError("no turns found; write one 'Name: text' per line")
    return turns


def reference_from_text(
    text: str,
    conversation_id: str,
    aliases: Mapping[str, Sequence[str]] | None = None,
) -> dict[str, Any]:
    """Return the right-answer dict for a transcript written as ``Name: text`` lines."""
    turns = _turns(text)
    spelling: dict[str, str] = {}
    for name, _ in turns:
        spelling.setdefault(_key(name), name)
    people: dict[str, list[str]] = {key: [] for key in spelling}
    for name, extra in (aliases or {}).items():
        key = _key(name)
        if key not in people:
            raise FormatError(f"alias given for {name!r}, who does not speak in the transcript")
        people[key].extend(extra)
    reference = {
        "conversation_id": conversation_id,
        "people": [{"name": spelling[key], "aliases": people[key]} for key in spelling],
        "turns": [{"speaker": spelling[_key(name)], "text": words} for name, words in turns],
    }
    parse_truth(reference)
    return reference


def reference_from_file(
    path: str | Path,
    conversation_id: str | None = None,
    aliases: Mapping[str, Sequence[str]] | None = None,
) -> dict[str, Any]:
    """Read a transcript file; the id defaults to the file name without its extension."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise FormatError(f"cannot read {path}: {exc.strerror or exc}") from exc
    except UnicodeDecodeError as exc:
        raise FormatError(f"{path} is not valid UTF-8: {exc}") from exc
    if conversation_id is None:
        conversation_id = Path(path).stem
    return reference_from_text(text, conversation_id, aliases)


def _alias_arg(value: str) -> tuple[str, list[str]]:
    name, sep, rest = value.partition("=")
    if not sep or not name.strip():
        raise argparse.ArgumentTypeError(f"{value!r}: write 'Name=alias1,alias2'")
    return name, [a.strip() for a in rest.split(",") if a.strip()]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m speaker_aware_eval.whos_who.reference",
        description="Turn a plain-text transcript ('Name: text' per line) into right-answer JSON.",
    )
    parser.add_argument("transcript", help="text file, one 'Name: text' turn per line")
    parser.add_argument("--id", dest="conversation_id", help="conversation id (default: file name)")
    parser.add_argument(
        "--alias",
        action="append",
        default=[],
        type=_alias_arg,
        metavar="NAME=ALIAS[,ALIAS]",
        help="aliases for one person; repeat for more people",
    )
    args = parser.parse_args(argv)
    aliases: dict[str, list[str]] = {}
    for name, extra in args.alias:
        aliases.setdefault(name, []).extend(extra)
    try:
        reference = reference_from_file(args.transcript, args.conversation_id, aliases)
    except FormatError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(reference, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
