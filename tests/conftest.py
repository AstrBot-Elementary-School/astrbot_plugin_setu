import importlib
import os
import sys
import tempfile
from pathlib import Path
from types import ModuleType

import pytest

_runtime = tempfile.TemporaryDirectory(prefix="setu-integration-")
os.environ["ASTRBOT_ROOT"] = _runtime.name

ROOT = Path(__file__).resolve().parents[1]
package = ModuleType("setu_test_plugin")
package.__path__ = [str(ROOT)]
sys.modules[package.__name__] = package


@pytest.fixture
def load():
    return lambda name: importlib.import_module("setu_test_plugin." + name)
