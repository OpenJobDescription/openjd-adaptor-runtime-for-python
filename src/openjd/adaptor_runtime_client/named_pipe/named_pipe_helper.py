# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from random import randint

import win32file
import pywintypes
import win32security
import win32con
import getpass
import winerror
import time
import win32pipe
import json
from typing import Dict, List, Optional
from pywintypes import HANDLE
from enum import Enum
import os


from .named_pipe_config import (
    NAMED_PIPE_BUFFER_SIZE,
    DEFAULT_MAX_NAMED_PIPE_INSTANCES,
    DEFAULT_NAMED_PIPE_SERVER_TIMEOUT_IN_SECONDS,
)

_logger = logging.getLogger(__name__)


class NamedPipeOperation(str, Enum):
    CONNECT = "connect"
    READ = "read"


class PipeDisconnectedException(Exception):
    """
    Exception raised when a Named Pipe is either broken or not connected.

    Attributes:
        error (pywintypes.error): An error raised by pywin32.
    """

    def __init__(self, error: pywintypes.error):
        self.winerror = error.winerror  # The numerical error code
        self.funcname = error.funcname  # The name of the function that caused the error
        self.strerror = error.strerror  # The human-readable error message

        self.message = f"An error occurred: {error.strerror} (Error code: {error.winerror}) in function {error.funcname }"
        super().__init__(self.message)

    def __str__(self):
        return self.message


class NamedPipeTimeoutError(Exception):
    """A custom error raised on timeouts when waiting for another error."""

    def __init__(
        self, operation: NamedPipeOperation, duration: float, error: Optional[Exception] = None
    ):
        """NamedPipe timeout exception.

        Args:
            operation (NamedPipeOperation): The type of NamedPipe operation that timed out.
            duration (float): The duration waited in seconds.
            error (Exception): The original error that was raised, if an error was raised by the operation.
        """
        self.error = error

        message = f"NamedPipe Server {operation.value} timeout after {duration} seconds."
        if error:
            message = os.linesep.join([message, f"Original error: {error}"])

        super().__init__(message)


class NamedPipeConnectTimeoutError(NamedPipeTimeoutError):
    """A custom error raised on connect timeouts when waiting for another error."""

    def __init__(self, duration: float, error: Exception):
        """Initialize TimeoutError with original error.

        Args:
            duration (float): The duration waited in seconds.
            error (Exception): The original error that was raised.
        """
        self.error = error
        super().__init__(NamedPipeOperation.CONNECT, duration, error)


class NamedPipeReadTimeoutError(NamedPipeTimeoutError):
    """A custom error raised on read timeouts."""

    def __init__(self, duration: float):
        """Initialize TimeoutError with original error.

        Args:
            duration (float): The duration waited in seconds.
        """
        super().__init__(NamedPipeOperation.READ, duration)


class NamedPipeNamingError(Exception):
    """Exception raised for errors in naming a named pipe."""

    pass


class NamedPipeHelper:
    """
    Helper class for reading from and writing to Named Pipes in Windows.

    This class provides static methods to interact with Named Pipes,
    facilitating data transmission between the server and the client.
    """

    @staticmethod
    def create_security_attributes():
        """
        Creates and returns security attributes for a named pipe,
        allowing access only to the current user and denying network access.

        Returns:
            win32security.SECURITY_ATTRIBUTES: A SECURITY_ATTRIBUTES object configured with the custom security descriptor.
        """

        # Get the username of the current user
        username = getpass.getuser()

        # Get the SID for the current user
        user_sid, _, _ = win32security.LookupAccountName(
            "",  # systemName: The name of the system or server where the account resides.
            # Search for the account on the local computer.
            # If Domain/User Format is used here, it will fetch the Name from the AD.
            username,
        )

        # Users who log on across a network. "S-1-5-2" is a group identifier added to the token of a process
        # when it was logged on across a network.
        # https://learn.microsoft.com/en-us/windows/win32/secauthz/well-known-sids
        network_sid = win32security.ConvertStringSidToSid("S-1-5-2")

        # Create a security descriptor and DACL
        security_descriptor = win32security.SECURITY_DESCRIPTOR()
        dacl = win32security.ACL()

        # Add a rule that allows the current user full control
        dacl.AddAccessAllowedAce(
            win32security.ACL_REVISION, win32con.GENERIC_READ | win32con.GENERIC_WRITE, user_sid
        )

        # Add a rule that denies network access
        dacl.AddAccessDeniedAce(win32security.ACL_REVISION, win32con.GENERIC_ALL, network_sid)

        # Set the ACL to the security descriptor
        security_descriptor.SetSecurityDescriptorDacl(
            1,  # A flag that indicates the presence of a DACL in the security descriptor.
            dacl,  # The DACL itself
            0,  # 0 means False. DACL has been explicitly specified by a user
        )

        # Create security attributes
        security_attributes = win32security.SECURITY_ATTRIBUTES()
        security_attributes.SECURITY_DESCRIPTOR = security_descriptor

        return security_attributes

    @staticmethod
    def create_named_pipe_server(pipe_name: str, time_out_in_seconds: float) -> Optional[HANDLE]:
        """
        Creates a new instance of a named pipe or an additional instance if the pipe already exists.

        Args:
            pipe_name (str): Name of the pipe for which the instance is to be created.
            time_out_in_seconds (float): time out in seconds in service side.

        Returns:
            HANDLE: The handler for the created named pipe instance.

        """

        pipe_handle = win32pipe.CreateNamedPipe(
            pipe_name,
            # A bi-directional pipe; both server and client processes can read from and write to the pipe.
            win32pipe.PIPE_ACCESS_DUPLEX,
            win32pipe.PIPE_TYPE_MESSAGE | win32pipe.PIPE_READMODE_MESSAGE | win32pipe.PIPE_WAIT,
            DEFAULT_MAX_NAMED_PIPE_INSTANCES,
            NAMED_PIPE_BUFFER_SIZE,  # nOutBufferSize
            NAMED_PIPE_BUFFER_SIZE,  # nInBufferSize
            time_out_in_seconds,
            NamedPipeHelper.create_security_attributes(),
        )
        if pipe_handle == win32file.INVALID_HANDLE_VALUE:
            return None
        return pipe_handle

    @staticmethod
    def _handle_pipe_exception(e: pywintypes.error) -> None:
        """
        Handles exceptions related to pipe operations.

        Args:
            e (pywintypes.error): The caught exception.

        Raises:
            PipeDisconnectedException: When the pipe is disconnected, broken, or invalid.
        """
        if e.winerror in [
            winerror.ERROR_BROKEN_PIPE,
            winerror.ERROR_PIPE_NOT_CONNECTED,
            winerror.ERROR_INVALID_HANDLE,
        ]:
            raise PipeDisconnectedException(e)
        else:
            raise

    @staticmethod
    def read_from_pipe_target(handle: HANDLE):
        """
        Reads data from a Named Pipe. Times out after timeout_in_seconds.
        Note: This method should be run in a thread with a timeout.
              win32.ReadFile can hang up, causing this to run indefinitely.

        Args:
            handle (HANDLE): The handle to the Named Pipe.
        """
        data_parts: List[str] = []
        while True:
            try:
                return_code, data = win32file.ReadFile(handle, NAMED_PIPE_BUFFER_SIZE)
                data_parts.append(data.decode("utf-8"))
                if return_code == winerror.ERROR_MORE_DATA:
                    continue
                elif return_code == winerror.NO_ERROR:
                    return data_parts
                else:
                    raise IOError(
                        f"Got error when reading from the Named Pipe with error code: {return_code}"
                    )
            # Server maybe shutdown during reading.
            except pywintypes.error as e:
                NamedPipeHelper._handle_pipe_exception(e)

    @staticmethod
    def read_from_pipe(handle: HANDLE, timeout_in_seconds: Optional[float] = 5.0) -> str:  # type: ignore
        """
        Reads data from a Named Pipe. Times out after timeout_in_seconds.

        Args:
            handle (HANDLE): The handle to the Named Pipe.
            timeout_in_seconds (Optional[float]): The maximum time in seconds to wait for data before
                raising a TimeoutError. Defaults to 5 seconds. None means waiting indefinitely.

        Returns:
            str: The data read from the Named Pipe.
        """

        with ThreadPoolExecutor(max_workers=1) as executor:
            start_time = time.time()
            future = executor.submit(NamedPipeHelper.read_from_pipe_target, handle)

            try:
                # Retrieve the result of the function with a timeout
                data_parts = future.result(timeout=timeout_in_seconds)
            except TimeoutError:
                # Close the handle will interrupt the ReadFile and the thread will end
                handle.close()
                duration = time.time() - start_time
                raise NamedPipeReadTimeoutError(duration)

        return "".join(data_parts)

    @staticmethod
    def write_to_pipe(handle: HANDLE, message: str) -> None:  # type: ignore
        """
        Writes data to a Named Pipe.

        Args:
            handle (HANDLE): The handle to the Named Pipe.
            message (str): The message to write to the Named Pipe.

        """
        try:
            win32file.WriteFile(handle, message.encode("utf-8"))
        # Server maybe shutdown during writing.
        except pywintypes.error as e:
            NamedPipeHelper._handle_pipe_exception(e)

    @staticmethod
    def establish_named_pipe_connection(pipe_name: str, timeout_in_seconds: float) -> HANDLE:
        """
        Creates a client handle for connecting to a named pipe server.

        This function attempts to establish a connection to a named pipe server.
        It keeps trying until the connection is successful or the specified timeout is exceeded.
        If the server pipe is not available (either not found or busy), it waits and retries.
        Once connected, the pipe is set to message-read mode.

        Args:
            pipe_name (str): The name of the pipe to connect to.
            timeout_in_seconds (float): The maximum time in seconds to wait for the server pipe
                to become available before raising an error. If None, the function will wait indefinitely.

        Returns:
            HANDLE: A handle to the connected pipe.

        Raises:
            pywintypes.error: If the connection cannot be established within the timeout period
                or due to other errors.

        """
        start_time = time.time()
        # Wait for the server pipe to become available.
        handle = None
        while handle is None:
            try:
                handle = win32file.CreateFile(
                    pipe_name,  # pipe name
                    # Give the read / write permission
                    win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                    0,  # Disable the sharing Mode
                    NamedPipeHelper.create_security_attributes(),
                    win32file.OPEN_EXISTING,  # Open existing pipe
                    0,  # No Additional flags
                    None,  # A valid handle to a template file, This parameter is ignored when opening an existing pipe.
                )
            except pywintypes.error as e:
                # NamedPipe server may be not ready,
                # or no additional resource to create new instance and need to wait for previous connection release
                if e.winerror in [winerror.ERROR_FILE_NOT_FOUND, winerror.ERROR_PIPE_BUSY]:
                    duration = time.time() - start_time
                    time.sleep(0.1)
                    # Check timeout limit
                    if duration > timeout_in_seconds:
                        _logger.error(
                            f"NamedPipe Server connect timeout. Duration: {duration} seconds, "
                            f"Timeout limit: {timeout_in_seconds} seconds."
                        )
                        raise NamedPipeConnectTimeoutError(duration, e)
                    continue
                _logger.error(f"Could not open pipe: {e}")
                raise e

        # Switch to message-read mode for the pipe. This ensures that each write operation is treated as a
        # distinct message. For example, a single write operation like "Hello from client." will be read
        # entirely in one request, avoiding partial reads like "Hello fr".
        win32pipe.SetNamedPipeHandleState(
            handle,  # The handle to the named pipe.
            win32pipe.PIPE_READMODE_MESSAGE,  # Set the pipe to message mode
            # Maximum bytes collected before transmission to the server.
            # 'None' means the system's default value is used.
            None,
            # Maximum time to wait
            # 'None' means the system's default value is used.
            None,
        )

        return handle

    @staticmethod
    def send_named_pipe_request(
        pipe_name: str,
        timeout_in_seconds: Optional[float],
        method: str,
        path: str,
        *,
        params: Optional[Dict] = None,
        json_body: Optional[Dict] = None,
    ) -> Dict:
        """
        Sends a request to a named pipe server and receives the response.

        This method establishes a connection to a named pipe server, sends a JSON-formatted request,
        and waits for a response.

        Args:
            pipe_name (str): The name of the pipe to connect to.
            timeout_in_seconds (Optional[float]): The maximum time in seconds to wait for the server to response.
                None means no timeout.
            method (str): The HTTP method type (e.g., 'GET', 'POST').
            path (str): The request path.
            params (dict, optional): Dictionary of URL parameters to append to the path.
            json_body (dict, optional): Dictionary representing the JSON body of the request.

        Returns:
            Dict: The parsed JSON response from the server.

        Raises:
            pywintypes.error: If there are issues in establishing a connection or sending the request.
            json.JSONDecodeError: If there is an error in parsing the server's response.
        """

        handle = NamedPipeHelper.establish_named_pipe_connection(
            pipe_name, DEFAULT_NAMED_PIPE_SERVER_TIMEOUT_IN_SECONDS
        )
        try:
            message_dict = {
                "method": method,
                "path": path,
            }

            if json_body:
                message_dict["body"] = json.dumps(json_body)
            if params:
                message_dict["params"] = json.dumps(params)
            message = json.dumps(message_dict)
            NamedPipeHelper.write_to_pipe(handle, message)
            result = NamedPipeHelper.read_from_pipe(handle, timeout_in_seconds)
        finally:
            handle.close()
        return json.loads(result)

    @staticmethod
    def check_named_pipe_exists(pipe_name: str) -> bool:
        """
        Checks if a named pipe exists.

        Args:
            pipe_name (str): The name of the pipe to check.

        Returns:
            bool: True if the pipe exists, False otherwise.
        """
        try:
            handle = win32file.CreateFile(
                pipe_name,
                win32file.GENERIC_READ,
                0,  # Disable the sharing Mode
                None,  # Don't need any security attributes
                win32file.OPEN_EXISTING,  # Open existing pipe
                0,  # No Additional flags
                None,  # A valid handle to a template file, This parameter is ignored when opening an existing pipe.
            )
            handle.close()
        except pywintypes.error as e:
            if e.winerror == winerror.ERROR_FILE_NOT_FOUND:
                return False
        return True

    @staticmethod
    def generate_pipe_name(prefix: str) -> str:
        """
        Generates a unique named pipe name.

        Args:
            prefix (str): The prefix to use for the pipe name.

        Returns:
            str: The unique named pipe name.
        """

        pipe_name = rf"\\.\pipe\{prefix}_{str(os.getpid())}"

        for i in range(5):
            if not NamedPipeHelper.check_named_pipe_exists(pipe_name):
                return pipe_name
            else:
                pipe_name = rf"\\.\pipe\{prefix}_{str(os.getpid())}_{str(i)}_{str(randint(0, 999))}"
        raise NamedPipeNamingError("Cannot find an available pipe name.")
