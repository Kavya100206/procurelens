PYTHON := $(shell if [ -f .venv/bin/python ]; then echo .venv/bin/python; elif which python3 >/dev/null 2>&1; then echo python3; else echo python; fi)

.PHONY: run test eval

# Run local services: starts mock vendor-risk API (port 8001) and Streamlit UI (port 8501)
run:
	$(PYTHON) run_local.py

# Run all deterministic tool and integration tests
test:
	$(PYTHON) -m unittest discover -s tests

# Comprehensive evaluation benchmark (Architecture A vs Architecture B on 20 cases)
# Pass FRESH=1 (e.g., `make eval FRESH=1`) to bypass disk cache and re-run all cases live
eval:
	$(PYTHON) evals/run_eval.py --architecture all $(if $(FRESH),--fresh,)
