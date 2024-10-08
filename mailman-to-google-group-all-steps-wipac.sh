#!/bin/bash

function press_any_key() {
    echo -e "\[\e[34m\]PRESS ANY KEY\[\e[00m\]"
    read -n 1 -s
}

set -ex
ssh lists.wipac.wisc.edu "/usr/lib/mailman/bin/add_members --welcome-msg=n -r - $1 <<< vbrik@icecube.wisc.edu"
ssh lists.wipac.wisc.edu ./pickle-mailman-list.py --list $1@wipac.wisc.edu
scp lists.wipac.wisc.edu:$1@wipac.wisc.edu.pkl gitignore/
scp lists.wipac.wisc.edu:/var/lib/mailman/archives/private/$1.mbox/$1.mbox gitignore/archives/ || true

ls -lh gitignore/$1*
ls -lh gitignore/archives/$1* || true

press_any_key
./mailman-to-google-group-settings-import.py \
    --browser-google-account-index 3 \
    --sa-creds gitignore/mailing-list-migration-381920-45ae46bb0e0e.json \
    --add-owner vbrik_gadm@icecube.wisc.edu \
    --sa-delegate vbrik_gadm@icecube.wisc.edu \
    --mailman-pickle gitignore/$1@wipac.wisc.edu.pkl

press_any_key
./mailman-to-google-group-members-import.py \
    --ignore listmgr@icecube.wisc.edu listmgr@wipac.wisc.edu \
    --browser-google-account-index 3 \
    --sa-creds gitignore/mailing-list-migration-381920-45ae46bb0e0e.json \
    --sa-delegate vbrik_gadm@icecube.wisc.edu \
    --mailman-pickle gitignore/$1@wipac.wisc.edu.pkl


ssh i3mail "cp /etc/mailman/aliases /etc/mailman/aliases.bak.$1.$(date +%s)"
ssh i3mail "cp /etc/postfix/transport /etc/postfix/transport.bak.$1.$(date +%s)"
ssh i3mail "cp /etc/postfix/local_recipients /etc/postfix/local_recipients.bak.$1.$(date +%s)"

press_any_key
ssh i3mail "sed '/^$1:.*$1.lists.wipac.wisc.edu$/s/^/#/' \
    /etc/mailman/aliases > /etc/mailman/aliases.preview"
ssh i3mail "diff -u /etc/mailman/aliases /etc/mailman/aliases.preview; true"
press_any_key
ssh i3mail "sed -i '/^$1:.*$1.lists.wipac.wisc.edu$/s/^/#/' \
    /etc/mailman/aliases"
ssh i3mail "cd /etc/mailman/; postalias aliases"

press_any_key
ssh i3mail "echo $1@wipac.wisc.edu relay:aspmx.l.google.com >> /etc/postfix/transport"
ssh i3mail "echo $1+unsubscribe@wipac.wisc.edu relay:aspmx.l.google.com >> /etc/postfix/transport"
ssh i3mail "echo $1 OK >> /etc/postfix/local_recipients"
ssh i3mail "echo $1+unsubscribe OK >> /etc/postfix/local_recipients"
ssh i3mail "tail /etc/postfix/transport"
ssh i3mail "tail /etc/postfix/local_recipients"
press_any_key
ssh i3mail "cd /etc/postfix; postmap hash:local_recipients"
ssh i3mail "cd /etc/postfix; postmap hash:transport"
ssh i3mail "postfix reload"

press_any_key
./mailman-to-google-group-standard-announcements.py \
    --list-addr $1@wipac.wisc.edu \
    --message-name SINGLE_VBRIK \
    --from-field "Vladimir Brik <vbrik@icecube.wisc.edu>"

press_any_key
scp lists.wipac.wisc.edu:/var/lib/mailman/archives/private/$1.mbox/$1.mbox gitignore/archives \
    && mkdir -p gitignore/archives/work/$1 \
    && ./mailman-to-google-group-message-import.py \
        --sa-creds gitignore/mailing-list-tools-10746a87da2c.json \
        --sa-delegator vbrik_gadm@icecube.wisc.edu \
        --src-mbox gitignore/archives/$1.mbox \
        --dst-group $1@wipac.wisc.edu \
        --work-dir gitignore/archives/work/$1

