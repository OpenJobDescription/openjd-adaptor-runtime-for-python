# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from __future__ import annotations

from argparse import ArgumentParser as _ArgumentParser
from signal import Signals
from time import sleep as _sleep
from types import FrameType as _FrameType
from threading import Thread as _Thread
from typing import Any as _Any
from typing import Dict as _Dict
from typing import Optional as _Optional

from openjd.adaptor_runtime_client import ClientInterface as _ClientInterface


class FakeClient(_ClientInterface):
    shutdown: bool

    def __init__(self, port: str) -> None:
        super().__init__(port)
        self.shutdown = False

    def close(self, args: _Optional[_Dict[str, _Any]]) -> None:
        print("closing")

    def graceful_shutdown(self, signum: int, frame: _Optional[_FrameType]) -> None:
        print(f"Received {Signals(signum).name} signal.")
        self.shutdown = True

    def run(self):
        count = 0
        while not self.shutdown:
            _sleep(0.25)
            count += 1


def run_client():
    test_client = FakeClient("1234")
    test_client.run()


if __name__ == "__main__":
    parser = _ArgumentParser()
    parser.add_argument("--run-in-thread", action="store_true")
    args = parser.parse_args()

    if args.run_in_thread:
        threaded_client = _Thread(target=run_client)
        threaded_client.start()
    else:
        run_client()
