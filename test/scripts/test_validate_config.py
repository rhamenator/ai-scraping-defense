from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from scripts import validate_config


def _fake_config(app_env: str = "staging") -> SimpleNamespace:
    return SimpleNamespace(
        model_uri="sklearn:///model",
        app_env=SimpleNamespace(value=app_env),
        tenant_id="tenant-123",
        log_level=SimpleNamespace(value="INFO"),
    )


def test_validate_configuration_injects_cli_environment(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("MODEL_URI=sklearn:///model\nTENANT_ID=tenant-123\n")

    loader = mock.Mock()
    loader.load_from_env.return_value = _fake_config()
    loader.validate_config.return_value = (True, [])

    with mock.patch.object(validate_config, "ConfigLoader", return_value=loader):
        result = validate_config.validate_configuration(
            env_file, strict=True, environment="staging"
        )

    assert result is True
    loader.load_from_env.assert_called_once()
    passed_env = loader.load_from_env.call_args.args[0]
    assert passed_env["APP_ENV"] == "staging"


def test_validate_configuration_fails_on_environment_conflict(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "MODEL_URI=sklearn:///model\nTENANT_ID=tenant-123\nAPP_ENV=production\n"
    )

    loader = mock.Mock()

    with mock.patch.object(validate_config, "ConfigLoader", return_value=loader):
        result = validate_config.validate_configuration(
            env_file, strict=True, environment="staging"
        )

    assert result is False
    loader.load_from_env.assert_not_called()
