# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from openjd.adaptor_runtime._osname import OSName
import pytest

if OSName.is_windows():
    pytest.skip("Posix-specific tests", allow_module_level=True)

import socket
from http import HTTPStatus
from unittest.mock import MagicMock, Mock, patch

import openjd.adaptor_runtime._http.request_handler as request_handler
from openjd.adaptor_runtime._background.http_server import BackgroundRequestHandler
from openjd.adaptor_runtime._http.request_handler import (
    HTTPResponse,
    RequestHandler,
    UnsupportedPlatformException,
)
from openjd.adaptor_runtime._osname import OSName


@pytest.fixture
def fake_request_handler() -> BackgroundRequestHandler:
    class FakeBackgroundRequestHandler(BackgroundRequestHandler):
        path: str = "/fake"

        def __init__(self) -> None:
            pass

        def _authenticate(self) -> bool:
            return True

    return FakeBackgroundRequestHandler()


class TestRequestHandler:
    """
    Tests for the RequestHandler class.
    """

    @patch.object(BackgroundRequestHandler, "_respond")
    def test_do_request(
        self,
        mock_respond: MagicMock,
        fake_request_handler: BackgroundRequestHandler,
    ):
        # GIVEN
        func = Mock()

        # WHEN
        fake_request_handler._do_request(func)

        # THEN
        func.assert_called_once()
        mock_respond.assert_called_once_with(func.return_value)

    @patch.object(BackgroundRequestHandler, "_respond")
    def test_do_request_responds_with_error_when_request_handler_raises(
        self,
        mock_respond: MagicMock,
        fake_request_handler: BackgroundRequestHandler,
        caplog: pytest.LogCaptureFixture,
    ):
        # GIVEN
        func = Mock()
        exc = Exception()
        func.side_effect = exc

        # WHEN
        fake_request_handler._do_request(func)

        # THEN
        func.assert_called_once()
        assert "Failed to handle request: " in caplog.text
        mock_respond.assert_called_once_with(HTTPResponse(HTTPStatus.INTERNAL_SERVER_ERROR))

    @patch.object(BackgroundRequestHandler, "send_response")
    @patch.object(BackgroundRequestHandler, "end_headers")
    def test_respond_with_success(
        self,
        mock_end_headers: MagicMock,
        mock_send_response: MagicMock,
        fake_request_handler: BackgroundRequestHandler,
    ):
        # GIVEN
        response = HTTPResponse(HTTPStatus.OK)

        # WHEN
        fake_request_handler._respond(response)

        # THEN
        mock_send_response.assert_called_once_with(response.status)
        mock_end_headers.assert_called_once()

    @patch.object(BackgroundRequestHandler, "send_error")
    @patch.object(BackgroundRequestHandler, "end_headers")
    def test_respond_with_error(
        self,
        mock_end_headers: MagicMock,
        mock_send_error: MagicMock,
        fake_request_handler: BackgroundRequestHandler,
    ):
        # GIVEN
        response = HTTPResponse(HTTPStatus.INTERNAL_SERVER_ERROR)

        # WHEN
        fake_request_handler._respond(response)

        # THEN
        mock_send_error.assert_called_once_with(response.status)
        mock_end_headers.assert_called_once()

    @patch.object(BackgroundRequestHandler, "send_header")
    @patch.object(BackgroundRequestHandler, "send_response")
    @patch.object(BackgroundRequestHandler, "end_headers")
    def test_respond_with_body(
        self,
        mock_end_headers: MagicMock,
        mock_send_response: MagicMock,
        mock_send_header: MagicMock,
        fake_request_handler: BackgroundRequestHandler,
    ):
        # GIVEN
        mock_wfile = MagicMock()
        fake_request_handler.wfile = mock_wfile
        body = "hello world"
        response = HTTPResponse(HTTPStatus.OK, body)

        # WHEN
        fake_request_handler._respond(response)

        # THEN
        mock_send_response.assert_called_once_with(response.status)
        mock_end_headers.assert_called_once()
        mock_send_header.assert_called_once_with("Content-Length", str(len(body.encode("utf-8"))))
        mock_wfile.write.assert_called_once_with(body.encode("utf-8"))


@pytest.mark.skipif(not OSName.is_posix(), reason="Posix-specific tests")
class TestAuthentication:
    """
    Tests for the RequestHandler authentication
    """

    class TestAuthenticate:
        """
        Tests for the RequestHandler._authenticate() method
        """

        cred_cls = request_handler.XUCred if OSName.is_macos() else request_handler.UCred

        @pytest.fixture
        def mock_handler(self) -> MagicMock:
            mock_socket = MagicMock(spec=socket.socket)
            mock_socket.family = socket.AddressFamily.AF_UNIX  # type: ignore[attr-defined]

            mock_handler = MagicMock(spec=RequestHandler)
            mock_handler.connection = mock_socket

            return mock_handler

        @patch.object(request_handler.os, "getuid")
        @patch.object(cred_cls, "from_buffer_copy")
        def test_accepts_same_uid(
            self, mock_from_buffer_copy: MagicMock, mock_getuid: MagicMock, mock_handler: MagicMock
        ) -> None:
            # GIVEN
            # Set the UID of the mocked calling process == our mocked UID
            mock_from_buffer_copy.return_value.uid = mock_getuid.return_value

            # WHEN
            result = RequestHandler._authenticate(mock_handler)

            # THEN
            assert result

        @patch.object(request_handler.os, "getuid")
        @patch.object(cred_cls, "from_buffer_copy")
        def test_rejects_different_uid(
            self, mock_from_buffer_copy: MagicMock, mock_getuid: MagicMock, mock_handler: MagicMock
        ) -> None:
            # GIVEN
            mock_getuid.return_value = 1
            mock_from_buffer_copy.return_value.uid = 2

            # WHEN
            result = RequestHandler._authenticate(mock_handler)

            # THEN
            assert not result

        def test_raises_if_not_on_unix_socket(self, mock_handler: MagicMock) -> None:
            # GIVEN
            mock_handler.connection.family = socket.AddressFamily.AF_INET

            # WHEN
            with pytest.raises(UnsupportedPlatformException) as raised_exc:
                RequestHandler._authenticate(mock_handler)

            # THEN
            assert raised_exc.match(
                "Failed to handle request because it was not made through a UNIX socket"
            )


class TestDoRequest:
    """
    Tests for the RequestHandler._do_request() method
    """

    def test_does_request_after_auth_succeeds(self) -> None:
        # GIVEN
        mock_handler = MagicMock(spec=RequestHandler)
        mock_handler._authenticate.return_value = True
        mock_func = Mock()

        # WHEN
        RequestHandler._do_request(mock_handler, mock_func)

        # THEN
        mock_handler._authenticate.assert_called_once()
        mock_func.assert_called_once()

    def test_responds_with_unauthorized_after_auth_fails(self):
        # GIVEN
        mock_handler = MagicMock(spec=RequestHandler)
        mock_handler._authenticate.return_value = False

        # WHEN
        RequestHandler._do_request(mock_handler, Mock())

        # THEN
        mock_handler._authenticate.assert_called_once()
        mock_handler._respond.assert_called_once_with(HTTPResponse(HTTPStatus.UNAUTHORIZED))

    def test_responds_with_500_for_unsupported_platform(self, caplog: pytest.LogCaptureFixture):
        # GIVEN
        mock_handler = MagicMock(spec=RequestHandler)
        exc = UnsupportedPlatformException("not UNIX")
        mock_handler._authenticate.side_effect = exc

        # WHEN
        RequestHandler._do_request(mock_handler, Mock())

        # THEN
        mock_handler._authenticate.assert_called_once()
        assert str(exc) in caplog.text
        mock_handler._respond.assert_called_once_with(
            HTTPResponse(HTTPStatus.INTERNAL_SERVER_ERROR)
        )
