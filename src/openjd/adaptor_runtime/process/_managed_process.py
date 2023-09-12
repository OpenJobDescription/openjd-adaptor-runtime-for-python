# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

"""Module for the ManagedProcess class"""
from __future__ import annotations

from abc import ABC as ABC, abstractmethod
from typing import List

from ..app_handlers import RegexHandler
from ._logging_subprocess import LoggingSubprocess

__all__ = ["ManagedProcess"]


class ManagedProcess(ABC):
    def __init__(
        self,
        run_data: dict,
        *,
        stdout_handler: RegexHandler | None = None,
        stderr_handler: RegexHandler | None = None,
    ):
        self.run_data = run_data
        self.stdout_handler = stdout_handler
        self.stderr_handler = stderr_handler

    # ===============================================
    #  Callbacks / virtual functions.
    # ===============================================

    @abstractmethod
    def get_executable(self) -> str:  # pragma: no cover
        """
        Return the path of the executable to run.
        """
        raise NotImplementedError()

    def get_arguments(self) -> List[str]:  # pragma: no cover
        """
        Return the args (as a list) to be used with the executable.
        """
        return []

    def get_startup_directory(self) -> str | None:  # pragma: no cover
        """
        Returns The directory that the executable should be run from.
        Note: Does not require that spaces be escaped
        """
        # This defaults to None because that is the default for Popen.
        return None

    # ===============================================
    #  Render Control
    # ===============================================

    def run(self):
        """
        Create a LoggingSubprocess to run the command.
        """
        exec = self.get_executable()
        args = self.get_arguments()
        args = [exec] + args
        startup_directory = self.get_startup_directory()

        subproc = LoggingSubprocess(
            args=args,
            startup_directory=startup_directory,
            stdout_handler=self.stdout_handler,
            stderr_handler=self.stderr_handler,
        )
        subproc.wait()
