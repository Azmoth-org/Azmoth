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
COMPOSE_AZURE ?= infra/docker/docker-compose.azure.yml

# ── The Azure deployment ──────────────────────────────────────────────────────────────────────
# The azure-* targets run against the VM over SSH, from here. Set the host once:
#
#     export AZURE_HOST=20.79.12.34
#     make azure-logs
#
# or per command: `make azure-logs AZURE_HOST=20.79.12.34`.
AZURE_HOST ?=
AZURE_USER ?= azmoth
DOMAIN ?= azmoth.com
REMOTE_ROOT ?= /opt/azmoth

# One definition of "the compose command on the server", so no target can drift into running the
# production file without the azure override — which would republish the engine's port 8000.
REMOTE_COMPOSE = cd $(REMOTE_ROOT)/repo && sudo COMPOSE_PROJECT_NAME=azmoth docker compose \
  -f infra/docker/docker-compose.yml -f infra/docker/docker-compose.azure.yml

# Fails with a usable message rather than sshing to "@".
require-host = @test -n "$(AZURE_HOST)" || { \
	echo "AZURE_HOST is not set."; \
	echo "  export AZURE_HOST=20.79.12.34      (or: make $@ AZURE_HOST=...)"; exit 2; }

.DEFAULT_GOAL := help
.PHONY: help backup-db restore-db list-backups verify-db up down logs \
        azure-provision deploy preflight \
        azure-ps azure-logs azure-logs-caddy azure-restart azure-shell azure-psql \
        azure-backup azure-verify-db azure-restore-test azure-cost

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

# ── Azure: deploying ──────────────────────────────────────────────────────────────────────────

azure-provision: ## Create the Azure VM, static IP, NSG and backup storage (idempotent)
	./infra/azure/provision.sh

deploy: ## Deploy HEAD to the Azure VM. Usage: make deploy AZURE_HOST=20.79.12.34
	$(require-host)
	./scripts/deploy.sh $(AZURE_HOST) --user $(AZURE_USER) --domain $(DOMAIN)

preflight: ## Run the pre-flight checklist against the deployment
	$(require-host)
	./scripts/preflight.sh $(AZURE_HOST) --user $(AZURE_USER) --domain $(DOMAIN)

# ── Azure: operating ──────────────────────────────────────────────────────────────────────────

azure-ps: ## What is running on the VM, and is it healthy
	$(require-host)
	@ssh $(AZURE_USER)@$(AZURE_HOST) '$(REMOTE_COMPOSE) ps'

azure-logs: ## Follow the engine's logs (JSON; pipe through jq). SERVICE=web for another
	$(require-host)
	@ssh -t $(AZURE_USER)@$(AZURE_HOST) '$(REMOTE_COMPOSE) logs -f --tail 100 $(or $(SERVICE),engine)'

azure-logs-caddy: ## Follow Caddy's logs — where a TLS or certificate problem shows up
	$(require-host)
	@ssh -t $(AZURE_USER)@$(AZURE_HOST) '$(REMOTE_COMPOSE) logs -f --tail 100 caddy'

azure-restart: ## Restart one service without rebuilding. Usage: make azure-restart SERVICE=web
	$(require-host)
	@test -n "$(SERVICE)" || { echo "usage: make azure-restart SERVICE=web|engine|caddy|marketing"; exit 2; }
	@ssh $(AZURE_USER)@$(AZURE_HOST) '$(REMOTE_COMPOSE) restart $(SERVICE)'
	@ssh $(AZURE_USER)@$(AZURE_HOST) '$(REMOTE_COMPOSE) ps $(SERVICE)'

azure-shell: ## An interactive shell on the VM, in the release directory
	$(require-host)
	@ssh -t $(AZURE_USER)@$(AZURE_HOST) 'cd $(REMOTE_ROOT)/repo && exec $$SHELL -l'

azure-psql: ## A psql session against the production database (no port is published; this is exec)
	$(require-host)
	@ssh -t $(AZURE_USER)@$(AZURE_HOST) '$(REMOTE_COMPOSE) exec postgres psql -U azmoth -d azmoth'

azure-verify-db: ## Check the deployed engine is on Postgres and the schema is migrated
	$(require-host)
	@ssh $(AZURE_USER)@$(AZURE_HOST) '$(REMOTE_COMPOSE) exec -T engine python -c "\
from app.config import get_settings; s = get_settings(); \
print(\"DATABASE_URL backend :\", s.database_backend); \
print(\"durable              :\", s.database_is_durable); \
print(\"APP_ENV              :\", s.app_env); \
assert s.database_is_durable, \"NOT Postgres — approvals would not be durable\""'
	@ssh $(AZURE_USER)@$(AZURE_HOST) '$(REMOTE_COMPOSE) exec -T engine alembic current'

# ── Azure: backups ────────────────────────────────────────────────────────────────────────────

azure-backup: ## Dump, verify, encrypt and push to Blob Storage — now, not on a schedule
	$(require-host)
	@ssh $(AZURE_USER)@$(AZURE_HOST) 'sudo $(REMOTE_ROOT)/repo/infra/scripts/backup-to-azure.sh'

azure-restore-test: ## Restore the newest dump into a scratch database and compare row counts
	$(require-host)
	./scripts/preflight.sh $(AZURE_HOST) --user $(AZURE_USER) --domain $(DOMAIN) 2>/dev/null \
		| sed -n '/6. Backups/,/7. Do these/p'

azure-cost: ## What the pilot has spent so far, and on what
	@az consumption usage list --output table 2>/dev/null \
		|| echo "az consumption needs a subscription that reports usage; see the portal's Cost analysis"
