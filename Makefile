.PHONY: lint fix test check build bootstrap coverage-diff security ty

check: lint ty test

lint:
	@uv run ruff check src/ tests/

fix:
	@uv run ruff check --fix src/ tests/
	@uv run ruff format src/ tests/

ty:
	@uv run ty check src/

test:
	@uv run pytest tests/

coverage-diff:
	@uv run diff-cover coverage.xml --compare-branch=origin/main --fail-under=95

bootstrap:
	uv sync --all-extras
	@echo "Run 'make check' to verify."

build:
	uv build

dev:
	uv run a2web serve --transport=stdio
