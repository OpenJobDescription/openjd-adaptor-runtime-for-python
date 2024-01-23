# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
import platform
from typing import Generator

from openjd.adaptor_runtime._osname import OSName
import string
import random
import pytest

if OSName.is_windows():
    import win32net
    import win32netcon


# List of platforms that can be used to mark tests as specific to that platform
# See [tool.pytest.ini_options] -> markers in pyproject.toml
_PLATFORMS = set(
    [
        "Linux",
        "Windows",
        "Darwin",
    ]
)


def pytest_runtest_setup(item: pytest.Item):
    """
    Hook that is run for each test.
    """

    # Skip platform-specific tests that don't apply to current platform
    supported_platforms = set(_PLATFORMS).intersection(mark.name for mark in item.iter_markers())
    plat = platform.system()
    if supported_platforms and plat not in supported_platforms:
        pytest.skip(f"Skipping non-{plat} test: {item.name}")


@pytest.fixture(scope="session")
def win_test_user() -> Generator:
    def generate_strong_password() -> str:
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
        password_characters = list(uppercase + lowercase + digit + special_char + other_chars)
        random.shuffle(password_characters)
        return "".join(password_characters)

    username = "RuntimeAdaptorTester"
    # No one need to know this password. So we will generate it randomly.
    password = generate_strong_password()

    def create_user() -> None:
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

    def delete_user() -> None:
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
