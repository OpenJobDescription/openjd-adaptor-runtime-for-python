# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

import sys

from openjd.adaptor_runtime import EntryPoint

from .adaptor import SampleAdaptor


def main():
    package_name = vars(sys.modules[__name__])["__package__"]
    if not package_name:
        raise RuntimeError(f"Must be run as a module. Do not run {__file__} directly")

    EntryPoint(SampleAdaptor).start()


if __name__ == "__main__":
    main()
