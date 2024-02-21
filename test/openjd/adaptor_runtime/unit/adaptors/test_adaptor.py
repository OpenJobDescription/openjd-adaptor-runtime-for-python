# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from __future__ import annotations

from unittest.mock import Mock, patch

from openjd.adaptor_runtime.adaptors import Adaptor, SemanticVersion


class FakeAdaptor(Adaptor):
    """
    Test implementation of a Adaptor
    """

    def __init__(self, init_data: dict):
        super().__init__(init_data)

    def on_run(self, run_data: dict):
        pass

    @property
    def integration_data_interface_version(self) -> SemanticVersion:
        return SemanticVersion(major=0, minor=1)


class TestRun:
    """
    Tests for the Adaptor._run method
    """

    @patch.object(FakeAdaptor, "on_run", autospec=True)
    @patch.object(FakeAdaptor, "__init__", return_value=None, autospec=True)
    def test_run(self, mocked_init: Mock, mocked_on_run: Mock) -> None:
        # GIVEN
        init_data: dict = {}
        run_data: dict = {}
        adaptor = FakeAdaptor(init_data)

        # WHEN
        adaptor._run(run_data)

        # THEN
        mocked_init.assert_called_once_with(adaptor, init_data)
        mocked_on_run.assert_called_once_with(adaptor, run_data)

    @patch.object(FakeAdaptor, "on_start", autospec=True)
    def test_start(self, mocked_on_start: Mock) -> None:
        # GIVEN
        init_data: dict = {}
        adaptor = FakeAdaptor(init_data)

        # WHEN
        adaptor._start()

        # THEN
        mocked_on_start.assert_called_once_with(adaptor)

    @patch.object(FakeAdaptor, "on_stop", autospec=True)
    def test_stop(self, mocked_on_stop: Mock) -> None:
        # GIVEN
        init_data: dict = {}
        adaptor = FakeAdaptor(init_data)

        # WHEN
        adaptor._stop()

        # THEN
        mocked_on_stop.assert_called_once_with(adaptor)

    @patch.object(FakeAdaptor, "on_cleanup", autospec=True)
    def test_cleanup(self, mocked_on_cleanup: Mock) -> None:
        # GIVEN
        init_data: dict = {}
        adaptor = FakeAdaptor(init_data)

        # WHEN
        adaptor._cleanup()

        # THEN
        mocked_on_cleanup.assert_called_once_with(adaptor)
