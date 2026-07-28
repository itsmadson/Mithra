VENV := .venv/bin

.PHONY: up down dev test coverage-probe migrate web-test e2e

dev:
	./scripts/dev.sh

up:
	docker compose up -d
	@until docker compose exec -T db pg_isready -U bina >/dev/null 2>&1; do sleep 1; done

down:
	docker compose down -v

test:
	$(VENV)/pytest tests -v

web-test:
	cd apps/web && npx vitest run

coverage-probe:
	$(VENV)/python scripts/check_coverage.py

migrate:
	cd services/api && PYTHONPATH=. ../../$(VENV)/alembic upgrade head

e2e:
	./scripts/e2e.sh
