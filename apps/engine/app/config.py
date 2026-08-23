"""Configuration.

Two rules govern this module:

**No absolute path is ever hard-coded.** The engine reads its logic (`.lp`, `.dl`) and its data
(catalog, rule CSVs, mapping) from `LOGIC_DIR` and `DATA_DIR`. Both default to the monorepo's
`logic/` and `data/`, discovered by walking up from this file until a directory holding both is
found — which resolves correctly from a checkout (`apps/engine/app/config.py` → repo root) and
from the container image (`/srv/app/config.py` → `/srv`). Either can be overridden by an
environment variable, which is how the Docker image and any future deployment point at them.

**Manual mode is the default and needs no configuration.** No API key, no model, no network call
is required to code a case: `DATABASE_URL` is the only setting that names an external service, and
it defaults to a local SQLite file so the suite and a bare `uvicorn` run with nothing configured.
It is also the only setting that can carry a credential in production — `.env.example` documents
it without one, and nothing here logs its value.

`.env.example` is a complete description of the knobs; `tests/test_production_fixes.py` asserts
that, so a new setting that is not documented there fails the suite.
"""

from __future__ import annotations

import hashlib
import os
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_DIR = Path(__file__).resolve().parent
ENGINE_DIR = APP_DIR.parent


def _find_repo_root() -> Path:
    """The nearest ancestor holding both `logic/` and `data/`.

    Checkout:  …/TARGET_MONOREPO/apps/engine/app → …/TARGET_MONOREPO
    Container: /srv/app                          → /srv

    Falling back to the engine's parent rather than raising keeps `--help` and `import app.config`
    working in a stripped environment; the missing directory is then reported by whichever loader
    actually needs it, naming the path it looked in.
    """
    for candidate in (APP_DIR, *APP_DIR.parents):
        if (candidate / "logic").is_dir() and (candidate / "data").is_dir():
            return candidate
    return ENGINE_DIR.parent.parent


REPO_ROOT = _find_repo_root()

#: Environment wins over discovery, so an image can place logic and data anywhere.
LOGIC_DIR = Path(os.getenv("LOGIC_DIR") or REPO_ROOT / "logic").resolve()
DATA_DIR = Path(os.getenv("DATA_DIR") or REPO_ROOT / "data").resolve()

#: Every catalog edition lives in its own directory under here — see `DEFAULT_CATALOG_VERSION`
#: and `app.catalog.catalog_loader` for how a `catalog_version` string becomes a path.
CATALOGS_DIR = DATA_DIR / "catalogs"

#: The two files the loader expects beside each other in every catalog directory.
CATALOG_FILENAME = "goae.official.json"
OVERRIDES_FILENAME = "overrides.json"

#: The catalog used when a caller names none.
#:
#: `goae_current` is the real, official 2192-position snapshot, and it is deliberately the default:
#: the other directories under `data/catalogs/` are small synthetic fixtures for temporal-routing
#: tests, and one of those becoming the process-wide default would silently replace the fee
#: schedule the engine bills with. Point this at a different edition only when that edition is
#: real data — `DEFAULT_CATALOG_VERSION` in the environment does it per deployment.
DEFAULT_CATALOG_VERSION = os.getenv("DEFAULT_CATALOG_VERSION") or "goae_current"

CATALOG_DIR = CATALOGS_DIR / DEFAULT_CATALOG_VERSION
RULES_DATA_DIR = DATA_DIR / "rules"
MAPPINGS_DIR = DATA_DIR / "mappings"
RAW_DIR = DATA_DIR / "raw"
LICENSED_DIR = DATA_DIR / "licensed"

#: XML schemas the engine validates input against. Ours, hand-written, licensed with the repo.
SCHEMAS_DIR = DATA_DIR / "schemas"

#: The PADnext subset schema. NOT the official XSD — see the long comment at the top of the file
#: for why the official one is not redistributed and what this one deliberately does not enforce.
PADNEXT_XSD_PATH = SCHEMAS_DIR / "padnext" / "padx_adl_v2.12.subset.xsd"

#: Where an operator who holds the official PADneXt schema puts it. Preferred over the subset
#: when present, and git-ignored like everything else under `data/licensed/`.
PADNEXT_LICENSED_XSD_PATH = LICENSED_DIR / "padnext" / "padx_adl_v2.12.xsd"

CATALOG_PATH = CATALOG_DIR / CATALOG_FILENAME
OVERRIDES_PATH = CATALOG_DIR / OVERRIDES_FILENAME
MAPPING_PATH = MAPPINGS_DIR / "entity_to_ziffer.csv"

ASP_PATH = LOGIC_DIR / "asp" / "goae_optimize.lp"
DATALOG_PATH = LOGIC_DIR / "datalog" / "goae_rules.dl"

CASES_DIR = LOGIC_DIR / "tests" / "cases"
GOLDEN_DIR = LOGIC_DIR / "tests" / "golden"
PADNEXT_EXAMPLES_DIR = CASES_DIR / "padnext"


class AppEnv(StrEnum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class ExtractionMode(StrEnum):
    #: Hand-written / upstream-produced clinical entities posted to the API. The only supported
    #: mode in this service: free-text extraction happens outside the engine boundary.
    MANUAL = "manual"


class UnverifiedRulePolicy(StrEnum):
    WARN = "warn"
    BLOCK = "block"
    IGNORE = "ignore"


class BaseFactorPolicy(StrEnum):
    EINFACHSATZ = "einfachsatz"
    SCHWELLENWERT = "schwellenwert"


class PadnextSchemaPolicy(StrEnum):
    """What a PADnext delivery that violates the subset schema is allowed to do.

    Deliberately the same three-value shape as `UnverifiedRulePolicy`, because it is the same
    kind of decision: how much authority to give a check that can be wrong about a real file.

        strict  (default)  the delivery is refused — `PadnextSchemaError`, HTTP 422
        warn               every violation becomes a finding and the audit runs anyway
        off                the schema is not consulted at all
    """

    STRICT = "strict"
    WARN = "warn"
    OFF = "off"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(ENGINE_DIR / ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    # -- service ------------------------------------------------------------------------
    app_env: AppEnv = AppEnv.DEVELOPMENT
    debug: bool = False

    # -- extraction ---------------------------------------------------------------------
    #: Manual by default, and manual is the only value: the engine takes structured clinical
    #: entities. Where they come from — a form, a PVS export, a model running elsewhere — is
    #: outside this boundary. See docs/architecture/ENGINE.md.
    extraction_mode: ExtractionMode = ExtractionMode.MANUAL

    # -- rules --------------------------------------------------------------------------
    #: Auto-extracted rules are unverified. Warning (not blocking) is the safe default: a
    #: machine-read rule must not suppress a chargeable service until a human confirms it.
    unverified_rule_policy: UnverifiedRulePolicy = UnverifiedRulePolicy.WARN

    #: § 5 Abs. 2 GOÄ — factors up to the Schwellenwert need no written justification, so that
    #: is the defensible default. `einfachsatz` is the maximally conservative reading.
    base_factor_policy: BaseFactorPolicy = BaseFactorPolicy.SCHWELLENWERT

    # -- solvers ------------------------------------------------------------------------
    #: Hard ceiling on one Clingo solve. Observed per-case time is ~30 ms; 5 s is three orders
    #: of magnitude of headroom and still bounds a pathological grounding.
    solver_timeout_seconds: float = Field(default=5.0, gt=0)
    souffle_bin: str = "souffle"
    souffle_timeout_s: float = Field(default=60.0, gt=0)

    # -- cache --------------------------------------------------------------------------
    cache_enabled: bool = True
    cache_max_entries: int = Field(default=256, ge=1)

    # -- database -----------------------------------------------------------------------
    #: Where proposals and the audit log live. A SQLAlchemy async URL, so the driver is part of
    #: the value: `postgresql+asyncpg://…` in production, `sqlite+aiosqlite://…` locally.
    #:
    #: The default is SQLite so that `pytest` and a bare `uvicorn` need no server — but SQLite is
    #: NOT a deployment target: it has one writer, no concurrent workers and no encryption at
    #: rest, and `docker-compose.yml` therefore sets `DATABASE_URL` to the Postgres service.
    #: `database_is_durable` is what the startup log warns on, so running on the wrong one is
    #: visible in the first ten lines of a container's output rather than assumed.
    #:
    #: Deliberately NOT reported by `GET /api/v1/health`: that would add a field to `HealthResponse`
    #: and therefore to the OpenAPI document, and this migration's contract with the frontend is
    #: that the document does not move. Surfacing it is a separate, deliberate API change.
    database_url: str = "sqlite+aiosqlite:///./test.db"

    #: Echo every statement. Separate from `debug` because SQL echo is far noisier than the rest
    #: of debug logging and, on a service that holds patient data, is a log-leak risk.
    database_echo: bool = False

    #: Connections held open per worker. Ignored by SQLite, which has no pool worth sizing.
    database_pool_size: int = Field(default=5, ge=1)
    database_max_overflow: int = Field(default=10, ge=0)

    #: Run `Base.metadata.create_all()` at startup instead of requiring Alembic. True is right for
    #: the SQLite default and for the test suite; it is refused in production (see
    #: `app.db.session.init_models`), where the schema must arrive through a reviewed migration.
    database_auto_create: bool = True

    # -- batch --------------------------------------------------------------------------
    #: Close batches a previous process left mid-flight, at startup, before serving a request.
    #:
    #: True is right for the single-process deployment this stack describes: `BackgroundTasks` dies
    #: with its process, so a `PENDING` or `PROCESSING` row at startup can only be a leftover, and
    #: leaving it would strand it forever. It is a setting rather than a hard-coded step because the
    #: assumption fails under more than one worker or a rolling deploy, where a starting process
    #: would reap a batch still running on a sibling — see
    #: `app.services.batch_audit.BatchAuditService.reap_interrupted_batches`.
    reap_interrupted_batches: bool = True

    # -- paths --------------------------------------------------------------------------
    logic_dir: Path = LOGIC_DIR
    data_dir: Path = DATA_DIR

    #: Left empty on purpose: the catalog file states its own version, and a mismatch between an
    #: environment variable and the shipped data is a lie waiting to be believed. Set it only to
    #: assert an expected snapshot — `catalog_version_mismatch` then fails loudly at startup.
    catalog_version: str = ""

    #: Which catalog edition is loaded when a caller names none — a **directory name** under
    #: `data/catalogs/`, and not to be confused with `catalog_version` above, which is the version
    #: string the chosen file *declares* and which the receipt records.
    #:
    #: `goae_current` holds the official snapshot; the temporal fixtures beside it are synthetic
    #: (see `data/catalogs/README.md`), so this defaults to the real data and a deployment has to
    #: say so to route anywhere else.
    default_catalog_version: str = DEFAULT_CATALOG_VERSION

    # -- request limits -----------------------------------------------------------------
    #: Largest request body the API accepts, enforced at the perimeter before the body is read.
    #: 32 MiB is far above any real PADnext delivery (the bundled example is 3 KB) and far below
    #: what would exhaust a container.
    max_request_bytes: int = 32 * 1024 * 1024

    # -- PADnext ------------------------------------------------------------------------
    #: Refusing production data is the default. See docs/compliance/PRIVATE_DATA_WARNING.md.
    padnext_allow_real_data: bool = False

    #: How hard the framing check bites. `strict` refuses a delivery whose document-level shape is
    #: wrong — the reasoning is in `data/schemas/padnext/padx_adl_v2.12.subset.xsd`: framing is
    #: fatal, positions are advisory. `warn` is the escape hatch for the day a real PVS export is
    #: 99 % conforming and still worth auditing; it turns every violation into a finding.
    padnext_schema_policy: PadnextSchemaPolicy = PadnextSchemaPolicy.STRICT

    # -- derived paths ------------------------------------------------------------------

    @property
    def catalogs_dir(self) -> Path:
        """The root all catalog editions live under. One directory per edition."""
        return self.data_dir / "catalogs"

    def catalog_dir_for(self, catalog_version: str | None = None) -> Path:
        """Resolve one edition's directory — the temporal routing step, as a pure path join.

        Validation of the name (and of whether that edition is actually on disk) belongs to
        `app.catalog.catalog_loader.resolve_catalog_dir`, which is what callers should use; this
        stays a path so `app.config` keeps importing with no data present.
        """
        return self.catalogs_dir / (catalog_version or self.default_catalog_version)

    @property
    def catalog_dir(self) -> Path:
        return self.catalog_dir_for()

    @property
    def rules_data_dir(self) -> Path:
        return self.data_dir / "rules"

    @property
    def mappings_dir(self) -> Path:
        return self.data_dir / "mappings"

    @property
    def catalog_path(self) -> Path:
        return self.catalog_dir / CATALOG_FILENAME

    @property
    def overrides_path(self) -> Path:
        return self.catalog_dir / OVERRIDES_FILENAME

    @property
    def mapping_path(self) -> Path:
        return self.mappings_dir / "entity_to_ziffer.csv"

    @property
    def schemas_dir(self) -> Path:
        return self.data_dir / "schemas"

    @property
    def padnext_xsd_path(self) -> Path:
        """The schema actually used: the official one where an operator has licensed it, ours
        otherwise. Resolved per call rather than cached, so dropping the licensed file in does not
        need a restart to be noticed by the next process to load the schema."""
        licensed = self.data_dir / "licensed" / "padnext" / "padx_adl_v2.12.xsd"
        if licensed.is_file():
            return licensed
        return self.schemas_dir / "padnext" / "padx_adl_v2.12.subset.xsd"

    @property
    def asp_path(self) -> Path:
        return self.logic_dir / "asp" / "goae_optimize.lp"

    @property
    def datalog_path(self) -> Path:
        return self.logic_dir / "datalog" / "goae_rules.dl"

    @property
    def cases_dir(self) -> Path:
        return self.logic_dir / "tests" / "cases"

    @property
    def golden_dir(self) -> Path:
        return self.logic_dir / "tests" / "golden"

    @property
    def database_backend(self) -> str:
        """`postgresql`, `sqlite`, … — the dialect name, without the driver."""
        scheme = self.database_url.split("://", 1)[0]
        return scheme.split("+", 1)[0]

    @property
    def database_is_durable(self) -> bool:
        """Whether the configured database is one an approval may be trusted to survive in.

        SQLite is a real database and it does survive a restart, so this is not about persistence
        — it is about the deployment claim: one writer, one file, no replication, no encryption at
        rest. An approval that a Rechnungsprüfer may be shown must not live there.
        """
        return self.database_backend == "postgresql"

    # -- versions -----------------------------------------------------------------------

    @property
    def clingo_version(self) -> str:
        """Read from the library rather than pinned in config, so it cannot disagree with it."""
        try:
            import clingo

            return clingo.__version__
        except ImportError:  # pragma: no cover - clingo is a hard requirement
            return ""

    @property
    def logic_version(self) -> str:
        """SHA-256 over the ASP and Datalog programs themselves.

        Part of the cache key and the receipt: editing a rule in `.lp` or `.dl` must invalidate
        both, and a version string a human maintains would not.
        """
        digest = hashlib.sha256()
        for path in (self.datalog_path, self.asp_path):
            digest.update(path.read_bytes() if path.is_file() else b"MISSING")
            digest.update(b"\0")
        return digest.hexdigest()

    # -- policy snapshot ----------------------------------------------------------------

    def policy_fingerprint(self) -> dict[str, str]:
        """Every setting that can change an answer. Feeds the cache key and the receipt hash.

        Deliberately excludes `debug`, `cache_enabled`, timeouts and request limits: they change
        how the answer is produced or reported, never what it is.
        """
        return {
            "extraction_mode": str(self.extraction_mode),
            "unverified_rule_policy": str(self.unverified_rule_policy),
            "base_factor_policy": str(self.base_factor_policy),
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
