# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

import os
import stat
from unittest.mock import mock_open, patch

import pytest

from openjd.adaptor_runtime._osname import OSName
from openjd.adaptor_runtime._utils import secure_open

READ_FLAGS = os.O_RDONLY
WRITE_FLAGS = os.O_WRONLY | os.O_TRUNC | os.O_CREAT
APPEND_FLAGS = os.O_WRONLY | os.O_APPEND | os.O_CREAT
EXCL_FLAGS = os.O_EXCL | os.O_CREAT | os.O_WRONLY
UPDATE_FLAGS = os.O_RDWR | os.O_CREAT

FLAG_DICT = {
    "r": READ_FLAGS,
    "w": WRITE_FLAGS,
    "a": APPEND_FLAGS,
    "x": EXCL_FLAGS,
    "+": UPDATE_FLAGS,
    "": 0,
}


@pytest.mark.parametrize(
    argnames=["path", "open_mode", "mask", "expected_os_open_kwargs"],
    argvalues=[
        (
            "/path/to/file",
            "".join((mode, update_flag)),
            mask,
            {
                "path": "/path/to/file",
                "flags": FLAG_DICT[mode] | FLAG_DICT[update_flag],
                "mode": stat.S_IWUSR | stat.S_IRUSR | mask,
            },
        )
        for mode in ("r", "w", "a", "x")
        for update_flag in ("", "+")
        for mask in (stat.S_IRGRP | stat.S_IWGRP, 0)
    ],
)
@patch.object(os, "open")
@pytest.mark.skipif(not OSName.is_linux(), reason="Linux-specific tests")
def test_secure_open_in_linux(mock_os_open, path, open_mode, mask, expected_os_open_kwargs):
    # WHEN
    with patch("builtins.open", mock_open()) as mocked_open:
        secure_open_kwargs = {"mask": mask} if mask else {}
        with secure_open(path, open_mode, **secure_open_kwargs):
            pass

    # THEN
    if open_mode == "r":
        del expected_os_open_kwargs["mode"]
    mock_os_open.assert_called_once_with(**expected_os_open_kwargs)
    mocked_open.assert_called_once_with(mock_os_open.return_value, open_mode)


@pytest.mark.parametrize(
    argnames=["path", "open_mode", "expected_os_open_kwargs"],
    argvalues=[
        (
            "/path/to/file",
            "".join((mode, update_flag)),
            {
                "path": "/path/to/file",
                "flags": FLAG_DICT[mode] | FLAG_DICT[update_flag],
            },
        )
        for mode in ("r", "w", "a", "x")
        for update_flag in ("", "+")
    ],
)
@patch.object(os, "open")
@patch("openjd.adaptor_runtime._utils._secure_open.set_file_permissions_in_windows")
@pytest.mark.skipif(not OSName.is_windows(), reason="Windows-specific tests")
def test_secure_open_in_windows(
    mock_file_permission_setting, mock_os_open, path, open_mode, expected_os_open_kwargs
):
    # WHEN
    with patch("builtins.open", mock_open()) as mocked_open:
        secure_open_kwargs = {}
        with secure_open(path, open_mode, **secure_open_kwargs):
            pass

    # THEN
    mock_os_open.assert_called_once_with(**expected_os_open_kwargs)
    mocked_open.assert_called_once_with(mock_os_open.return_value, open_mode)


@pytest.mark.parametrize(
    argnames=["path", "open_mode", "encoding", "newline"],
    argvalues=[
        (
            "/path/to/file",
            "w",
            encoding,
            newline,
        )
        for encoding in ("utf-8", "utf-16", None)
        for newline in ("\n", "\r\n", None)
    ],
)
@patch.object(os, "open")
@patch("openjd.adaptor_runtime._utils._secure_open.set_file_permissions_in_windows")
def test_secure_open_passes_open_kwargs(
    mock_file_permission_setting, mock_os_open, path, open_mode, encoding, newline
):
    # WHEN
    open_kwargs = {}
    if encoding:
        open_kwargs["encoding"] = encoding
    if newline:
        open_kwargs["newline"] = newline

    with patch("builtins.open", mock_open()) as mocked_open:
        with secure_open(path, open_mode, **open_kwargs):
            pass

    # THEN
    mocked_open.assert_called_once_with(mock_os_open.return_value, open_mode, **open_kwargs)


def test_raises_when_nonvalid_mode():
    # WHEN
    with pytest.raises(ValueError) as exc_info:
        with secure_open("/path/to/file", "something"):
            pass

    # THEN
    assert str(exc_info.value) == "Nonvalid mode: 'something'"
