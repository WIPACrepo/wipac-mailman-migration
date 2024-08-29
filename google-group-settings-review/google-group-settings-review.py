#!/usr/bin/env python
import argparse
import sys
from pprint import pprint
from subprocess import check_output
from collections import OrderedDict


def main():
    parser = argparse.ArgumentParser(
            description="",
            formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('args', nargs='*')
    args = parser.parse_args()
    pprint(args)

    info = check_output("/usr/local/bin/gam/gam info group icb@icecube.wisc.edu".split(), encoding="utf8")
    info_lines = [l.strip() for l in info.split("\n") if l.strip()]
    members = [line.replace("manager", "MANAGER").replace("member: ", "").replace(" (user)", "") for line in info_lines
               if line.endswith(" (user)") or line.endswith(" (group)")]

    basic_attrs = ('name', 'description', 'email')

    posting_policy = (
        ('whoCanPostMessage', "managers, members, owners, domain (IceCube), anyone"),
        ('messageModerationLevel', "everybody, non-members, new-members, none/nobody"),
        ('spamModerationLevel', "allow, moderate, reject"),
        ('whoCanModerateContent', "members, managers"),
    )
    sendMessageDenyNotification

    privacy = (
        ('whoCanViewGroup', "anyone (bad!), domain (IceCube), members, managers"),
        ('whoCanViewMembership', "domain (IceCube), members, managers"),
        ('whoCanDiscoverGroup', "anyone, domain (IceCube), members"),
        ('isArchived', "true, false"),
    )

    member_management = (
        ('whoCanAdd', "members, managers"),
        ('whoCanJoin', "domain (IceCube), domain-can-request, anybody-by-invite"),
        ('whoCanLeaveGroup', "members, nobody"),
    )

    patches = (
        ("isArchived", "isArchived (keep message archives)"),
        ("whoCanModerateContent", "whoCanModerateContent (messages)"),
        ('messageModerationLevel', "messageModerationLevel (whom to moderate)"),
        ('whoCanViewGroup (access to archives)', "anyone (bad!), domain (IceCube), members, managers"),
    )

    message = ""
    for attr in basic_attrs:
        message += [line for line in info_lines if line.startswith(f"{attr}:")][0] + "\n"

    def show_attrs(attrs):
        text = ""
        for attr, choices in attrs:
            text += [line for line in info_lines if line.startswith(f"{attr}:")][0]
            text += f"  {'{'}{choices}{'}'}" + "\n"
        return text

    message += "\nPOSTING POLICY\n"
    message += show_attrs(posting_policy)

    message += "\nPRIVACY SETTINGS\n"
    message += show_attrs(privacy)

    message += "\nMEMBER MANAGEMENT\n"
    message += show_attrs(member_management)

#    message += "\nMEMBER LIST\n"
#    message += "\n".join(members)

    for old, new in patches:
        message = message.replace(old, new)

    print(message)


if __name__ == '__main__':
    sys.exit(main())

