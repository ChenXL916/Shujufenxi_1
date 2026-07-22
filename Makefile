.PHONY: dev stop logs migrate seed sync-fixture sync-feishu test test-unit test-integration test-e2e lint typecheck format check build backup verify-production

PYTHON ?= python

dev stop logs migrate seed sync-fixture sync-feishu test test-unit test-integration test-e2e lint typecheck format check build backup verify-production:
	$(PYTHON) scripts/task_runner.py $@
