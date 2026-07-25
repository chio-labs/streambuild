format:
	uv run ruff format .


lint:
	uv run ruff check --fix .


type:
	uv run ty check src tests


test:
	uv run pytest tests/unit -q -n auto


test-all:
	uv run pytest tests/unit -q -n auto
	uv run pytest tests/integration -q -n 4
	uv run pytest tests/e2e -q -n 3


check-test-conventions:
	uv run check-test-conventions tests


check-structure-conventions:
	uv run check-structure-conventions src/streambuild scripts


check-type-annotation-conventions:
	uv run check-type-annotation-conventions src tests


check:
	uv run ruff format .
	uv run ruff check --fix .
	uv run ty check src tests
	uv run check-test-conventions tests
	uv run check-structure-conventions src/streambuild scripts
	uv run check-type-annotation-conventions src tests


verify:
	uv run ruff format .
	uv run ruff check --fix .
	uv run ty check src tests
	uv run pytest tests/unit -q -n auto
	uv run pytest tests/integration -q -n 4
	uv run pytest tests/e2e -q -n 3
	uv run check-test-conventions tests
	uv run check-structure-conventions src/streambuild scripts
	uv run check-type-annotation-conventions src tests


check-ci:
	uv run ruff format --check .
	uv run ruff check .
	uv run ty check src tests
	uv run check-test-conventions tests
	uv run check-structure-conventions src/streambuild scripts
	uv run check-type-annotation-conventions src tests


verify-ci:
	uv run ruff format --check .
	uv run ruff check .
	uv run ty check src tests
	uv run pytest tests/unit -q -n auto
	uv run pytest tests/integration -q -n 4
	uv run pytest tests/e2e -q -n 3
	uv run check-test-conventions tests
	uv run check-structure-conventions src/streambuild scripts
	uv run check-type-annotation-conventions src tests
