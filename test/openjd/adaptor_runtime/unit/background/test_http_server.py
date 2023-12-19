# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

import json
import os
import socketserver
from http import HTTPStatus
from threading import Event
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from openjd.adaptor_runtime._background import server_response, http_server
from openjd.adaptor_runtime.adaptors import AdaptorRunner
from openjd.adaptor_runtime.adaptors._adaptor_runner import _OPENJD_FAIL_STDOUT_PREFIX
from openjd.adaptor_runtime._background.http_server import (
    BackgroundHTTPServer,
    BackgroundRequestHandler,
    BackgroundResourceRequestHandler,
    CancelHandler,
    StopHandler,
    HeartbeatHandler,
    RunHandler,
    ShutdownHandler,
    StartHandler,
)
from openjd.adaptor_runtime._background.server_response import (
    AsyncFutureRunner,
    ThreadPoolExecutor,
)
from openjd.adaptor_runtime._background.log_buffers import InMemoryLogBuffer
from openjd.adaptor_runtime._background.model import AdaptorState, BufferedOutput


@pytest.fixture
def fake_server() -> socketserver.BaseServer:
    class FakeServer(socketserver.BaseServer):
        def __init__(self) -> None:
            pass

    return FakeServer()


@pytest.fixture
def fake_request_handler() -> BackgroundRequestHandler:
    class FakeBackgroundRequestHandler(BackgroundRequestHandler):
        path: str = "/fake"

        def __init__(self) -> None:
            pass

    return FakeBackgroundRequestHandler()


class TestAsyncFutureRunner:
    """
    Tests for the AsyncFutureRunner class
    """

    @patch.object(ThreadPoolExecutor, "submit")
    def test_submit(self, mock_submit: MagicMock):
        # GIVEN
        mock_fn = MagicMock()
        args = ("hello", "world")
        kwargs = {"hello": "world"}
        runner = AsyncFutureRunner()

        # WHEN
        runner.submit(mock_fn, *args, **kwargs)

        # THEN
        mock_submit.assert_called_once_with(mock_fn, *args, **kwargs)

    @patch.object(AsyncFutureRunner, "is_running", new_callable=PropertyMock)
    def test_submit_raises_if_running(self, mock_is_running: MagicMock):
        # GIVEN
        mock_is_running.return_value = True
        runner = AsyncFutureRunner()

        # WHEN
        with pytest.raises(Exception) as raised_exc:
            runner.submit(print)

        # THEN
        mock_is_running.assert_called_once()
        assert raised_exc.match("Cannot submit new task while another task is running")

    @pytest.mark.parametrize(
        argnames=["running"],
        argvalues=[[True], [False]],
        ids=["Running", "Not running"],
    )
    def test_is_running_reflects_future(self, running: bool):
        # GIVEN
        mock_future = MagicMock()
        mock_future.running.return_value = running
        runner = AsyncFutureRunner()
        runner._future = mock_future

        # WHEN
        is_running = runner.is_running

        # THEN
        assert is_running == running
        mock_future.running.assert_called_once()

    @pytest.mark.parametrize(
        argnames=["running", "done", "expected"],
        argvalues=[
            [True, True, True],
            [True, False, True],
            [False, True, True],
            [False, False, False],
        ],
        ids=[
            "running and done",
            "running and not done",
            "not running and done",
            "not running and not done",
        ],
    )
    def test_has_started_reflects_future(self, running: bool, done: bool, expected: bool):
        # GIVEN
        mock_future = MagicMock()
        mock_future.running.return_value = running
        mock_future.done.return_value = done
        runner = AsyncFutureRunner()
        runner._future = mock_future

        # WHEN
        has_started = runner.has_started

        # THEN
        assert has_started == expected
        mock_future.running.assert_called_once()
        # Only assert done called if the OR expression was not short-circuited
        if not running:
            mock_future.done.assert_called_once()

    @patch.object(server_response.time, "sleep")
    @patch.object(AsyncFutureRunner, "has_started", new_callable=PropertyMock)
    def test_wait_for_start(self, mock_has_started, mock_sleep):
        # GIVEN
        mock_has_started.side_effect = [False, True]
        runner = AsyncFutureRunner()

        # WHEN
        runner.wait_for_start()

        # THEN
        assert mock_sleep.called_once_with(AsyncFutureRunner._WAIT_FOR_START_INTERVAL)


class TestBackgroundRequestHandler:
    """
    Tests for the BackgroundRequestHandler class
    """

    def test_init_raises_when_server_is_incompatible(self, fake_server: socketserver.BaseServer):
        # WHEN
        with pytest.raises(TypeError) as raised_err:
            BackgroundRequestHandler("".encode("utf-8"), "", fake_server)

        assert raised_err.match(
            f"Received incompatible server class. Expected {BackgroundHTTPServer.__name__}, "
            f"but got {type(fake_server)}"
        )


class TestBackgroundResourceRequestHandler:
    """
    Tests for the RequestHandler class
    """

    def test_server_property_raises(
        self,
        fake_server: socketserver.BaseServer,
        fake_request_handler: BackgroundRequestHandler,
    ):
        # GIVEN
        class FakeRequestHandler(BackgroundResourceRequestHandler):
            def __init__(self, handler: BackgroundRequestHandler) -> None:
                self.handler = handler

        fake_request_handler.server = fake_server
        handler = FakeRequestHandler(fake_request_handler)

        # WHEN
        with pytest.raises(TypeError) as raised_err:
            handler.server

        # THEN
        assert raised_err.match(
            f"Incompatible HTTP server class. Expected {BackgroundHTTPServer.__name__}, got: "
            + type(fake_server).__name__
        )


class TestHeartbeatHandler:
    """
    Tests for the HeartbeatHandler class
    """

    @pytest.mark.parametrize(
        argnames=[
            "is_running",
        ],
        argvalues=[
            [True],
            [False],
        ],
        ids=["working", "idle"],
    )
    def test_returns_adaptor_status(
        self,
        fake_request_handler: BackgroundRequestHandler,
        is_running: bool,
    ):
        # GIVEN
        mock_server = MagicMock(spec=BackgroundHTTPServer)
        mock_server._log_buffer = None

        mock_server._future_runner = MagicMock()
        mock_server._future_runner.is_running = is_running

        mock_server._adaptor_runner = MagicMock()
        mock_server._adaptor_runner.state = AdaptorState.NOT_STARTED

        fake_request_handler.server = mock_server
        fake_request_handler.headers = {"Content-Length": 0}  # type: ignore
        fake_request_handler.path = ""
        handler = HeartbeatHandler(fake_request_handler)

        # WHEN
        response = handler.get()

        # THEN
        expected_status = "working" if is_running else "idle"
        assert response.status == HTTPStatus.OK
        assert response.body == json.dumps(
            {
                "state": "not_started",
                "status": expected_status,
                "output": {
                    "id": BufferedOutput.EMPTY,
                    "output": "",
                },
                "failed": False,
            }
        )

    @patch.object(HeartbeatHandler, "_parse_ack_id")
    @patch.object(InMemoryLogBuffer, "chunk")
    def test_gets_log_buffer_chunk(
        self,
        mock_chunk: MagicMock,
        mock_parse_ack_id: MagicMock,
        fake_request_handler: BackgroundRequestHandler,
    ):
        # GIVEN
        mock_parse_ack_id.return_value = None
        expected_output = BufferedOutput("id", "output")
        mock_chunk.return_value = expected_output

        mock_server = MagicMock(spec=BackgroundHTTPServer)
        mock_server._log_buffer = InMemoryLogBuffer()

        mock_server._future_runner = MagicMock()
        mock_server._future_runner.is_running = True

        mock_server._adaptor_runner = MagicMock()
        mock_server._adaptor_runner.state = AdaptorState.RUN

        fake_request_handler.server = mock_server
        fake_request_handler.headers = {"Content-Length": 0}  # type: ignore
        fake_request_handler.path = ""
        handler = HeartbeatHandler(fake_request_handler)

        # WHEN
        response = handler.get()

        # THEN
        mock_parse_ack_id.assert_called_once()
        mock_chunk.assert_called_once()
        assert response.status == HTTPStatus.OK
        assert response.body == json.dumps(
            {
                "state": "run",
                "status": "working",
                "output": {
                    "id": expected_output.id,
                    "output": expected_output.output,
                },
                "failed": False,
            }
        )

    @pytest.mark.parametrize(
        argnames=["valid_ack_id"],
        argvalues=[[True], [False]],
        ids=["Valid ACK ID", "Nonvalid ACK ID"],
    )
    @patch.object(HeartbeatHandler, "_parse_ack_id")
    @patch.object(InMemoryLogBuffer, "clear")
    @patch.object(InMemoryLogBuffer, "chunk")
    def test_processes_ack_id(
        self,
        mock_chunk: MagicMock,
        mock_clear: MagicMock,
        mock_parse_ack_id: MagicMock,
        valid_ack_id: bool,
        fake_request_handler: BackgroundRequestHandler,
        caplog: pytest.LogCaptureFixture,
    ):
        # GIVEN
        caplog.set_level(0)
        expected_ack_id = "ack_id"
        mock_parse_ack_id.return_value = expected_ack_id
        expected_output = BufferedOutput("id", "output")
        mock_chunk.return_value = expected_output
        mock_clear.return_value = valid_ack_id

        mock_server = MagicMock(spec=BackgroundHTTPServer)
        mock_server._log_buffer = InMemoryLogBuffer()

        mock_server._future_runner = MagicMock()
        mock_server._future_runner.is_running = True

        mock_server._adaptor_runner = MagicMock()
        mock_server._adaptor_runner.state = AdaptorState.RUN

        fake_request_handler.server = mock_server
        fake_request_handler.headers = {"Content-Length": 0}  # type: ignore
        fake_request_handler.path = ""
        handler = HeartbeatHandler(fake_request_handler)

        # WHEN
        response = handler.get()

        # THEN
        mock_parse_ack_id.assert_called_once()
        mock_chunk.assert_called_once()
        mock_clear.assert_called_once_with(expected_ack_id)
        if valid_ack_id:
            assert f"Received ACK for chunk: {expected_ack_id}" in caplog.text
        else:
            assert f"Received ACK for old or invalid chunk: {expected_ack_id}" in caplog.text
        assert response.status == HTTPStatus.OK
        assert response.body == json.dumps(
            {
                "state": "run",
                "status": "working",
                "output": {
                    "id": expected_output.id,
                    "output": expected_output.output,
                },
                "failed": False,
            }
        )

    @patch.object(HeartbeatHandler, "_parse_ack_id")
    @patch.object(InMemoryLogBuffer, "chunk")
    def test_sets_failed_if_adaptor_fails(
        self,
        mock_chunk: MagicMock,
        mock_parse_ack_id: MagicMock,
        fake_request_handler: BackgroundRequestHandler,
    ) -> None:
        # GIVEN
        mock_parse_ack_id.return_value = None
        expected_output = BufferedOutput(
            "id",
            os.linesep.join(
                ["INFO: regular message", f"ERROR: {_OPENJD_FAIL_STDOUT_PREFIX}failure message"]
            ),
        )
        mock_chunk.return_value = expected_output

        mock_server = MagicMock(spec=BackgroundHTTPServer)
        mock_server._log_buffer = InMemoryLogBuffer()

        mock_server._future_runner = MagicMock()
        mock_server._future_runner.is_running = True

        mock_server._adaptor_runner = MagicMock()
        mock_server._adaptor_runner.state = AdaptorState.RUN

        fake_request_handler.server = mock_server
        fake_request_handler.headers = {"Content-Length": 0}  # type: ignore
        fake_request_handler.path = ""

        handler = HeartbeatHandler(fake_request_handler)

        # WHEN
        response = handler.get()

        # THEN
        mock_parse_ack_id.assert_called_once()
        mock_chunk.assert_called_once()
        assert response.status == HTTPStatus.OK
        assert response.body == json.dumps(
            {
                "state": "run",
                "status": "working",
                "output": {
                    "id": expected_output.id,
                    "output": expected_output.output,
                },
                "failed": True,
            }
        )

    class TestParseAckId:
        """
        Tests for the HeartbeatHandler._parse_ack_id method
        """

        @patch("urllib.parse.urlparse")
        @patch("urllib.parse.parse_qs")
        def test_parses_ack_id(
            self,
            mock_parse_qs: MagicMock,
            mock_urlparse: MagicMock,
        ):
            # GIVEN
            ack_id = "123"
            parsed_qs = {HeartbeatHandler._ACK_ID_KEY: [ack_id]}
            mock_url = MagicMock()
            mock_urlparse.return_value = mock_url
            mock_parse_qs.return_value = parsed_qs

            mock_handler = MagicMock()
            handler = HeartbeatHandler(mock_handler)

            # WHEN
            result = handler._parse_ack_id()

            # THEN
            mock_urlparse.assert_called_once_with(mock_handler.path)
            mock_parse_qs.assert_called_once_with(mock_url.query)
            assert ack_id == result

        @patch("urllib.parse.urlparse")
        @patch("urllib.parse.parse_qs")
        def test_returns_none_if_ack_id_not_found(
            self,
            mock_parse_qs: MagicMock,
            mock_urlparse: MagicMock,
        ):
            # GIVEN
            mock_url = MagicMock()
            mock_urlparse.return_value = mock_url
            mock_parse_qs.return_value = {}

            mock_handler = MagicMock()
            handler = HeartbeatHandler(mock_handler)

            # WHEN
            result = handler._parse_ack_id()

            # THEN
            mock_urlparse.assert_called_once_with(mock_handler.path)
            mock_parse_qs.assert_called_once_with(mock_url.query)
            assert result is None

        @patch("urllib.parse.urlparse")
        @patch("urllib.parse.parse_qs")
        def test_raises_if_more_than_one_ack_id(
            self,
            mock_parse_qs: MagicMock,
            mock_urlparse: MagicMock,
        ):
            # GIVEN
            ack_id = "123"
            parsed_qs = {HeartbeatHandler._ACK_ID_KEY: [ack_id, ack_id]}
            mock_url = MagicMock()
            mock_urlparse.return_value = mock_url
            mock_parse_qs.return_value = parsed_qs

            mock_handler = MagicMock()
            handler = HeartbeatHandler(mock_handler)

            # WHEN
            with pytest.raises(ValueError) as raised_err:
                handler._parse_ack_id()

            # THEN
            mock_urlparse.assert_called_once_with(mock_handler.path)
            mock_parse_qs.assert_called_once_with(mock_url.query)
            assert raised_err.match(
                f"Expected one value for {HeartbeatHandler._ACK_ID_KEY}, but found: 2"
            )


class TestShutdownHandler:
    """
    Tests for the ShutdownHandler class
    """

    def test_signals_to_the_server_thread(self):
        # GIVEN
        mock_request_handler = MagicMock()
        mock_server = MagicMock(spec=BackgroundHTTPServer)
        mock_shutdown_event = MagicMock(spec=Event)
        mock_server._shutdown_event = mock_shutdown_event
        mock_request_handler.server = mock_server
        mock_request_handler.headers = {"Content-Length": 0}
        mock_request_handler.path = ""
        handler = ShutdownHandler(mock_request_handler)

        # WHEN
        response = handler.put()

        # THEN
        mock_shutdown_event.set.assert_called_once()
        assert response.status == HTTPStatus.OK
        assert response.body is None


class TestRunHandler:
    """
    Tests for the RunHandler.
    """

    @patch("json.loads")
    @patch.object(http_server.ServerResponseGenerator, "submit")
    def test_submits_adaptor_run_to_worker(self, mock_submit: MagicMock, mock_loads: MagicMock):
        # GIVEN
        content_length = 123
        run_data = {"run": "data"}
        str_run_data = json.dumps(run_data)
        mock_loads.return_value = run_data

        mock_server = MagicMock(spec=BackgroundHTTPServer)
        mock_future_runner = MagicMock()
        mock_future_runner.is_running = False
        mock_server._future_runner = mock_future_runner
        mock_server._adaptor_runner = MagicMock()

        mock_handler = MagicMock()
        mock_handler.headers = {"Content-Length": str(content_length)}
        mock_handler.rfile.read.return_value = str_run_data.encode("utf-8")
        mock_handler.path = ""
        mock_handler.server = mock_server
        handler = RunHandler(mock_handler)

        # WHEN
        result = handler.put()

        # THEN
        mock_handler.rfile.read.assert_called_once_with(content_length)
        mock_loads.assert_called_once_with(str_run_data)
        mock_submit.assert_called_once_with(
            mock_server._adaptor_runner._run,
            run_data,
        )
        assert result is mock_submit.return_value

    def test_returns_400_if_busy(self):
        # GIVEN
        mock_server = MagicMock(spec=BackgroundHTTPServer)
        mock_future_runner = MagicMock()
        mock_future_runner.is_running = True
        mock_server._future_runner = mock_future_runner

        mock_handler = MagicMock()
        mock_handler.server = mock_server
        mock_handler.headers = {"Content-Length": 0}
        mock_handler.path = ""

        handler = RunHandler(mock_handler)

        # WHEN
        result = handler.put()

        # THEN
        assert result.status == HTTPStatus.BAD_REQUEST


class TestStartHandler:
    """
    Tests for the StartHandler class
    """

    @patch.object(http_server.ServerResponseGenerator, "submit")
    def test_put_starts_adaptor_runner(self, mock_submit: MagicMock):
        # GIVEN
        mock_request_handler = MagicMock()
        mock_server = MagicMock(spec=BackgroundHTTPServer)
        mock_server._adaptor_runner = MagicMock(spec=AdaptorRunner)
        mock_request_handler.server = mock_server
        mock_request_handler.headers = {"Content-Length": 0}
        mock_request_handler.path = ""

        mock_future_runner = MagicMock()
        mock_future_runner.is_running = False
        mock_server._future_runner = mock_future_runner
        handler = StartHandler(mock_request_handler)

        # WHEN
        response = handler.put()

        # THEN

        mock_submit.assert_called_once_with(mock_server._adaptor_runner._start)
        assert response is mock_submit.return_value

    def test_returns_400_if_busy(self):
        # GIVEN
        mock_server = MagicMock(spec=BackgroundHTTPServer)
        mock_future_runner = MagicMock()
        mock_future_runner.is_running = True
        mock_server._future_runner = mock_future_runner

        mock_handler = MagicMock()
        mock_handler.server = mock_server
        mock_handler.headers = {"Content-Length": 0}
        mock_handler.path = ""
        handler = StartHandler(mock_handler)

        # WHEN
        result = handler.put()

        # THEN
        assert result.status == HTTPStatus.BAD_REQUEST


class TestStopHandlerr:
    """
    Tests for the StopHandler class
    """

    @patch.object(http_server.ServerResponseGenerator, "submit")
    def test_put_ends_adaptor_runner(self, mock_submit: MagicMock):
        # GIVEN
        mock_request_handler = MagicMock()
        mock_server = MagicMock(spec=BackgroundHTTPServer)
        mock_server._adaptor_runner = MagicMock(spec=AdaptorRunner)
        mock_request_handler.server = mock_server
        mock_request_handler.headers = {"Content-Length": 0}
        mock_request_handler.path = ""

        mock_future_runner = MagicMock()
        mock_future_runner.is_running = False
        mock_server._future_runner = mock_future_runner

        handler = StopHandler(mock_request_handler)

        # WHEN
        response = handler.put()

        # THEN
        mock_submit.assert_called_once_with(handler.server_response._stop_adaptor)
        assert response is mock_submit.return_value

    def test_returns_400_if_busy(self):
        # GIVEN
        mock_server = MagicMock(spec=BackgroundHTTPServer)
        mock_future_runner = MagicMock()
        mock_future_runner.is_running = True
        mock_server._future_runner = mock_future_runner

        mock_handler = MagicMock()
        mock_handler.server = mock_server
        mock_handler.headers = {"Content-Length": 0}
        mock_handler.path = ""
        handler = StopHandler(mock_handler)

        # WHEN
        result = handler.put()

        # THEN
        assert result.status == HTTPStatus.BAD_REQUEST


class TestCancelHandler:
    """
    Tests for the CancelHandler class
    """

    @patch.object(http_server.ServerResponseGenerator, "submit")
    def test_put_cancels_adaptor_runner(self, mock_submit: MagicMock):
        # GIVEN
        mock_request_handler = MagicMock()
        mock_server = MagicMock(spec=BackgroundHTTPServer)
        mock_server._adaptor_runner = MagicMock(spec=AdaptorRunner)
        mock_server._adaptor_runner.state = AdaptorState.RUN
        mock_request_handler.server = mock_server
        mock_request_handler.headers = {"Content-Length": 0}
        mock_request_handler.path = ""

        mock_future_runner = MagicMock()
        mock_future_runner.is_running = True
        mock_server._future_runner = mock_future_runner

        handler = CancelHandler(mock_request_handler)

        # WHEN
        response = handler.put()

        # THEN
        mock_submit.assert_called_once_with(
            mock_server._adaptor_runner._cancel,
            force_immediate=True,
        )
        assert response is mock_submit.return_value

    def test_returns_immediately_if_future_not_running(self):
        # GIVEN
        mock_server = MagicMock(spec=BackgroundHTTPServer)
        mock_future_runner = MagicMock()
        mock_future_runner.is_running = False
        mock_server._future_runner = mock_future_runner

        mock_handler = MagicMock()
        mock_handler.headers = {"Content-Length": 0}
        mock_handler.path = ""
        mock_handler.server = mock_server
        handler = CancelHandler(mock_handler)

        # WHEN
        result = handler.put()

        # THEN
        assert result.status == HTTPStatus.OK
        assert result.body == "No action required"

    @pytest.mark.parametrize(
        argnames=["state"],
        argvalues=[
            [AdaptorState.NOT_STARTED],
            [AdaptorState.STOP],
            [AdaptorState.CLEANUP],
            [AdaptorState.CANCELED],
        ],
        ids=["NOT_STARTED", "END", "CLEANUP", "CANCELED"],
    )
    def test_returns_immediately_if_adaptor_not_cancelable(self, state: AdaptorState):
        # GIVEN
        mock_server = MagicMock(spec=BackgroundHTTPServer)
        mock_future_runner = MagicMock()
        mock_future_runner.is_running = True
        mock_server._future_runner = mock_future_runner

        mock_adaptor_runner = MagicMock()
        mock_adaptor_runner.state = state
        mock_server._adaptor_runner = mock_adaptor_runner

        mock_handler = MagicMock()
        mock_handler.headers = {"Content-Length": 0}
        mock_handler.path = ""
        mock_handler.server = mock_server
        handler = CancelHandler(mock_handler)

        # WHEN
        result = handler.put()

        # THEN
        assert result.status == HTTPStatus.OK
        assert result.body == "No action required"
