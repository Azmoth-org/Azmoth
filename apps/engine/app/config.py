"""Configuration.

Two rules govern this module:

**No absolute path is ever hard-coded.** The engine reads its logic (`.lp`, `.dl`) and its data
(catalog, rule CSVs, mapping) from `LOGIC_DIR` and `DATA_DIR`. Both default to the monorepo's
`logic/` and `data/`, discovered by walking up from this file until a directory holding both is
found — which resolves correctly from a checkout (`apps/engine/app/config.py` → repo root) and
from the container image (`/srv/app/config.py` → `/srv`). Either can be overridden by an
environment variable, which is how the Docker image and any future deployment point at them.

**Manual mode is the default and needs no configuration.** Nothing here requires an API key, a
network call, or a secret of any kind. `.env.example` is a complete description of the knobs.
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

CATALOG_DIR = DATA_DIR / "catalogs" / "goae_current"
RULES_DATA_DIR = DATA_DIR / "rules"
MAPPINGS_DIR = DATA_DIR / "mappings"
RAW_DIR = DATA_DIR / "raw"
LICENSED_DIR = DATA_DIR / "licensed"

CATALOG_PATH = CATALOG_DIR / "goae.official.json"
OVERRIDES_PATH = CATALOG_DIR / "overrides.json"
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

    # -- paths --------------------------------------------------------------------------
    logic_dir: Path = LOGIC_DIR
    data_dir: Path = DATA_DIR

    #: Left empty on purpose: the catalog file states its own version, and a mismatch between an
    #: environment variable and the shipped data is a lie waiting to be believed. Set it only to
    #: assert an expected snapshot — `catalog_version_mismatch` then fails loudly at startup.
    catalog_version: str = ""

    # -- request limits -----------------------------------------------------------------
    #: Largest request body the API accepts, enforced at the perimeter before the body is read.
    #: 32 MiB is far above any real PADnext delivery (the bundled example is 3 KB) and far below
    #: what would exhaust a container.
    max_request_bytes: int = 32 * 1024 * 1024

    # -- PADnext ------------------------------------------------------------------------
    #: Refusing production data is the default. See docs/compliance/PRIVATE_DATA_WARNING.md.
    padnext_allow_real_data: bool = False

    # -- derived paths ------------------------------------------------------------------

    @property
    def catalog_dir(self) -> Path:
        return self.data_dir / "catalogs" / "goae_current"

    @property
    def rules_data_dir(self) -> Path:
        return self.data_dir / "rules"

    @property
    def mappings_dir(self) -> Path:
        return self.data_dir / "mappings"

    @property
    def catalog_path(self) -> Path:
        return self.catalog_dir / "goae.official.json"

    @property
    def overrides_path(self) -> Path:
        return self.catalog_dir / "overrides.json"

    @property
    def mapping_path(self) -> Path:
        return self.mappings_dir / "entity_to_ziffer.csv"

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
