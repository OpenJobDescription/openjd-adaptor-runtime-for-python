# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

# Windows Named Pipe Server Configuration
NAMED_PIPE_BUFFER_SIZE = 8192
DEFAULT_NAMED_PIPE_TIMEOUT_MILLISECONDS = 5000
# This number must be >= 2, one instance is for normal operation communication
# and the other one is for immediate shutdown communication
DEFAULT_MAX_NAMED_PIPE_INSTANCES = 4
# The maximum time in seconds to wait for the server pipe to become available before raising an error.
DEFAULT_NAMED_PIPE_SERVER_TIMEOUT_IN_SECONDS = 60
