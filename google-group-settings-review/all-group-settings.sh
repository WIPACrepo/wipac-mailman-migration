#!/bin/bash

gam=/usr/local/bin/gam/gam

for group in $($gam print groups 2> /dev/null | grep @); do
    echo "-------------- $group"
    while ! timeout 5 $gam info group $group; do
        echo Retrying $group > /dev/stderr
        sleep 0.2
    done
    echo
done
