# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

import logging

_STDOUT_LEVEL = logging.ERROR + 1
logging.addLevelName(_STDOUT_LEVEL, "STDOUT")

_STDERR_LEVEL = logging.ERROR + 2
logging.addLevelName(_STDERR_LEVEL, "STDERR")

_ADAPTOR_OUTPUT_LEVEL = logging.ERROR + 3
logging.addLevelName(_ADAPTOR_OUTPUT_LEVEL, "ADAPTOR_OUTPUT")
