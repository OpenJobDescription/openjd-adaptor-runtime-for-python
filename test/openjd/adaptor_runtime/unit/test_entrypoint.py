# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from __future__ import annotations

import argparse
import json
import os
import signal
from pathlib import Path
from typing import Optional
from unittest.mock import ANY, MagicMock, Mock, PropertyMock, mock_open, patch

import jsonschema
import pytest
import yaml

import openjd.adaptor_runtime._entrypoint as runtime_entrypoint
from openjd.adaptor_runtime import EntryPoint
from openjd.adaptor_runtime.adaptors.configuration import (
    ConfigurationManager,
    RuntimeConfiguration,
)
from openjd.adaptor_runtime.adaptors import BaseAdaptor, SemanticVersion
from openjd.adaptor_runtime._background import BackendRunner, FrontendRunner
from openjd.adaptor_runtime._background.frontend_runner import _FRONTEND_RUNNER_REQUEST_TIMEOUT
from openjd.adaptor_runtime._background.model import ConnectionSettings
from openjd.adaptor_runtime._osname import OSName
from openjd.adaptor_runtime._entrypoint import _load_data

from .adaptors.fake_adaptor import FakeAdaptor
from .adaptors.configuration.stubs import AdaptorConfigurationStub, RuntimeConfigurationStub


@pytest.fixture(autouse=True)
def mock_configuration():
    with patch.object(
        ConfigurationManager, "build_config", return_value=RuntimeConfigurationStub()
    ):
        yield


@pytest.fixture(autouse=True)
def mock_logging():
    with (
        patch.object(
            BaseAdaptor,
            "config",
            new_callable=PropertyMock(return_value=AdaptorConfigurationStub()),
        ),
    ):
        yield


@pytest.fixture(autouse=True)
def mock_getLogger():
    with patch.object(runtime_entrypoint.logging, "getLogger"):
        yield


@pytest.fixture
def mock_adaptor_cls():
    mock_adaptor_cls = MagicMock()
    mock_adaptor_cls.return_value.config = AdaptorConfigurationStub()
    mock_adaptor_cls.return_value.integration_data_interface_version = SemanticVersion(
        major=1, minor=5
    )
    mock_adaptor_cls.__name__ = "MockAdaptor"
    return mock_adaptor_cls


class TestStart:
    """
    Tests for the EntryPoint.start method
    """

    def test_errors_with_no_command(
        self, mock_adaptor_cls: MagicMock, capsys: pytest.CaptureFixture[str]
    ):
        # GIVEN
        with (
            patch.object(runtime_entrypoint.sys, "argv", ["Adaptor"]),
            patch.object(argparse._sys, "exit") as sys_exit,  # type: ignore
        ):
            entrypoint = EntryPoint(mock_adaptor_cls)

            # WHEN
            entrypoint.start()

        # THEN
        captured = capsys.readouterr()
        assert "No command was provided." in captured.err
        sys_exit.assert_called_once_with(2)

    def test_version_info(
        self,
        mock_adaptor_cls: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ):
        # GIVEN
        with patch.object(
            runtime_entrypoint.sys,
            "argv",
            [
                "Adaptor",
                "version-info",
            ],
        ):
            entrypoint = EntryPoint(mock_adaptor_cls)

            # WHEN
            entrypoint.start()

        # THEN
        captured = capsys.readouterr()
        assert yaml.safe_load(captured.out) == {
            "OpenJD Adaptor CLI Version": str(runtime_entrypoint._ADAPTOR_CLI_VERSION),
            "MockAdaptor Data Interface Version": "1.5",
        }

    @pytest.mark.parametrize("integration_version", ["1.4", "1.5"])
    def test_is_compatible(
        self,
        mock_adaptor_cls: MagicMock,
        capsys: pytest.CaptureFixture[str],
        integration_version: str,
    ):
        # GIVEN
        with patch.object(
            runtime_entrypoint.sys,
            "argv",
            [
                "Adaptor",
                "is-compatible",
                "--openjd-adaptor-cli-version",
                str(runtime_entrypoint._ADAPTOR_CLI_VERSION),
                "--integration-data-interface-version",
                integration_version,
            ],
        ):
            entrypoint = EntryPoint(mock_adaptor_cls)

            # WHEN
            entrypoint.start()

        # THEN
        captured = capsys.readouterr()
        assert "Installed interface versions are compatible with expected:" in captured.out

    def test_bad_version_string(
        self,
        mock_adaptor_cls: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ):
        # GIVEN
        def exit():
            raise Exception

        with (
            patch.object(
                runtime_entrypoint.sys,
                "argv",
                [
                    "Adaptor",
                    "is-compatible",
                    "--openjd-adaptor-cli-version",
                    str(runtime_entrypoint._ADAPTOR_CLI_VERSION),
                    "--integration-data-interface-version",
                    "1.0.0",
                ],
            ),
            patch.object(argparse._sys, "exit") as sys_exit,  # type: ignore
        ):
            entrypoint = EntryPoint(mock_adaptor_cls)

            # WHEN
            entrypoint.start()

        # THEN
        captured = capsys.readouterr()
        assert 'Provided version "1.0.0" was not of form Major.Minor' in captured.err
        sys_exit.assert_called_once_with(2)

    @pytest.mark.parametrize("integration_version", ["0.9", "1.6", "1.40", "1.50", "2.0"])
    def test_is_not_compatible(
        self,
        mock_adaptor_cls: MagicMock,
        capsys: pytest.CaptureFixture[str],
        integration_version: str,
    ):
        # GIVEN
        with (
            patch.object(
                runtime_entrypoint.sys,
                "argv",
                [
                    "Adaptor",
                    "is-compatible",
                    "--openjd-adaptor-cli-version",
                    str(runtime_entrypoint._ADAPTOR_CLI_VERSION),
                    "--integration-data-interface-version",
                    integration_version,
                ],
            ),
            patch.object(argparse._sys, "exit") as sys_exit,  # type: ignore
        ):
            entrypoint = EntryPoint(mock_adaptor_cls)

            # WHEN
            entrypoint.start()

        # THEN
        captured = capsys.readouterr()
        assert "Installed interface versions are incompatible with expected:" in captured.err
        sys_exit.assert_called_once_with(2)

    def test_creates_adaptor_with_init_data(self, mock_adaptor_cls: MagicMock):
        # GIVEN
        init_data = {"init": "data"}
        with patch.object(
            runtime_entrypoint.sys,
            "argv",
            [
                "Adaptor",
                "run",
                "--init-data",
                json.dumps(init_data),
            ],
        ):
            entrypoint = EntryPoint(mock_adaptor_cls)

            # WHEN
            entrypoint.start()

        # THEN
        mock_adaptor_cls.assert_called_with(init_data, path_mapping_data={})

    def test_creates_adaptor_with_path_mapping(self, mock_adaptor_cls: MagicMock):
        # GIVEN
        init_data = {"init": "data"}
        path_mapping_rules = {"path_mapping_rules": "data"}
        with patch.object(
            runtime_entrypoint.sys,
            "argv",
            [
                "Adaptor",
                "run",
                "--init-data",
                json.dumps(init_data),
                "--path-mapping-rules",
                json.dumps(path_mapping_rules),
            ],
        ):
            entrypoint = EntryPoint(mock_adaptor_cls)

            # WHEN
            entrypoint.start()

        # THEN
        mock_adaptor_cls.assert_called_with(init_data, path_mapping_data=path_mapping_rules)

    @patch.object(FakeAdaptor, "_cleanup")
    @patch.object(FakeAdaptor, "_start")
    def test_raises_adaptor_exception(
        self,
        mock_start: MagicMock,
        mock_cleanup: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ):
        # GIVEN
        mock_start.side_effect = Exception()
        with patch.object(runtime_entrypoint.sys, "argv", ["Adaptor", "run"]):
            entrypoint = EntryPoint(FakeAdaptor)

            # WHEN
            with pytest.raises(Exception) as raised_exc:
                entrypoint.start()

        # THEN
        assert raised_exc.value is mock_start.side_effect
        assert "Error running the adaptor: " in caplog.text
        mock_start.assert_called_once()
        mock_cleanup.assert_called_once()

    @patch.object(FakeAdaptor, "_cleanup")
    @patch.object(FakeAdaptor, "_start")
    def test_raises_adaptor_cleanup_exception(
        self,
        mock_start: MagicMock,
        mock_cleanup: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ):
        # GIVEN
        mock_start.side_effect = Exception()
        mock_cleanup.side_effect = Exception()
        with patch.object(runtime_entrypoint.sys, "argv", ["Adaptor", "run"]):
            entrypoint = EntryPoint(FakeAdaptor)

            # WHEN
            with pytest.raises(Exception) as raised_exc:
                entrypoint.start()

        # THEN
        assert raised_exc.value is mock_cleanup.side_effect
        assert "Error running the adaptor: " in caplog.text
        assert "Error cleaning up the adaptor: " in caplog.text
        mock_start.assert_called_once()
        mock_cleanup.assert_called_once()

    @patch.object(argparse.ArgumentParser, "parse_args")
    def test_raises_argparse_exception(
        self, mock_parse_args: MagicMock, caplog: pytest.LogCaptureFixture
    ):
        # GIVEN
        mock_parse_args.side_effect = Exception()
        entrypoint = EntryPoint(FakeAdaptor)

        # WHEN
        with pytest.raises(Exception) as raised_exc:
            entrypoint.start()

        # THEN
        assert raised_exc.value is mock_parse_args.side_effect
        assert "Error parsing command line arguments: " in caplog.text

    @patch.object(ConfigurationManager, "build_config")
    def test_raises_jsonschema_validation_err(
        self,
        mock_build_config: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ):
        # GIVEN
        mock_build_config.side_effect = jsonschema.ValidationError("")
        entrypoint = EntryPoint(FakeAdaptor)

        # WHEN
        with pytest.raises(jsonschema.ValidationError) as raised_err:
            entrypoint.start()

        # THEN
        mock_build_config.assert_called_once()
        assert raised_err.value is mock_build_config.side_effect
        assert "Nonvalid runtime configuration file: " in caplog.text

    @patch.object(ConfigurationManager, "get_default_config")
    @patch.object(ConfigurationManager, "build_config")
    def test_uses_default_config_on_unsupported_system(
        self,
        mock_build_config: MagicMock,
        mock_get_default_config: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ):
        # GIVEN
        mock_build_config.side_effect = NotImplementedError()
        mock_get_default_config.return_value = RuntimeConfigurationStub()
        entrypoint = EntryPoint(FakeAdaptor)

        # WHEN
        entrypoint._init_config()

        # THEN
        mock_build_config.assert_called_once()
        mock_get_default_config.assert_called_once()
        assert entrypoint.config is mock_get_default_config.return_value
        assert f"The current system ({OSName()}) is not supported for runtime "
        assert (
            "configuration. Only the default configuration will be loaded. Full error: "
            in caplog.text
        )

    @patch.object(ConfigurationManager, "build_config")
    @patch.object(RuntimeConfiguration, "config", new_callable=PropertyMock)
    @patch.object(runtime_entrypoint, "print")
    def test_shows_config(
        self,
        print_spy: MagicMock,
        mock_config: MagicMock,
        mock_build_config: MagicMock,
    ):
        # GIVEN
        config = {"key": "value"}
        mock_config.return_value = config
        mock_build_config.return_value = RuntimeConfiguration({})
        with patch.object(runtime_entrypoint.sys, "argv", ["Adaptor", "show-config"]):
            entrypoint = EntryPoint(FakeAdaptor)

            # WHEN
            entrypoint.start()

        # THEN
        mock_build_config.assert_called_once()
        mock_config.assert_called_once()
        print_spy.assert_called_once_with(yaml.dump(config, indent=2))

    def test_runs_in_run_mode(self, mock_adaptor_cls: MagicMock):
        # GIVEN
        init_data = {"init": "data"}
        run_data = {"run": "data"}
        with patch.object(
            runtime_entrypoint.sys,
            "argv",
            [
                "Adaptor",
                "run",
                "--init-data",
                json.dumps(init_data),
                "--run-data",
                json.dumps(run_data),
            ],
        ):
            entrypoint = EntryPoint(mock_adaptor_cls)

            # WHEN
            entrypoint.start()

        # THEN
        mock_adaptor_cls.assert_called_with(init_data, path_mapping_data=ANY)

        mock_adaptor_cls.return_value._start.assert_called_once()
        mock_adaptor_cls.return_value._run.assert_called_once_with(run_data)
        mock_adaptor_cls.return_value._stop.assert_called_once()
        mock_adaptor_cls.return_value._cleanup.assert_called_once()

    @patch.object(runtime_entrypoint, "AdaptorRunner")
    @patch.object(runtime_entrypoint.signal, "signal")
    def test_runmode_signal_hook(
        self,
        signal_mock: MagicMock,
        mock_adaptor_runner: MagicMock,
        mock_adaptor_cls: MagicMock,
    ):
        # GIVEN
        init_data = {"init": "data"}
        run_data = {"run": "data"}
        with patch.object(
            runtime_entrypoint.sys,
            "argv",
            [
                "Adaptor",
                "run",
                "--init-data",
                json.dumps(init_data),
                "--run-data",
                json.dumps(run_data),
            ],
        ):
            entrypoint = EntryPoint(mock_adaptor_cls)

            # WHEN
            entrypoint.start()
            entrypoint._sigint_handler(MagicMock(), MagicMock())

        # THEN
        signal_mock.assert_any_call(signal.SIGINT, entrypoint._sigint_handler)
        if OSName.is_posix():
            signal_mock.assert_any_call(signal.SIGTERM, entrypoint._sigint_handler)
        else:
            signal_mock.assert_any_call(signal.SIGBREAK, entrypoint._sigint_handler)  # type: ignore[attr-defined]
        mock_adaptor_runner.return_value._cancel.assert_called_once()

    @patch.object(runtime_entrypoint, "InMemoryLogBuffer")
    @patch.object(runtime_entrypoint, "AdaptorRunner")
    @patch.object(BackendRunner, "run")
    @patch.object(BackendRunner, "__init__", return_value=None)
    def test_runs_background_serve(
        self,
        mock_init: MagicMock,
        mock_run: MagicMock,
        mock_adaptor_runner: MagicMock,
        mock_log_buffer: MagicMock,
        mock_adaptor_cls: MagicMock,
    ):
        # GIVEN
        init_data = {"init": "data"}
        conn_file = Path(os.sep) / "path" / "to" / "conn_file"
        with patch.object(
            runtime_entrypoint.sys,
            "argv",
            [
                "Adaptor",
                "daemon",
                "_serve",
                "--init-data",
                json.dumps(init_data),
                "--connection-file",
                str(conn_file),
            ],
        ):
            entrypoint = EntryPoint(mock_adaptor_cls)

            # WHEN
            entrypoint.start()

        # THEN
        mock_adaptor_cls.assert_called_with(init_data, path_mapping_data=ANY)
        mock_adaptor_runner.assert_called_once_with(
            adaptor=mock_adaptor_cls.return_value,
        )
        mock_init.assert_called_once_with(
            mock_adaptor_runner.return_value,
            connection_file_path=conn_file.resolve(),
            log_buffer=mock_log_buffer.return_value,
        )
        mock_run.assert_called_once()

    @patch.object(runtime_entrypoint, "AdaptorRunner")
    @patch.object(BackendRunner, "run")
    @patch.object(BackendRunner, "__init__", return_value=None)
    @patch.object(runtime_entrypoint.signal, "signal")
    def test_background_serve_no_signal_hook(
        self,
        signal_mock: MagicMock,
        mock_init: MagicMock,
        mock_run: MagicMock,
        mock_runtime_entrypoint: MagicMock,
        mock_adaptor_cls: MagicMock,
    ):
        # GIVEN
        init_data = {"init": "data"}
        conn_file = os.path.join(os.sep, "path", "to", "conn_file")
        with patch.object(
            runtime_entrypoint.sys,
            "argv",
            [
                "Adaptor",
                "daemon",
                "_serve",
                "--init-data",
                json.dumps(init_data),
                "--connection-file",
                conn_file,
            ],
        ):
            entrypoint = EntryPoint(mock_adaptor_cls)

            # WHEN
            entrypoint.start()

        # THEN
        signal_mock.assert_not_called()

    @patch.object(FrontendRunner, "__init__", return_value=None)
    def test_background_start_raises_when_adaptor_module_not_loaded(
        self,
        mock_magic_init: MagicMock,
    ):
        # GIVEN
        conn_file = Path(os.sep) / "path" / "to" / "conn_file"
        with patch.object(
            runtime_entrypoint.sys,
            "argv",
            [
                "Adaptor",
                "daemon",
                "start",
                "--connection-file",
                str(conn_file),
            ],
        ):
            entrypoint = EntryPoint(FakeAdaptor)

            # WHEN
            with patch.dict(runtime_entrypoint.sys.modules, {FakeAdaptor.__module__: None}):
                with pytest.raises(ModuleNotFoundError) as raised_err:
                    entrypoint.start()

        # THEN
        assert raised_err.match(f"Adaptor module is not loaded: {FakeAdaptor.__module__}")
        mock_magic_init.assert_called_once_with(timeout_s=_FRONTEND_RUNNER_REQUEST_TIMEOUT)

    @pytest.mark.parametrize(
        argnames="reentry_exe",
        argvalues=[
            (None,),
            (Path("reeentry_exe_value"),),
        ],
    )
    @patch.object(FrontendRunner, "__init__", return_value=None)
    @patch.object(FrontendRunner, "init")
    @patch.object(FrontendRunner, "start")
    def test_runs_background_start(
        self,
        mock_start: MagicMock,
        mock_init: MagicMock,
        mock_magic_init: MagicMock,
        reentry_exe: Optional[Path],
    ):
        # GIVEN
        conn_file = Path(os.sep) / "path" / "to" / "conn_file"
        with patch.object(
            runtime_entrypoint.sys,
            "argv",
            [
                "Adaptor",
                "daemon",
                "start",
                "--connection-file",
                str(conn_file),
            ],
        ):
            mock_adaptor_module = Mock()
            entrypoint = EntryPoint(FakeAdaptor)

            # WHEN
            with patch.dict(
                runtime_entrypoint.sys.modules, {FakeAdaptor.__module__: mock_adaptor_module}
            ):
                entrypoint.start(reentry_exe=reentry_exe)

        # THEN
        mock_magic_init.assert_called_once_with(timeout_s=_FRONTEND_RUNNER_REQUEST_TIMEOUT)
        mock_init.assert_called_once_with(
            adaptor_module=mock_adaptor_module,
            connection_file_path=conn_file.resolve(),
            init_data={},
            path_mapping_data={},
            reentry_exe=reentry_exe,
        )
        mock_start.assert_called_once_with()

    @patch.object(runtime_entrypoint.ConnectionSettingsFileLoader, "load")
    @patch.object(FrontendRunner, "__init__", return_value=None)
    @patch.object(FrontendRunner, "shutdown")
    @patch.object(FrontendRunner, "stop")
    def test_runs_background_stop(
        self,
        mock_end: MagicMock,
        mock_shutdown: MagicMock,
        mock_magic_init: MagicMock,
        mock_connection_settings_load: MagicMock,
    ):
        # GIVEN
        connection_settings = ConnectionSettings("socket")
        mock_connection_settings_load.return_value = connection_settings
        with patch.object(
            runtime_entrypoint.sys,
            "argv",
            [
                "Adaptor",
                "daemon",
                "stop",
                "--connection-file",
                "/path/to/conn/file",
            ],
        ):
            entrypoint = EntryPoint(FakeAdaptor)

            # WHEN
            entrypoint.start()

        # THEN
        mock_magic_init.assert_called_once_with(
            connection_settings=connection_settings, timeout_s=_FRONTEND_RUNNER_REQUEST_TIMEOUT
        )
        mock_end.assert_called_once()
        mock_shutdown.assert_called_once_with()

    @patch.object(runtime_entrypoint.ConnectionSettingsFileLoader, "load")
    @patch.object(FrontendRunner, "__init__", return_value=None)
    @patch.object(FrontendRunner, "run")
    def test_runs_background_run(
        self,
        mock_run: MagicMock,
        mock_magic_init: MagicMock,
        mock_connection_settings_load: MagicMock,
    ):
        # GIVEN
        conn_settings = ConnectionSettings("socket")
        mock_connection_settings_load.return_value = conn_settings
        run_data = {"run": "data"}
        with patch.object(
            runtime_entrypoint.sys,
            "argv",
            [
                "Adaptor",
                "daemon",
                "run",
                "--run-data",
                json.dumps(run_data),
                "--connection-file",
                "/path/to/conn/file",
            ],
        ):
            entrypoint = EntryPoint(FakeAdaptor)

            # WHEN
            entrypoint.start()

        # THEN
        mock_magic_init.assert_called_once_with(
            connection_settings=conn_settings, timeout_s=_FRONTEND_RUNNER_REQUEST_TIMEOUT
        )
        mock_run.assert_called_once_with(run_data)
        mock_connection_settings_load.assert_called_once()

    @patch.object(runtime_entrypoint.ConnectionSettingsFileLoader, "load")
    @patch.object(FrontendRunner, "__init__", return_value=None)
    @patch.object(FrontendRunner, "run")
    @patch.object(runtime_entrypoint.signal, "signal")
    def test_background_no_signal_hook(
        self,
        signal_mock: MagicMock,
        mock_run: MagicMock,
        mock_magic_init: MagicMock,
        mock_connection_settings_load: MagicMock,
    ):
        # GIVEN
        conn_file = Path(os.sep) / "path" / "to" / "conn_file"
        run_data = {"run": "data"}
        with patch.object(
            runtime_entrypoint.sys,
            "argv",
            [
                "Adaptor",
                "daemon",
                "run",
                "--run-data",
                json.dumps(run_data),
                "--connection-file",
                str(conn_file),
            ],
        ):
            entrypoint = EntryPoint(FakeAdaptor)

            # WHEN
            entrypoint.start()

        # THEN
        signal_mock.assert_not_called()

    @pytest.mark.parametrize(
        argnames="reentry_exe",
        argvalues=[
            (None,),
            (Path("reeentry_exe_value"),),
        ],
    )
    @patch.object(FrontendRunner, "__init__", return_value=None)
    @patch.object(FrontendRunner, "init")
    @patch.object(FrontendRunner, "start")
    def test_frontend_runner_timeout_override(
        self,
        mock_start: MagicMock,
        mock_init: MagicMock,
        mock_magic_init: MagicMock,
        reentry_exe: Optional[Path],
    ):
        # GIVEN
        test_timeout_override = 600
        conn_file = Path(os.sep) / "path" / "to" / "conn_file"
        with patch.object(
            runtime_entrypoint.sys,
            "argv",
            [
                "Adaptor",
                "daemon",
                "start",
                "--connection-file",
                str(conn_file),
            ],
        ):
            mock_adaptor_module = Mock()
            entrypoint = EntryPoint(FakeAdaptor)

            # WHEN
            with patch.dict(
                runtime_entrypoint.sys.modules, {FakeAdaptor.__module__: mock_adaptor_module}
            ):
                entrypoint.start(reentry_exe=reentry_exe, timeout_in_seconds=test_timeout_override)

        # THEN
        mock_magic_init.assert_called_once_with(timeout_s=test_timeout_override)
        mock_init.assert_called_once_with(
            adaptor_module=mock_adaptor_module,
            connection_file_path=conn_file.resolve(),
            init_data={},
            path_mapping_data={},
            reentry_exe=reentry_exe,
        )
        mock_start.assert_called_once_with()

    @patch.object(runtime_entrypoint, "ConnectionSettingsFileLoader")
    @patch.object(runtime_entrypoint, "FrontendRunner")
    def test_makes_connection_file_path_absolute(
        self,
        mock_runner: MagicMock,
        mock_connection_settings_loader: MagicMock,
    ):
        # GIVEN
        conn_file = Path("relpath")
        with patch.object(
            runtime_entrypoint.sys,
            "argv",
            [
                "Adaptor",
                "daemon",
                "run",
                "--connection-file",
                str(conn_file),
            ],
        ):
            entrypoint = EntryPoint(FakeAdaptor)

            # WHEN
            mock_is_absolute: MagicMock
            with (
                patch.object(
                    runtime_entrypoint.Path, "is_absolute", return_value=False
                ) as mock_is_absolute,
                patch.object(
                    runtime_entrypoint.Path, "absolute", return_value=Path("absolute")
                ) as mock_absolute,
            ):
                entrypoint.start()

        # THEN
        mock_is_absolute.assert_called_once()
        mock_absolute.assert_any_call()
        mock_connection_settings_loader.assert_called_once_with(mock_absolute.return_value)
        mock_runner.assert_called_once_with(
            connection_settings=mock_connection_settings_loader.return_value.load.return_value,
            timeout_s=_FRONTEND_RUNNER_REQUEST_TIMEOUT,
        )


class TestLoadData:
    """
    Tests for the _load_data method
    """

    def test_defaults_to_dict(self):
        assert _load_data("") == {}

    @pytest.mark.parametrize(
        argnames=["input", "expected"],
        argvalues=[
            [json.dumps({"hello": "world"}), {"hello": "world"}],
            [yaml.dump({"hello": "world"}), {"hello": "world"}],
        ],
        ids=["JSON", "YAML"],
    )
    def test_accepts_string(self, input: str, expected: dict, caplog: pytest.LogCaptureFixture):
        # WHEN
        output = _load_data(input)

        # THEN
        assert output == expected

    @pytest.mark.parametrize(
        argnames=["input", "expected"],
        argvalues=[
            [json.dumps({"hello": "world"}), {"hello": "world"}],
            [yaml.dump({"hello": "world"}), {"hello": "world"}],
        ],
        ids=["JSON", "YAML"],
    )
    def test_accepts_file(self, input: str, expected: dict):
        # GIVEN
        filepath = "/my/file"
        file_uri = f"file://{filepath}"

        # WHEN
        open_mock: MagicMock
        with patch.object(runtime_entrypoint, "open", mock_open(read_data=input)) as open_mock:
            output = _load_data(file_uri)

        # THEN
        assert output == expected
        open_mock.assert_called_once_with(filepath, encoding="utf-8")

    @patch.object(runtime_entrypoint, "open")
    def test_raises_on_os_error(self, mock_open: MagicMock, caplog: pytest.LogCaptureFixture):
        # GIVEN
        filepath = "/my/file.txt"
        file_uri = f"file://{filepath}"
        mock_open.side_effect = OSError()

        # WHEN
        with pytest.raises(OSError) as raised_err:
            _load_data(file_uri)

        # THEN
        assert raised_err.value is mock_open.side_effect
        mock_open.assert_called_once_with(filepath, encoding="utf-8")
        assert "Failed to open data file: " in caplog.text

    def test_raises_when_parsing_fails(self, caplog: pytest.LogCaptureFixture):
        # GIVEN
        input = "@"

        # WHEN
        with pytest.raises(yaml.YAMLError):
            _load_data(input)

        # THEN
        assert "Failed to load data as JSON or YAML: " in caplog.text

    def test_raises_on_nonvalid_parsed_data_type(self):
        # GIVEN
        input = "input"

        # WHEN
        with pytest.raises(ValueError) as raised_err:
            _load_data(input)

        # THEN
        assert raised_err.match(f"Expected loaded data to be a dict, but got {type(input)}")
