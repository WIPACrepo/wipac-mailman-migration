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

    info = check_output("/usr/local/bin/gam/gam info group icb@icecube.wisc.edu".split(), encoding="utf8")
    info_lines = [l.strip() for l in info.split("\n") if l.strip()]
    members = [line.replace("manager", "MANAGER").replace("member: ", "").replace(" (user)", "") for line in info_lines
               if line.endswith(" (user)") or line.endswith(" (group)")]

    basic_attrs = ('name', 'description', 'email')

    adv_attrs = {
        # posting policy
        'whoCanPostMessage': {
            None: "Who can post",
            "ANYONE_CAN_POST": "anybody (all messages are accepted)",
            "ALL_MANAGERS_CAN_POST": "group managers",
            "ALL_MEMBERS_CAN_POST": "group members",
            "ALL_IN_DOMAIN_CAN_POST": "everybody from IceCube",
        },
        "messageModerationLevel": {
            None: "Message moderation",
            "MODERATE_ALL_MESSAGES": "all messages are moderated",
            "MODERATE_NON_MEMBERS": "messages from non-members are moderated",
            "MODERATE_NONE": "accept all messages without moderation",
        },
        "spamModerationLevel": {
            None: "Spam policy",
            "ALLOW": "accept suspected spam",
            "MODERATE": "moderate suspected spam",
            "REJECT": "reject suspected spam",
        },
        "whoCanModerateContent": {
            None: "Who can accept/reject messages",
            "ALL_MEMBERS": "all group members",
            "OWNERS_AND_MANAGERS": "group managers",
            "OWNERS_ONLY": "group owners",
            "NONE": "nobody",
        },
        "sendMessageDenyNotification": {
            None: "When non-spam is rejected",
            "true": "notify senders",
            "false": "reject silently",
        },
        # privacy
        "whoCanViewGroup": {
            None: "Who can view message archive",
            "ANYONE_CAN_VIEW": "anybody (publicly available on the Internet)",
            "ALL_IN_DOMAIN_CAN_VIEW": "anybody from IceCube",
            "ALL_MEMBERS_CAN_VIEW": "only group member",
            "ALL_MANAGERS_CAN_VIEW": "only managers",
        },
        "whoCanViewMembership": {
            None: "Who can view group membership",
            "ALL_IN_DOMAIN_CAN_VIEW": "everybody from IceCube",
            "ALL_MEMBERS_CAN_VIEW": "only group members",
            "ALL_MANAGERS_CAN_VIEW": "only group managers",

        },
        "whoCanDiscoverGroup": {
            None: "Who can find this group",
            "ANYONE_CAN_DISCOVER": "anybody on the Internet",
            "ALL_IN_DOMAIN_CAN_DISCOVER": "everybody from IceCube",
            "ALL_MEMBERS_CAN_DISCOVER": "only members",
        },
        "isArchived": {
            None: "Maintain archive of group messages",
            "true": "yes",
            "false": "no",
        },
        # membership
        "whoCanModerateMembers": {
            None: "Who can add/remove members",
            "ALL_MEMBERS": "group members",
            "OWNERS_AND_MANAGERS": "group owners and managers",
            "OWNERS_ONLY": "group owners",
            "NONE": "nobody (managed out of band)",
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
            "NONE_CAN_LEAVE": "nobody",
        },
    }

    patches = (
        ("isArchived", "isArchived (keep message archives)"),
        ("whoCanModerateContent", "whoCanModerateContent (messages)"),
        ("whoCanModerateMembers", "xxxx (messages)"),
        ('messageModerationLevel', "messageModerationLevel (whom to moderate)"),
        ('whoCanViewGroup (access to archives)', "anyone (bad!), domain (IceCube), members, managers"),
    )

    message = ""
    for attr in basic_attrs:
        message += [line for line in info_lines if line.startswith(f"{attr}:")][0] + "\n"

    def show_attrs(attrs):
        text = ""
        for attr in attrs:
            val = [line.strip().split() for line in info_lines
                   if line.startswith(f"{attr}:")][0][-1]
            text += f"{adv_attrs[attr][None]}: {adv_attrs[attr][val]}\n"
        return text

    message += "\nPOSTING POLICY\n"
    message += show_attrs(("whoCanPostMessage", "messageModerationLevel", "spamModerationLevel",
                           "whoCanModerateContent", "sendMessageDenyNotification"))

    message += "\nPRIVACY SETTINGS\n"
    message += show_attrs(("isArchived", "whoCanViewGroup", "whoCanViewMembership", "whoCanDiscoverGroup"))

    message += "\nMEMBER MANAGEMENT\n"
    message += show_attrs(("whoCanModerateMembers", "whoCanJoin", "whoCanLeaveGroup"))

    message += "\nMEMBER LIST\n"
    #message += "\n".join(members)

    for old, new in patches:
        message = message.replace(old, new)

    print(message)


if __name__ == '__main__':
    sys.exit(main())

