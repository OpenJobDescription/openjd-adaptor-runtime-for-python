# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from openjd.adaptor_runtime_client import ClientInterface

if TYPE_CHECKING:
    from types import FrameType
    from typing import Any


class AdaptorClient(ClientInterface):
    """
    This class uses the Adaptor Runtime's Python implementation for a client that can request and handle
    actions from the server in adaptor_example.py.

    In this case, the contract between the server in AdaptorExample.py and this client consists of a single
    "print" command, in addition to the built-in "close" command.
    """

    def __init__(self, server_path: str) -> None:
        super().__init__(server_path)
        # All customized actions needed to be put in this dict
        # There is key value pair is pre-defined in this dict {"close": self.close}
        self.actions.update(
            {
                "print": self.print,
            }
        )

    def print(self, args: dict[str, Any] | None) -> None:
        """
        This function prints a message fetched from an action queue when `print` action is fetched from the action queue.
        """
        if args is None:
            print("App: 'args' in print action is None", flush=True)
        else:
            print(f"App: {args.get('message')}", flush=True)

    def close(self, args: dict[str, Any] | None) -> None:
        print("'close' function is called", flush=True)

    def graceful_shutdown(self, signum: int, frame: FrameType | None) -> None:
        """
        This function will be called when the application got the SIGTERM in the Linux or SIGBREAK in Windows.
        """
        print(f"received signal: {signum}\ngracefully shutting down", flush=True)


def main():
    if len(sys.argv) < 2:
        print("Argument for server path required, but no arguments were passed")
        sys.exit(1)

    client = AdaptorClient(str(sys.argv[1]))
    client.poll()


if __name__ == "__main__":
    main()
