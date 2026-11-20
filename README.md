# speaker-aware-eval

**speaker-aware-eval**: a speaker-aware eval for AI output from multi-speaker conversations. Did the system get *who said what* right?

It scores a system's output against a human-checked right answer and reports, word
by word, who was credited with what. It does not care how the output was made.

> **Status:** version 0.1.0. The API may change before 1.0.

How the scorer was checked on real conversations, and what was not shown, is in
[How it was validated](docs/how-it-was-validated.md). What happened when three
transcription services were compared on the same calls, and why the first scores were
unfair, is in [Comparing three transcription services](docs/vendor-comparison.md).

## What it does today

- **Who's-who scorer** — lines the system's words up with the right answer and
  credits each word to the right or wrong person. It reports a headline score,
  how much of the right answer the score covers, per-person scores, and the kinds
  of mistake (named as another person, name not matched to one person in the call,
  no name, voices mixed between people, a second voice for the same person, swapped
  names, a partial name).
- **Pass bar** — the command exits 0 when the headline score meets the bar, 1 when
  it does not, and 2 on bad input. You can also set a minimum coverage
  (`--min-coverage`, off by default), so a high score on very few matched words
  does not pass.
- **Neutral JSON in, report out** — any source can be scored once a small adapter
  converts it to the input format.
- **Zero dependencies** — pure Python standard library.

## Quick start

```bash
pip install -e .
python -m speaker_aware_eval.whos_who TRUTH.json OUTPUT.json --report report.json
```

The right answer and the system output are JSON files:

```json
{
  "conversation_id": "call-001",
  "people": [{"name": "Dana Reyes", "aliases": ["Dana", "Agent"]}],
  "turns": [{"speaker": "Dana Reyes", "text": "Thanks for calling."}]
}
```

```json
{
  "conversation_id": "call-001",
  "turns": [{"voice": "SPEAKER_00", "speaker": "Dana Reyes", "text": "Thanks for calling."}]
}
```

See `speaker_aware_eval/whos_who/formats.py` for the full format and
`python -m speaker_aware_eval.whos_who --help` for the options.

## Limits

Read these before quoting a number from the scorer. The evidence behind the scorer,
and where it stops, is in [How it was validated](docs/how-it-was-validated.md).

- **Only matched words are scored.** Read the coverage next to the score. A high score on
  a small share of the right answer says little; `--min-coverage` turns that into a gate.
- **A voice that holds two people can still score 100%.** The score credits each word to
  the name the system gave, turn by turn. If every turn is named correctly, the score is
  100% even when one voice carries two people. The report still marks that voice as
  `merged` in `voice_map`, so check it next to the score.
- **Matching gets slow on repetitive text.** Time grows fast when a transcript repeats a
  few words over and over. On one laptop, 10,000 words took under half a second with
  2,000 different words and about 8 seconds with 20. Normal speech is in the fast range;
  a broken output that loops on a phrase is not. The scorer does not stop you, so check
  what you feed it.
- **Spelling is reviewed by people.** The scorer never guesses that "Brant" means
  "Brandt"; add accepted spellings as aliases.

## Walkthrough notebook

[`notebooks/01-score-a-call.ipynb`](notebooks/01-score-a-call.ipynb) scores a made-up
earnings call step by step, using only the public API. It runs offline in seconds and
is committed with its outputs, so it reads on GitHub without running.

```bash
pip install -e ".[notebooks]"
jupyter lab notebooks/01-score-a-call.ipynb
```

## Development

```bash
pip install -e ".[dev]"
make lint        # ruff check and format check
make test        # unit tests
make notebooks   # run the public notebooks offline
make ci          # all of the above
```

## License

[MIT](LICENSE)
