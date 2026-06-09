SKILL_NAME := jetredline
VERSION := $(shell cat skills/jetredline/VERSION)
SKILL_ZIP := $(SKILL_NAME)-skill-$(VERSION).zip
JETCITE_SRC := ../jetcite/src/jetcite
JETCITE_DEST := skills/jetredline/lib/jetcite
SPLITMARKS_SRC := ../splitmarks/splitmarks.py
SPLITMARKS_DEST := skills/jetredline/splitmarks.py

PLUGIN_ZIP := $(SKILL_NAME)-plugin-$(VERSION).zip
WEB_ZIP := $(SKILL_NAME)-web-$(VERSION).zip

.PHONY: package package-plugin package-web package-all clean install test test-structure test-unit release vendor-jetcite vendor-splitmarks drift-check

# Public package targets clean first (so zip -r never updates a stale archive),
# then delegate to a build-* recipe. package-all cleans once and builds all three
# without the per-target clean clobbering siblings.
package: clean build-skill
package-plugin: clean build-plugin
package-web: clean build-web
package-all: clean build-skill build-plugin build-web

# Standalone skill zip: jetredline/ at the archive root. For manual drops into
# ~/.claude/skills/ — NOT a plugin (no manifest).
build-skill:
	cd skills && zip -r ../$(SKILL_ZIP) jetredline/ \
		-x "jetredline/.venv/*" "jetredline/node_modules/*" \
		   "jetredline/package-lock.json" "*/__pycache__/*"

# Plugin archive for Cowork/marketplace upload: manifest at root + the skill tree
# it references via plugin.json's "skills": "./skills/jetredline".
build-plugin:
	zip -r $(PLUGIN_ZIP) .claude-plugin/plugin.json skills/jetredline/ \
		-x "skills/jetredline/.venv/*" "skills/jetredline/node_modules/*" \
		   "skills/jetredline/package-lock.json" "*/__pycache__/*"

# Web / Projects bundle: model-facing content only. The Python scripts are inert
# without Bash, so ship just SKILL.md + references + VERSION as uploadable knowledge.
build-web:
	zip -r $(WEB_ZIP) \
		skills/jetredline/SKILL.md \
		skills/jetredline/references/ \
		skills/jetredline/VERSION \
		-x "*/__pycache__/*"

# NOTE: jet-hub installs by git clone of this repo's default branch, not from any
# zip — so a release must push main. The zips are attached for direct uploads
# (Cowork plugin upload, Projects web bundle, manual skill drop).
release: package-all
	@VERSION=$$(cat skills/jetredline/VERSION) && \
	git tag -a "v$$VERSION" -m "Release v$$VERSION" && \
	git push origin main && \
	git push origin "v$$VERSION" && \
	gh release create "v$$VERSION" $(SKILL_ZIP) $(PLUGIN_ZIP) $(WEB_ZIP) --title "v$$VERSION" --generate-notes && \
	echo "Released v$$VERSION"

.PHONY: build-skill build-plugin build-web

clean:
	rm -f $(SKILL_NAME)-skill-*.zip $(SKILL_NAME)-plugin-*.zip $(SKILL_NAME)-web-*.zip

install:
	bash install.sh

vendor-jetcite:
	@test -d $(JETCITE_SRC) || (echo "FAIL: jetcite source not found at $(JETCITE_SRC)" && exit 1)
	rm -rf $(JETCITE_DEST)
	mkdir -p skills/jetredline/lib
	cp -r $(JETCITE_SRC) $(JETCITE_DEST)
	find $(JETCITE_DEST) -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@echo "Vendored jetcite from $(JETCITE_SRC)"

vendor-splitmarks:
	@test -f $(SPLITMARKS_SRC) || (echo "FAIL: splitmarks source not found at $(SPLITMARKS_SRC)" && exit 1)
	cp $(SPLITMARKS_SRC) $(SPLITMARKS_DEST)
	@echo "Vendored splitmarks from $(SPLITMARKS_SRC)"

# Fail if the vendored splitmarks copy has drifted from its canonical source.
# Tolerant of canonical being absent (e.g. on an install-only machine).
drift-check:
	@if [ -f $(SPLITMARKS_SRC) ]; then \
	  cmp -s $(SPLITMARKS_SRC) $(SPLITMARKS_DEST) || { echo "DRIFT: $(SPLITMARKS_DEST) differs from canonical $(SPLITMARKS_SRC) — run 'make vendor-splitmarks'"; exit 1; }; \
	  echo "splitmarks: in sync with canonical."; \
	else \
	  echo "splitmarks: canonical repo not present ($(SPLITMARKS_SRC)); skipping drift check."; \
	fi

test: test-structure test-unit

test-structure: drift-check
	@echo "Validating skill structure..."
	@test -f skills/jetredline/SKILL.md || (echo "FAIL: skills/jetredline/SKILL.md missing" && exit 1)
	@test -d skills/jetredline/references || (echo "FAIL: skills/jetredline/references/ missing" && exit 1)
	@test -f skills/jetredline/package.json || (echo "FAIL: skills/jetredline/package.json missing" && exit 1)
	@test -d skills/jetredline/lib/jetcite || (echo "FAIL: skills/jetredline/lib/jetcite/ missing — run 'make vendor-jetcite'" && exit 1)
	@test -f install.sh || (echo "FAIL: install.sh missing" && exit 1)
	@test -f install.ps1 || (echo "FAIL: install.ps1 missing" && exit 1)
	@test -f README.md || (echo "FAIL: README.md missing" && exit 1)
	@echo "All structure checks passed."

test-unit:
	@echo "Running unit tests..."
	skills/jetredline/.venv/bin/python3 -m pytest tests/ -v
