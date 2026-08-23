COMPOSE := docker compose -f docker/compose.yml

-include .env
export

.PHONY: start reset inject stop dev logs verify verify-warning

start:
	$(COMPOSE) up -d --build --wait
	stb build --project-dir . --auto-approve

reset:
	$(COMPOSE) down --volumes --remove-orphans
	$(MAKE) start

inject:
	$(COMPOSE) run --rm --no-deps producer \
		python -u /app/producer/fake_orders_producer.py inject-future

stop:
	$(COMPOSE) down --remove-orphans

dev:
	stb dev --project-dir .

logs:
	$(COMPOSE) logs --follow producer redpanda clickhouse

verify:
	stb compile --project-dir .
	stb test --project-dir .
	stb audit --project-dir .
	python scripts/verify_demo.py

verify-warning:
	python scripts/verify_warning_recovery.py
