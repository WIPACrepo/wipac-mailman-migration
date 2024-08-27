#!/bin/bash

function press_any_key() {
    echo -e "\[\e[34m\]PRESS ANY KEY\[\e[00m\]"
    read -n 1 -s
}

set -ex
ssh mailman "/usr/lib/mailman/bin/add_members --welcome-msg=n -r - $1 <<< vbrik@icecube.wisc.edu"
ssh mailman ./pickle-mailman-list.py --list $1@icecube.wisc.edu
scp mailman:$1@icecube.wisc.edu.pkl gitignore/
scp i3mail:/mnt/i3mail/mailman/archives/private/$1.mbox/$1.mbox gitignore/

ls -lh gitignore/$1*

press_any_key
./mailman-to-google-group-settings-import.py \
    --browser-google-account-index 3 \
    --sa-creds gitignore/mailing-list-migration-381920-45ae46bb0e0e.json \
    --add-owner vbrik_gadm@icecube.wisc.edu \
    --sa-delegate vbrik_gadm@icecube.wisc.edu \
    --mailman-pickle gitignore/$1@icecube.wisc.edu.pkl

press_any_key
./mailman-to-google-group-members-import.py \
    --ignore listmgr@icecube.wisc.edu \
    --browser-google-account-index 3 \
    --sa-creds gitignore/mailing-list-migration-381920-45ae46bb0e0e.json \
    --sa-delegate vbrik_gadm@icecube.wisc.edu \
    --mailman-pickle gitignore/$1@icecube.wisc.edu.pkl


ssh i3mail "cp /etc/mailman/aliases /etc/mailman/aliases.bak.$1.$(date +%s)"
ssh i3mail "cp /etc/postfix/transport /etc/postfix/transport.bak.$1.$(date +%s)"
ssh i3mail "cp /etc/postfix/local_recipients /etc/postfix/local_recipients.bak.$1.$(date +%s)"

press_any_key
ssh i3mail "sed '/^$1[:-].*|.usr.lib.mailman.mail.mailman [a-z][a-z]* $1\"$/s/^/#/' \
    /etc/mailman/aliases > /etc/mailman/aliases.preview"
ssh i3mail "diff -u /etc/mailman/aliases /etc/mailman/aliases.preview; true"
press_any_key
ssh i3mail "sed -i '/^$1[:-].*|.usr.lib.mailman.mail.mailman [a-z][a-z]* $1\"$/s/^/#/' \
    /etc/mailman/aliases"
ssh i3mail "cd /etc/mailman/; postalias aliases"

press_any_key
ssh i3mail "echo $1@icecube.wisc.edu relay:aspmx.l.google.com >> /etc/postfix/transport"
ssh i3mail "echo $1+unsubscribe@icecube.wisc.edu relay:aspmx.l.google.com >> /etc/postfix/transport"
ssh i3mail "echo $1 OK >> /etc/postfix/local_recipients"
ssh i3mail "echo $1+unsubscribe OK >> /etc/postfix/local_recipients"
ssh i3mail "tail /etc/postfix/transport"
ssh i3mail "tail /etc/postfix/local_recipients"
press_any_key
ssh i3mail "cd /etc/postfix; postmap hash:local_recipients"
ssh i3mail "cd /etc/postfix; postmap hash:transport"

press_any_key
./mailman-to-google-group-standard-announcements.py \
    --list-name $1 \
    --message-name SINGLE_VBRIK \
    --from-field "Vladimir Brik <vbrik@icecube.wisc.edu>"

press_any_key
mkdir -p gitignore/work/$1
./mailman-to-google-group-message-import.py \
    --sa-creds gitignore/mailing-list-tools-10746a87da2c.json \
    --sa-delegator vbrik_gadm@icecube.wisc.edu \
    --src-mbox gitignore/$1.mbox \
    --dst-group $1@icecube.wisc.edu \
    --work-dir gitignore/work/$1

