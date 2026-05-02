.PHONY: help setup-env install test backfill-garmin backfill-strava brief smoke-test deploy-bot deploy-mcp

help:
	@echo "Targets:"
	@echo "  setup-env         crea .env da .env.example"
	@echo "  install           pip install requirements"
	@echo "  test              esegui pytest"
	@echo "  backfill-garmin   sync ultimi 730 giorni Garmin"
	@echo "  backfill-strava   sync ultimi 730 giorni Strava"
	@echo "  brief             genera brief manuale (richiede secrets locali)"
	@echo "  smoke-test        check connettività verso tutti i servizi"
	@echo "  deploy-bot        wrangler deploy del Telegram bot"
	@echo "  deploy-mcp        wrangler deploy del MCP server"

setup-env:
	@if [ ! -f .env ]; then cp .env.example .env && echo "✅ Creato .env — compila i valori"; else echo ".env già esiste"; fi

install:
	pip install -r requirements.txt

test:
	PYTHONPATH=. pytest tests/ -v

backfill-garmin:
	INGEST_DAYS_BACK=730 PYTHONPATH=. python -m coach.ingest.garmin

backfill-strava:
	INGEST_DAYS_BACK=730 PYTHONPATH=. python -m coach.ingest.strava

brief:
	PYTHONPATH=. python -m coach.planning.briefing

smoke-test:
	PYTHONPATH=. python -m scripts.smoke_test

deploy-bot:
	cd workers/telegram-bot && npx wrangler deploy

deploy-mcp:
	cd workers/mcp-server && npx wrangler deploy
