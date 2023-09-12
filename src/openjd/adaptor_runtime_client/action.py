# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from __future__ import annotations

import json as _json
import sys as _sys
from dataclasses import asdict as _asdict
from dataclasses import dataclass as _dataclass
from typing import Any as _Any
from typing import Dict as _Dict
from typing import Optional as _Optional


@_dataclass(frozen=True)
class Action:
    """This is the class representation of the Actions to be performed on the DCC."""

    name: str
    args: _Optional[_Dict[str, _Any]] = None

    def __str__(self) -> str:
        return _json.dumps(_asdict(self))

    @staticmethod
    def from_json_string(json_str: str) -> _Optional[Action]:
        try:
            ad = _json.loads(json_str)
        except Exception as e:
            print(
                f'ERROR: Unable to convert "{json_str}" to json. The following exception was '
                f"raised:\n{e}",
                file=_sys.stderr,
                flush=True,
            )
            return None

        try:
            return Action(ad["name"], ad["args"])
        except Exception as e:
            print(
                f"ERROR: Unable to convert the json dictionary ({ad}) to an action. The following "
                f"exception was raised:\n{e}",
                file=_sys.stderr,
                flush=True,
            )
            return None

    @staticmethod
    def from_bytes(s: bytes) -> _Optional[Action]:
        return Action.from_json_string(s.decode())
