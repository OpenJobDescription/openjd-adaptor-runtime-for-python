# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

import os
from typing import List
from logging import getLogger

from openjd.adaptor_runtime._osname import OSName
from openjd.adaptor_runtime.adaptors import CommandAdaptor, SemanticVersion
from openjd.adaptor_runtime.process import ManagedProcess

logger = getLogger(__name__)


class IntegManagedProcess(ManagedProcess):
    @property
    def integration_data_interface_version(self) -> SemanticVersion:
        return SemanticVersion(major=0, minor=1)

    def get_executable(self) -> str:
        """
        Defines the executable to be used by the process. This method must be implemented, as it's abstract in
        ManagedProcess. In this example, it returns 'powershell.exe' for Windows to run PowerShell scripts,
        and '/bin/echo' for other operating systems.
        """
        if OSName.is_windows():
            # In Windows, we cannot directly run the powershell script.
            # Need to use PowerShell.exe to run the command.
            return "powershell.exe"
        else:
            return os.path.abspath(os.path.join(os.path.sep, "bin", "echo"))

    def get_arguments(self) -> List[str]:
        """
        Specifies the arguments for the executable. Override to provide specific arguments;
        defaults to an empty list if not overridden.
        """
        return self.run_data.get("args", [""])


class CommandAdaptorExample(CommandAdaptor):
    """
    This class demonstrates how an adaptor operates within the adaptor runtime environment by invoking specific
    lifecycle methods (on_*) to communicate with an application process.
    This example uses PowerShell on Windows and the 'echo' command on other OSes as executables.

    Implement the get_managed_process method to define command execution. Optionally, on_prerun and
    on_postrun can be overridden to run code before and after the managed process.
    """

    @property
    def integration_data_interface_version(self) -> SemanticVersion:
        return SemanticVersion(major=0, minor=1)

    def get_managed_process(self, run_data: dict) -> ManagedProcess:
        """
        Must be implemented to specify how commands are run, making use of the ManagedProcess.
        This is crucial for the CommandAdaptor's functionality.
        """
        return IntegManagedProcess(run_data)

    def on_prerun(self):
        """
        `on_prerun` will be run before the ManagedProcess runs. Useful for setup operations or logging.
        """
        # Print only goes to stdout and is not captured in daemon mode.
        print("prerun-print")
        # Logging is captured in daemon mode.
        logger.info(str(self.init_data.get("on_prerun", "")))

    def on_postrun(self):
        """
        `on_postrun` will be run after the ManagedProcess completes. Can be used for cleanup or further processing.
        """
        # Print only goes to stdout and is not captured in daemon mode.
        print("postrun-print")
        # Logging is captured in daemon mode.
        logger.info(str(self.init_data.get("on_postrun", "")))
