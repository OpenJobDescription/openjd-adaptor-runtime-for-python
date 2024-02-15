# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from __future__ import annotations

import os
import shutil
from pathlib import Path

from openjd.adaptor_runtime.adaptors import Adaptor, SemanticVersion


class TestRun:
    """
    Tests for the Adaptor._run method
    """

    _OPENJD_PROGRESS_STDOUT_PREFIX: str = "openjd_progress: "
    _OPENJD_STATUS_STDOUT_PREFIX: str = "openjd_status: "

    def test_run(self, capsys) -> None:
        first_progress = 0.0
        first_status_message = "Starting the printing of run_data"
        second_progress = 100.0
        second_status_message = "Finished printing"

        class PrintAdaptor(Adaptor):
            """
            Test implementation of an Adaptor.
            """

            def on_run(self, run_data: dict):
                # This run funciton will simply print the run_data.
                self.update_status(progress=first_progress, status_message=first_status_message)
                print("run_data:")
                for key, value in run_data.items():
                    print(f"\t{key} = {value}")
                self.update_status(progress=second_progress, status_message=second_status_message)

            @property
            def integration_data_interface_version(self) -> SemanticVersion:
                return SemanticVersion(major=0, minor=1)

        # GIVEN
        init_data: dict = {}
        run_data: dict = {"key1": "value1", "key2": "value2", "key3": "value3"}
        adaptor = PrintAdaptor(init_data)

        # WHEN
        adaptor._run(run_data)
        result = capsys.readouterr().out.strip()

        # THEN
        assert f"{self._OPENJD_PROGRESS_STDOUT_PREFIX}{first_progress}" in result
        assert f"{self._OPENJD_STATUS_STDOUT_PREFIX}{first_status_message}" in result
        assert f"{self._OPENJD_PROGRESS_STDOUT_PREFIX}{second_progress}" in result
        assert f"{self._OPENJD_STATUS_STDOUT_PREFIX}{second_status_message}" in result
        assert "run_data:\n\tkey1 = value1\n\tkey2 = value2\n\tkey3 = value3" in result

    def test_start_end_cleanup(self, tmpdir, capsys) -> None:
        """
        We are going to test the start and end methods
        """

        class FileAdaptor(Adaptor):
            def on_start(self):
                # Open a temp file
                self.f = tmpdir.mkdir("test").join("hello.txt")

            def on_run(self, run_data: dict):
                # Write hello world to temp file
                self.f.write("Hello World from FileAdaptor!")

            def on_stop(self):
                # Read from temp file
                print(self.f.read())

            def on_cleanup(self):
                # Delete temp file
                path = Path(str(self.f))
                parent_dir = path.parent.absolute()
                os.remove(str(self.f))
                shutil.rmtree(parent_dir)

            @property
            def integration_data_interface_version(self) -> SemanticVersion:
                return SemanticVersion(major=0, minor=1)

        init_dict: dict = {}
        fa = FileAdaptor(init_dict)

        # Creates the path for the temp file.
        fa._start()

        # Writes to the temp file
        fa._run({})

        # The file exists after writing.
        assert os.path.exists(str(fa.f))

        # Printing the contents of the file.
        fa._stop()
        assert capsys.readouterr().out.strip() == "Hello World from FileAdaptor!"

        # Deleting the file created before.
        fa._cleanup()
        assert not os.path.exists(str(fa.f))
