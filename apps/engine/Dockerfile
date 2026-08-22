# syntax=docker/dockerfile:1
#
# Build context is the MONOREPO ROOT, not this directory: the image needs logic/ and data/, which
# live outside apps/engine on purpose. From the repo root:
#
#     docker build -f apps/engine/Dockerfile -t govatax-engine:0.3.0 .
#
# or use infra/docker/docker-compose.yml, which sets the context correctly.

FROM python:3.11-slim

# --- Soufflé -------------------------------------------------------------------------------
# Soufflé is NOT in the Debian/Ubuntu archives, so the upstream release .deb is used. It is built
# for Ubuntu 22.04; rather than let dpkg try to satisfy Ubuntu dependencies on Debian, the archive
# is unpacked directly and its handful of shared libraries come from Debian's own repos.
#
# `mcpp` is not optional: Soufflé shells out to a C preprocessor before parsing a .dl file even in
# interpreter mode, and aborts with "failed to locate mcpp or gcc pre-processors" without one.
# mcpp is ~90 kB, against ~60 MB for pulling in gcc.
#
# Pinned to 2.5 — the same version the golden snapshots were produced with. A different Soufflé
# can legitimately evaluate the same program to the same model in a different order, and the
# version is part of the receipt hash, so an unpinned bump would silently change what a receipt
# means.
ARG SOUFFLE_VERSION=2.5
ARG SOUFFLE_DEB=x86_64-ubuntu-2204-souffle-2.5-Linux.deb
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates curl mcpp libffi8 libgomp1 libncurses6 libsqlite3-0 zlib1g \
    && curl -fsSL -o /tmp/souffle.deb \
        "https://github.com/souffle-lang/souffle/releases/download/${SOUFFLE_VERSION}/${SOUFFLE_DEB}" \
    && dpkg-deb -x /tmp/souffle.deb / \
    && rm /tmp/souffle.deb \
    && apt-get purge -y --auto-remove curl \
    && rm -rf /var/lib/apt/lists/* \
    # Prove the rules engine actually evaluates at build time rather than at demo time.
    && printf '.decl t(x:number)\nt(1).\n.output t\n' > /tmp/smoke.dl \
    && souffle -D- /tmp/smoke.dl && rm /tmp/smoke.dl \
    && souffle --version

# --- Python deps ---------------------------------------------------------------------------
WORKDIR /srv
COPY apps/engine/requirements.txt .
# --retries/--timeout are not padding: a --no-cache rebuild re-downloads every wheel, and on a slow
# link pip's default 15 s read timeout gives up mid-wheel and fails with "No matching distribution
# found" — indistinguishable, at a glance, from a genuinely bad version pin.
RUN pip install --no-cache-dir --retries 10 --timeout 120 -r requirements.txt

# --- App, logic and data -------------------------------------------------------------------
# The logic programs and the catalog are not "assets": the image is useless without them, and
# LOGIC_DIR/DATA_DIR below is what makes the layout inside the image independent of the monorepo's.
COPY apps/engine/app ./app
COPY apps/engine/scripts ./scripts
COPY apps/engine/tests ./tests
COPY apps/engine/pytest.ini ./pytest.ini
# The migration history and its Alembic configuration are part of the image, not a dev-only
# artefact: the container migrates itself on start (see the entrypoint), so `alembic upgrade head`
# has to be runnable inside it.
COPY apps/engine/alembic ./alembic
COPY apps/engine/alembic.ini ./alembic.ini
COPY logic ./logic
COPY data ./data

RUN chmod +x /srv/scripts/docker-entrypoint.sh

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/srv \
    LOGIC_DIR=/srv/logic \
    DATA_DIR=/srv/data \
    APP_ENV=production \
    DEBUG=false \
    SOUFFLE_BIN=souffle \
    EXTRACTION_MODE=manual \
    UNVERIFIED_RULE_POLICY=warn \
    BASE_FACTOR_POLICY=schwellenwert \
    SOLVER_TIMEOUT_SECONDS=5 \
    CACHE_ENABLED=true \
    PADNEXT_ALLOW_REAL_DATA=false \
    DATABASE_AUTO_CREATE=false
# Two things about the database are set above, and one deliberately is not.
#
# DATABASE_AUTO_CREATE=false: the schema comes from `alembic upgrade head` in the entrypoint, never
# from `create_all`. A schema that appeared without a migration has no rollback and no history, and
# app/db/session.py refuses create_all under APP_ENV=production for exactly that reason.
#
# There is NO DATABASE_URL default. Any default would be wrong: a SQLite path is refused by the
# production guard and unwritable anyway (/srv is root-owned and the runtime user is 10001), and a
# hostname is something only the deployment knows. Without it the container fails at startup naming
# the variable — the right outcome for a service whose job is to keep a record it cannot keep.

# Fail the build if the shipped data cannot actually drive a coding run. Catching a broken catalog
# or a missing logic program here is much cheaper than catching it in front of a user.
RUN python scripts/engine_cli.py check

# --- Non-root ------------------------------------------------------------------------------
# Created after the COPYs so the app tree stays root-owned and read-only to the runtime user:
# nothing in a request path writes to /srv, and the container should not be able to.
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin engine
USER 10001

EXPOSE 8000

# Checks the rules engine specifically, not just that the process is listening: a container whose
# Soufflé is missing would answer HTTP fine and fail every coding request.
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,json,sys; \
d=json.load(urllib.request.urlopen('http://localhost:8000/api/v1/health')); \
sys.exit(0 if d['souffle_available'] and d['status']=='ok' else 1)"

# Migrations run in the entrypoint, so they happen whatever `command:` a compose file or an
# orchestrator supplies. See scripts/docker-entrypoint.sh for why this is not a chained CMD.
ENTRYPOINT ["/srv/scripts/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
