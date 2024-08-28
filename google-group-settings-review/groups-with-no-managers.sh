#!/bin/bash

gam=/usr/local/bin/gam/gam
tmp_file=/tmp/sdaopasfdkop

for group in $($gam print groups 2> /dev/null | grep @); do
    while ! timeout 5 $gam print group-members group $group > $tmp_file 2> $tmp_file.stderr; do
        echo Retrying $group > /dev/stderr
        cat $tmp_file.stderr > /dev/stderr
        cat $tmp_file > /dev/stderr
        sleep 0.2
    done
    if grep -q email $tmp_file; then
        grep -v _gadm $tmp_file | grep -v listmgr | grep -q 'MANAGER\|OWNER' || echo $group
    fi
done
