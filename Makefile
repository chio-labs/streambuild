.PHONY: dist test-browser test-e2e test-integration ui-verify


format:
	uv run ruff format .


lint:
	uv run ruff check --fix .


type:
	uv run ty check src tests scripts


test:
	uv run pytest tests/unit -q -n auto


test-integration:
	uv run pytest tests/integration -q -n 4


test-e2e:
	uv run pytest tests/e2e -q -m "not performance and not browser" -n 2
	uv run pytest tests/e2e -q -m "performance and not browser" -k 3000 -n 2
	uv run pytest tests/e2e -q -m "performance and not browser" -k 10000 -n 2


test-all:
	$(MAKE) test
	$(MAKE) test-integration
	$(MAKE) test-e2e
	$(MAKE) test-browser


test-browser:
	uv run pytest tests/e2e -q -m browser -n 2 \
		--browser chromium --tracing retain-on-failure --video retain-on-failure \
		--screenshot only-on-failure --output test-results --durations=25


check:
	uv run ruff format .
	uv run ruff check --fix .
	uv run ty check src tests scripts
	uv run fensu check


verify:
	uv run ruff format .
	uv run ruff check --fix .
	uv run ty check src tests scripts
	uv run fensu check
	$(MAKE) ui-verify
	$(MAKE) test
	$(MAKE) test-integration
	$(MAKE) test-e2e
	$(MAKE) test-browser


ui-install:
	cd ui && npm ci


ui-build:
	cd ui && npm run build
	rm -rf src/streambuild/dev_server/static
	cp -r ui/build src/streambuild/dev_server/static


ui-verify:
	cd ui && npm run check
	cd ui && npm run verify:lanes
	cd ui && npm run verify:lineage-activity
	cd ui && npm run verify:run-timeline


dist:
	$(MAKE) ui-install
	$(MAKE) ui-build
	rm -f dist/*.whl dist/*.tar.gz
	uv build
	uv run python scripts/verify_wheel_assets.py


ui-dev:
	cd ui && npm run dev


check-ci:
	uv run ruff format --check .
	uv run ruff check .
	uv run ty check src tests scripts
	uv run fensu check


verify-ci:
	uv run ruff format --check .
	uv run ruff check .
	uv run ty check src tests scripts
	uv run fensu check
	$(MAKE) ui-verify
	$(MAKE) test
	$(MAKE) test-integration
	$(MAKE) test-e2e
	$(MAKE) test-browser
