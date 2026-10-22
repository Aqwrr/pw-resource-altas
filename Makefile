PYTHON ?= python
TASK = $(PYTHON) tools/project.py

.PHONY: help deps assets run lint format test build package release publish clean
.DEFAULT_GOAL := help

help:
	@$(TASK) help
deps:
	$(TASK) deps
assets:
	$(TASK) assets
run:
	$(TASK) run
lint:
	$(TASK) lint
format:
	$(TASK) format
test:
	$(TASK) test
build:
	$(TASK) build
package:
	$(TASK) package
release:
	$(TASK) release
publish:
	$(TASK) publish
clean:
	$(TASK) clean
