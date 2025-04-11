# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

"""Module for the LoggingSubprocess class"""
from __future__ import annotations

import logging
import signal
import subprocess
import uuid
from types import TracebackType
from typing import Any, Sequence, TypeVar, Dict

from .._osname import OSName
from ..app_handlers import RegexHandler
from ._logging import _STDERR_LEVEL, _STDOUT_LEVEL
from ._stream_logger import StreamLogger

__all__ = ["LoggingSubprocess"]

_logger = logging.getLogger(__name__)


class LoggingSubprocess(object):
    """A process whose stdout/stderr lines are sent to a configurable logger"""

    _logger: logging.Logger
    _process: subprocess.Popen
    _stdout_logger: StreamLogger
    _stderr_logger: StreamLogger
    _terminate_threads: bool

    def __init__(
        self,
        *,
        # Required keyword-only arguments
        args: Sequence[str],
        # Optional keyword-only arguments
        startup_directory: str | None = None,  # This is None, because Popen's default is None
        logger: logging.Logger = _logger,
        stdout_handler: RegexHandler | None = None,
        stderr_handler: RegexHandler | None = None,
        encoding: str = "utf-8",
    ):
        if not logger:
            raise ValueError("No logger specified")
        if not args or len(args) < 1:
            raise ValueError("Insufficient args")

        self._terminate_threads = False
        self._logger = logger

        self._logger.info("Running command: %s", subprocess.list2cmdline(args))

        # Create the subprocess
        popen_params: Dict[str, Any] = dict(
            args=args,
            stdin=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdout=subprocess.PIPE,
            encoding=encoding,
            cwd=startup_directory,
        )
        if OSName.is_windows():  # pragma: is-posix
            # In Windows, this is required for signal. SIGBREAK will be sent to the entire process group.
            # Without this one, current process will also get the SIGBREAK and may react incorrectly.
            popen_params.update(creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)  # type: ignore[attr-defined]
        self._process = subprocess.Popen(**popen_params)

        if not self._process.stdout:  # pragma: no cover
            raise RuntimeError("process stdout not set")
        if not self._process.stderr:  # pragma: no cover
            raise RuntimeError("process stdout not set")

        # Create the stdout/stderr stream logging threads
        stdout_loggers = [self._logger]
        stderr_loggers = [self._logger]
        proc_uuid = uuid.uuid4()  # ensure loggers are unique to this process for regexhandlers

        def _register_handler(logger_name: str, handler: RegexHandler) -> logging.Logger:
            """Registers a handler with the logger name provided and returns the logger"""
            handler_logger = logging.getLogger(logger_name)
            handler_logger.setLevel(1)
            handler_logger.addHandler(handler)
            return handler_logger

        if stdout_handler is not None:
            stdout_loggers.append(_register_handler(f"stdout-{proc_uuid}", stdout_handler))
        if stderr_handler is not None:
            stderr_loggers.append(_register_handler(f"stderr-{proc_uuid}", stderr_handler))

        self._stdout_logger = StreamLogger(
            name="AdaptorRuntimeStdoutLogger",
            stream=self._process.stdout,
            loggers=stdout_loggers,
            level=_STDOUT_LEVEL,
        )
        self._stderr_logger = StreamLogger(
            name="AdaptorRuntimeStderrLogger",
            stream=self._process.stderr,
            loggers=stderr_loggers,
            level=_STDERR_LEVEL,
        )

        self._stdout_logger.start()
        self._stderr_logger.start()

    @property
    def pid(self) -> int:
        """Returns the PID of the sub-process"""
        return self._process.pid

    @property
    def returncode(self) -> int | None:
        """
        Before accessing this property, ensure the process has been terminated (calling wait() or
        terminate()). You can check is_running before accessing this value.

        :return: None if the process has not yet exited. Otherwise, it returns the exit code of the
                 process
        """
        # poll() is required to update the returncode
        # See https://docs.python.org/3/library/subprocess.html#subprocess.Popen.poll
        poll_result = self._process.poll()
        return poll_result

    @property
    def is_running(self) -> bool:
        """
        Determine whether the subprocess is running.
        :return: True if it is running; False otherwise
        """
        return self._process is not None and self._process.poll() is None

    def __enter__(self) -> LoggingSubprocess:
        return self

    def __exit__(self, type: TypeVar, value: Any, traceback: TracebackType) -> None:
        self.wait()

    def _cleanup_io_threads(self) -> None:
        self._logger.debug(
            "Finished terminating/waiting for the process. About to cleanup the IO threads."
        )

        # Wait for the logging threads to exit
        self._terminate_threads = True

        self._stdout_logger.join()
        if not self._process.stdout:  # pragma: no cover
            raise RuntimeError("process stdout not piped")
        # Must be after the join; before will cause an exception due to file in use.
        self._process.stdout.close()

        self._stderr_logger.join()
        if not self._process.stderr:  # pragma: no cover
            raise RuntimeError("process stderr not piped")
        # Must be after the join; before will cause an exception due to file in use.
        self._process.stderr.close()

    def terminate(self, grace_time_s: float = 60) -> None:
        """
        Sends a signal to soft terminate (SIGTERM) the process after the passed grace time (in
        seconds). If the grace time is 0 or the process hasn't terminated after the grace period,
        sending SIGKILL to interrupt/terminate the process.
        """
        if not self._process or self._terminate_threads:
            return
        self._logger.debug(f"Asked to terminate the subprocess (pid={self._process.pid}).")

        if not self.is_running:
            self._logger.info("Cannot terminate the process, because it is not running.")
            return

        # If we want to stop the process immediately.
        if grace_time_s == 0:
            self._logger.info(f"Immediately stopping process (pid={self._process.pid}).")
            self._process.kill()
            self._process.wait()
        else:
            signal_type: signal.Signals
            if OSName.is_windows():  # pragma: is-posix
                # We use `CREATE_NEW_PROCESS_GROUP` to create the process,
                # so pid here is also the process group id and SIGBREAK can be only sent to the process group.
                # Any processes in the process group will receive the SIGBREAK signal.
                signal_type = signal.CTRL_BREAK_EVENT  # type: ignore[attr-defined]
            else:  # pragma: is-windows
                signal_type = signal.SIGTERM

            self._logger.info(
                f"Sending the {signal_type.name} signal to pid={self._process.pid} and waiting {grace_time_s}"
                " seconds for it to exit."
            )
            self._process.send_signal(signal_type)

            try:
                self._process.wait(timeout=grace_time_s)
                self._logger.info(f"Finished terminating the subprocess (pid={self._process.pid}).")
            except subprocess.TimeoutExpired:
                self._logger.info(
                    f"Process (pid={self._process.pid}) did not complete in the allotted time "
                    f"after the {'SIGTERM' if OSName.is_posix() else 'SIGBREAK'} signal, "
                    f"now sending the SIGKILL signal."
                )
                self._process.kill()  # SIGKILL, on Windows, this is an alias for terminate
                self._process.wait()
                self._logger.info(f"Finished killing the subprocess (pid={self._process.pid}).")

        # _process.communicate will close the _process.stdout and _process.stderr.
        self._cleanup_io_threads()

    def wait(self) -> None:
        """
        Waits for the process to finish.
        """
        if not self._process or self._terminate_threads:
            return
        self._logger.info(f"Asked to wait for the subprocess (pid={self._process.pid}) to finish.")

        # Wait for the running process
        if self.is_running:
            if not self._process.stdin:  # pragma: no cover
                raise RuntimeError("process stdin not piped")
            self._process.stdin.close()

            self._logger.debug(f"Telling pid {self._process.pid} to wait.")
            self._process.wait()

            self._logger.info(f"Finished waiting for the subprocess (pid={self._process.pid}).")

            self._cleanup_io_threads()
