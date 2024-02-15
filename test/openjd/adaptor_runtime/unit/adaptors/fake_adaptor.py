# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from __future__ import annotations

from openjd.adaptor_runtime.adaptors import BaseAdaptor, SemanticVersion

__all__ = ["FakeAdaptor"]


class FakeAdaptor(BaseAdaptor):
    def __init__(self, init_data: dict, **kwargs):
        super().__init__(init_data, **kwargs)

    @property
    def integration_data_interface_version(self) -> SemanticVersion:
        return SemanticVersion(major=0, minor=1)

    def _start(self):
        pass

    def _run(self, run_data: dict):
        pass

    def _cleanup(self):
        pass

    def _stop(self):
        pass
