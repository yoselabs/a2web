.PHONY: lint fix test test-cov check build bootstrap coverage-diff security ty bench eval eval-baseline eval-detail bless-contracts handler-probe

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

# Output benchmark — runs WebFetchBaseline + A2WebDetail + A2WebExtract
# against eval/corpus.yaml, scores four axes (quality, token cost, clarity,
# data-contract conformance), writes a dated report under eval/runs/.
# Prefers the Claude Code OS session (no ANTHROPIC_API_KEY needed);
# `A2WEB_BENCH_PROVIDER` forces the provider.
bench:
	uv run python -m a2web.llm_eval

# `make eval` is kept as an alias of `make bench`.
eval:
	uv run python -m a2web.llm_eval

eval-baseline:
	uv run python -m a2web.llm_eval --mode baseline

eval-detail:
	uv run python -m a2web.llm_eval --mode detail

# Live-network handler probe — exercises every registered handler against
# a real representative URL. Catches transport-layer regressions (e.g.,
# the linux.do Cloudflare-block) that monkeypatched unit tests miss.
# NOT wired into `make check` — runs deliberately, hits the open internet.
handler-probe:
	uv run python -m a2web.handler_probe
