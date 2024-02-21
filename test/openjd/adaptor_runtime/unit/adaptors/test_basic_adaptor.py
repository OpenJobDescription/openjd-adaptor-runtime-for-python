# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from __future__ import annotations

from unittest.mock import MagicMock, patch

from openjd.adaptor_runtime.adaptors import CommandAdaptor, SemanticVersion
from openjd.adaptor_runtime.process import ManagedProcess


class FakeCommandAdaptor(CommandAdaptor):
    """
    Test implementation of a CommandAdaptor
    """

    def __init__(self, init_data: dict):
        super().__init__(init_data)

    def get_managed_process(self, run_data: dict) -> ManagedProcess:
        return MagicMock()

    @property
    def integration_data_interface_version(self) -> SemanticVersion:
        return SemanticVersion(major=0, minor=1)


class TestRun:
    """
    Tests for the CommandAdaptor.run method
    """

    @patch.object(FakeCommandAdaptor, "get_managed_process")
    def test_runs_managed_process(self, get_managed_process_mock: MagicMock):
        # GIVEN
        run_data = {"run": "data"}
        adaptor = FakeCommandAdaptor({})

        # WHEN
        adaptor._run(run_data)

        # THEN
        get_managed_process_mock.assert_called_once_with(run_data)
        get_managed_process_mock.return_value.run.assert_called_once()
