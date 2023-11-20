# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

import sys
import time


def repeat_message(message, count):
    for _ in range(count):
        print(message)
        print(message, file=sys.stderr)
        time.sleep(0.01)


if __name__ == "__main__":
    message = sys.argv[1]
    num_times = int(sys.argv[2])
    repeat_message(message, num_times)
