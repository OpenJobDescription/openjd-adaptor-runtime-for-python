# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

import logging
import os
import sys
import threading
import time

from openjd.adaptor_runtime.adaptors import Adaptor, SemanticVersion
from openjd.adaptor_runtime.application_ipc import ActionsQueue, AdaptorServer
from openjd.adaptor_runtime.process import LoggingSubprocess
from openjd.adaptor_runtime_client import Action

_logger = logging.getLogger(__name__)


class AdaptorExample(Adaptor):
    """
    This adaptor runs in the adaptor runtime, which invokes the various on_* methods defined here.
    In each of these methods, this adaptor will send commands (in response to a request) to the application
    process for it to perform. In this example, the application simply prints a message; however, in real adaptors,
    these commands correspond to operations that can be done in the 3rd party application.
    """

    def __init__(self, init_data: dict, **_):
        super().__init__(init_data)
        self.actions = ActionsQueue()

    @property
    def integration_data_interface_version(self) -> SemanticVersion:
        return SemanticVersion(major=0, minor=1)

    def on_start(self) -> None:
        _logger.info("on_start")
        # Start the server thread
        self.server = AdaptorServer(
            actions_queue=self.actions,
            adaptor=self,
        )
        self.server_thread = threading.Thread(
            target=self.server.serve_forever,
            name="AdaptorExampleServerThread",
        )
        self.server_thread.start()

        # Start the adaptor client process
        self.adaptor_client_process = LoggingSubprocess(
            args=[
                sys.executable,
                os.path.join(os.path.dirname(__file__), "adaptor_client.py"),
                self.server.server_path,
            ],
            logger=_logger,
        )

        # Wait for the adaptor client process to start
        while not self.adaptor_client_process.is_running:
            if (return_code := self.adaptor_client_process.returncode) is not None:
                raise Exception(
                    f"Application process unexpectedly exited with return code {return_code}"
                )
            else:
                time.sleep(0.1)

        self.enqueue_print("`on_start` is called.")
        # do something
        time.sleep(0.5)
        self.enqueue_print("`on_start` is finished.")

    def on_run(self, run_data: dict) -> None:
        _logger.info(f"on_run: {run_data}")
        self.enqueue_print(f"`on_run` is called with run_data: {run_data}")
        # do something
        time.sleep(0.5)
        self.enqueue_print("`on_run` is finished.")

    def on_end(self) -> None:
        if self.adaptor_client_process.is_running:
            self.enqueue_print("'on_end' is called")
        else:
            _logger.info("Application already exited.")

    def on_cleanup(self) -> None:
        self.enqueue_print("`on_cleanup` is called.")
        # do something then call the close action
        time.sleep(0.5)
        self.actions.enqueue_action(Action("close"), front=True)

        # Check if the adaptor client process is initialized before termination
        # on_start maybe interrupted.
        if hasattr(self, "adaptor_client_process"):
            start = time.time()
            while self.adaptor_client_process.is_running:
                if time.time() - start >= 5:
                    _logger.info("Application process did not exit within 5s. Start termination.")
                    self.adaptor_client_process.terminate()
                    break
                else:
                    time.sleep(0.5)

        if hasattr(self, "server"):
            self.server.shutdown()

        if hasattr(self, "server_thread"):
            self.server_thread.join(timeout=5)
            if self.server_thread.is_alive():
                _logger.error("Failed to shutdown the AdaptorExample server")

    def on_stop(self):
        _logger.info("on_stop")
        self.enqueue_print("`on_stop` is called.")
        # do something
        time.sleep(0.5)
        self.enqueue_print("`on_stop` is finished.")

    def on_cancel(self):
        self.enqueue_print("`on_cancel` is called. Execute the `close` action.")
        self.actions.enqueue_action(Action("close"), front=True)
        self.adaptor_client_process.terminate()

    def enqueue_print(self, message: str) -> None:
        self.actions.enqueue_action(Action("print", {"message": message}))
