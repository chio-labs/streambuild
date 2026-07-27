format:
	uv run ruff format .


lint:
	uv run ruff check --fix .


type:
	uv run ty check src tests scripts


test:
	uv run pytest tests/unit -q -n auto


test-all:
	uv run pytest tests/unit -q -n auto
	uv run pytest tests/integration -q -n 4
	uv run pytest tests/e2e -q -m "not performance" -n 4
	uv run pytest tests/e2e -q -m performance -k 3000 -n 4
	uv run pytest tests/e2e -q -m performance -k 10000 -n 4


check:
	uv run ruff format .
	uv run ruff check --fix .
	uv run ty check src tests scripts
	uv run fensu check
	uv run fensu skills --check


verify:
	uv run ruff format .
	uv run ruff check --fix .
	uv run ty check src tests scripts
	uv run fensu check
	uv run fensu skills --check
	uv run pytest tests/unit -q -n auto
	uv run pytest tests/integration -q -n 4
	uv run pytest tests/e2e -q -m "not performance" -n 4
	uv run pytest tests/e2e -q -m performance -k 3000 -n 4
	uv run pytest tests/e2e -q -m performance -k 10000 -n 4


check-ci:
	uv run ruff format --check .
	uv run ruff check .
	uv run ty check src tests scripts
	uv run fensu check
	uv run fensu skills --check


verify-ci:
	uv run ruff format --check .
	uv run ruff check .
	uv run ty check src tests scripts
	uv run fensu check
	uv run fensu skills --check
	uv run pytest tests/unit -q -n auto
	uv run pytest tests/integration -q -n 4
	uv run pytest tests/e2e -q -m "not performance" -n 4
	uv run pytest tests/e2e -q -m performance -k 3000 -n 4
	uv run pytest tests/e2e -q -m performance -k 10000 -n 4
