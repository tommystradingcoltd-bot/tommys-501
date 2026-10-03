.PHONY: install run test lint migrate seed helper-login docker-up docker-down backup restore

install:
	pip install -r requirements.txt
	playwright install chromium

run:            ## run locally with SQLite + mock data
	alembic upgrade head && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

test:
	APP_ENV=test pytest -q

lint:
	ruff check app tests

migrate:        ## create a migration after editing app/models.py
	alembic revision --autogenerate -m "$(m)" && alembic upgrade head

helper-login:   ## open the helper browser (headed) so you can log in to each marketplace once
	python -m scripts.helper_login

docker-up:
	docker compose up --build -d

docker-down:
	docker compose down

backup:         ## dump Postgres (docker) or copy SQLite
	@mkdir -p backups && ( docker compose exec -T db pg_dump -U dealfinder dealfinder > backups/dealfinder-$$(date +%F).sql 2>/dev/null || cp data/dealfinder.db backups/dealfinder-$$(date +%F).db ) && ls -1 backups | tail -1

restore:        ## make restore f=backups/dealfinder-YYYY-MM-DD.sql
	docker compose exec -T db psql -U dealfinder dealfinder < $(f)
