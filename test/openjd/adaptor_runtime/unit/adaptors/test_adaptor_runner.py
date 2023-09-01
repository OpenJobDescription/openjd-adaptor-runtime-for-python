# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from unittest.mock import MagicMock, patch

import pytest

from openjd.adaptor_runtime.adaptors import AdaptorRunner

from .fake_adaptor import FakeAdaptor


class TestRun:
    """
    Tests for the AdaptorRunner._run method
    """

    @patch.object(FakeAdaptor, "_run")
    def test_runs_adaptor(self, adaptor_run_mock: MagicMock):
        # GIVEN
        run_data = {"run": "data"}
        runner = FakeAdaptorRunner()

        # WHEN
        runner._run(run_data)

        # THEN
        adaptor_run_mock.assert_called_once_with(run_data)

    @patch.object(FakeAdaptor, "_run")
    def test_run_throws(self, adaptor_run_mock: MagicMock, caplog: pytest.LogCaptureFixture):
        # GIVEN
        exc = Exception()
        adaptor_run_mock.side_effect = exc
        runner = FakeAdaptorRunner()

        # WHEN
        with pytest.raises(Exception) as raised_exc:
            runner._run({})

        # THEN
        assert raised_exc.value is exc
        assert "Error encountered while running adaptor: " in caplog.text


class TestStart:
    """
    Tests for the AdaptorRunner._start method
    """

    @patch.object(FakeAdaptor, "_start")
    def test_starts_adaptor(self, adaptor_start_mock: MagicMock):
        # GIVEN
        runner = FakeAdaptorRunner()

        # WHEN
        runner._start()

        # THEN
        adaptor_start_mock.assert_called_once()

    @patch.object(FakeAdaptor, "_start")
    def test_start_throws(self, adaptor_start_mock: MagicMock, caplog: pytest.LogCaptureFixture):
        # GIVEN
        exc = Exception()
        adaptor_start_mock.side_effect = exc
        runner = FakeAdaptorRunner()

        # WHEN
        with pytest.raises(Exception) as raised_exc:
            runner._start()

        # THEN
        assert raised_exc.value is exc
        assert "Error encountered while starting adaptor: " in caplog.text
        adaptor_start_mock.assert_called_once()


class TestStop:
    """
    Tests for the AdaptorRunner._stop method
    """

    @patch.object(FakeAdaptor, "_stop")
    def test_stops_adaptor(self, adaptor_end_mock: MagicMock):
        # GIVEN
        runner = FakeAdaptorRunner()

        # WHEN
        runner._stop()

        # THEN
        adaptor_end_mock.assert_called_once()

    @patch.object(FakeAdaptor, "_stop")
    def test_stop_throws(self, adaptor_end_mock: MagicMock, caplog: pytest.LogCaptureFixture):
        # GIVEN
        exc = Exception()
        adaptor_end_mock.side_effect = exc
        runner = FakeAdaptorRunner()

        # WHEN
        with pytest.raises(Exception) as raised_exc:
            runner._stop()

        # THEN
        assert raised_exc.value is exc
        assert "Error encountered while stopping adaptor: " in caplog.text
        adaptor_end_mock.assert_called_once()


class TestCleanup:
    """
    Tests for the AdaptorRunner._cleanup method
    """

    @patch.object(FakeAdaptor, "_cleanup")
    def test_cleanup_adaptor(self, adaptor_cleanup_mock: MagicMock):
        # GIVEN
        runner = FakeAdaptorRunner()

        # WHEN
        runner._cleanup()

        # THEN
        adaptor_cleanup_mock.assert_called_once()

    @patch.object(FakeAdaptor, "_cleanup")
    def test_cleanup_throws(
        self, adaptor_cleanup_mock: MagicMock, caplog: pytest.LogCaptureFixture
    ):
        # GIVEN
        exc = Exception()
        adaptor_cleanup_mock.side_effect = exc
        runner = FakeAdaptorRunner()

        # WHEN
        with pytest.raises(Exception) as raised_exc:
            runner._cleanup()

        # THEN
        assert raised_exc.value is exc
        assert "Error encountered while cleaning up adaptor: " in caplog.text
        adaptor_cleanup_mock.assert_called_once()


class TestCancel:
    """
    Tests for the AdaptorRunner._cancel method
    """

    @patch.object(FakeAdaptor, "cancel")
    def test_cancel_adaptor(self, adaptor_cancel_mock: MagicMock):
        # GIVEN
        runner = FakeAdaptorRunner()

        # WHEN
        runner._cancel()

        # THEN
        adaptor_cancel_mock.assert_called_once()

    @patch.object(FakeAdaptor, "cancel")
    def test_cancel_throws(self, adaptor_cancel_mock: MagicMock, caplog: pytest.LogCaptureFixture):
        # GIVEN
        exc = Exception()
        adaptor_cancel_mock.side_effect = exc
        runner = FakeAdaptorRunner()

        # WHEN
        with pytest.raises(Exception) as raised_exc:
            runner._cancel()

        # THEN
        assert raised_exc.value is exc
        assert "Error encountered while canceling the adaptor: " in caplog.text
        adaptor_cancel_mock.assert_called_once()


class FakeAdaptorRunner(AdaptorRunner):
    def __init__(self):
        super().__init__(adaptor=FakeAdaptor({}))
