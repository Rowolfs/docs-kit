PYTHON ?= .venv/bin/python

.PHONY: build demo test lint-yaml
build:
	$(PYTHON) scripts/build_site.py --project-dir . --output-dir build/site --site-url https://rowolfs.github.io/docs-kit/

demo:
	$(PYTHON) scripts/build_site.py --project-dir demo --output-dir build/demo/docs-kit --site-url http://127.0.0.1:8766/docs-kit/

test:
	$(PYTHON) -m unittest discover -s tests -v

lint-yaml:
	$(PYTHON) -m yamllint .github/workflows .yamllint.yml
