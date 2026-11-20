"""Earnings-21 right-answer adapter.

Earnings-21 publishes a pipe-separated token file per call
(``transcripts/nlp_references/<file_id>.nlp``) and a shared
``speaker-metadata.csv`` mapping integer speaker ids to names. This module turns
one call into the scorer's right-answer JSON.

The token file columns are ``token|speaker|ts|endTs|punctuation|case|tags|wer_tags``.
Only ``token``, ``speaker``, ``punctuation`` and ``case`` are needed for scoring.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

NLP_COLUMNS = ("token", "speaker", "ts", "endTs", "punctuation", "case", "tags", "wer_tags")
SENTENCE_END = frozenset({".", "?", "!"})


def _read_nlp(path: str | Path) -> list[dict[str, str]]:
    try:
        with open(path, encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="|")
            if reader.fieldnames is None:
                raise ValueError(f"{path}: missing header row")
            missing = [column for column in NLP_COLUMNS if column not in reader.fieldnames]
            if missing:
                raise ValueError(f"{path}: missing columns {missing}")
            return [dict(row) for row in reader]
    except OSError as exc:
        raise ValueError(f"cannot read {path}: {exc.strerror or exc}") from exc


def load_speaker_metadata(path: str | Path) -> dict[str, dict[str, str]]:
    """Load ``speaker-metadata.csv`` as ``{file_id: {speaker_id: name}}``."""
    try:
        with open(path, encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise ValueError(f"{path}: missing header row")
            required = ("file_id", "speaker_id", "speaker_name")
            missing = [column for column in required if column not in reader.fieldnames]
            if missing:
                raise ValueError(f"{path}: missing columns {missing}")
            metadata: dict[str, dict[str, str]] = {}
            for row in reader:
                file_id = (row.get("file_id") or "").strip()
                speaker_id = (row.get("speaker_id") or "").strip()
                name = (row.get("speaker_name") or "").strip()
                if not file_id or not speaker_id:
                    continue
                metadata.setdefault(file_id, {})[speaker_id] = name
            return metadata
    except OSError as exc:
        raise ValueError(f"cannot read {path}: {exc.strerror or exc}") from exc


def _apply_case(token: str, case: str) -> str:
    if case == "UC":
        return token[:1].upper() + token[1:].lower()
    if case == "LC":
        return token.lower()
    if case == "CA":
        return token.upper()
    return token


def _token_text(row: dict[str, str]) -> str:
    token = (row.get("token") or "").strip()
    if not token:
        return ""
    return _apply_case(token, (row.get("case") or "").strip()) + (row.get("punctuation") or "")


def group_tokens(rows: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    """Group tokens into turns by contiguous speaker and sentence end."""
    turns: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for row in rows:
        speaker = (row.get("speaker") or "").strip()
        text = _token_text(row)
        if not speaker or not text:
            continue
        if current is None or current["speaker"] != speaker:
            current = {"speaker": speaker, "parts": []}
            turns.append(current)
        current["parts"].append(text)
        if (row.get("punctuation") or "").strip() in SENTENCE_END:
            current = None
    return [
        {"speaker": turn["speaker"], "text": " ".join(turn["parts"])}
        for turn in turns
        if turn["parts"]
    ]


def _file_id_from_path(path: str | Path) -> str:
    return Path(path).stem


UNNAMED_SPEAKER_MODES = ("error", "placeholder")


def _unnamed_speakers(
    rows: Iterable[dict[str, str]], metadata: Mapping[str, str]
) -> dict[str, int]:
    """Speaker ids that have no name in the metadata, with their token counts, in call order."""
    counts: dict[str, int] = {}
    for row in rows:
        speaker = (row.get("speaker") or "").strip()
        if speaker and _token_text(row) and not metadata.get(speaker):
            counts[speaker] = counts.get(speaker, 0) + 1
    return counts


def build_truth(
    nlp_path: str | Path,
    speaker_metadata_path: str | Path,
    *,
    file_id: str | None = None,
    aliases: Mapping[str, Iterable[str]] | None = None,
    unnamed_speakers: str = "error",
) -> dict[str, Any]:
    """Build right-answer JSON for one Earnings-21 call.

    ``aliases`` maps a reference name to other spellings the right answer accepts for
    that person. Each reference name must be a person in this call.

    A speaker with no name in ``speaker-metadata.csv`` (no row for this call, or an empty
    ``speaker_name``) is a gap in the data, so by default it raises ``ValueError`` naming
    each such speaker id and its token count. Pass ``unnamed_speakers="placeholder"`` to
    name that speaker ``"Speaker <id>"`` instead. The scorer's placeholder rule then leaves
    that speaker's words out of the score, and the report's ``placeholder_rule`` counts show
    how many. Any other value raises ``ValueError``.
    """
    if unnamed_speakers not in UNNAMED_SPEAKER_MODES:
        raise ValueError(
            f"unnamed_speakers must be one of {list(UNNAMED_SPEAKER_MODES)}, "
            f"not {unnamed_speakers!r}"
        )
    resolved_id = (file_id or _file_id_from_path(nlp_path)).strip()
    if not resolved_id:
        raise ValueError("file_id is required")
    rows = _read_nlp(nlp_path)
    metadata = load_speaker_metadata(speaker_metadata_path).get(resolved_id, {})
    if unnamed_speakers == "error":
        unnamed = _unnamed_speakers(rows, metadata)
        if unnamed:
            listed = ", ".join(f"{sid} ({n} tokens)" for sid, n in unnamed.items())
            raise ValueError(
                f"{resolved_id}: no name in the speaker metadata for speaker {listed}. "
                'Fix the metadata, or pass unnamed_speakers="placeholder" to name them '
                '"Speaker <id>" (the scorer then leaves their words out of the score).'
            )

    def name_for(speaker_id: str) -> str:
        return metadata.get(speaker_id) or f"Speaker {speaker_id}"

    grouped = group_tokens(rows)
    if not grouped:
        raise ValueError(f"{nlp_path}: no usable tokens")
    turns = [{"speaker": name_for(turn["speaker"]), "text": turn["text"]} for turn in grouped]
    people: list[dict[str, str]] = []
    seen: set[str] = set()
    for turn in turns:
        if turn["speaker"] not in seen:
            seen.add(turn["speaker"])
            people.append({"name": turn["speaker"]})
    if aliases is not None:
        unknown = sorted(set(aliases) - seen)
        if unknown:
            raise ValueError(
                f"{resolved_id}: aliases given for names that are not in this call: {unknown}"
            )
        for person in people:
            extra = sorted({a for a in aliases.get(person["name"], ()) if a != person["name"]})
            if extra:
                person["aliases"] = extra
    return {"conversation_id": resolved_id, "people": people, "turns": turns}


def load_truth(
    nlp_path: str | Path,
    speaker_metadata_path: str | Path,
    *,
    file_id: str | None = None,
    aliases: Mapping[str, Iterable[str]] | None = None,
    unnamed_speakers: str = "error",
) -> dict[str, Any]:
    """Alias for :func:`build_truth` for symmetry with the scorer loaders."""
    return build_truth(
        nlp_path,
        speaker_metadata_path,
        file_id=file_id,
        aliases=aliases,
        unnamed_speakers=unnamed_speakers,
    )


def write_json(data: dict[str, Any], path: str | Path) -> None:
    """Write JSON deterministically (sorted keys, trailing newline)."""
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")
