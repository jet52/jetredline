SKILL_NAME := jetredline
VERSION := $(shell cat skills/jetredline/VERSION)
SKILL_ZIP := $(SKILL_NAME)-skill-$(VERSION).zip
JETCITE_SRC := ../jetcite/src/jetcite
JETCITE_DEST := skills/jetredline/lib/jetcite
SPLITMARKS_SRC := ../splitmarks/splitmarks.py
SPLITMARKS_DEST := skills/jetredline/splitmarks.py
TEXTQUALITY_SRC := ../splitmarks/textquality.py
TEXTQUALITY_DEST := skills/jetredline/textquality.py
CITESTYLE_SRC := ../jetcite/reference/nd-citation-style.md
CITESTYLE_DEST := skills/jetredline/references/nd-citation-style.md
NDRULES_DB := $(HOME)/code/ndlaw-mcp/rules.db
NDRULES_DEST := skills/jetredline/references/nd-appellate-rules.md

PLUGIN_ZIP := $(SKILL_NAME)-plugin-$(VERSION).zip
WEB_ZIP := $(SKILL_NAME)-web-$(VERSION).zip

.PHONY: package package-plugin package-web package-all clean install test test-structure test-unit release check-assets vendor-jetcite vendor-splitmarks vendor-textquality vendor-citestyle vendor-ndrules drift-check version-check

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
release: version-check package-all
	@VERSION=$$(cat skills/jetredline/VERSION) && \
	git tag -a "v$$VERSION" -m "Release v$$VERSION" && \
	git push origin main && \
	git push origin "v$$VERSION" && \
	gh release create "v$$VERSION" $(SKILL_ZIP) $(PLUGIN_ZIP) $(WEB_ZIP) --title "v$$VERSION" --generate-notes && \
	$(MAKE) --no-print-directory check-assets TAG="v$$VERSION" ASSETS="$(SKILL_ZIP) $(PLUGIN_ZIP) $(WEB_ZIP)" && \
	echo "Released v$$VERSION"

# `gh release create` exits 0 after silently skipping an asset: v4.19.1 was
# handed all three zips, attached only the plugin and web ones, and reported
# success — so the release announced itself complete while missing the
# standalone skill zip that manual installers download. Nothing in the
# toolchain caught it; it was found by eye. This asserts every expected asset
# actually landed, retries once, then fails hard.
check-assets:
	@test -n "$(TAG)" || { echo "check-assets: TAG not set"; exit 1; }
	@for f in $(ASSETS); do \
	  if ! gh release view "$(TAG)" --json assets --jq '.assets[].name' | grep -qx "$$f"; then \
	    echo "MISSING: $$f did not attach to $(TAG); retrying upload"; \
	    gh release upload "$(TAG)" "$$f" --clobber || true; \
	  fi; \
	done
	@missing=0; \
	for f in $(ASSETS); do \
	  gh release view "$(TAG)" --json assets --jq '.assets[].name' | grep -qx "$$f" || \
	    { echo "FAIL: $$f is still not attached to $(TAG)"; missing=1; }; \
	done; \
	[ $$missing -eq 0 ] || exit 1; \
	echo "assets verified on $(TAG): $(ASSETS)"

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

# Depends on vendor-textquality because splitmarks imports textquality inside a
# try/except: vendoring the script without the module leaves --check-text
# silently back on the old density-only behaviour, which is the exact failure
# this pairing exists to prevent. The two always move together.
vendor-splitmarks: vendor-textquality
	@test -f $(SPLITMARKS_SRC) || (echo "FAIL: splitmarks source not found at $(SPLITMARKS_SRC)" && exit 1)
	cp $(SPLITMARKS_SRC) $(SPLITMARKS_DEST)
	@echo "Vendored splitmarks from $(SPLITMARKS_SRC)"

# Text-layer quality scorer that splitmarks --check-text consults to tell a
# corrupt text layer (dense but garbage) from a missing one. Authored here
# originally; canonical copy now lives in the splitmarks repo beside the script
# that imports it, so jetmemo and jetrehearing get the same module rather than
# vendoring splitmarks 2.2.0 and silently falling back to 2.1.0 behaviour. It
# must land in the same directory as splitmarks.py for that import to resolve.
vendor-textquality:
	@test -f $(TEXTQUALITY_SRC) || (echo "FAIL: textquality source not found at $(TEXTQUALITY_SRC)" && exit 1)
	cp $(TEXTQUALITY_SRC) $(TEXTQUALITY_DEST)
	@echo "Vendored textquality from $(TEXTQUALITY_SRC)"

# The ND Supreme Court's Redbook supplement. Canonical copy lives in the jetcite
# repo so jetmemo, jetredline, and jetrehearing cite one identical rule set.
vendor-citestyle:
	@test -f $(CITESTYLE_SRC) || (echo "FAIL: citation-style source not found at $(CITESTYLE_SRC)" && exit 1)
	cp $(CITESTYLE_SRC) $(CITESTYLE_DEST)
	@echo "Vendored nd-citation-style.md from $(CITESTYLE_SRC)"

# Fail if the vendored splitmarks copy has drifted from its canonical source.
# Tolerant of canonical being absent (e.g. on an install-only machine).
# The appellate-rules reference. Not a vendored copy of a file: the rule text
# is generated from the ndlaw corpus, because the hand-maintained version
# drifted into misstating four Rule 4 subdivisions at once. The preamble and
# the quick-reference notes outside the generated markers are preserved.
vendor-ndrules:
	python3 skills/jetredline/nd_rules_export.py

drift-check:
	@if [ -f $(SPLITMARKS_SRC) ]; then \
	  cmp -s $(SPLITMARKS_SRC) $(SPLITMARKS_DEST) || { echo "DRIFT: $(SPLITMARKS_DEST) differs from canonical $(SPLITMARKS_SRC) — run 'make vendor-splitmarks'"; exit 1; }; \
	  echo "splitmarks: in sync with canonical."; \
	else \
	  echo "splitmarks: canonical repo not present ($(SPLITMARKS_SRC)); skipping drift check."; \
	fi
	@if [ -f $(TEXTQUALITY_SRC) ]; then \
	  cmp -s $(TEXTQUALITY_SRC) $(TEXTQUALITY_DEST) || { echo "DRIFT: $(TEXTQUALITY_DEST) differs from canonical $(TEXTQUALITY_SRC) — run 'make vendor-textquality'"; exit 1; }; \
	  echo "textquality: in sync with canonical."; \
	else \
	  echo "textquality: canonical repo not present ($(TEXTQUALITY_SRC)); skipping drift check."; \
	fi
	@if [ -f $(CITESTYLE_SRC) ]; then \
	  cmp -s $(CITESTYLE_SRC) $(CITESTYLE_DEST) || { echo "DRIFT: $(CITESTYLE_DEST) differs from canonical $(CITESTYLE_SRC) — run 'make vendor-citestyle'"; exit 1; }; \
	  echo "nd-citation-style: in sync with canonical."; \
	else \
	  echo "nd-citation-style: canonical repo not present ($(CITESTYLE_SRC)); skipping drift check."; \
	fi
	@if [ -f "$(NDRULES_DB)" ] || [ -n "$$NDLAW_URL" ]; then \
	  python3 skills/jetredline/nd_rules_export.py --check; \
	else \
	  echo "nd-appellate-rules: ndlaw corpus not present ($(NDRULES_DB)); skipping drift check."; \
	fi

# The version lives in three places that must agree: VERSION (canonical, drives
# the zip names and check_update.py), the plugin manifest, and the SKILL.md
# frontmatter the model reads. v4.9.0 shipped with only VERSION bumped; this
# target makes that failure loud instead of silent.
version-check:
	@V=$$(cat skills/jetredline/VERSION) && \
	PV=$$(sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' .claude-plugin/plugin.json | head -1) && \
	SV=$$(sed -n 's/^version:[[:space:]]*//p' skills/jetredline/SKILL.md | head -1) && \
	if [ "$$V" != "$$PV" ] || [ "$$V" != "$$SV" ]; then \
	  echo "VERSION DRIFT: VERSION=$$V plugin.json=$$PV SKILL.md=$$SV"; exit 1; \
	fi; \
	echo "version: $$V consistent across VERSION, plugin.json, SKILL.md."

test: test-structure test-unit

test-structure: drift-check version-check
	@echo "Validating skill structure..."
	@test -f skills/jetredline/SKILL.md || (echo "FAIL: skills/jetredline/SKILL.md missing" && exit 1)
	@test -d skills/jetredline/references || (echo "FAIL: skills/jetredline/references/ missing" && exit 1)
	@test -f skills/jetredline/package.json || (echo "FAIL: skills/jetredline/package.json missing" && exit 1)
	@test -d skills/jetredline/lib/jetcite || (echo "FAIL: skills/jetredline/lib/jetcite/ missing — run 'make vendor-jetcite'" && exit 1)
	@test -f skills/jetredline/splitmarks.py || (echo "FAIL: skills/jetredline/splitmarks.py missing — run 'make vendor-splitmarks'" && exit 1)
	@test -f skills/jetredline/textquality.py || (echo "FAIL: skills/jetredline/textquality.py missing — run 'make vendor-textquality'" && exit 1)
	@test -f skills/jetredline/nd_rules_export.py || (echo "FAIL: skills/jetredline/nd_rules_export.py missing" && exit 1)
	@test -f install.sh || (echo "FAIL: install.sh missing" && exit 1)
	@test -f install.ps1 || (echo "FAIL: install.ps1 missing" && exit 1)
	@test -f README.md || (echo "FAIL: README.md missing" && exit 1)
	@echo "All structure checks passed."

test-unit:
	@echo "Running unit tests..."
	skills/jetredline/.venv/bin/python3 -m pytest tests/ -v
