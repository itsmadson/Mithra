VENV := .venv/bin

.PHONY: up down test coverage-probe migrate web-test e2e

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

# Seeds a finished job straight into the database so the browser run never
# depends on Mapillary, a token, or network reachability. The token below is a
# placeholder that satisfies config validation; no Mapillary call is made,
# because the worker is not part of this run.
PYPATH := services/api:services/worker:packages/ml
E2E_ENV := MAPILLARY_TOKEN='MLY|e2e|placeholder' \
           DATABASE_URL='postgresql+psycopg://bina:bina@localhost:5432/bina'

e2e:
	PYTHONPATH=$(PYPATH) $(E2E_ENV) $(VENV)/python tests/e2e/seed.py
	cd apps/web && NEXT_PUBLIC_API_URL=http://localhost:8010 npm run build
	pkill -f "uvicorn bina_api.main" 2>/dev/null || true
	pkill -f "next-server" 2>/dev/null || true
	PYTHONPATH=$(PYPATH) $(E2E_ENV) $(VENV)/uvicorn bina_api.main:app --port 8010 &
	cd apps/web && NEXT_PUBLIC_API_URL=http://localhost:8010 npm run start &
	@sleep 10
	cd tests/e2e && npx playwright test; status=$$?; \
	  pkill -f "uvicorn bina_api.main" 2>/dev/null || true; \
	  pkill -f "next-server" 2>/dev/null || true; \
	  exit $$status
