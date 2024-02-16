# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from abc import abstractmethod
from typing import TypeVar

from .configuration import AdaptorConfiguration
from ._base_adaptor import BaseAdaptor

__all__ = ["Adaptor"]

_T = TypeVar("_T", bound=AdaptorConfiguration)


class Adaptor(BaseAdaptor[_T]):
    """An Adaptor.

    Derived classes must override the on_run method, and may also optionally
    override the on_start, on_end, on_cleanup, and on_cancel methods.
    """

    # ===============================================
    #  Callbacks / virtual functions.
    # ===============================================

    def on_start(self):  # pragma: no cover
        """
        For job stickiness. Will start everything required for the Task. Will be used for all
        SubTasks.
        """
        pass

    @abstractmethod
    def on_run(self, run_data: dict):  # pragma: no cover
        """
        This will run for every task and will setup everything needed to render (including calling
        any managed processes). This will be overridden and defined in each advanced plugin.
        """
        pass

    def on_stop(self):  # pragma: no cover
        """
        For job stickiness. Will stop everything required for the Task before moving on to a new
        Task.
        """
        pass

    def on_cleanup(self):  # pragma: no cover
        """
        This callback will be any additional cleanup required by the adaptor.
        """
        pass

    # ===============================================
    # ===============================================

    def _start(self):  # pragma: no cover
        self.on_start()

    def _run(self, run_data: dict):
        """
        :param run_data: This is the data that changes between the different Tasks. Eg. frame
        number.
        """
        self.on_run(run_data)

    def _stop(self):  # pragma: no cover
        self.on_stop()

    def _cleanup(self):  # pragma: no cover
        self.on_cleanup()
