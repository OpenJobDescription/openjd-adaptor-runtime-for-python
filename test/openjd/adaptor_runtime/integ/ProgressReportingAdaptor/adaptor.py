# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from openjd.adaptor_runtime.adaptors import Adaptor, SemanticVersion


class ProgressReportingAdaptor(Adaptor):
    """
    A minimal adaptor that calls update_status to report progress during on_run.
    Used to test that progress messages propagate from the background adaptor
    to the frontend process's stdout.
    """

    @property
    def integration_data_interface_version(self) -> SemanticVersion:
        return SemanticVersion(major=0, minor=1)

    def on_run(self, run_data: dict) -> None:
        progress = run_data.get("progress", 50.0)
        self.update_status(progress=progress)
