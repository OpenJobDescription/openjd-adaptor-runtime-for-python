# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

import json
from http import HTTPStatus as _HTTPStatus
from unittest.mock import MagicMock, Mock, PropertyMock, patch
from urllib.parse import urlencode

from _pytest.capture import CaptureFixture as _CaptureFixture
from openjd.adaptor_runtime_client import Action as _Action

from openjd.adaptor_runtime.application_ipc import ActionsQueue as _ActionsQueue
from openjd.adaptor_runtime.application_ipc import AdaptorServer as _AdaptorServer
from openjd.adaptor_runtime.application_ipc._http_request_handler import (
    ActionEndpoint,
)
from openjd.adaptor_runtime.application_ipc._http_request_handler import (
    AdaptorHTTPRequestHandler as _AdaptorHTTPRequestHandler,
)
from openjd.adaptor_runtime.application_ipc._http_request_handler import (
    PathMappingEndpoint,
)
from openjd.adaptor_runtime.application_ipc._http_request_handler import (
    PathMappingRulesEndpoint,
)
from openjd.adaptor_runtime._http.request_handler import HTTPResponse

from ..adaptors.fake_adaptor import FakeAdaptor


class TestPathMappingEndpoint:
    @patch.object(PathMappingEndpoint, "query_string_params", new_callable=PropertyMock)
    def test_get_internal_error(self, mock_qsp):
        # GIVEN
        mock_request_handler = MagicMock()
        mock_server = MagicMock(spec=_AdaptorServer)
        mock_request_handler.server = mock_server
        mock_qsp.side_effect = Exception("Something bad happened")
        handler = PathMappingEndpoint(mock_request_handler)

        # WHEN
        response = handler.get()

        # THEN
        assert response == HTTPResponse(
            _HTTPStatus.INTERNAL_SERVER_ERROR, str(mock_qsp.side_effect)
        )

    def test_get_no_params_returns_bad_request(self):
        # GIVEN
        adaptor = FakeAdaptor({})
        mock_request_handler = MagicMock()
        mock_server = MagicMock(spec=_AdaptorServer)
        mock_server.adaptor = adaptor
        mock_request_handler.server = mock_server
        mock_request_handler.path = "localhost:8080/path_mapping"

        handler = PathMappingEndpoint(mock_request_handler)

        # WHEN
        response = handler.get()

        # THEN
        assert response == HTTPResponse(_HTTPStatus.BAD_REQUEST, "Missing path in query string.")

    def test_get_returns_mapped_path(self):
        # GIVEN
        SOURCE_PATH = "Z:\\asset_storage1"
        DEST_PATH = "/mnt/shared/asset_storage1"
        adaptor = FakeAdaptor(
            {},
            path_mapping_data={
                "path_mapping_rules": [
                    {
                        "source_path_format": "windows",
                        "source_path": SOURCE_PATH,
                        "destination_os": "linux",
                        "destination_path": DEST_PATH,
                    }
                ]
            },
        )
        mock_request_handler = MagicMock()
        mock_server = MagicMock(spec=_AdaptorServer)
        mock_server.adaptor = adaptor
        mock_request_handler.server = mock_server
        mock_request_handler.path = "localhost:8080/path_mapping?" + urlencode(
            {"path": SOURCE_PATH + "\\somefile.png"}
        )

        handler = PathMappingEndpoint(mock_request_handler)

        # WHEN
        response = handler.get()

        # THEN
        assert response == HTTPResponse(
            _HTTPStatus.OK, json.dumps({"path": DEST_PATH + "/somefile.png"})
        )


class TestPathMappingRulesEndpoint:
    def test_get_returns_rules(self):
        # GIVEN
        SOURCE_PATH = "Z:\\asset_storage1"
        DEST_PATH = "/mnt/shared/asset_storage1"
        rules = {
            "source_path_format": "Windows",
            "source_path": SOURCE_PATH,
            "destination_os": "Linux",
            "destination_path": DEST_PATH,
        }
        adaptor = FakeAdaptor(
            {},
            path_mapping_data={"path_mapping_rules": [rules]},
        )
        mock_request_handler = MagicMock()
        mock_server = MagicMock(spec=_AdaptorServer)
        mock_server.adaptor = adaptor
        mock_request_handler.server = mock_server
        mock_request_handler.path = "localhost:8080/path_mapping_rules"

        handler = PathMappingRulesEndpoint(mock_request_handler)

        # WHEN
        response = handler.get()

        # THEN
        assert response == HTTPResponse(_HTTPStatus.OK, json.dumps({"path_mapping_rules": [rules]}))


class TestActionEndpoint:
    def test_get_returns_action(self):
        # GIVEN
        mock_request_handler = MagicMock()
        mock_server = MagicMock(spec=_AdaptorServer)
        mock_server.actions_queue = _ActionsQueue()
        mock_request_handler.server = mock_server

        a1 = _Action("a1", {"arg1": "val1"})
        mock_server.actions_queue.enqueue_action(a1)

        handler = ActionEndpoint(mock_request_handler)

        # WHEN
        response = handler.get()

        # THEN
        assert response == HTTPResponse(_HTTPStatus.OK, str(a1))

    def test_dequeue_no_action(self) -> None:
        # GIVEN
        mock_request_handler = MagicMock()
        mock_server = MagicMock(spec=_AdaptorServer)
        mock_server.actions_queue = _ActionsQueue()
        mock_request_handler.server = mock_server

        handler = ActionEndpoint(mock_request_handler)

        # WHEN
        action = handler._dequeue_action()

        # THEN
        assert action is None

    @patch.object(_AdaptorHTTPRequestHandler, "__init__", return_value=None)
    def test_dequeue_action(self, mocked_init: Mock) -> None:
        # GIVEN
        mock_request_handler = MagicMock()
        mock_server = MagicMock(spec=_AdaptorServer)
        mock_server.actions_queue = _ActionsQueue()
        mock_request_handler.server = mock_server

        handler = ActionEndpoint(mock_request_handler)

        a1 = _Action("a1", {"arg1": "val1"})
        mock_server.actions_queue.enqueue_action(a1)

        # WHEN
        action = handler._dequeue_action()

        # THEN
        assert action == a1

    def test_dequeue_action_no_server(self, capsys: _CaptureFixture) -> None:
        # GIVEN
        mock_request_handler = MagicMock()
        mock_request_handler.server = None
        handler = ActionEndpoint(mock_request_handler)

        # WHEN
        action = handler._dequeue_action()

        # THEN
        assert action is None
        assert (
            "Could not retrieve the next action because the server or actions queue"
            " wasn't set." in capsys.readouterr().err
        )

    def test_dequeue_action_no_queue(self, capsys: _CaptureFixture) -> None:
        # GIVEN
        mock_request_handler = MagicMock()
        mock_server = MagicMock(spec=_AdaptorServer)
        mock_request_handler.server = mock_server

        handler = ActionEndpoint(mock_request_handler)

        # WHEN
        action = handler._dequeue_action()

        # THEN
        assert action is None
        assert (
            "Could not retrieve the next action because the server or actions queue"
            " wasn't set." in capsys.readouterr().err
        )
