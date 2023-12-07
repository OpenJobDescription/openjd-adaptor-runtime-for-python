# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from __future__ import annotations

from typing import Any as _Any
from typing import Dict as _Dict
from typing import Optional as _Optional

from openjd.adaptor_runtime_client import ClientInterface as _ClientInterface


class FakeAppClient(_ClientInterface):
    def __init__(self, socket_path: str) -> None:
        super().__init__(socket_path)
        self.actions.update({"hello_world": self.hello_world})

    def close(self, args: _Optional[_Dict[str, _Any]]) -> None:
        print("closing")

    def hello_world(self, args: _Optional[_Dict[str, _Any]]) -> None:
        print(f"args = {args}")

    def graceful_shutdown(self):
        print("Gracefully shutting down.")
