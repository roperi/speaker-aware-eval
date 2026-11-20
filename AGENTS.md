# AGENTS.md

Repository map for AI coding agents.

## Repo map

```
speaker-aware-eval/
├── README.md                  what it is, quick start, development
├── AGENTS.md                  this file
├── LICENSE                    MIT
├── CHANGELOG.md               changes by version
├── speaker_aware_eval/        the Python package (standard library only)
│   └── whos_who/              who's-who scorer: JSON in, report and pass/fail gate out
│       └── adapters/          converters from other output formats
├── tests/                     unit tests and made-up fixtures
├── notebooks/                 walkthrough notebook, committed with its outputs
├── scripts/run_notebooks.py   runs the notebooks offline (used by `make notebooks`)
├── Makefile, pyproject.toml   build, test, lint
└── .github/workflows/ci.yml   lint, tests and notebooks on Python 3.11 and 3.12
```

## Working rules

- The package stays standard-library only (`dependencies = []`).
- Examples and fixtures use neutral, made-up names and data only.
- Run `make lint` and `make test` before proposing changes. After changing the scorer
  or a notebook, run `make notebooks` and re-save the notebook's outputs with
  `python scripts/run_notebooks.py --save notebooks/01-score-a-call.ipynb`.
- The public API is the names in each module's `__all__`. It may change before 1.0.
