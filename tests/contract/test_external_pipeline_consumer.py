"""An installed product imports and collects its tests without importing demo packages."""

# test-owner: product
from __future__ import annotations

import os
import subprocess
import sys
import zipfile
from pathlib import Path

from stage_gen.provider_env import PROVIDER_ENV_KEYS


def _install_wheel(repository: Path, tmp_path: Path, environment: dict[str, str]) -> Path:
    wheels = tmp_path / "wheels"
    subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--no-isolation", "--outdir", str(wheels)],
        cwd=repository,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    # Materialize the built wheel into an external site-packages ownership root.
    installed = tmp_path / "site-packages"
    with zipfile.ZipFile(next(wheels.glob("*.whl"))) as archive:
        archive.extractall(installed)
    for module in (
        "stage_gen_legacy",
        "demo_game_tools",
        "demo_game_collection",
        "bellweather_pipeline",
        "iron_petal_unit_pipeline",
        "ember_hollow_pipeline",
        "the_grain_pipeline",
    ):
        assert not (installed / module).exists()
    return installed


def test_public_modules_and_components_import_without_optional_consumers() -> None:
    program = """
import importlib
import importlib.abc
import pkgutil
import sys
class NoConsumers(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {
            'demo_game_collection',
            'demo_game_tools',
            'iron_petal_unit_pipeline',
            'bellweather_pipeline',
            'stage_gen_legacy',
            'ember_hollow_pipeline',
            'the_grain_pipeline',
        }:
            raise AssertionError('Public surface imported optional consumer: ' + fullname)
sys.meta_path.insert(0, NoConsumers())
import stage_gen.runview
import stage_gen.application
import stage_gen.components
for module in pkgutil.iter_modules(stage_gen.components.__path__):
    if module.ispkg and not module.name.startswith('_'):
        importlib.import_module('stage_gen.components.' + module.name)
assert not any(
    name.split('.')[0] in {
        'stage_gen_legacy', 'demo_game_tools', 'demo_game_collection',
        'bellweather_pipeline', 'iron_petal_unit_pipeline',
        'ember_hollow_pipeline', 'the_grain_pipeline',
    }
    for name in sys.modules
)
print('public imports have no optional consumers')
"""
    completed = subprocess.run(
        [sys.executable, "-I", "-c", program], check=False, capture_output=True, text=True
    )
    assert completed.returncode == 0, completed.stderr


def test_selected_product_tests_collect_using_only_the_installed_core(tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[2]
    environment = os.environ.copy()
    for key in (*PROVIDER_ENV_KEYS, "PYTHONPATH"):
        environment.pop(key, None)
    environment["GRIDA_FX_DISABLE_DOTENV"] = "1"
    installed = _install_wheel(repository, tmp_path, environment)
    program = """
import importlib.abc
import sys
from pathlib import Path
installed, repository = map(Path, sys.argv[1:])
sys.path[:0] = [str(installed), str(repository)]
attempted = set()
class NoConsumers(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {
            'demo_game_collection',
            'demo_game_tools',
            'iron_petal_unit_pipeline',
            'bellweather_pipeline',
            'stage_gen_legacy',
            'ember_hollow_pipeline',
            'the_grain_pipeline',
        }:
            attempted.add(fullname)
            raise AssertionError('Product collection attempted an optional import: ' + fullname)
sys.meta_path.insert(0, NoConsumers())
from scripts.test_ownership import paths_for
import stage_gen
assert Path(stage_gen.__file__).is_relative_to(installed)
import pytest
status = pytest.main(['--collect-only', '-q', *paths_for(repository, 'product')])
assert not attempted, sorted(attempted)
raise SystemExit(status)
"""
    completed = subprocess.run(
        [sys.executable, "-I", "-c", program, str(installed), str(repository)],
        cwd=repository,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "tests collected" in completed.stdout
