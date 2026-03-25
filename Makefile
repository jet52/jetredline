SKILL_NAME := jetredline
VERSION := $(shell cat skills/jetredline/VERSION)
SKILL_ZIP := $(SKILL_NAME)-skill-$(VERSION).zip
JETCITE_SRC := ../jetcite/src/jetcite
JETCITE_DEST := skills/jetredline/lib/jetcite

.PHONY: package clean install test test-structure test-unit vendor-jetcite

package: clean
	cd skills && zip -r ../$(SKILL_ZIP) jetredline/ \
		-x "jetredline/.venv/*" "jetredline/node_modules/*" \
		   "jetredline/package-lock.json" "*/__pycache__/*"

clean:
	rm -f $(SKILL_NAME)-skill-*.zip

install:
	bash install.sh

vendor-jetcite:
	@test -d $(JETCITE_SRC) || (echo "FAIL: jetcite source not found at $(JETCITE_SRC)" && exit 1)
	rm -rf $(JETCITE_DEST)
	mkdir -p skills/jetredline/lib
	cp -r $(JETCITE_SRC) $(JETCITE_DEST)
	find $(JETCITE_DEST) -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@echo "Vendored jetcite from $(JETCITE_SRC)"

test: test-structure test-unit

test-structure:
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
