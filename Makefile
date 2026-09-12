PY := .venv/bin/python
RUFF := .venv/bin/ruff
SRC := lpcore lp lpdeck lpstudio main.py dev_spin.py gen_release_icon.py tests

.PHONY: help check lint test fix run deck shot gammaray studio

check: lint test          ## lint + smoke test (run before pushing)

lint:                     ## static checks: undefined names, dead imports
	$(RUFF) check --select F $(SRC)

test:                     ## render smoke + settings + state tests (headless)
	$(PY) tests/test_render.py
	$(PY) tests/test_state.py
	$(PY) tests/test_lyrics.py

fix:                      ## auto-fix what ruff can
	$(RUFF) check --select F --fix $(SRC)

run:                      ## launch the app
	$(PY) main.py

deck:                     ## launch lp-deck (the desktop QML player)
	$(PY) -m lpdeck

studio:                   ## launch lp-studio (the vinyl-style authoring tool)
	$(PY) -m lpstudio

shot:                     ## headless screenshot of lp-deck → /tmp/lpdeck.png (ARGS=...)
	$(PY) -m lpdeck.shot /tmp/lpdeck.png --play $(ARGS)
	@echo "wrote /tmp/lpdeck.png"

gammaray:                 ## inspect a running lp-deck live (needs gammaray installed)
	gammaray $(PY) -m lpdeck

help:                     ## list these targets
	@grep -hE '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-10s %s\n", $$1, $$2}'
