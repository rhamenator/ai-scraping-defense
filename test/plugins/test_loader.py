import importlib
import sys
from pathlib import Path


def _reload_plugins(monkeypatch, plugin_dir: Path):
    monkeypatch.setenv("PLUGIN_DIR", str(plugin_dir))
    from src import plugins as plugins_module

    importlib.reload(plugins_module)
    for name in list(sys.modules):
        if name.startswith("plugins."):
            del sys.modules[name]
    return plugins_module


def test_loads_valid_plugin(monkeypatch, tmp_path):
    plugin_path = tmp_path / "valid.py"
    plugin_path.write_text("def check(req):\n    return 0.5\n")
    plugins_module = _reload_plugins(monkeypatch, tmp_path)
    plugins = plugins_module.load_plugins(["valid"])
    assert len(plugins) == 1
    assert plugins[0](object()) == 0.5


def test_skips_symlink_outside(monkeypatch, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "evil.py").write_text("def check(req):\n    return 1\n")
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    (plugin_dir / "evil.py").symlink_to(outside / "evil.py")
    plugins_module = _reload_plugins(monkeypatch, plugin_dir)
    assert plugins_module.load_plugins(["evil"]) == []


def test_skips_plugin_missing_check(monkeypatch, tmp_path):
    (tmp_path / "nocheck.py").write_text("x = 1\n")
    plugins_module = _reload_plugins(monkeypatch, tmp_path)
    assert plugins_module.load_plugins(["nocheck"]) == []


def test_no_duplicate_sys_modules(monkeypatch, tmp_path):
    plugin_path = tmp_path / "dup.py"
    plugin_path.write_text("def check(req):\n    return 0.1\n")
    plugins_module = _reload_plugins(monkeypatch, tmp_path)
    first = plugins_module.load_plugins(["dup"])
    assert len(first) == 1
    before = [name for name in sys.modules if name.startswith("plugins.")]
    second = plugins_module.load_plugins(["dup"])
    after = [name for name in sys.modules if name.startswith("plugins.")]
    assert len(second) == 1
    assert before == after
