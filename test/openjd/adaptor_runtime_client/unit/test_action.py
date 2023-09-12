# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

import json as _json
from dataclasses import asdict as _asdict

import pytest
from _pytest.capture import CaptureFixture as _CaptureFixture

from openjd.adaptor_runtime_client import Action as _Action


class TestAction:
    def test_action_dict_cast(self) -> None:
        """Tests the action can be converted to a dictionary we expect."""
        name = "test"
        args = None
        expected_dict = {"name": name, "args": args}

        a = _Action(name)

        assert _asdict(a) == expected_dict

    def test_action_to_from_string(self) -> None:
        """Test that the action can be turned into a string and a string can be converted to an
        action."""
        name = "test"
        args = None
        expected_dict_str = _json.dumps({"name": name, "args": args})

        a = _Action(name)

        # Testing the action can be converted to a string as expected
        assert str(a) == expected_dict_str

        # Testing that we can convert bytes to an Action
        # This also tests Action.from_json_string.
        a2 = _Action.from_bytes(expected_dict_str.encode())

        assert a2 is not None
        if a2 is not None:  # This is just for mypy
            assert a.name == a2.name
            assert a.args == a2.args

    json_errors = [
        pytest.param(
            "action_1",
            'Unable to convert "action_1" to json. The following exception was raised:',
            id="NonvalidJSON",
        ),
        pytest.param(
            '{"foo": "bar"}',
            "Unable to convert the json dictionary ({'foo': 'bar'}) to an action. The following "
            "exception was raised:",
            id="NonvalidKeys",
        ),
    ]

    @pytest.mark.parametrize("json_str, expected_error", json_errors)
    def test_action_from_nonvalid_string(
        self, json_str: str, expected_error: str, capsys: _CaptureFixture
    ) -> None:
        """Testing that exceptions were raised properly when attempting to convert a string to an
        action."""
        a = _Action.from_json_string(json_str)

        assert a is None
        assert expected_error in capsys.readouterr().err
