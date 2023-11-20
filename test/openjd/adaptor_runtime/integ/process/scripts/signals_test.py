# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

import signal
import sys
import time
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def flush_logging():
    for handler in logger.handlers:
        handler.flush()


def func_trap(signum, frame):
    logger.info(f"Trapped: {signal.Signals(signum).name}")
    flush_logging()
    if exit_after_signal:
        exit(0)


def set_signal_handlers():
    signals = [signal.SIGTERM, signal.SIGINT]
    for sig in signals:
        signal.signal(sig, func_trap)


if __name__ == "__main__":
    exit_after_signal = sys.argv[1] == "True"
    logger.info("Starting signals_test.py Script")
    flush_logging()
    set_signal_handlers()

    while True:
        logger.info(datetime.now().strftime("%Y-%m-%d_%H:%M:%S"))
        time.sleep(1)
