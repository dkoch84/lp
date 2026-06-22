PY := .venv/bin/python
SRC := lpcore lp lpdeck main.py dev_spin.py gen_release_icon.py tests

.PHONY: check lint test fix run

check: lint test          ## lint + smoke test (run before pushing)

lint:                     ## static checks: undefined names, dead imports
	ruff check --select F $(SRC)

test:                     ## render smoke + settings tests (headless)
	$(PY) tests/test_render.py

fix:                      ## auto-fix what ruff can
	ruff check --select F --fix $(SRC)

run:                      ## launch the app
	$(PY) main.py
