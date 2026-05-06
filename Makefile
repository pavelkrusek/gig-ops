.PHONY: ui lint typecheck typecheck-pyright test test-full check

lint:
	uv run ruff check .

typecheck: typecheck-pyright

typecheck-pyright:
	uv run pyright

test:
	uv run pytest -m "not slow"

test-full:
	uv run pytest

check: lint typecheck test
