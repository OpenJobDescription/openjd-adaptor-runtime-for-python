# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from __future__ import annotations

import logging

from ._adaptor_states import AdaptorState, AdaptorStates
from ._base_adaptor import BaseAdaptor as BaseAdaptor
from .._utils._constants import _OPENJD_FAIL_STDOUT_PREFIX

__all__ = ["AdaptorRunner"]

_logger = logging.getLogger(__name__)


class AdaptorRunner(AdaptorStates):
    """
    Class that is responsible for running adaptors.
    """

    def __init__(self, *, adaptor: BaseAdaptor):
        self.adaptor = adaptor
        self.state = AdaptorState.NOT_STARTED

    def _start(self):
        _logger.debug("Starting...")
        self.state = AdaptorState.START

        try:
            self.adaptor._start()
        except Exception as e:
            _fail(f"Error encountered while starting adaptor: {e}")
            raise

    def _run(self, run_data: dict):
        _logger.debug("Running task")
        self.state = AdaptorState.RUN

        try:
            self.adaptor._run(run_data)
        except Exception as e:
            _fail(f"Error encountered while running adaptor: {e}")
            raise

        _logger.debug("Task complete")

    def _stop(self):
        _logger.debug("Stopping...")
        self.state = AdaptorState.STOP

        try:
            self.adaptor._stop()
        except Exception as e:
            _fail(f"Error encountered while stopping adaptor: {e}")
            raise

    def _cleanup(self):
        _logger.debug("Cleaning up...")
        self.state = AdaptorState.CLEANUP

        try:
            self.adaptor._cleanup()
        except Exception as e:
            _fail(f"Error encountered while cleaning up adaptor: {e}")
            raise

        _logger.debug("Cleanup complete")

    def _cancel(self):
        _logger.debug("Canceling...")
        self.state = AdaptorState.CANCELED

        try:
            self.adaptor.cancel()
        except Exception as e:
            _fail(f"Error encountered while canceling the adaptor: {e}")
            raise

        _logger.debug("Cancel complete")


def _fail(reason: str):
    _logger.error(f"{_OPENJD_FAIL_STDOUT_PREFIX}{reason}")
