# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

import threading as _threading
from time import sleep as _sleep
from typing import Dict
from unittest import mock as _mock

import pytest
from openjd.adaptor_runtime_client import Action as _Action

from openjd.adaptor_runtime.adaptors import Adaptor
from openjd.adaptor_runtime.application_ipc import ActionsQueue as _ActionsQueue
from .fake_app_client import FakeAppClient as _FakeAppClient
from openjd.adaptor_runtime._osname import OSName
from openjd.adaptor_runtime.application_ipc import AdaptorServer as _AdaptorServer

if OSName.is_windows():
    from openjd.adaptor_runtime._named_pipe.named_pipe_helper import NamedPipeHelper


@pytest.fixture
def adaptor():
    class FakeAdaptor(Adaptor):
        def __init__(self, path_mapping_rules):
            super().__init__({}, path_mapping_data={"path_mapping_rules": path_mapping_rules})

        def on_run(self, run_data: dict):
            return

    path_mapping_rules = [
        {
            "source_path_format": "windows",
            "source_path": "Z:\\asset_storage1",
            "destination_os": "linux",
            "destination_path": "/mnt/shared/asset_storage1",
        },
        {
            "source_path_format": "windows",
            "source_path": "🌚\\🌒\\🌓\\🌔\\🌝\\🌖\\🌗\\🌘\\🌚",
            "destination_os": "linux",
            "destination_path": "🌝/🌖/🌗/🌘/🌚/🌒/🌓/🌔/🌝",
        },
    ]

    return FakeAdaptor(path_mapping_rules)


def start_test_server(test_server: _AdaptorServer):
    """This is the function responsible for starting the test server.

    Args:
        aq (_ActionsQueue): The queue containing the actions to be performed by application.
    """
    test_server.serve_forever()


def start_test_client(client: _FakeAppClient):
    """Given a client, this app will make the client poll for the next action.

    Args:
        client (_FakeAppClient): The client used in our tests.
    """
    client.poll()


class TestAdaptorIPC:
    """Integration tests to for the Adaptor IPC."""

    @pytest.mark.parametrize(
        argnames=("source_path", "dest_path"),
        argvalues=[
            ("Z:\\asset_storage1\\somefile.png", "/mnt/shared/asset_storage1/somefile.png"),
            ("🌚\\🌒\\🌓\\🌔\\🌝\\🌖\\🌗\\🌘\\🌚", "🌝/🌖/🌗/🌘/🌚/🌒/🌓/🌔/🌝"),
        ],
    )
    def test_map_path(self, adaptor: Adaptor, source_path: str, dest_path: str):
        # GIVEN
        test_server = _AdaptorServer(_ActionsQueue(), adaptor)
        server_thread = _threading.Thread(target=start_test_server, args=(test_server,))
        server_thread.start()

        # Create a client passing in the port number from the server.
        client = _FakeAppClient(test_server.server_path)
        mapped_path = client.map_path(source_path)

        # Giving time to avoid a race condition in which we close the thread before setup.
        _sleep(1)

        # Cleanup
        test_server.shutdown()
        server_thread.join()

        # THEN
        assert mapped_path == dest_path

    @_mock.patch.object(_FakeAppClient, "close")
    @_mock.patch.object(_FakeAppClient, "hello_world")
    def test_action_performed(
        self, mocked_hw: _mock.Mock, mocked_close: _mock.Mock, adaptor: Adaptor
    ):
        """This test will confirm an action was performed on the client."""
        # The argument for the hello world action.
        hw_args = {"foo": "barr"}

        # Create an action queue with actions enqueued
        aq = _ActionsQueue()
        aq.enqueue_action(_Action("hello_world", hw_args))
        aq.enqueue_action(_Action("close"))

        # Create a server and pass the actions queue.
        test_server = _AdaptorServer(aq, adaptor)

        # Create thread for the AdaptorServer.
        server_thread = _threading.Thread(target=start_test_server, args=(test_server,))
        server_thread.start()

        # Create a client passing in the port number from the server.
        client = _FakeAppClient(test_server.server_path)

        # Create a thread for the client.
        client_thread = _threading.Thread(target=start_test_client, args=(client,))
        client_thread.start()

        # Giving time to avoid a race condition in which we close the thread before setup.
        if OSName.is_linux():
            _sleep(1)
        else:
            # TODO: Need to investigate why Windows is slower
            _sleep(5)

        # Cleanup
        test_server.shutdown()
        server_thread.join()
        client_thread.join()

        # Confirming the test ran successfully.
        mocked_hw.assert_called_once_with(hw_args)
        mocked_close.assert_called_once()

    @_mock.patch.object(_FakeAppClient, "close")
    @_mock.patch.object(_FakeAppClient, "hello_world")
    def test_long_polling(self, mocked_hw: _mock.Mock, mocked_close: _mock.Mock, adaptor: Adaptor):
        """This test will test long polling works as expected."""
        # The argument for the hello world action.
        hw_args = {"foo": "barr"}

        # Create an action queue with actions enqueued
        aq = _ActionsQueue()
        aq.enqueue_action(_Action("hello_world", hw_args))

        # Create a server and pass the actions queue.
        test_server = _AdaptorServer(aq, adaptor)

        # Create thread for the AdaptorServer.
        server_thread = _threading.Thread(target=start_test_server, args=(test_server,))
        server_thread.start()

        # Create a client passing in the port number from the server.
        client = _FakeAppClient(test_server.server_path)

        # Create a thread for the client.
        client_thread = _threading.Thread(target=start_test_client, args=(client,))
        client_thread.start()

        # Giving time to avoid a race condition in which we close the thread before setup.
        if OSName.is_linux():
            _sleep(1)
        else:
            # TODO: Need to investigate why Windows is slower
            _sleep(5)

        # Confirming the test ran successfully.
        mocked_hw.assert_called_once_with(hw_args)

        # Sleeping while the client is running to simulate a delay in enqueuing an action.
        # We are going to sleep for less than the REQUEST_TIMEOUT.
        _sleep(2)

        # Verifying close wasn't called.
        assert not mocked_close.called

        def enqueue_close_action():
            """This is the function to enqueue the close action."""
            aq.enqueue_action(_Action("close"))

        # Creating a thread to delay the close action to "force" long polling on the client.
        close_thread = _threading.Thread(target=enqueue_close_action)
        close_thread.start()

        if OSName.is_windows():
            # Need to wait for the action finish
            # TODO: Need to investigate why Windows is slower
            _sleep(3)

        # Cleanup
        test_server.shutdown()
        server_thread.join()
        client_thread.join()
        close_thread.join()

        # Verifying the test was successful.
        mocked_close.assert_called_once()

    @pytest.mark.skipif(not OSName.is_windows(), reason="Windows named pipe test")
    def test_adaptor_ipc_with_incorrect_request_path(self, adaptor: Adaptor):
        # GIVEN
        # Create a server and pass the actions queue.
        test_server = _AdaptorServer(_ActionsQueue(), adaptor)

        # Create thread for the AdaptorServer.
        server_thread = _threading.Thread(target=start_test_server, args=(test_server,))
        server_thread.start()

        # WHEN
        result: Dict = NamedPipeHelper.send_named_pipe_request(test_server.server_path, 5, "GET", "none")  # type: ignore
        # Cleanup
        test_server.shutdown()
        server_thread.join()

        # THEN
        assert "Incorrect request path none." == result["body"]
        assert 404 == result["status"]

    @pytest.mark.skipif(not OSName.is_windows(), reason="Windows named pipe test")
    def test_adaptor_ipc_with_incorrect_request_method(self, adaptor: Adaptor):
        # GIVEN
        # Create a server and pass the actions queue.
        test_server = _AdaptorServer(_ActionsQueue(), adaptor)

        # Create thread for the AdaptorServer.
        server_thread = _threading.Thread(target=start_test_server, args=(test_server,))
        server_thread.start()

        # WHEN
        result: Dict = NamedPipeHelper.send_named_pipe_request(test_server.server_path, 5, "none", "/action")  # type: ignore
        # Cleanup
        test_server.shutdown()
        server_thread.join()

        # THEN
        assert "Incorrect request method none for the path /action." == result["body"]
        assert 405 == result["status"]
