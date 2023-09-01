#!/bin/bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

num2=$(($2))
for ((i=1;i<=num2;i++))
do
    echo $1
    >&2 echo $1
    sleep 0.01
done