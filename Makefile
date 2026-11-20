# The project's virtual environment when there is one (it has the notebook tools), else python3.
# Override with PYTHON=... on the command line or in the environment.
PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)

.PHONY: help ci test lint notebooks clean

help: ## Show available commands
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z0-9_.-]+:.*##/ {printf "\033[36m%-12s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

ci: lint test notebooks ## Run everything CI runs

test: ## Run all unit tests.
	$(PYTHON) -m unittest discover -s tests -v

lint: ## Run ruff linter and format checker.
	ruff check .
	ruff format --check .

notebooks: ## Execute the public notebooks offline; fail on any error (needs the dev extra).
	$(PYTHON) scripts/run_notebooks.py notebooks/*.ipynb

clean: ## Clean up generated files.
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
