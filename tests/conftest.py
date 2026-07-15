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
"""

import os
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


TEST_DOTENV_PATH = Path(__file__).parent / ".env-gw-spaceheat-test"
TEST_DOTENV_PATH_VAR = "GW_SPACEHEAT_TEST_DOTENV_PATH"
TEST_HARDWARE_LAYOUT_PATH = Path(__file__).parent / "config" / "nolan-layout.json"
# The test env copies only the layout file into the per-test config dir; the
# ops artifact is pinned by env var to the matching per-home fixture instead.
TEST_OPS_PARAMS_PATH = (
    Path(__file__).parent
    / "config"
    / "nolan-layout"
    / "gw.house0.operational.params.json"
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
os.environ.setdefault("SCADA_OPERATIONAL_PARAMS_PATH", str(TEST_OPS_PARAMS_PATH))

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
