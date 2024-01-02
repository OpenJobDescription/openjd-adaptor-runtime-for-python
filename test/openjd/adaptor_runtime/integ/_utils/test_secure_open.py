# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from openjd.adaptor_runtime._osname import OSName
import pytest
import os
import tempfile
import random
import string

from openjd.adaptor_runtime._utils import secure_open

if OSName.is_windows():
    import win32net
    import win32netcon
    import win32security


def generate_strong_password():
    password_length = 14

    # Generate at least one character from each category
    uppercase = random.choice(string.ascii_uppercase)
    lowercase = random.choice(string.ascii_lowercase)
    digit = random.choice(string.digits)
    special_char = random.choice(string.punctuation)

    # Ensure the rest of the password is made up of a random mix of characters
    remaining_length = password_length - 4
    other_chars = "".join(
        random.choice(string.ascii_letters + string.digits + string.punctuation)
        for _ in range(remaining_length)
    )

    # Combine and shuffle
    password = list(uppercase + lowercase + digit + special_char + other_chars)
    random.shuffle(password)
    password = "".join(password)

    return password


@pytest.fixture
def win_test_user():
    username = "RuntimeAdaptorTester"
    # No one need to know this password. So we will generate it randomly.
    password = generate_strong_password()

    def create_user():
        try:
            win32net.NetUserGetInfo(None, username, 1)
            print(f"User '{username}' already exists. Skip the User Creation")
        except win32net.error:
            # https://learn.microsoft.com/en-us/windows/win32/api/lmaccess/nf-lmaccess-netuseradd#examples
            user_info = {
                "name": username,
                "password": password,
                # The privilege level of the user. USER_PRIV_USER is a standard user.
                "priv": win32netcon.USER_PRIV_USER,
                "home_dir": None,
                "comment": None,
                # Account control flags. UF_SCRIPT is required here.
                "flags": win32netcon.UF_SCRIPT,
                "script_path": None,
            }
            try:
                win32net.NetUserAdd(None, 1, user_info)
                print(f"User '{username}' created successfully.")
            except Exception as e:
                print(f"Failed to create user '{username}': {e}")
                raise e

    def delete_user():
        try:
            win32net.NetUserDel(None, username)
            print(f"User '{username}' deleted successfully.")
        except win32net.error as e:
            print(f"Failed to delete user '{username}': {e}")
            raise e

    create_user()
    yield username, password
    # Delete the user after test completes
    delete_user()


@pytest.fixture
def create_file():
    """
    This fixture will create a file which can be only read / written by the file owner
    """
    characters = string.ascii_letters + string.digits + string.punctuation
    file_content = "".join(random.choice(characters) for _ in range(10))
    test_file_name = (
        f"secure_open_test_{''.join(random.choice(string.ascii_letters) for _ in range(10))}.txt"
    )
    test_file_path = os.path.join(tempfile.gettempdir(), test_file_name)
    with secure_open(test_file_path, open_mode="w") as test_file:
        test_file.write(file_content)
    yield test_file_path, file_content
    os.remove(test_file_path)


class TestSecureOpen:
    def test_secure_open_write_and_read(self, create_file):
        """
        Test if the file owner can write and read the file
        """
        test_file_path, file_content = create_file
        with secure_open(test_file_path, open_mode="r") as test_file:
            result = test_file.read()
        assert result == file_content

    @pytest.mark.skipif(not OSName.is_windows(), reason="Windows-specific tests")
    def test_secure_open_file_windows_permission(self, create_file, win_test_user):
        """
        Test if only the file owner has the permission to read the file.
        """
        test_file_path, file_content = create_file
        user_name, password = win_test_user
        logon_type = win32security.LOGON32_LOGON_INTERACTIVE
        provider = win32security.LOGON32_PROVIDER_DEFAULT

        # Log on with the user's credentials and get the token handle
        token_handle = win32security.LogonUser(user_name, "", password, logon_type, provider)
        # Impersonate the user
        win32security.ImpersonateLoggedOnUser(token_handle)

        try:
            with pytest.raises(PermissionError):
                with open(test_file_path, "r") as f:
                    f.read()
        finally:
            # Revert the impersonation
            win32security.RevertToSelf()
