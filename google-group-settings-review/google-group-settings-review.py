#!/usr/bin/env python
import argparse
import sys
from pprint import pprint
from subprocess import check_output
from collections import OrderedDict
from email.message import EmailMessage
import smtplib

def main():
    parser = argparse.ArgumentParser(
            description="",
            formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('group_email')
    args = parser.parse_args()

    info = check_output(f"/usr/local/bin/gam/gam info group {args.group_email}".split(), encoding="utf8")
    info_lines = [l.strip() for l in info.split("\n") if l.strip()]
    caretakers = [line.split()[1] for line in info_lines
               if (line.startswith("owner: ") or line.startswith("manager: "))
                  and ('gadm' not in line)]
    group_email = [l.split()[-1] for l in info_lines if l.startswith("email: ")][0]
    group_local_part = group_email.split('@')[0]

    if not caretakers:
        print(f"group {group_email} has no non-gadm caretakers")
        print()
        return

    basic_attrs = ('name', 'description', 'email')

    adv_attrs = {
        # posting policy
        'whoCanPostMessage': {
            None: "Who can post",
            "ANYONE_CAN_POST": "anybody can post (!!!)",
            "ALL_MANAGERS_CAN_POST": "managers only",
            "ALL_MEMBERS_CAN_POST": "members only",
            "ALL_IN_DOMAIN_CAN_POST": "everybody from IceCube",
            "NONE_CAN_POST": "nobody",
            "ALL_OWNERS_CAN_POST": "owners only",
        },
        "whoCanModerateContent": {
            None: "Who can approve/deny",
            "ALL_MEMBERS": "members",
            "OWNERS_AND_MANAGERS": "managers",
            "OWNERS_ONLY": "owners",
            "NONE": "nobody",
        },
        "messageModerationLevel": {
            None: "Message approval",
            "MODERATE_ALL_MESSAGES": "all messages require approval",
            "MODERATE_NON_MEMBERS": "messages from non-members require approval",
            "MODERATE_NONE": "accept all non-spam messages",
        },
        "spamModerationLevel": {
            None: "Spam handling",
            "ALLOW": "accept suspected spam (!!!)",
            "MODERATE": "require approval for suspected spam",
            "REJECT": "reject suspected spam",
        },
        "sendMessageDenyNotification": {
            None: "Upon rejection",
            "true": "notify senders",
            "false": "reject silently",
        },
        # privacy
        "whoCanViewGroup": {
            None: "Who can view archive",
            "ANYONE_CAN_VIEW": "anybody can view group archive (!!!)",
            "ALL_IN_DOMAIN_CAN_VIEW": "everybody from IceCube",
            "ALL_MEMBERS_CAN_VIEW": "members",
            "ALL_MANAGERS_CAN_VIEW": "managers",
            "ALL_OWNERS_CAN_VIEW": "owners",
        },
        "whoCanViewMembership": {
            None: "Who can view membership",
            "ALL_IN_DOMAIN_CAN_VIEW": "everybody from IceCube",
            "ALL_MEMBERS_CAN_VIEW": "members",
            "ALL_MANAGERS_CAN_VIEW": "managers",
            "ALL_OWNERS_CAN_VIEW": "owners",
        },
        "whoCanDiscoverGroup": {
            None: "Who can find group",
            "ANYONE_CAN_DISCOVER": "anybody (!!!)",
            "ALL_IN_DOMAIN_CAN_DISCOVER": "everybody from IceCube",
            "ALL_MEMBERS_CAN_DISCOVER": "only members",
        },
        "isArchived": {
            None: "Keep archive",
            "true": "yes",
            "false": "no",
        },
        # membership
        "whoCanModerateMembers": {
            None: "Who can add/remove members",
            "ALL_MEMBERS": "members",
            "OWNERS_AND_MANAGERS": "owners and managers",
            "OWNERS_ONLY": "owners",
            "NONE": "nobody (membership managed out-of-band)",
        },
        "whoCanJoin": {
            None: "Who can join the group",
            "ANYONE_CAN_JOIN": "anybody on the internet can join",
            "ALL_IN_DOMAIN_CAN_JOIN": "everybody from IceCube can join",
            "INVITED_CAN_JOIN": "only invited users can join",
            "CAN_REQUEST_TO_JOIN": "non-members can request to join",
        },
        "whoCanLeaveGroup": {
            None: "Who can leave the group",
            "ALL_MANAGERS_CAN_LEAVE": "only managers",
            "ALL_MEMBERS_CAN_LEAVE": "any member",
            "NONE_CAN_LEAVE": "nobody (membership managed out-of-band)",
            "ALL_OWNERS_CAN_LEAVE":"owners",
        },
    }

    patches = (
        ("isArchived", "isArchived (keep message archives)"),
        ("whoCanModerateContent", "whoCanModerateContent (messages)"),
        ("whoCanModerateMembers", "xxxx (messages)"),
        ('messageModerationLevel', "messageModerationLevel (whom to moderate)"),
        ('whoCanViewGroup (access to archives)', "anyone (bad!), domain (IceCube), members, managers"),
    )

    message = f"""
Hello

As an owner or manager of {args.group_email},
please review its settings summary at the end of this email. The reason for
this request is that certain configuration of our old mailing list system
could not be replicated exactly in Google Groups. One important case is
pattern-based whitelisting that Google Groups doesn't support. We had to allow
anybody to post to groups that used this feature for backward compatibility.

If after reviewing the configuration summary at the end of this email you
decide to change group settings, you can do it here:
https://groups.google.com/a/icecube.wisc.edu/g/{group_local_part}/settings
(you may need to switch to your IceCube account).

Our detailed Google Group administration guide, which includes explanations
of all group settings is here: 
https://wiki.icecube.wisc.edu/index.php/Google_Groups_Admin_Guide

Please contact help@icecube.wisc.edu with questions.

--------------------------------------

"""
    for attr in basic_attrs:
        message += [line.split(maxsplit=1)[-1]  for line in info_lines if line.startswith(f"{attr}:")][0] + "\n"

    def show_attrs(attrs):
        text = ""
        for attr in attrs:
            val = [line.strip().split() for line in info_lines
                   if line.startswith(f"{attr}:")][0][-1]
            text += f"{adv_attrs[attr][None]:{'.'}{'<'}{27}} {adv_attrs[attr][val]}\n"
        return text

    message += "\nMESSAGE POSTING POLICY\n"
    message += show_attrs(("whoCanPostMessage", "messageModerationLevel", "spamModerationLevel",
                           "whoCanModerateContent", "sendMessageDenyNotification"))

    message += "\nGROUP PRIVACY SETTINGS\n"
    message += show_attrs(("isArchived", "whoCanViewGroup", "whoCanViewMembership", "whoCanDiscoverGroup"))

    message += "\nMEMBER MANAGEMENT\n"
    message += show_attrs(("whoCanModerateMembers", "whoCanJoin", "whoCanLeaveGroup"))

#    message += "\nMEMBER LIST\n"
#    message += "\n".join(members)

    for old, new in patches:
        message = message.replace(old, new)

    message += f"\n\nOWNERS AND MANAGERS:\n{'\n'.join(caretakers)}"
    print(message)

    s=smtplib.SMTP('i3mail.icecube.wisc.edu', 25)
    for addr in caretakers:
        print(addr)
        m = EmailMessage()
        m['To'] = addr
        m['Subject'] = f"Please review settings of {group_email}"
        m['From'] = "vladimir.brik@icecube.wisc.edu"
        m.set_content(f'<font face="monospace">{message.replace("\n", "<br>")}</font>', subtype='html')
        try:
            s.send_message(m)
        except smtplib.SMTPRecipientsRefused:
            s = smtplib.SMTP('i3mail.icecube.wisc.edu', 25)


if __name__ == '__main__':
    sys.exit(main())

