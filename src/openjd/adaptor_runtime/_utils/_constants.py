# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

import re

_OPENJD_LOG_PATTERN = r"^openjd_\S+: "
_OPENJD_LOG_REGEX = re.compile(_OPENJD_LOG_PATTERN)

_OPENJD_FAIL_STDOUT_PREFIX = "openjd_fail: "
_OPENJD_PROGRESS_STDOUT_PREFIX = "openjd_progress: "
_OPENJD_STATUS_STDOUT_PREFIX = "openjd_status: "
_OPENJD_ENV_STDOUT_PREFIX = "openjd_env: "

_OPENJD_ADAPTOR_SOCKET_ENV = "OPENJD_ADAPTOR_SOCKET"
