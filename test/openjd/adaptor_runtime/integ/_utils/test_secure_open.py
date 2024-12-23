# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from openjd.adaptor_runtime._osname import OSName
import pytest
import os
import tempfile
import random
import string

from openjd.adaptor_runtime._utils import secure_open

if OSName.is_windows():
    import win32security


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
    with secure_open(test_file_path, open_mode="w", encoding="utf-8") as test_file:
        test_file.write(file_content)
    yield test_file_path, file_content
    os.remove(test_file_path)


class TestSecureOpen:
    def test_secure_open_write_and_read(self, create_file):
        """
        Test if the file owner can write and read the file
        """
        test_file_path, file_content = create_file
        with secure_open(test_file_path, open_mode="r", encoding="utf-8") as test_file:
            result = test_file.read()
        assert result == file_content

    @pytest.mark.skipif(not OSName.is_windows(), reason="Windows-specific tests")
    @pytest.mark.skipif(
        os.getenv("GITHUB_ACTIONS") != "true",
        reason="Skip this test in local env to avoid user creation with elevated privilege.",
    )
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
                with open(test_file_path, "r", encoding="utf-8") as f:
                    f.read()
        finally:
            # Revert the impersonation
            win32security.RevertToSelf()
