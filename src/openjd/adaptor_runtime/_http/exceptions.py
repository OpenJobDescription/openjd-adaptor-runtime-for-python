# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.


class UnsupportedPlatformException(Exception):
    pass


class NonvalidSocketPathException(Exception):
    """Raised when a socket path is not valid"""

    pass


class NoSocketPathFoundException(Exception):
    """Raised when a valid socket path could not be found"""

    pass
