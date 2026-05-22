.PHONY: lint fix test test-cov check build bootstrap coverage-diff security ty eval eval-baseline eval-detail bless-contracts

check: lint ty test-cov

lint:
	@uv run ruff check src/ tests/

fix:
	@uv run ruff check --fix src/ tests/
	@uv run ruff format src/ tests/

ty:
	@uv run ty check src/

test:
	@uv run pytest tests/

test-cov:
	@uv run pytest tests/ --cov=a2web --cov-report=xml --cov-report=term-missing --cov-fail-under=85

coverage-diff:
	@uv run diff-cover coverage.xml --compare-branch=origin/main --fail-under=95

# Re-bless the golden API-contract files after an intentional envelope change.
# Review the resulting diff under tests/contracts/ before committing.
bless-contracts:
	@A2WEB_BLESS_CONTRACTS=1 uv run pytest tests/contracts/test_contracts.py -q -p no:cacheprovider

bootstrap:
	uv sync --all-extras
	@echo "Run 'make check' to verify."

build:
	uv build

dev:
	uv run a2web serve --transport=stdio

# Eval suite — runs WebFetchBaseline + A2WebDetail + A2WebExtract against the
# default corpus, judges with Sonnet, writes a dated report under eval/runs/.
# Requires `[llm]` extras (`uv sync --extra llm`) and ANTHROPIC_API_KEY.
eval:
	uv run python -m a2web.llm.eval

eval-baseline:
	uv run python -m a2web.llm.eval --mode baseline

eval-detail:
	uv run python -m a2web.llm.eval --mode detail
