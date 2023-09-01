# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum

__all__ = [
    "AdaptorState",
    "AdaptorStates",
]


class AdaptorState(str, Enum):
    """
    Enumeration of the different states an adaptor can be in.
    """

    NOT_STARTED = "not_started"
    START = "start"
    RUN = "run"
    STOP = "stop"
    CLEANUP = "cleanup"
    CANCELED = "canceled"


class AdaptorStates(ABC):
    """
    Abstract class containing functions to transition an adaptor between states.
    """

    @abstractmethod
    def _start(self):  # pragma: no cover
        """
        Starts the adaptor.
        """
        pass

    @abstractmethod
    def _run(self, run_data: dict):  # pragma: no cover
        """
        Runs the adaptor.

        Args:
            run_data (dict): The data required to run the adaptor.
        """
        pass

    @abstractmethod
    def _stop(self):  # pragma: no cover
        """
        Stops the adaptor run.
        """
        pass

    @abstractmethod
    def _cleanup(self):  # pragma: no cover
        """
        Performs any cleanup the adaptor may need.
        """
        pass
