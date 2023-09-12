#!/bin/bash
# This script's purpose is to ignore SIGTERM so we can test whether or not the process is exited properly.
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

trap_with_arg() {
    func="$1" ; shift
    for sig ; do
        trap "$func $sig" "$sig"
    done
}

func_trap() {
    echo "Trapped: $1"
}

trap_with_arg func_trap INT TERM EXIT

echo 'Starting no_sigterm.sh Script'

while true; do
    date +%F_%T
    sleep 1
done
