import importlib.util
import sys
from pathlib import Path


def load_common_module():
    root = Path(__file__).resolve().parents[1]
    module_path = root / "scripts" / "_apimart_common.py"
    spec = importlib.util.spec_from_file_location("_apimart_common", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
