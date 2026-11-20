"""Execute notebooks offline and fail on the first error.

Usage:
    python scripts/run_notebooks.py notebooks/01-score-a-call.ipynb          # check only
    python scripts/run_notebooks.py --save notebooks/01-score-a-call.ipynb   # re-save outputs
"""

from __future__ import annotations

import sys
from pathlib import Path

import nbformat
from nbclient import NotebookClient
from nbclient.exceptions import CellExecutionError


def main(args: list[str]) -> int:
    save = "--save" in args
    paths = [a for a in args if a != "--save"]
    if not paths:
        print("usage: run_notebooks.py [--save] NOTEBOOK [NOTEBOOK ...]", file=sys.stderr)
        return 2
    for path in paths:
        try:
            notebook = nbformat.read(path, as_version=4)
            client = NotebookClient(
                notebook,
                timeout=300,
                kernel_name="python3",
                resources={"metadata": {"path": str(Path(path).parent)}},
                record_timing=False,
            )
            client.execute()
            if save:
                nbformat.write(notebook, path)
        except CellExecutionError as exc:
            print(f"FAILED {path}\n{exc}", file=sys.stderr)
            return 1
        except Exception as exc:  # unreadable file, timeout, dead or missing kernel, write error
            print(f"FAILED {path}: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
        print(f"ok {path}" + (" (outputs saved)" if save else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
