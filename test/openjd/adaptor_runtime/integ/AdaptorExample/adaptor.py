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
    This class demonstrates how an adaptor operates within the adaptor runtime environment by invoking specific
    lifecycle methods (on_*) to communicate with an application process.
    This example simulates sending 'print' actions to an application client, which merely prints messages. However, in
    practical scenarios, these would trigger specific operations within a third-party application.

    Implementing the on_run method is mandatory for all adaptors. Optionally, on_start, on_end, on_cleanup, and
    on_cancel methods can also be overridden for more granular control over the adaptor's lifecycle.
    """

    def __init__(self, init_data: dict, **_):
        super().__init__(init_data)
        self.actions = ActionsQueue()

    @property
    def integration_data_interface_version(self) -> SemanticVersion:
        return SemanticVersion(major=0, minor=1)

    def on_start(self) -> None:
        """
        `on_start` is used for setting up the environment or dependencies.
        This is the method run during the *start* phase of the Adaptor's lifecycle:
        +-------+
        | start |  -> run -> stop -> cleanup
        +-------+
        """

        # This example initializes a server thread to interact with a client application, showing command exchange and
        # execution.
        _logger.info("on_start")

        # Initialize the server thread to manage actions
        self.server = AdaptorServer(
            # actions_queue will be used for storing the actions. In the client application, it will keep polling the
            # actions from this queue and run actions
            actions_queue=self.actions,
            adaptor=self,
        )
        # The server will keep running until `stop` is called
        self.server_thread = threading.Thread(
            target=self.server.serve_forever,
            name="AdaptorExampleServerThread",
        )
        self.server_thread.start()

        # Initiate the client process to run actions from the queue. The client process will keep polling the
        # actions from the action queue and run them.
        # Note that this Adaptor Runtime's built-in server/client communication support can be leveraged with
        # any application that is able to run Python scripts.
        self.adaptor_client_process = LoggingSubprocess(
            args=[
                sys.executable,
                os.path.join(os.path.dirname(__file__), "adaptor_client.py"),
                self.server.server_path,
            ],
            logger=_logger,
        )

        # Ensure the client process starts successfully
        while not self.adaptor_client_process.is_running:
            if (return_code := self.adaptor_client_process.returncode) is not None:
                raise Exception(
                    f"Application process unexpectedly exited with return code {return_code}"
                )
            else:
                time.sleep(0.1)

        # A print action is pushed to the action queue and adaptor client will fetch it from the queue and run them
        self.enqueue_print("`on_start` is called.")
        # do something
        time.sleep(0.5)
        # An action can accept empty args.
        self.actions.enqueue_action(Action("print", None))
        # Fetch and print the init data passed by the `--init-data`
        self.enqueue_print(f"self.init_data: {self.init_data}")
        self.enqueue_print("`on_start` is finished.")

    def on_run(self, run_data: dict) -> None:
        """
        `on_run` is an abstract method and must be overridden and defined in each adaptor.
        The `run_data` argument is provided by the `--run-data` command-line argument.

        This is the method run during the *run* phase of the Adaptor's lifecycle:
                 +-----+
        start -> | run | -> stop -> cleanup
                 +-----+
        """
        _logger.info(f"on_run: {run_data}")
        self.enqueue_print(f"`on_run` is called with run_data: {run_data}")
        # do something
        time.sleep(0.5)
        self.enqueue_print("`on_run` is finished.")

    def on_stop(self):
        """
        `on_stop` method should be used for ensuring that the adaptor and associated tasks are properly terminated.

        This is the method run during the *stop* phase of the Adaptor's lifecycle:
                        +------+
        start -> run -> | stop | -> cleanup
                        +------+
        """
        _logger.info("on_stop")
        self.enqueue_print("`on_stop` is called.")
        # do something
        time.sleep(0.5)
        self.enqueue_print("`on_stop` is finished.")

    def on_cleanup(self) -> None:
        """
        `on_cleanup` is method used for final cleanup tasks.

        This is the method run during the *cleanup* phase of the Adaptor's lifecycle:
                                +---------+
        start -> run -> stop -> | cleanup |
                                +---------+
        """
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

    def on_cancel(self):
        """
        Handles the cancellation or termination of a running task, typically triggered by external signals.
        It's a part of the graceful shutdown process, ensuring tasks are stopped in an orderly manner.

        Note: graceful shutdown process will be triggered when the application got the SIGTERM in the Linux or
        SIGBREAK in Windows.
        """
        self.enqueue_print("`on_cancel` is called. Run the `close` action.")
        self.actions.enqueue_action(Action("close"), front=True)
        self.adaptor_client_process.terminate()

    def enqueue_print(self, message: str) -> None:
        """
        A utility method for queuing print actions. It demonstrates how actions are structured and added to the queue
        for execution by the client process.
        """
        self.actions.enqueue_action(Action("print", {"message": message}))
