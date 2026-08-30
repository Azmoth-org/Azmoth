# Operational commands. The ones somebody has to run correctly under pressure.
#
# A Makefile rather than a README section, because "the command to restore the database" is not a
# thing to reconstruct from prose at two in the morning. `make help` lists everything.
#
# Development commands stay in package.json and pnpm — `pnpm turbo lint typecheck build` and
# `pytest` are not here, deliberately, because duplicating them would create two ways to run the
# same check and one of them would go stale.

COMPOSE ?= infra/docker/docker-compose.yml
COMPOSE_DEV ?= infra/docker/docker-compose.dev.yml

.DEFAULT_GOAL := help
.PHONY: help backup-db restore-db list-backups verify-db up down logs

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

backup-db: ## Dump the database to ./backups/, and verify the dump is readable
	@BACKUP_DIR=$(or $(BACKUP_DIR),backups) COMPOSE_FILE=$(COMPOSE) ./infra/scripts/backup-db.sh

restore-db: ## Restore a dump. Destructive; asks for confirmation. Usage: make restore-db FILE=backups/x.dump
	@test -n "$(FILE)" || { echo "usage: make restore-db FILE=backups/<file>.dump"; exit 2; }
	@BACKUP_DIR=$(or $(BACKUP_DIR),backups) COMPOSE_FILE=$(COMPOSE) ./infra/scripts/restore-db.sh "$(FILE)"

list-backups: ## Show the dumps on this machine, newest first
	@ls -lht backups/*.dump 2>/dev/null || echo "no backups yet — run 'make backup-db'"

verify-db: ## Check the running engine is on Postgres and the schema is migrated
	@docker compose -f $(COMPOSE) exec -T engine python -c "\
from app.config import get_settings; s = get_settings(); \
print('DATABASE_URL backend :', s.database_backend); \
print('durable              :', s.database_is_durable); \
print('APP_ENV              :', s.app_env); \
assert s.database_is_durable, 'NOT Postgres — approvals would not be durable'"
	@docker compose -f $(COMPOSE) exec -T engine alembic current

up: ## Start the production stack
	docker compose -f $(COMPOSE) up --build -d

down: ## Stop the stack, keeping the volumes
	docker compose -f $(COMPOSE) down

logs: ## Follow the engine's logs (JSON; pipe through jq)
	docker compose -f $(COMPOSE) logs -f engine
