"""The walkthrough notebook's made-up call must keep showing every error label."""

import ast
import json
import re
import unittest
from pathlib import Path

import speaker_aware_eval.whos_who as whos_who
import speaker_aware_eval.whos_who.adapters as adapters
from speaker_aware_eval.whos_who import ERROR_LABELS, ScorerConfig, load_output, load_truth, score

FIXTURES = Path(__file__).parent / "fixtures" / "whos_who"
PUBLIC_NOTEBOOKS = sorted((Path(__file__).parents[1] / "notebooks").glob("*.ipynb"))


class EarningsCall(unittest.TestCase):
    def setUp(self):
        self.truth = load_truth(FIXTURES / "earnings_call_truth.json")
        self.output = load_output(FIXTURES / "earnings_call_output.json")

    def test_every_error_label_fires_when_partial_names_count_as_errors(self):
        report = score(self.truth, self.output, ScorerConfig(partial_is_correct=False))
        by_label = report["words"]["by_label"]
        for label in ERROR_LABELS:
            self.assertGreater(by_label[label], 0, label)

    def test_default_config_credits_the_partial_name(self):
        report = score(self.truth, self.output)
        self.assertEqual(report["words"]["by_label"]["partial"], 0)
        self.assertGreater(report["words"]["partial_words"], 0)
        self.assertEqual(report["coverage"]["share"], 1.0)


class PublicNotebooks(unittest.TestCase):
    """Source and saved outputs of public notebooks stay on made-up data."""

    # Local settings files must never be named in a public notebook.
    FORBIDDEN = (r"\.env",)

    def test_there_is_a_public_notebook(self):
        self.assertTrue(PUBLIC_NOTEBOOKS)

    def test_no_private_data_in_source_or_outputs(self):
        for path in PUBLIC_NOTEBOOKS:
            text = path.read_text(encoding="utf-8")
            for pattern in self.FORBIDDEN:
                self.assertIsNone(re.search(pattern, text), f"{path.name}: {pattern}")

    def test_notebooks_are_committed_with_outputs_and_no_absolute_paths(self):
        for path in PUBLIC_NOTEBOOKS:
            notebook = json.loads(path.read_text(encoding="utf-8"))
            code = [c for c in notebook["cells"] if c["cell_type"] == "code"]
            for cell in code:
                self.assertIsNotNone(
                    cell["execution_count"], f"{path.name}: a code cell was never executed"
                )
                if "print(" in "".join(cell["source"]):
                    self.assertTrue(cell["outputs"], f"{path.name}: a printing cell has no output")
            text = path.read_text(encoding="utf-8")
            self.assertIsNone(
                re.search(r"(/home/|/Users/|/workspace/|/tmp/|\b[A-Za-z]:\\\\)", text),
                f"{path.name}: an absolute local path",
            )


# The public API: the names in each module's __all__. Everything else in the package is private.
PUBLIC_MODULES = {
    "speaker_aware_eval.whos_who": set(whos_who.__all__),
    "speaker_aware_eval.whos_who.adapters": set(adapters.__all__),
}


def import_problems(source):
    """Imports in `source` that reach past the public API, or import difflib."""
    problems = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] == "difflib":
                    problems.append(f"import {alias.name}")
                elif alias.name.startswith("speaker_aware_eval") and (
                    alias.name not in PUBLIC_MODULES
                ):
                    problems.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module.split(".")[0] == "difflib":
                problems.append(f"from {module}")
                continue
            if not module.startswith("speaker_aware_eval"):
                continue
            if module not in PUBLIC_MODULES:
                problems.append(f"from {module}")
                continue
            for alias in node.names:
                if alias.name not in PUBLIC_MODULES[module]:
                    problems.append(f"from {module} import {alias.name}")
    return problems


class PublicNotebookImports(unittest.TestCase):
    """Public notebooks use only the public API, and show the scorer's own alignment."""

    def test_notebooks_import_only_the_public_api(self):
        for path in PUBLIC_NOTEBOOKS:
            notebook = json.loads(path.read_text(encoding="utf-8"))
            for cell in notebook["cells"]:
                if cell["cell_type"] == "code":
                    source = "".join(cell["source"])
                    self.assertEqual(import_problems(source), [], f"{path.name}:\n{source}")

    def test_the_check_catches_internal_imports(self):
        caught = (
            "from difflib import SequenceMatcher",
            "import difflib",
            "from speaker_aware_eval.whos_who.scoring import words",
            "from speaker_aware_eval.whos_who.names import Roster",
            "from speaker_aware_eval.whos_who.cli import main",
            "from speaker_aware_eval.whos_who import formats",
            "import speaker_aware_eval.whos_who.scoring",
        )
        for line in caught:
            self.assertTrue(import_problems(line), line)
        allowed = (
            "from speaker_aware_eval.whos_who import align, roster_for, ERROR_LABELS",
            "from speaker_aware_eval.whos_who.adapters import build_output, deepgram",
            "import json",
            "# The notebook no longer uses difflib.",
        )
        for line in allowed:
            self.assertEqual(import_problems(line), [], line)


if __name__ == "__main__":
    unittest.main()
