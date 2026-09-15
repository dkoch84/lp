PY := .venv/bin/python
RUFF := .venv/bin/ruff
SRC := lpcore lp lpdeck lpstudio main.py dev_spin.py gen_release_icon.py tests

.PHONY: help check lint test fix run deck shot shot-kiosk gammaray studio studio-shot prerender video release-assets

check: lint test          ## lint + tests (run before pushing)

lint:                     ## ruff (rules + rationale live in ruff.toml)
	$(RUFF) check $(SRC)

test:                     ## run the test suite (headless)
	$(PY) -m pytest tests/ -q

fix:                      ## auto-fix what ruff can
	$(RUFF) check --fix $(SRC)

run:                      ## launch the app
	$(PY) main.py

deck:                     ## launch lp-deck (the desktop QML player)
	$(PY) -m lpdeck

studio:                   ## launch lp-studio (the vinyl-style authoring tool)
	$(PY) -m lpstudio

studio-shot:              ## headless screenshot of lp-studio → /tmp/lpstudio.png (ARGS=...)
	$(PY) -m lpstudio.shot /tmp/lpstudio.png $(ARGS)

shot:                     ## headless screenshot of lp-deck → /tmp/lpdeck.png (ARGS=...)
	$(PY) -m lpdeck.shot /tmp/lpdeck.png --play $(ARGS)
	@echo "wrote /tmp/lpdeck.png"

prerender:                ## render missing vinyl style images (ONLY=name, FORCE=1 for all)
	$(PY) -m lpcore.vinyl.prerender $(foreach n,$(ONLY),--only $(n)) $(if $(FORCE),--force,)

shot-kiosk:               ## headless screenshot of the lp kiosk → /tmp/lp.png (ARGS=...)
	$(PY) -m lp.shot /tmp/lp.png $(ARGS)
	@echo "wrote /tmp/lp.png"

video:                    ## render an album as the kiosk plays it: ALBUM="/music/Artist/Album" OUT=x.mp4 (ARGS=...)
	$(PY) -m lp.video "$(ALBUM)" $(OUT) $(ARGS)

release-assets:           ## build what the Release workflow ships, into dist/ (TAG=name)
	$(PY) -m lp.release --tag $(TAG) --out dist

gammaray:                 ## inspect a running lp-deck live (needs gammaray installed)
	gammaray $(PY) -m lpdeck

help:                     ## list these targets
	@grep -hE '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-10s %s\n", $$1, $$2}'
