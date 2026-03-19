SKILL_NAME := jetredline
VERSION := $(shell cat skills/jetredline/VERSION)
SKILL_ZIP := $(SKILL_NAME)-skill-$(VERSION).zip
PLUGIN_ZIP := $(SKILL_NAME)-plugin-$(VERSION).zip

.PHONY: package plugin clean install test

package: clean
	cd skills && zip -r ../$(SKILL_ZIP) jetredline/ \
		-x "jetredline/.venv/*" "jetredline/node_modules/*" \
		   "jetredline/package-lock.json" "jetredline/__pycache__/*"

plugin: clean
	zip -r $(PLUGIN_ZIP) .claude-plugin/ skills/ install.sh install.ps1 README.md \
		-x "skills/jetredline/.venv/*" "skills/jetredline/node_modules/*" \
		   "skills/jetredline/package-lock.json" "skills/jetredline/__pycache__/*"

clean:
	rm -f $(SKILL_NAME)-skill-*.zip $(SKILL_NAME)-plugin-*.zip

install:
	bash install.sh

test:
	@echo "Validating skill structure..."
	@test -f skills/jetredline/SKILL.md || (echo "FAIL: skills/jetredline/SKILL.md missing" && exit 1)
	@test -d skills/jetredline/references || (echo "FAIL: skills/jetredline/references/ missing" && exit 1)
	@test -f skills/jetredline/package.json || (echo "FAIL: skills/jetredline/package.json missing" && exit 1)
	@test -f .claude-plugin/plugin.json || (echo "FAIL: .claude-plugin/plugin.json missing" && exit 1)
	@test -f install.sh || (echo "FAIL: install.sh missing" && exit 1)
	@test -f install.ps1 || (echo "FAIL: install.ps1 missing" && exit 1)
	@test -f README.md || (echo "FAIL: README.md missing" && exit 1)
	@echo "All checks passed."
