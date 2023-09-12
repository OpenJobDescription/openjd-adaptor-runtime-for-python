# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from __future__ import annotations

from abc import abstractmethod
from typing import TypeVar

from .configuration import AdaptorConfiguration
from ..process import ManagedProcess
from ._base_adaptor import BaseAdaptor

__all__ = [
    "CommandAdaptor",
]

_T = TypeVar("_T", bound=AdaptorConfiguration)


class CommandAdaptor(BaseAdaptor[_T]):
    """
    Base class for command adaptors that utilize a ManagedProcess.

    Derived classes must override the get_managed_process method, and
    may optionally override the on_prerun and on_postrun methods.
    """

    def _start(self):  # pragma: no cover
        pass

    def _run(self, run_data: dict):
        process = self.get_managed_process(run_data)

        self.on_prerun()
        process.run()
        self.on_postrun()

    def _stop(self):  # pragma: no cover
        pass

    def _cleanup(self):  # pragma: no cover
        pass

    @abstractmethod
    def get_managed_process(self, run_data: dict) -> ManagedProcess:  # pragma: no cover
        """
        Gets the ManagedProcess for this adaptor to run.

        Args:
            run_data (dict): The data required by the ManagedProcess.

        Returns:
            ManagedProcess: The ManagedProcess to run.
        """
        pass

    def on_prerun(self):  # pragma: no cover
        """
        Method that is invoked before the ManagedProcess is run.
        You can override this method to run code before the ManagedProcess is run.
        """
        pass

    def on_postrun(self):  # pragma: no cover
        """
        Method that is invoked after the ManagedProcess is run.
        You can override this method to run code after the ManagedProcess is run.
        """
        pass
