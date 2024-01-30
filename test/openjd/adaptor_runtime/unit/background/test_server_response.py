# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from unittest.mock import MagicMock
import pytest
from openjd.adaptor_runtime._osname import OSName

if OSName.is_windows():
    from openjd.adaptor_runtime._background.backend_named_pipe_server import (
        WinBackgroundNamedPipeServer,
    )
else:
    from openjd.adaptor_runtime._background.http_server import BackgroundHTTPServer

from openjd.adaptor_runtime._background.server_response import ServerResponseGenerator
from http import HTTPStatus


class TestServerResponseGenerator:
    def test_submits_work(self):
        # GIVEN
        def my_fn():
            pass

        args = ("one", "two")
        kwargs = {"three": 3, "four": 4}

        mock_future_runner = MagicMock()
        if OSName.is_windows():
            mock_server = MagicMock(spec=WinBackgroundNamedPipeServer)
        else:
            mock_server = MagicMock(spec=BackgroundHTTPServer)
        mock_server._future_runner = mock_future_runner
        mock_response_method = MagicMock()
        mock_server_response = MagicMock()
        mock_server_response.server = mock_server
        mock_server_response.response_method = mock_response_method

        # WHEN
        ServerResponseGenerator.submit(mock_server_response, my_fn, *args, **kwargs)

        # THEN
        mock_future_runner.submit.assert_called_once_with(my_fn, *args, **kwargs)
        mock_future_runner.wait_for_start.assert_called_once()
        # assert mock_response_method.assert_called_once_with(HTTPStatus.OK)
        mock_response_method.assert_called_once_with(HTTPStatus.OK)

    def test_returns_500_if_fails_to_submit_work(self, caplog: pytest.LogCaptureFixture):
        # GIVEN
        def my_fn():
            pass

        args = ("one", "two")
        kwargs = {"three": 3, "four": 4}

        if OSName.is_windows():
            mock_server = MagicMock(spec=WinBackgroundNamedPipeServer)
        else:
            mock_server = MagicMock(spec=BackgroundHTTPServer)
        mock_future_runner = MagicMock()
        exc = Exception()
        mock_future_runner.submit.side_effect = exc
        mock_server._future_runner = mock_future_runner
        mock_response_method = MagicMock()
        mock_server_response = MagicMock()
        mock_server_response.server = mock_server
        mock_server_response.response_method = mock_response_method

        # WHEN
        ServerResponseGenerator.submit(mock_server_response, my_fn, *args, **kwargs)

        # THEN
        mock_future_runner.submit.assert_called_once_with(my_fn, *args, **kwargs)
        mock_response_method.assert_called_once_with(
            HTTPStatus.INTERNAL_SERVER_ERROR, body=str(exc)
        )

        assert "Failed to submit work: " in caplog.text
