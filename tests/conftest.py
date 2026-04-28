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

from gwproactor.config import DEFAULT_LAYOUT_FILE
from gwproactor_test import (
    clean_test_env,  # noqa: F401
    default_test_env,  # noqa: F401
    restore_loggers, # noqa: F401
)
from gwproactor_test import set_hardware_layout_test_path
from gwproactor_test.pytest_options import add_live_test_options
from gwproactor_test.certs import set_test_certificate_cache_dir

TEST_HARDWARE_LAYOUT_PATH = Path(__file__).parent / "config" / DEFAULT_LAYOUT_FILE
DEFAULT_LOCAL_TEST_DOTENV_PATH = str(Path(__file__).parent / "config" / ".env-local")

# gwproactor_test's autouse default_test_env fixture reads GWPROACTOR_TEST_DOTENV_PATH
# (or falls back to tests/.env-gwproactor-test). Default local pytest runs here to a
# repo-owned non-TLS env file so local tests do not require fresh certs by default.
os.environ.setdefault("GWPROACTOR_TEST_DOTENV_PATH", DEFAULT_LOCAL_TEST_DOTENV_PATH)

set_test_certificate_cache_dir(Path(__file__).parent / ".certificate_cache")
set_hardware_layout_test_path(TEST_HARDWARE_LAYOUT_PATH)

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
