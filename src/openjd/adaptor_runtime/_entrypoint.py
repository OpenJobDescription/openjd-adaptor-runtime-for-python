# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from __future__ import annotations

import logging
import os
import signal
import sys

from pathlib import Path
from argparse import ArgumentParser, Namespace
from types import FrameType as FrameType
from typing import TYPE_CHECKING, Any, Optional, Type, TypeVar, NamedTuple, Tuple

import jsonschema
import yaml

from .adaptors import AdaptorRunner, BaseAdaptor
from ._background import BackendRunner, FrontendRunner, InMemoryLogBuffer, LogBufferHandler
from .adaptors.configuration import (
    RuntimeConfiguration,
    ConfigurationManager,
)
from ._osname import OSName
from ._utils._logging import (
    _OPENJD_LOG_REGEX,
    ConditionalFormatter,
)
from .adaptors import SemanticVersion

if TYPE_CHECKING:  # pragma: no cover
    from .adaptors.configuration import AdaptorConfiguration

__all__ = ["EntryPoint"]

_U = TypeVar("_U", bound=BaseAdaptor)

_ADAPTOR_CLI_VERSION = SemanticVersion(major=0, minor=1)
_CLI_HELP_TEXT = {
    "init_data": (
        "Data to pass to the adaptor during initialization. "
        "This can be a JSON string or the path to a file containing a JSON string in the format "
        "file://path/to/file.json"
    ),
    "run_data": (
        "Data to pass to the adaptor when it is being run. "
        "This can be a JSON string or the path to a file containing a JSON string in the format "
        "file://path/to/file.json"
    ),
    "path_mapping_rules": (
        "Path mapping rules to make available to the adaptor while it's running. "
        "This can be a JSON string or the path to a file containing a JSON string in the format "
        "file://path/to/file.json"
    ),
    "show_config": ("Prints the adaptor runtime configuration, then the program exits."),
    "connection_file": "The file path to the connection file for use in background mode.",
}

_DIR = os.path.dirname(os.path.realpath(__file__))
# Keyword args to init the ConfigurationManager for the runtime.
_ENV_CONFIG_PATH_PREFIX = "RUNTIME_CONFIG_PATH"
_system_config_path_prefix = "/etc" if OSName.is_posix() else os.environ["PROGRAMDATA"]
_system_config_path = os.path.abspath(
    os.path.join(
        _system_config_path_prefix,
        "openjd",
        "worker",
        "adaptors",
        "runtime",
        "configuration.json",
    )
)

_runtime_config_paths: dict[Any, Any] = {
    "schema_path": os.path.abspath(os.path.join(_DIR, "configuration.schema.json")),
    "default_config_path": os.path.abspath(os.path.join(_DIR, "configuration.json")),
    "system_config_path": _system_config_path,
    "user_config_rel_path": os.path.join(
        ".openjd", "worker", "adaptors", "runtime", "configuration.json"
    ),
}

_logger = logging.getLogger(__name__)


class _LogConfig(NamedTuple):
    formatter: ConditionalFormatter
    stream_handler: logging.StreamHandler
    runtime_logger: logging.Logger
    adaptor_logger: logging.Logger


class _IntegrationData(NamedTuple):
    init_data: dict
    run_data: dict
    path_mapping_data: dict


class _VersionInfo(NamedTuple):
    adaptor_cli_version: SemanticVersion
    integration_data_interface_version: SemanticVersion

    def has_compatibility_with(self, expected: "_VersionInfo") -> bool:
        """Returns a boolean representing if the versions of this adaptor CLI and integration data
        interface are compatible with the expected adaptor CLI and integration data interface.

        This check is NOT commutative. It is assumed that self contains the versions of the
        installed (running) Adaptor and that the VersionInfo being passed contains the versions
        expected by something like a job template.

        Args:
            other (_VersionInfo): The VersionInfo to compare with.
        """
        return self.adaptor_cli_version.has_compatibility_with(
            expected.adaptor_cli_version
        ) and self.integration_data_interface_version.has_compatibility_with(
            expected.integration_data_interface_version
        )


class EntryPoint:
    """
    The main entry point of the adaptor runtime.
    """

    def __init__(self, adaptor_class: Type[_U]) -> None:
        self.adaptor_class = adaptor_class
        # This will be the current AdaptorRunner when using the 'run' command, rather than
        # 'background' command
        self._adaptor_runner: Optional[AdaptorRunner] = None

    def _init_loggers(self) -> _LogConfig:
        "Creates runtime/adaptor loggers"
        formatter = ConditionalFormatter(
            "%(levelname)s: %(message)s", ignore_patterns=[_OPENJD_LOG_REGEX]
        )
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)

        runtime_logger = logging.getLogger(__package__)
        runtime_logger.setLevel(logging.INFO)  # Start with INFO, will get updated with config
        runtime_logger.addHandler(stream_handler)

        adaptor_logger = logging.getLogger(self.adaptor_class.__module__.split(".")[0])
        adaptor_logger.addHandler(stream_handler)

        return _LogConfig(formatter, stream_handler, runtime_logger, adaptor_logger)

    def _init_config(self) -> None:
        """Initializes self.config_manager"""
        additional_config_path = os.environ.get(_ENV_CONFIG_PATH_PREFIX)
        self.config_manager = ConfigurationManager(
            config_cls=RuntimeConfiguration,
            **_runtime_config_paths,
            additional_config_paths=[additional_config_path] if additional_config_path else [],
        )
        try:
            self.config = self.config_manager.build_config()
        except jsonschema.ValidationError as e:
            _logger.error(f"Nonvalid runtime configuration file: {e}")
            raise
        except NotImplementedError as e:
            _logger.warning(
                f"The current system ({OSName()}) is not supported for runtime "
                f"configuration. Only the default configuration will be loaded. Full error: {e}"
            )
            # The above call to build_config() would have already successfully retrieved the
            # default config for this error to be raised, so we can assume the default config
            # is valid here.
            self.config = self.config_manager.get_default_config()

    def _get_version_info(self) -> _VersionInfo:
        return _VersionInfo(
            adaptor_cli_version=_ADAPTOR_CLI_VERSION,
            integration_data_interface_version=self.adaptor_class(
                {}
            ).integration_data_interface_version,
        )

    def _get_integration_data(self, parsed_args: Namespace) -> _IntegrationData:
        return _IntegrationData(
            init_data=parsed_args.init_data if hasattr(parsed_args, "init_data") else {},
            run_data=parsed_args.run_data if hasattr(parsed_args, "run_data") else {},
            path_mapping_data=parsed_args.path_mapping_rules
            if hasattr(parsed_args, "path_mapping_rules")
            else {},
        )

    def start(self, reentry_exe: Optional[Path] = None) -> None:
        """
        Starts the run of the adaptor.

        Args:
            reentry_exe (Path): The path to the binary executable that for adaptor reentry.
        """
        log_config = self._init_loggers()
        parser, parsed_args = self._parse_args()
        version_info = self._get_version_info()

        if parsed_args.command == "is-compatible":
            return self._handle_is_compatible(version_info, parsed_args, parser)
        elif parsed_args.command == "version-info":
            return print(
                yaml.dump(
                    {
                        "OpenJD Adaptor CLI Version": str(version_info.adaptor_cli_version),
                        f"{self.adaptor_class.__name__} Data Interface Version": str(
                            version_info.integration_data_interface_version
                        ),
                    },
                    indent=2,
                )
            )
        self._init_config()
        if not parsed_args.command:
            parser.print_help()
            parser.error("No command was provided.")
        elif parsed_args.command == "show-config":
            return print(yaml.dump(self.config.config, indent=2))

        integration_data = self._get_integration_data(parsed_args)

        adaptor: BaseAdaptor[AdaptorConfiguration] = self.adaptor_class(
            integration_data.init_data, path_mapping_data=integration_data.path_mapping_data
        )

        log_config.adaptor_logger.setLevel(adaptor.config.log_level)
        log_config.runtime_logger.setLevel(self.config.log_level)

        if parsed_args.command == "run":
            return self._handle_run(adaptor, integration_data)
        elif parsed_args.command == "daemon":  # pragma: no branch
            return self._handle_daemon(
                adaptor, parsed_args, log_config, integration_data, reentry_exe
            )

    def _handle_is_compatible(
        self, version_info: _VersionInfo, parsed_args: Namespace, parser: ArgumentParser
    ):
        try:
            expected_version_info = _VersionInfo(
                SemanticVersion.parse(parsed_args.openjd_adaptor_cli_version),
                SemanticVersion.parse(parsed_args.integration_data_interface_version),
            )
        except ValueError as e:
            parser.error(str(e))
            return

        if not version_info.has_compatibility_with(expected_version_info):
            parser.error(
                "Installed interface versions are incompatible with expected:"
                "\nInstalled:"
                f"\n\tOpenJD Adaptor CLI Version: {version_info.adaptor_cli_version}"
                f"\n\t{self.adaptor_class.__name__} Data Interface Version: {version_info.integration_data_interface_version}"
                "\nExpected:"
                f"\n\tOpenJD Adaptor CLI Version: {expected_version_info.adaptor_cli_version}"
                f"\n\t{self.adaptor_class.__name__} Data Interface Version: {expected_version_info.integration_data_interface_version}"
            )
        else:
            print(
                "Installed interface versions are compatible with expected:"
                "\nInstalled:"
                f"\n\tOpenJD Adaptor CLI Version: {version_info.adaptor_cli_version}"
                f"\n\t{self.adaptor_class.__name__} Data Interface Version: {version_info.integration_data_interface_version}"
                "\nExpected:"
                f"\n\tOpenJD Adaptor CLI Version: {expected_version_info.adaptor_cli_version}"
                f"\n\t{self.adaptor_class.__name__} Data Interface Version: {expected_version_info.integration_data_interface_version}"
            )
            return

    def _handle_run(
        self, adaptor: BaseAdaptor[AdaptorConfiguration], integration_data: _IntegrationData
    ):
        self._adaptor_runner = AdaptorRunner(adaptor=adaptor)
        # To be able to handle cancelation via signals
        signal.signal(signal.SIGINT, self._sigint_handler)
        if OSName.is_posix():  # pragma: is-windows
            signal.signal(signal.SIGTERM, self._sigint_handler)
        else:  # pragma: is-posix
            signal.signal(signal.SIGBREAK, self._sigint_handler)  # type: ignore[attr-defined]
        try:
            self._adaptor_runner._start()
            self._adaptor_runner._run(integration_data.run_data)
            self._adaptor_runner._stop()
            self._adaptor_runner._cleanup()
        except Exception as e:
            _logger.error(f"Error running the adaptor: {e}")
            try:
                self._adaptor_runner._cleanup()
            except Exception as e:
                _logger.error(f"Error cleaning up the adaptor: {e}")
                raise
            raise

    def _handle_daemon(
        self,
        adaptor: BaseAdaptor[AdaptorConfiguration],
        parsed_args: Namespace,
        log_config: _LogConfig,
        integration_data: _IntegrationData,
        reentry_exe: Optional[Path] = None,
    ):
        connection_file = parsed_args.connection_file
        if not os.path.isabs(connection_file):
            connection_file = os.path.abspath(connection_file)
        subcommand = parsed_args.subcommand if hasattr(parsed_args, "subcommand") else None

        if subcommand == "_serve":
            # Replace stream handler with log buffer handler since output will be buffered in
            # background mode
            log_buffer = InMemoryLogBuffer(formatter=log_config.formatter)
            buffer_handler = LogBufferHandler(log_buffer)
            for logger in [log_config.runtime_logger, log_config.adaptor_logger]:
                logger.removeHandler(log_config.stream_handler)
                logger.addHandler(buffer_handler)

            # This process is running in background mode. Create the backend server and serve
            # forever until a shutdown is requested
            backend = BackendRunner(
                AdaptorRunner(adaptor=adaptor),
                connection_file,
                log_buffer=log_buffer,
            )
            backend.run()
        else:
            # This process is running in frontend mode. Create the frontend runner and send
            # the appropriate request to the backend.
            frontend = FrontendRunner(connection_file)
            if subcommand == "start":
                adaptor_module = sys.modules.get(self.adaptor_class.__module__)
                if adaptor_module is None:
                    raise ModuleNotFoundError(
                        f"Adaptor module is not loaded: {self.adaptor_class.__module__}"
                    )

                frontend.init(
                    adaptor_module,
                    integration_data.init_data,
                    integration_data.path_mapping_data,
                    reentry_exe,
                )
                frontend.start()
            elif subcommand == "run":
                frontend.run(integration_data.run_data)
            elif subcommand == "stop":
                frontend.stop()
                frontend.shutdown()

    def _parse_args(self) -> Tuple[ArgumentParser, Namespace]:
        parser = self._build_argparser()
        try:
            return parser, parser.parse_args(sys.argv[1:])
        except Exception as e:
            _logger.error(f"Error parsing command line arguments: {e}")
            raise

    def _build_argparser(self) -> ArgumentParser:
        parser = ArgumentParser(
            prog="adaptor_runtime",
            add_help=True,
            usage=f"{self.adaptor_class.__name__} <command> [arguments]",
        )
        subparser = parser.add_subparsers(dest="command", title="commands")

        subparser.add_parser("show-config", help=_CLI_HELP_TEXT["show_config"])
        subparser.add_parser(
            "version-info",
            help="Prints CLI and data interface versions, then the program exits.",
        )

        compat_parser = subparser.add_parser(
            "is-compatible",
            help="Validates compatiblity for the adaptor CLI interface and integration data interface provided",
        )
        compat_parser.add_argument(
            "--openjd-adaptor-cli-version",
            metavar="<Major.Minor>",
            help="The version of the openjd adaptor CLI to compare with the installed adaptor.",
            required=True,
        )
        compat_parser.add_argument(
            "--integration-data-interface-version",
            metavar="<Major.Minor>",
            help=f"The version of the {self.adaptor_class.__name__}'s data interface to compare with the installed adaptor.",
            required=True,
        )

        init_data = ArgumentParser(add_help=False)
        init_data.add_argument(
            "--init-data", default="", type=_load_data, help=_CLI_HELP_TEXT["init_data"]
        )
        run_data = ArgumentParser(add_help=False)
        run_data.add_argument(
            "--run-data", default="", type=_load_data, help=_CLI_HELP_TEXT["run_data"]
        )

        path_mapping_rules = ArgumentParser(add_help=False)
        path_mapping_rules.add_argument(
            "--path-mapping-rules",
            default="",
            required=False,
            type=_load_data,
            help=_CLI_HELP_TEXT["path_mapping_rules"],
        )

        subparser.add_parser(
            "run",
            parents=[init_data, path_mapping_rules, run_data],
            help="Run through the start, run, stop, cleanup adaptor states.",
        )

        connection_file = ArgumentParser(add_help=False)
        connection_file.add_argument(
            "--connection-file",
            default="",
            help=_CLI_HELP_TEXT["connection_file"],
            required=True,
        )

        bg_parser = subparser.add_parser("daemon", help="Runs the adaptor in a daemon mode.")
        bg_subparser = bg_parser.add_subparsers(
            dest="subcommand",
            title="subcommands",
            required=True,
            # Explicitly set the metavar to "hide" the "_serve" command
            metavar="{start,run,stop}",
        )

        # "Hidden" command that actually runs the adaptor runtime in background mode
        bg_subparser.add_parser("_serve", parents=[init_data, path_mapping_rules, connection_file])

        bg_subparser.add_parser("start", parents=[init_data, path_mapping_rules, connection_file])
        bg_subparser.add_parser("run", parents=[run_data, connection_file])
        bg_subparser.add_parser("stop", parents=[connection_file])

        return parser

    def _sigint_handler(self, signum: int, frame: Optional[FrameType]) -> None:
        """Signal handler that is invoked when the process receives a SIGINT/SIGTERM"""
        if self._adaptor_runner is not None:
            _logger.info("Interruption signal recieved.")
            # OpenJD dictates that a SIGTERM/SIGINT results in a cancel workflow being
            # kicked off.
            self._adaptor_runner._cancel()


def _load_data(data: str) -> dict:
    """
    Parses an input JSON/YAML (filepath or string-encoded) into a dictionary.

    Args:
        data (str): The filepath or string representation of the JSON/YAML to parse.

    Raises:
        ValueError: Raised when the JSON/YAML is not parsed to a dictionary.
    """
    if not data:
        return {}

    try:
        loaded_data = _load_yaml_json(data)
    except OSError as e:
        _logger.error(f"Failed to open data file: {e}")
        raise
    except yaml.YAMLError as e:
        _logger.error(f"Failed to load data as JSON or YAML: {e}")
        raise

    if not isinstance(loaded_data, dict):
        raise ValueError(f"Expected loaded data to be a dict, but got {type(loaded_data)}")

    return loaded_data


def _load_yaml_json(data: str) -> Any:
    """
    Loads a YAML/JSON file/string.

    Note that yaml.safe_load() is capable of loading JSON documents.
    """
    loaded_yaml = None
    if data.startswith("file://"):
        filepath = data[len("file://") :]
        with open(filepath) as yaml_file:
            loaded_yaml = yaml.safe_load(yaml_file)
    else:
        loaded_yaml = yaml.safe_load(data)

    return loaded_yaml
