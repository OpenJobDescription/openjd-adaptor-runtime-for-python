# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
import time

from openjd.adaptor_runtime._osname import OSName
import json
import os
import pytest
import threading

if OSName.is_windows():
    import pywintypes
    import win32file
    import win32pipe
    import win32security
    import win32api
    from openjd.adaptor_runtime_client.named_pipe.named_pipe_helper import NamedPipeHelper
else:
    # Cannot put this on the top of this file or mypy will complain
    pytest.mark.skip(reason="NamedPipe is only implemented in Windows.")

PIPE_NAME = r"\\.\pipe\TestPipe"
TIMEOUT_SECONDS = 5


def pipe_server(pipe_name, message_to_send, return_message):
    """
    A simple pipe server for testing.
    """
    server_handle = NamedPipeHelper.create_named_pipe_server(pipe_name, TIMEOUT_SECONDS)
    win32pipe.ConnectNamedPipe(server_handle, None)
    received_message = NamedPipeHelper.read_from_pipe(server_handle)
    received_obj = json.loads(received_message)
    assert received_obj["method"] == message_to_send["method"]
    assert received_obj["path"] == message_to_send["path"]
    assert json.loads(received_obj["body"]) == message_to_send["json_body"]
    NamedPipeHelper.write_to_pipe(server_handle, return_message)
    win32file.CloseHandle(server_handle)


@pytest.fixture
def start_pipe_server():
    """
    Fixture to start the pipe server in a separate thread.
    """
    message_to_send = dict(method="POST", path="/test", json_body={"message": "Hello from client"})
    return_message = '{"Response":"Hello from server"}'
    server_thread = threading.Thread(
        target=pipe_server, args=(PIPE_NAME, message_to_send, return_message)
    )
    server_thread.start()
    yield message_to_send, return_message
    server_thread.join()


@pytest.mark.skipif(not OSName.is_windows(), reason="NamedPipe is only implemented in Windows.")
class TestNamedPipeHelper:
    def test_named_pipe_communication(self, start_pipe_server):
        """
        A test for validating basic NamedPipe functions, Connect, Read, Write
        """
        # GIVEN
        message_to_send, expected_response = start_pipe_server

        # WHEN
        response = NamedPipeHelper.send_named_pipe_request(
            PIPE_NAME, TIMEOUT_SECONDS, **message_to_send
        )

        # THEN
        assert response == json.loads(expected_response)

    def test_check_named_pipe_exists(self):
        """
        Test if the script can check if a named pipe exists.
        """

        # GIVEN
        pipe_name = r"\\.\pipe\test_if_named_pipe_exist"
        assert not NamedPipeHelper.check_named_pipe_exists(pipe_name)
        server_handle = NamedPipeHelper.create_named_pipe_server(pipe_name, TIMEOUT_SECONDS)

        # WHEN
        is_existed = False
        # Need to wait for launching the NamedPipe Server
        for _ in range(10):
            if NamedPipeHelper.check_named_pipe_exists(pipe_name):
                is_existed = True
                break
            time.sleep(1)

        # THEN
        win32file.CloseHandle(server_handle)
        assert is_existed

    @pytest.mark.skipif(
        os.getenv("GITHUB_ACTIONS") != "true",
        reason="Skip this test in local env to avoid user creation with elevated privilege.",
    )
    def test_fail_to_connect_to_named_pipe_with_different_user(
        self, win_test_user, start_pipe_server
    ):
        """
        This test is used for validating the security descriptor is working.
        Only the user who start running the named pipe server can connect to it.
        Any other users will get the error `Access is denied`
        """
        # GIVEN
        user_name, password = win_test_user
        logon_type = win32security.LOGON32_LOGON_INTERACTIVE
        provider = win32security.LOGON32_PROVIDER_DEFAULT
        message_to_send, expected_response = start_pipe_server

        # WHEN
        # Log on with the user's credentials and get the token handle
        token_handle = win32security.LogonUser(user_name, "", password, logon_type, provider)
        # Impersonate the user
        win32security.ImpersonateLoggedOnUser(token_handle)

        # THEN
        with pytest.raises(pywintypes.error) as excinfo:
            NamedPipeHelper.send_named_pipe_request(PIPE_NAME, TIMEOUT_SECONDS, **message_to_send)
            assert "Access is denied" in str(excinfo.value)

        # Revert the impersonation
        win32security.RevertToSelf()

        # Close the token handle
        win32api.CloseHandle(token_handle)

        # Send a message to unblock the I/O
        NamedPipeHelper.send_named_pipe_request(PIPE_NAME, TIMEOUT_SECONDS, **message_to_send)
