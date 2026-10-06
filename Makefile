PYTHON := $(shell if [ -f .venv/bin/python ]; then echo .venv/bin/python; elif which python3 >/dev/null 2>&1; then echo python3; else echo python; fi)

.PHONY: run test eval

# Run local services: starts mock vendor-risk API (port 8001) and Streamlit UI (port 8501)
run:
	$(PYTHON) run_local.py

# Run all deterministic tool and integration tests
test:
	$(PYTHON) -m unittest discover -s tests

# Evaluation suite placeholder
eval:
	@echo "available in Phase 6"
