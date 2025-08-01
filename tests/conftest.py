"""Local pytest configuration"""

from pathlib import Path

import pytest

from gwproactor.config import DEFAULT_LAYOUT_FILE
from gwproactor_test import (
    restore_loggers, # noqa: F401
    clean_test_env,  # noqa: F401
    default_test_env,  # noqa: F401
    restore_loggers,  # noqa: F401
)
from gwproactor_test import set_hardware_layout_test_path
from gwproactor_test.pytest_options import add_live_test_options
from gwproactor_test.certs import set_test_certificate_cache_dir


TEST_DOTENV_PATH = "tests/.env-gw-spaceheat-test"
TEST_DOTENV_PATH_VAR = "GW_SPACEHEAT_TEST_DOTENV_PATH"
TEST_HARDWARE_LAYOUT_PATH = Path(__file__).parent / "config" / DEFAULT_LAYOUT_FILE

set_test_certificate_cache_dir(Path(__file__).parent / ".certificate_cache")
set_hardware_layout_test_path(TEST_HARDWARE_LAYOUT_PATH)

@pytest.fixture(autouse=True)
def always_restore_loggers(restore_loggers):
    ...


def pytest_addoption(parser: pytest.Parser) -> None:
    add_live_test_options(parser, include_tree=True)
