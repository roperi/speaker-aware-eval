# How it was validated

**In short:** the who's-who scorer was run on 20 real earnings calls and 9 real
interview episodes. A person then checked its error labels by hand, and the first
check failed. The fixes that followed passed the second check. This page says what
was checked, what changed because of it, what was tried and dropped, how the code
was built, and what has not been shown. It gives counts and method. The scores from
comparing three transcription services are on [their own page](vendor-comparison.md).

## Checked on real conversations

The scorer was run on two sources of real speaker-labelled conversation:

- **20 calls from the public Earnings-21 dataset** ([Rev's speech-datasets
  repository](https://github.com/revdotcom/speech-datasets)), about 21.3 hours of
  audio. The audio was used privately for the checks and is not redistributed here.
- **9 corrected episodes from a private pipeline.** These were an easy test: few
  guests carry real names in the corrected transcripts.

Running on real data changed the scorer in four ways:

- **Placeholder speakers are left out of the score.** A turn labelled "Speaker 3"
  names nobody, so it can't be right or wrong about who spoke. The report shows
  coverage next to the score, so you can see how much of the call was scored.
- **Roles count as identities.** "Operator" is a person-like label that a transcript
  can get right or wrong, so it is scored.
- **Accepted spellings come from a reviewed alias list.** A person decides that
  "Brant" is an accepted spelling of "Brandt", and the list records it.
- **There is no near-match name guessing.** A guess would turn spelling into
  accuracy, and nobody could audit it.

## Labels checked by hand

The scorer labels each kind of mistake: named as another person, name not matched
to one person in the call, no name, voices mixed together, a second voice for the
same person, swapped names, a partial name. A label is only useful if it describes
what actually went wrong in that turn.

The owner judged those labels against the transcripts by hand, with a pass mark of
18 correct out of 20 set before looking at any result:

- **First check:** 10 labels from each source. 16 of 20 were right, so it failed.
- **Fixes:** the scorer now lists every other applicable mistake beside a turn's
  main label, and reports the main voice of a person split across voices. The
  sheet used for the check also explains split and merged voices in plain words.
- **Repeat check:** a fresh sheet of 20 labels. All 20 were right, which passes.

## What comparing transcription services taught

The same 20 calls went through three transcription services, which are not named
here. The scores and the method are on [the comparison page](vendor-comparison.md).
Every service used the same naming step (the step that turns anonymous voices
into names) and the same scorer settings.

- **The first comparison was unfair.** The alias list had been reviewed against one
  service's output only. That service got credit for its own spellings and the
  others did not, so spelling looked like accuracy.
- **The fix was one shared list.** The owner reviewed 140 candidate spellings (110
  accepted, 30 rejected). The alias list grew from 99 to 209 entries, the same for
  all three services, and the rescore removed most of the gap.
- **Per-call spread is large.** An average hides calls where one service did much
  worse than another, so read coverage and per-call results beside any average.

This page gives counts and method only; the scores for the comparison are on
[the comparison page](vendor-comparison.md).

## Tried and stopped

A second capability was planned: checking whether a summary credits the right
person. It was assessed on real data and stopped:

- In a sample of 34 claims about people from 14 summaries, only 8 were quotes or
  close paraphrases. A deterministic check can't decide the rest.
- That check flagged correct claims as wrong.
- No real misattribution was found in those summaries.
- A summary mostly credits the wrong person when the transcript's speaker labels
  are already wrong, and this scorer already catches that one step earlier.
- A model-only judge was ruled out as the thing that decides pass or fail.

## How it was built

- **Spec-driven work items.** Each change had a scope, a specification, a plan, a
  task list, a validation record and a review record, written before and during the
  work.
- **AI coding agents wrote the code and the records.** They worked in
  spec-driven sessions. The owner set the direction, approved every plan, judged
  the labels by hand, read the walkthrough notebooks, and merged every change.
- **Two reviews per change.** A review in a fresh session before the pull request,
  and an automated review of the pull request after.
- **Unchanged scores.** When the scorer's word-alignment code was reorganised to
  expose a public API, all 120 real reports came out byte-identical to before.
- **One public commit.** The code is developed in a private source repository that
  holds the licensed data and the working records. A fail-closed exporter copies the
  public files into a fresh history, after scanning them for private names, scores
  and paths. That is why this repository starts with a single commit and doesn't
  show how the work unfolded.

## Limits

- **One source for the harder test.** Twenty earnings calls, with one naming prompt
  and model. The private episodes were an easy test.
- **The alias list was reviewed for those calls.** Other calls would need their own
  review.
- **The thresholds are reasoned defaults.** They were not calibrated on data.
- **No evidence yet of use by others.**

See the [README's limits](../README.md#limits) before quoting a number from the
scorer, and the [walkthrough notebook](../notebooks/01-score-a-call.ipynb) for the
scorer working on a made-up call.
