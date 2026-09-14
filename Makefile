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
COMPOSE_AWS ?= infra/docker/docker-compose.aws.yml

# ── The AWS deployment ────────────────────────────────────────────────────────────────────────
# The aws-* targets run against the VM over SSH, from here. Set the host once:
#
#     export AWS_HOST=3.120.45.67
#     make aws-logs
#
# or per command: `make aws-logs AWS_HOST=3.120.45.67`.
AWS_HOST ?=
AWS_USER ?= azmoth
DOMAIN ?= azmoth.com
REMOTE_ROOT ?= /opt/azmoth

# One definition of "the compose command on the server", so no target can drift into running the
# production file without the aws override — which would republish the engine's port 8000.
REMOTE_COMPOSE = cd $(REMOTE_ROOT)/repo && sudo COMPOSE_PROJECT_NAME=azmoth docker compose \
  -f infra/docker/docker-compose.yml -f infra/docker/docker-compose.aws.yml

# Fails with a usable message rather than sshing to "@".
require-host = @test -n "$(AWS_HOST)" || { \
	echo "AWS_HOST is not set."; \
	echo "  export AWS_HOST=3.120.45.67      (or: make $@ AWS_HOST=...)"; exit 2; }

.DEFAULT_GOAL := help
.PHONY: help backup-db restore-db list-backups verify-db up down logs \
        aws-provision deploy rollback preflight \
        aws-ps aws-logs aws-logs-caddy aws-restart aws-shell aws-psql \
        aws-backup aws-verify-db aws-migrate aws-check-db aws-cost

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

# ── AWS: deploying ────────────────────────────────────────────────────────────────────────────

aws-provision: ## Create the EC2 VM, Elastic IP, security group and S3 backup bucket (idempotent)
	./infra/aws/provision.sh

deploy: ## Deploy HEAD to the AWS VM. Usage: make deploy AWS_HOST=3.120.45.67
	$(require-host)
	@# Make exports its environment to the recipe's shell, so the secrets deploy.sh reads from the
	@# environment pass straight through. On the FIRST deploy both Neon strings are required:
	@#
	@#   DATABASE_URL='...ep-xxx...' DATABASE_URL_POOLED='...ep-xxx-pooler...' make deploy
	@#
	@# On every deploy after that they are already in /opt/azmoth/shared/.env and this is enough.
	@# Nothing is built on the box — the images come from GHCR at HEAD's sha, so HEAD must be pushed
	@# and its release-images workflow must have finished. deploy.sh checks before it touches the VM.
	./scripts/deploy.sh $(AWS_HOST) --user $(AWS_USER) --domain $(DOMAIN)

rollback: ## Roll back to an earlier image. Usage: make rollback TAG=6a3c14c AWS_HOST=...
	$(require-host)
	@test -n "$(TAG)" || { echo "usage: make rollback TAG=<sha> AWS_HOST=..."; \
		echo "  candidates:"; git log --format='    %h  %s' -10; exit 2; }
	@# A pull and a restart, not a rebuild — and it does NOT undo a migration. See
	@# docs/deploy/RUNBOOK.md section 6 before rolling back across one.
	./scripts/deploy.sh $(AWS_HOST) --user $(AWS_USER) --domain $(DOMAIN) --tag $(TAG)

preflight: ## Run the pre-flight checklist against the deployment
	$(require-host)
	./scripts/preflight.sh $(AWS_HOST) --user $(AWS_USER) --domain $(DOMAIN)

# ── AWS: operating ────────────────────────────────────────────────────────────────────────────

aws-ps: ## What is running on the VM, and is it healthy
	$(require-host)
	@ssh $(AWS_USER)@$(AWS_HOST) '$(REMOTE_COMPOSE) ps'

aws-logs: ## Follow the engine's logs (JSON; pipe through jq). SERVICE=web for another
	$(require-host)
	@ssh -t $(AWS_USER)@$(AWS_HOST) '$(REMOTE_COMPOSE) logs -f --tail 100 $(or $(SERVICE),engine)'

aws-logs-caddy: ## Follow Caddy's logs — where a TLS or certificate problem shows up
	$(require-host)
	@ssh -t $(AWS_USER)@$(AWS_HOST) '$(REMOTE_COMPOSE) logs -f --tail 100 caddy'

aws-restart: ## Restart one service without repulling. Usage: make aws-restart SERVICE=web
	$(require-host)
	@# Three services, and that is the whole list: postgres and marketing are profiled out of the
	@# aws override (Neon's and Vercel's respectively).
	@test -n "$(SERVICE)" || { echo "usage: make aws-restart SERVICE=web|engine|caddy"; exit 2; }
	@ssh $(AWS_USER)@$(AWS_HOST) '$(REMOTE_COMPOSE) restart $(SERVICE)'
	@ssh $(AWS_USER)@$(AWS_HOST) '$(REMOTE_COMPOSE) ps $(SERVICE)'

aws-shell: ## An interactive shell on the VM, in the release directory
	$(require-host)
	@ssh -t $(AWS_USER)@$(AWS_HOST) 'cd $(REMOTE_ROOT)/repo && exec $$SHELL -l'

aws-psql: ## A psql session against Neon, in a container on the VM (nothing is installed on it)
	$(require-host)
	@# The database is Neon's, so this is no longer `exec postgres psql` — there is no postgres
	@# container. It runs psql in a throwaway pinned image and reads the connection string out of
	@# the deployment's own env file, so there is one copy of that credential on the box.
	@#
	@# --network=host is not needed (an outbound TLS connection works on the default bridge) and
	@# the URL reaches psql through the environment, so it never appears in `ps` on the VM.
	@#
	@# Note this is the DIRECT endpoint. An interactive session uses SET and session state, neither
	@# of which the pooler supports.
	@ssh -t $(AWS_USER)@$(AWS_HOST) 'set -a; . $(REMOTE_ROOT)/shared/.env; set +a; \
	  sudo docker run --rm -it -e PGURL="$$(echo $$DATABASE_URL | sed "s/+asyncpg//")" \
	    postgres:17-alpine sh -c "psql \"\$$PGURL\""'

aws-verify-db: ## Check the deployed engine reached Neon, on the direct endpoint, at schema head
	$(require-host)
	@ssh $(AWS_USER)@$(AWS_HOST) '$(REMOTE_COMPOSE) exec -T engine python -c "\
import urllib.parse; \
from app.config import get_settings; s = get_settings(); \
host = urllib.parse.urlsplit(s.database_url.replace(\"+asyncpg\", \"\")).hostname or \"\"; \
print(\"DATABASE_URL backend :\", s.database_backend); \
print(\"durable              :\", s.database_is_durable); \
print(\"APP_ENV              :\", s.app_env); \
print(\"db host              :\", host); \
print(\"endpoint             :\", \"POOLED — WRONG\" if \"-pooler.\" in host else \"direct\"); \
assert s.database_is_durable, \"NOT Postgres — approvals would not be durable\"; \
assert \"-pooler.\" not in host, \"the engine is on the POOLED endpoint; it must use the direct one\""'
	@ssh $(AWS_USER)@$(AWS_HOST) '$(REMOTE_COMPOSE) exec -T engine sh -c "\
echo -n \"current : \"; alembic current; echo -n \"head    : \"; alembic heads"'

aws-migrate: ## Run alembic upgrade head against Neon's direct endpoint, without a full deploy
	$(require-host)
	@ssh $(AWS_USER)@$(AWS_HOST) '$(REMOTE_COMPOSE) run --rm engine-migrate'

# ── AWS: backups ──────────────────────────────────────────────────────────────────────────────

aws-backup: ## Dump Neon over the network, verify, encrypt and push to S3 — now, not on a schedule
	$(require-host)
	@ssh $(AWS_USER)@$(AWS_HOST) 'sudo $(REMOTE_ROOT)/repo/infra/scripts/backup-to-s3.sh'

aws-check-db: ## The database section of the pre-flight: reachable, right endpoints, at head
	$(require-host)
	@# There is no postgres container on this box, and creating a throwaway database inside the
	@# Neon project on every invocation would burn the Free plan's compute allowance to prove
	@# something Neon's own instant restore already covers. A real restore drill needs the age
	@# private key and is therefore a human's job — docs/OPERATIONS.md § 7.7.
	./scripts/preflight.sh $(AWS_HOST) --user $(AWS_USER) --domain $(DOMAIN) 2>/dev/null \
		| sed -n '/6. The Neon database/,/7. Do these/p'

aws-cost: ## What the pilot has spent so far, and on what
	@aws ce get-cost-and-usage \
		--time-period Start=$$(date -u +%Y-%m-01),End=$$(date -u -d tomorrow +%Y-%m-%d) \
		--granularity MONTHLY --metrics UnblendedCost --group-by Type=DIMENSION,Key=SERVICE \
		--output table 2>/dev/null \
		|| echo "Cost Explorer needs 'ce:GetCostAndUsage' on your caller; see the console's Cost Explorer instead."
