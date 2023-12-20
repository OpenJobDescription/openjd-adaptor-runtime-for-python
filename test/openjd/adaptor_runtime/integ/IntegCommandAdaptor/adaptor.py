# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

import os
from typing import List
from logging import getLogger

from openjd.adaptor_runtime._osname import OSName
from openjd.adaptor_runtime.adaptors import CommandAdaptor
from openjd.adaptor_runtime.process import ManagedProcess

logger = getLogger(__name__)


class IntegManagedProcess(ManagedProcess):
    def __init__(self, run_data: dict) -> None:
        super().__init__(run_data)

    def get_executable(self) -> str:
        if OSName.is_windows():
            # In Windows, we cannot directly execute the powershell script.
            # Need to use PowerShell.exe to run the command.
            return "powershell.exe"
        else:
            return os.path.abspath(os.path.join(os.path.sep, "bin", "echo"))

    def get_arguments(self) -> List[str]:
        return self.run_data.get("args", "")


class IntegCommandAdaptor(CommandAdaptor):
    def __init__(self, init_data: dict, path_mapping_data: dict):
        super().__init__(init_data, path_mapping_data=path_mapping_data)

    def get_managed_process(self, run_data: dict) -> ManagedProcess:
        return IntegManagedProcess(run_data)

    def on_prerun(self):
        # Print only goes to stdout and is not captured in daemon mode.
        print("prerun-print")
        # Logging is captured in daemon mode.
        logger.info(self.init_data.get("on_prerun", ""))

    def on_postrun(self):
        # Print only goes to stdout and is not captured in daemon mode.
        print("postrun-print")
        # Logging is captured in daemon mode.
        logger.info(self.init_data.get("on_postrun", ""))
