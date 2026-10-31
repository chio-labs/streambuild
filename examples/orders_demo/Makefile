COMPOSE := docker compose -f docker/compose.yml

-include .env
export

.PHONY: start reset inject stop dev logs verify verify-warning

start:
	$(COMPOSE) up -d --build --wait
	sqt build --project-dir . --auto-approve

reset:
	$(COMPOSE) down --volumes --remove-orphans
	$(MAKE) start

inject:
	$(COMPOSE) run --rm --no-deps producer \
		python -u /app/producer/fake_orders_producer.py inject-future

stop:
	$(COMPOSE) down --remove-orphans

dev:
	sqt dev --project-dir .

logs:
	$(COMPOSE) logs --follow producer redpanda clickhouse

verify:
	sqt compile --project-dir .
	sqt test --project-dir .
	sqt audit --project-dir .
	python scripts/verify_demo.py

verify-warning:
	python scripts/verify_warning_recovery.py
