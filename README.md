# speaker-aware-eval

**speaker-aware-eval**: a speaker-aware eval for AI output from multi-speaker conversations. Did the system get *who said what* right?

It scores a system's output against a human-checked right answer and reports, word
by word, who was credited with what. It does not care how the output was made.

> **Status:** version 0.2.0. The API may change before 1.0.

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
  converts it to the input format, and a right answer can be typed as plain text
  (see [Making a reference](#making-a-reference)).
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

## Making a reference

The right answer is a JSON file, but you do not have to write JSON. Type it as plain text,
one turn per line as `Name: what they said`:

```text
Dana Reyes: Thanks for calling. How can I help?
Sam Ortiz: Hi, my order has not arrived.
Dana Reyes: Let me check. It should be there by 10:30.
```

Then convert it:

```bash
python -m speaker_aware_eval.whos_who.reference call.txt --id call-001 \
    --alias "Dana Reyes=Dana,Agent" > truth.json
```

- The speaker is the text before the first colon that is followed by a space, so a colon
  inside the words ("by 10:30") is fine. A name can be up to 60 characters.
- Blank lines are ignored. A line with no speaker stops the command with an error that
  names the line (exit code 2). A turn that runs over several lines must be joined by hand.
- `--alias "Name=alias1,alias2"` adds accepted spellings for one person. Repeat it for more
  people. A name that does not speak in the file is an error, which catches typos.
- `--id` defaults to the file name without its extension. The system output must carry the
  same id.
- From Python: `reference_from_text(text, "call-001", {"Dana Reyes": ["Dana"]})` and
  `reference_from_file(path)` return the same data as a dict.

## Using it in CI

The command exits 0 when the gate passes, 1 when it fails and 2 on bad input. Set the bar
with `--min-score` and, so that a high score on few matched words cannot pass, a coverage
bar with `--min-coverage`. Two patterns fit a CI job:

1. **Re-score stored outputs.** Keep the right answer and a saved system output in the
   repository and score them on every change. It is free and fast. It catches a changed
   scorer, threshold or alias list. It does **not** catch a changed model or prompt,
   because the stored output does not change.
2. **Re-run the system on a fixed sample.** Run the system on the same few recordings each
   time, then score the fresh output. It catches changes to the model or the prompt. It
   costs API calls on every run, and scores move a little between runs, so set the bar with
   a margin below your usual score. Whether that cost is worth it is your choice.

A minimal job for either pattern, after the output has been produced or restored:

```yaml
- run: pip install -e .
- run: >
    python -m speaker_aware_eval.whos_who truth.json output.json
    --min-score 0.9 --min-coverage 0.8
```

The step fails the job on exit code 1 or 2.

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
