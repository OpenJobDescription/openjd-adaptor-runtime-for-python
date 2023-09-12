#!/bin/bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# The purpose of this script is to print when it receives a SIGTERM then exit.

_handler() {
  echo "Trapped: $1"
  exit
}

trap '_handler TERM' SIGTERM

echo 'Starting print_signals.sh Script'

while true; do
    date +%F_%T
    sleep 1
done
