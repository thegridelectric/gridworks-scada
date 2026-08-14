"""Pytest bootstrap for the entire ``tests/`` tree.

In this repository, this file provides repo-wide test bootstraps that determine the .env
variables and the hardware layout. This means in particular that the testing DOES NOT use your existing
local `.env` settings. It does this by

- setting the default pytest dotenv path for local runs
- selecting the hardware layout used by the upstream ``gwproactor_test``
  autouse fixture
- pointing test certificate lookup at the repo's test certificate cache

The actual per-test environment setup is performed by the imported
``gwproactor_test`` fixtures, which create an isolated XDG config area for each
test and copy the selected hardware layout into that temp config location.

The scada boots from a PAIR of authored artifacts, so this file also copies the
operational-params fixture in beside the layout under the fixed name the scada
expects (actors.config.DEFAULT_OPS_PARAMS_FILE). Upstream copies only the
layout, so without this the pair would be split and the same-folder default
resolution would never be exercised.
"""

import os
import shutil
from pathlib import Path

import pytest

from gwproactor_test import (
    clean_test_env,  # noqa: F401
    default_test_env,  # noqa: F401
    restore_loggers, # noqa: F401
)
from gwproactor_test import set_hardware_layout_test_path
from gwproactor_test.pytest_options import add_live_test_options
from gwproactor_test.certs import set_test_certificate_cache_dir
from gwproactor.config import Paths

from actors.config import DEFAULT_OPS_PARAMS_FILE


TEST_DOTENV_PATH = Path(__file__).parent / ".env-gw-spaceheat-test"
TEST_DOTENV_PATH_VAR = "GW_SPACEHEAT_TEST_DOTENV_PATH"
TEST_HARDWARE_LAYOUT_PATH = Path(__file__).parent / "config" / "gw.nolan.layout.json"
# The test env copies only the layout file into the per-test config dir; the
# ops artifact is pinned by env var to its APPROVED partner (sema_to_dc.
# APPROVED_PAIRS): a gw.nolan.layout pairs only with gw.nolan.operational.params.
TEST_OPS_PARAMS_PATH = (
    Path(__file__).parent
    / "config"
    / "gw.nolan.operational.params.json"
)

# Bridge the scada-specific test dotenv to gwproactor_test, whose autouse
# default_test_env fixture reads GWPROACTOR_TEST_DOTENV_PATH (defaulting to a
# name this repo does not use). Without this, tests/.env-gw-spaceheat-test —
# which turns TLS off for the plain local broker — never loads, and the LTN
# broker's TLS-on default hangs against the local mosquitto, timing out every
# scada<->LTN link test. An explicitly-set GWPROACTOR_TEST_DOTENV_PATH (or the
# scada-specific GW_SPACEHEAT_TEST_DOTENV_PATH override) still wins.
os.environ.setdefault(
    "GWPROACTOR_TEST_DOTENV_PATH",
    os.environ.get(TEST_DOTENV_PATH_VAR, str(TEST_DOTENV_PATH)),
)

set_test_certificate_cache_dir(Path(__file__).parent / ".certificate_cache")
set_hardware_layout_test_path(TEST_HARDWARE_LAYOUT_PATH)


# Every proactor in a live tree gets its own config dir (~/.config/gridworks/<name>);
# each needs the pair, so seed them all.
PATHS_NAMES = ("scada", "scada2", "ltn")


@pytest.fixture(autouse=True)
def copy_test_operational_params(default_test_env):  # noqa: F811
    """Copy the operational-params fixture into each per-test config dir, beside
    the layout upstream copied in, under the name the scada resolves to. Ordered
    after default_test_env by depending on it. Nothing pins the path, so the boot
    resolves it the way a deployment does — the default is under test."""
    for name in PATHS_NAMES:
        dest = Path(Paths(name=name).hardware_layout).parent / DEFAULT_OPS_PARAMS_FILE
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(TEST_OPS_PARAMS_PATH, dest)
    yield

@pytest.fixture(autouse=True)
def always_restore_loggers(restore_loggers):
    ...


def pytest_addoption(parser: pytest.Parser) -> None:
    add_live_test_options(parser, include_tree=True)
    group = parser.getgroup("gridworks-scada")
    group.addoption(
        "--admin-verbosity",
        type=int,
        help="Run Admin live tests with the --verbose argument passed to admin this many times.",
    )
