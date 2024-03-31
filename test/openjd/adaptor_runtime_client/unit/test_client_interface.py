# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from http import HTTPStatus
import json
from signal import Signals
from types import FrameType as _FrameType
from typing import (
    Any as _Any,
    Dict as _Dict,
    List as _List,
    Optional as _Optional,
    Generator,
    Tuple,
    Dict,
)
from unittest import mock
from unittest.mock import patch, MagicMock
from urllib.parse import urlencode

import pytest
from _pytest.capture import CaptureFixture as _CaptureFixture

from openjd.adaptor_runtime._osname import OSName
from openjd.adaptor_runtime_client import (
    Action as _Action,
    ClientInterface as _ClientInterface,
    PathMappingRule as _PathMappingRule,
)

win_client_interface = pytest.importorskip("openjd.adaptor_runtime_client.win_client_interface")


class FakeClient(_ClientInterface):
    """Since we need to override the DCC Client (because it's an interface).
    We are going to use this FakeClient for our testing.
    """

    def __init__(self, socket_path: str) -> None:
        super().__init__(socket_path)
        self.actions.update({"hello_world": self.hello_world})

    def hello_world(self, args: _Optional[_Dict[str, _Any]]) -> None:
        print(f"args = {args}")

    def graceful_shutdown(self, signum: int, frame: _Optional[_FrameType]) -> None:
        print(f"Received {Signals(signum).name} signal.")

    # This function needs to be overridden.
    def close(self, args: _Optional[_Dict[str, _Any]]) -> None:
        pass


@pytest.mark.skipif(not OSName.is_posix(), reason="Posix-specific tests")
class TestPosixClientInterface:
    @pytest.mark.parametrize(
        argnames=("original_path", "new_path"),
        argvalues=[
            ("original/path", "new/path"),
            ("🌚\\🌒\\🌓\\🌔\\🌝\\🌖\\🌗\\🌘\\🌚", "🌝/🌖/🌗/🌘/🌚/🌒/🌓/🌔/🌝"),
        ],
    )
    @mock.patch("http.client.HTTPConnection.close")
    @mock.patch("http.client.HTTPConnection.request")
    @mock.patch("http.client.HTTPConnection.getresponse")
    def test_map_path(
        self,
        mocked_HTTPConnection_getresponse: mock.Mock,
        mocked_HTTPConnection_request: mock.Mock,
        mocked_HTTPConnection_close: mock.Mock,
        original_path: str,
        new_path: str,
    ) -> None:
        # GIVEN
        mocked_response = mock.Mock()
        mocked_response.status = 200
        mocked_response.read.return_value = json.dumps({"path": new_path}).encode("utf-8")
        mocked_response.length = len(mocked_response.read.return_value)
        mocked_HTTPConnection_getresponse.return_value = mocked_response

        dcc_client = FakeClient(socket_path="socket_path")

        # WHEN
        mapped = dcc_client.map_path(original_path)

        # THEN
        assert mapped == new_path
        mocked_HTTPConnection_request.assert_has_calls(
            [
                mock.call(
                    "GET",
                    "/path_mapping?" + urlencode({"path": original_path}),
                    headers={"Content-type": "application/json"},
                ),
            ]
        )
        mocked_HTTPConnection_close.assert_has_calls(
            [
                mock.call(),
            ]
        )

    @pytest.mark.parametrize(
        argnames="rules",
        argvalues=[
            (
                [
                    {
                        "source_path_format": "one",
                        "source_path": "here",
                        "destination_os": "two",
                        "destination_path": "there",
                    }
                ]
            ),
        ],
    )
    @mock.patch("http.client.HTTPConnection.close")
    @mock.patch("http.client.HTTPConnection.request")
    @mock.patch("http.client.HTTPConnection.getresponse")
    def test_path_mapping_rules(
        self,
        mocked_HTTPConnection_getresponse: mock.Mock,
        mocked_HTTPConnection_request: mock.Mock,
        mocked_HTTPConnection_close: mock.Mock,
        rules: _List[_Any],
    ) -> None:
        # GIVEN
        mocked_response = mock.Mock()
        mocked_response.status = 200
        mocked_response.read.return_value = json.dumps({"path_mapping_rules": rules}).encode(
            "utf-8"
        )
        mocked_response.length = len(mocked_response.read.return_value)
        mocked_HTTPConnection_getresponse.return_value = mocked_response

        dcc_client = FakeClient(socket_path="socket_path")

        # WHEN
        expected = dcc_client.path_mapping_rules()

        # THEN
        assert len(expected) == len(rules)
        for i in range(0, len(expected)):
            assert _PathMappingRule(**rules[i]) == expected[i]

        mocked_HTTPConnection_request.assert_has_calls(
            [
                mock.call(
                    "GET",
                    "/path_mapping_rules",
                    headers={"Content-type": "application/json"},
                ),
            ]
        )
        mocked_HTTPConnection_close.assert_has_calls(
            [
                mock.call(),
            ]
        )

    @mock.patch("http.client.HTTPConnection.close")
    @mock.patch("http.client.HTTPConnection.request")
    @mock.patch("http.client.HTTPConnection.getresponse")
    def test_path_mapping_rules_throws_nonvalid_json(
        self,
        mock_getresponse: mock.Mock,
        mock_request: mock.Mock,
        mock_close: mock.Mock,
    ):
        # GIVEN
        mock_response = mock.Mock()
        mock_response.status = HTTPStatus.OK
        mock_response.read.return_value = "bad json".encode("utf-8")
        mock_getresponse.return_value = mock_response
        client = FakeClient(socket_path="socket_path")

        # WHEN
        with pytest.raises(RuntimeError) as raised_err:
            client.path_mapping_rules()

        # THEN
        assert "Expected JSON string from /path_mapping_rules endpoint, but got error: " in str(
            raised_err.value
        )
        mock_request.assert_called_once_with(
            "GET", "/path_mapping_rules", headers={"Content-type": "application/json"}
        )
        mock_getresponse.assert_called_once()
        mock_close.assert_called_once()

    @mock.patch("http.client.HTTPConnection.close")
    @mock.patch("http.client.HTTPConnection.request")
    @mock.patch("http.client.HTTPConnection.getresponse")
    def test_path_mapping_rules_throws_not_list(
        self,
        mock_getresponse: mock.Mock,
        mock_request: mock.Mock,
        mock_close: mock.Mock,
    ):
        # GIVEN
        response_val = {"path_mapping_rules": "this-is-not-a-list"}
        mock_response = mock.Mock()
        mock_response.status = HTTPStatus.OK
        mock_response.read.return_value = json.dumps(response_val).encode("utf-8")
        mock_getresponse.return_value = mock_response
        client = FakeClient(socket_path="socket_path")

        # WHEN
        with pytest.raises(RuntimeError) as raised_err:
            client.path_mapping_rules()

        # THEN
        assert (
            f"Expected list for path_mapping_rules, but got: {response_val['path_mapping_rules']}"
            in str(raised_err.value)
        )
        mock_request.assert_called_once_with(
            "GET", "/path_mapping_rules", headers={"Content-type": "application/json"}
        )
        mock_getresponse.assert_called_once()
        mock_close.assert_called_once()

    @mock.patch("http.client.HTTPConnection.close")
    @mock.patch("http.client.HTTPConnection.request")
    @mock.patch("http.client.HTTPConnection.getresponse")
    def test_path_mapping_rules_throws_not_path_mapping_rule(
        self,
        mock_getresponse: mock.Mock,
        mock_request: mock.Mock,
        mock_close: mock.Mock,
    ):
        # GIVEN
        response_val = {"path_mapping_rules": ["not-a-rule-dict"]}
        mock_response = mock.Mock()
        mock_response.status = HTTPStatus.OK
        mock_response.read.return_value = json.dumps(response_val).encode("utf-8")
        mock_getresponse.return_value = mock_response
        client = FakeClient(socket_path="socket_path")

        # WHEN
        with pytest.raises(RuntimeError) as raised_err:
            client.path_mapping_rules()

        # THEN
        assert (
            f"Expected PathMappingRule object, but got: not-a-rule-dict\nAll rules: {response_val['path_mapping_rules']}"
            in str(raised_err.value)
        )
        mock_request.assert_called_once_with(
            "GET", "/path_mapping_rules", headers={"Content-type": "application/json"}
        )
        mock_getresponse.assert_called_once()
        mock_close.assert_called_once()

    @mock.patch("http.client.HTTPConnection.close")
    @mock.patch("http.client.HTTPConnection.request")
    @mock.patch("http.client.HTTPConnection.getresponse")
    def test_map_path_error(
        self,
        mocked_HTTPConnection_getresponse: mock.Mock,
        mocked_HTTPConnection_request: mock.Mock,
        mocked_HTTPConnection_close: mock.Mock,
    ) -> None:
        # GIVEN
        ORIGINAL_PATH = "some/path"
        REASON = "Could not process request."
        mocked_response = mock.Mock()
        mocked_response.status = 500
        mocked_response.read.return_value = REASON.encode("utf-8")
        mocked_response.length = len(mocked_response.read.return_value)
        mocked_HTTPConnection_getresponse.return_value = mocked_response

        dcc_client = FakeClient(socket_path="socket_path")

        # WHEN
        with pytest.raises(RuntimeError) as exc_info:
            dcc_client.map_path(ORIGINAL_PATH)

        # THEN
        mocked_HTTPConnection_request.assert_has_calls(
            [
                mock.call(
                    "GET",
                    "/path_mapping?" + urlencode({"path": ORIGINAL_PATH}),
                    headers={"Content-type": "application/json"},
                ),
            ]
        )
        mocked_HTTPConnection_close.assert_has_calls(
            [
                mock.call(),
            ]
        )
        assert str(exc_info.value) == (
            f"ERROR: Failed to get a mapped path for path '{ORIGINAL_PATH}'. "
            f"Server response: Status: {mocked_response.status}, Response: '{REASON}'"
        )

    @mock.patch("http.client.HTTPConnection.close")
    @mock.patch("http.client.HTTPConnection.request")
    @mock.patch("http.client.HTTPConnection.getresponse")
    def test_request_next_action(
        self,
        mocked_HTTPConnection_getresponse: mock.Mock,
        mocked_HTTPConnection_request: mock.Mock,
        mocked_HTTPConnection_close: mock.Mock,
    ) -> None:
        mocked_response = mock.Mock()
        mocked_response.status = "mocked_status"
        mocked_response.reason = "mocked_reason"
        mocked_response.length = None

        mocked_HTTPConnection_getresponse.return_value = mocked_response

        socket_path = "socket_path"
        dcc_client = FakeClient(socket_path)
        assert dcc_client.socket_path == socket_path
        status, reason, action = dcc_client._request_next_action()

        assert action is None

        a1 = _Action("a1")
        bytes_a1 = bytes(str(a1), "utf-8")

        mocked_response.read.return_value = bytes_a1
        mocked_response.length = len(bytes_a1)

        status, reason, action = dcc_client._request_next_action()
        mocked_HTTPConnection_request.assert_has_calls(
            [
                mock.call("GET", "/action", headers={"Content-type": "application/json"}),
                mock.call("GET", "/action", headers={"Content-type": "application/json"}),
            ]
        )
        mocked_HTTPConnection_close.assert_has_calls(
            [
                mock.call(),
                mock.call(),
            ]
        )

        assert status == "mocked_status"
        assert reason == "mocked_reason"
        assert str(action) == str(a1)


class TestWindowsClientInterface:
    @pytest.fixture
    def patched_named_pipe_helper(
        self,
    ) -> Generator[Tuple[MagicMock, MagicMock, MagicMock], None, None]:
        with (
            patch.object(
                win_client_interface.NamedPipeHelper, "write_to_pipe"
            ) as mock_write_to_pipe,
            patch.object(
                win_client_interface.NamedPipeHelper, "establish_named_pipe_connection"
            ) as mock_establish_named_pipe_connection,
            patch.object(
                win_client_interface.NamedPipeHelper, "read_from_pipe"
            ) as mock_read_from_pipe,
        ):
            yield mock_write_to_pipe, mock_establish_named_pipe_connection, mock_read_from_pipe

    @pytest.mark.parametrize(
        argnames=("original_path", "new_path"),
        argvalues=[
            ("original/path", "new/path"),
            ("🌚\\🌒\\🌓\\🌔\\🌝\\🌖\\🌗\\🌘\\🌚", "🌝/🌖/🌗/🌘/🌚/🌒/🌓/🌔/🌝"),
        ],
    )
    def test_map_path(
        self,
        original_path: str,
        new_path: str,
        patched_named_pipe_helper: Tuple[MagicMock, MagicMock, MagicMock],
    ) -> None:
        (
            mock_write_to_pipe,
            mock_establish_named_pipe_connection,
            mock_read_from_pipe,
        ) = patched_named_pipe_helper
        # GIVEN
        body = json.dumps({"status": 200, "body": json.dumps({"path": new_path})})
        mock_read_from_pipe.return_value = body
        dcc_client = FakeClient(socket_path="socket_path")
        # WHEN
        mapped = dcc_client.map_path(original_path)

        # THEN
        assert mapped == new_path
        mock_write_to_pipe.assert_has_calls(
            [
                mock.call(
                    mock_establish_named_pipe_connection(),
                    json.dumps(
                        {
                            "method": "GET",
                            "path": "/path_mapping",
                            "params": json.dumps({"path": [original_path]}),
                        }
                    ),
                ),
            ]
        )
        mock_establish_named_pipe_connection().close.assert_called_once()

    @pytest.mark.parametrize(
        argnames="rules",
        argvalues=[
            (
                [
                    {
                        "source_path_format": "one",
                        "source_path": "here",
                        "destination_os": "two",
                        "destination_path": "there",
                    }
                ]
            ),
        ],
    )
    def test_path_mapping_rules(
        self,
        rules: _List[_Any],
        patched_named_pipe_helper: Tuple[MagicMock, MagicMock, MagicMock],
    ) -> None:
        (
            mock_write_to_pipe,
            mock_establish_named_pipe_connection,
            mock_read_from_pipe,
        ) = patched_named_pipe_helper
        body = json.dumps({"status": 200, "body": json.dumps({"path_mapping_rules": rules})})
        mock_read_from_pipe.return_value = body

        dcc_client = FakeClient(socket_path="socket_path")

        # WHEN
        expected = dcc_client.path_mapping_rules()

        # THEN
        assert len(expected) == len(rules)
        for i in range(0, len(expected)):
            assert _PathMappingRule(**rules[i]) == expected[i]

        mock_write_to_pipe.assert_has_calls(
            [
                mock.call(
                    mock_establish_named_pipe_connection(),
                    json.dumps(
                        {
                            "method": "GET",
                            "path": "/path_mapping_rules",
                        }
                    ),
                ),
            ]
        )
        mock_establish_named_pipe_connection().close.assert_called_once()

    def test_path_mapping_rules_throws_nonvalid_json(
        self,
        patched_named_pipe_helper: Tuple[MagicMock, MagicMock, MagicMock],
    ) -> None:
        (
            mock_write_to_pipe,
            mock_establish_named_pipe_connection,
            mock_read_from_pipe,
        ) = patched_named_pipe_helper
        # GIVEN

        body = json.dumps({"status": 200, "body": "bad json"})
        mock_read_from_pipe.return_value = body

        client = FakeClient(socket_path="socket_path")

        # WHEN
        with pytest.raises(RuntimeError) as raised_err:
            client.path_mapping_rules()

        # THEN
        assert "Expected JSON string from /path_mapping_rules endpoint, but got error: " in str(
            raised_err.value
        )

        mock_write_to_pipe.assert_has_calls(
            [
                mock.call(
                    mock_establish_named_pipe_connection(),
                    json.dumps(
                        {
                            "method": "GET",
                            "path": "/path_mapping_rules",
                        }
                    ),
                ),
            ]
        )

        mock_read_from_pipe.assert_called_once()
        mock_establish_named_pipe_connection().close.assert_called_once()

    @pytest.mark.parametrize(
        "response_val, expected_error",
        [
            (
                {"path_mapping_rules": "this-is-not-a-list"},
                "Expected list for path_mapping_rules, but got: this-is-not-a-list",
            ),
            (
                {"path_mapping_rules": ["not-a-rule-dict"]},
                "Expected PathMappingRule object, but got: not-a-rule-dict",
            ),
        ],
    )
    def test_path_mapping_rules_throws_errors(
        self,
        response_val: Dict[str, str],
        expected_error: str,
        patched_named_pipe_helper: Tuple[MagicMock, MagicMock, MagicMock],
    ) -> None:
        (
            mock_write_to_pipe,
            mock_establish_named_pipe_connection,
            mock_read_from_pipe,
        ) = patched_named_pipe_helper
        # GIVEN
        body = json.dumps({"status": 200, "body": json.dumps(response_val)})
        mock_read_from_pipe.return_value = body
        client = FakeClient(socket_path="socket_path")

        # WHEN
        with pytest.raises(RuntimeError) as raised_err:
            client.path_mapping_rules()

        # THEN
        assert expected_error in str(raised_err.value)
        mock_write_to_pipe.assert_has_calls(
            [
                mock.call(
                    mock_establish_named_pipe_connection(),
                    json.dumps(
                        {
                            "method": "GET",
                            "path": "/path_mapping_rules",
                        }
                    ),
                ),
            ]
        )
        mock_read_from_pipe.assert_called_once()
        mock_establish_named_pipe_connection().close.assert_called_once()

    def test_map_path_error(
        self,
        patched_named_pipe_helper: Tuple[MagicMock, MagicMock, MagicMock],
    ) -> None:
        (
            mock_write_to_pipe,
            mock_establish_named_pipe_connection,
            mock_read_from_pipe,
        ) = patched_named_pipe_helper
        ORIGINAL_PATH = "some/path"
        REASON = "Could not process request."

        body = json.dumps({"status": 500, "body": REASON})
        mock_read_from_pipe.return_value = body

        dcc_client = FakeClient(socket_path="socket_path")

        # WHEN
        with pytest.raises(RuntimeError) as exc_info:
            dcc_client.map_path(ORIGINAL_PATH)

        # THEN
        mock_write_to_pipe.assert_has_calls(
            [
                mock.call(
                    mock_establish_named_pipe_connection(),
                    json.dumps(
                        {
                            "method": "GET",
                            "path": "/path_mapping",
                            "params": '{"path": ["some/path"]}',
                        }
                    ),
                ),
            ]
        )
        mock_read_from_pipe.assert_called_once()
        mock_establish_named_pipe_connection().close.assert_called_once()
        assert str(exc_info.value) == (
            f"ERROR: Failed to get a mapped path for path '{ORIGINAL_PATH}'. "
            f"Server response: Status: 500, Response: '{REASON}'"
        )

    def test_request_next_action(
        self,
        patched_named_pipe_helper: Tuple[MagicMock, MagicMock, MagicMock],
    ) -> None:
        (
            mock_write_to_pipe,
            mock_establish_named_pipe_connection,
            mock_read_from_pipe,
        ) = patched_named_pipe_helper

        socket_path = "socket_path"
        dcc_client = FakeClient(socket_path)
        assert dcc_client.server_path == socket_path
        body = json.dumps({"status": 200, "body": ""})
        mock_read_from_pipe.return_value = body
        status, reason, action = dcc_client._request_next_action()

        assert action is None

        a1 = _Action("a1")

        body = json.dumps({"status": 200, "body": str(a1)})
        mock_read_from_pipe.return_value = body

        status, reason, action = dcc_client._request_next_action()

        mock_write_to_pipe.assert_has_calls(
            [
                mock.call(
                    mock_establish_named_pipe_connection(),
                    json.dumps(
                        {
                            "method": "GET",
                            "path": "/action",
                        }
                    ),
                ),
                mock.call(
                    mock_establish_named_pipe_connection(),
                    json.dumps(
                        {
                            "method": "GET",
                            "path": "/action",
                        }
                    ),
                ),
            ]
        )

        assert len(mock_establish_named_pipe_connection().close.call_args_list) == 2

        assert status == 200
        assert reason == "OK"
        assert str(action) == str(a1)


class TestPerformAction:
    @mock.patch.object(_ClientInterface, "_perform_action")
    def test_poll(self, mocked_perform_action: mock.Mock, capsys: _CaptureFixture) -> None:
        a1 = _Action("render", {"arg1": "val1"})
        a2 = _Action("close")

        with mock.patch.object(
            _ClientInterface,
            "_request_next_action",
            side_effect=[
                (404, "Not found", a1),
                (200, "OK", None),
                (200, "OK", a1),
                (200, "OK", a2),
            ],
        ):
            dcc_client = FakeClient(socket_path="socket_path")
            dcc_client.poll()

            mocked_perform_action.assert_has_calls([mock.call(a1), mock.call(a2)])

            assert (
                "An error was raised when trying to connect to the server: 404 Not found\n"
                in capsys.readouterr().err
            )

    def test_perform_action(self) -> None:
        a1 = _Action("hello_world", {"arg1": "Hello!", "arg2": "How are you?"})

        with mock.patch.object(FakeClient, "hello_world") as mocked_hello_world:
            dcc_client = FakeClient(socket_path="socket_path")
            dcc_client._perform_action(a1)

        mocked_hello_world.assert_called_once_with(a1.args)

    def test_perform_nonvalid_action(self, capsys: _CaptureFixture) -> None:
        a2 = _Action("nonvalid")
        dcc_client = FakeClient(socket_path="socket_path")
        dcc_client._perform_action(a2)

        assert (
            capsys.readouterr().err
            == f"ERROR: Attempted to perform the following action: {a2}. But this action doesn't "
            "exist in the actions dictionary.\n"
        )
