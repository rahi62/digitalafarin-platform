.PHONY: check zip

check:
	python -m compileall agent/digitalafarin_agent apps/api >/dev/null
	python -m json.tool apps/web/package.json >/dev/null
	@echo "Static checks passed"

zip:
	cd .. && zip -qr digitalafarin-platform.zip digitalafarin-platform -x '*/.venv/*' '*/node_modules/*' '*/.next/*'
