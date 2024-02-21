# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

import logging

from openjd.adaptor_runtime.adaptors import Adaptor, SemanticVersion

_logger = logging.getLogger(__name__)


class SampleAdaptor(Adaptor):
    """
    Adaptor class that is used for background mode integration tests.
    """

    def __init__(self, init_data: dict, **_):
        super().__init__(init_data)

    @property
    def integration_data_interface_version(self) -> SemanticVersion:
        return SemanticVersion(major=0, minor=1)

    def on_start(self):
        _logger.info("on_start")

    def on_run(self, run_data: dict):
        _logger.info(f"on_run: {run_data}")

    def on_stop(self):
        _logger.info("on_stop")

    def on_cleanup(self):
        _logger.info("on_cleanup")
