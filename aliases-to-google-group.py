#!/usr/bin/env python
import argparse
import sys
import pickle
import colorlog
import logging
from pprint import pformat

# noinspection PyPackageRequirements
from google.oauth2 import service_account

# noinspection PyPackageRequirements
from googleapiclient import discovery

# noinspection PyPackageRequirements
from googleapiclient.errors import HttpError

from utils import get_google_group_config_from_mailman_config


handler = colorlog.StreamHandler()
handler.setFormatter(colorlog.ColoredFormatter("%(log_color)s%(levelname)s:%(message)s"))
logger = colorlog.getLogger("settings-import")
logger.propagate = False
logger.addHandler(handler)
logging.basicConfig(level=logging.INFO)

def set_controlled_mailing_list_setting(ggcfg, unsubscribe_instructions):
    def _override(cfg, key, value):
        if key not in cfg:
            logger.warning(f"Setting {key} to be '{value}'")
        elif cfg[key] != value:
            logger.warning(f"Overriding {key} from '{cfg[key]}' to '{value}'")
        cfg[key] = value

    _override(ggcfg, "whoCanJoin", "INVITED_CAN_JOIN")
    _override(ggcfg, "whoCanViewGroup", "ALL_MEMBERS_CAN_VIEW")
    _override(ggcfg, "whoCanLeaveGroup", "NONE_CAN_LEAVE")
    _override(ggcfg, "includeCustomFooter", "true")
    _override(
        ggcfg,
        "customFooterText",
        (
            "Message archives are at https://groups.google.com (log in with your IceCube account)"
            + (
                "\nTo unsubscribe, use the group membership management interface on https://user-management.icecube.aq"
                if unsubscribe_instructions
                else ""
            )
        ),
    )
    _override(ggcfg, "whoCanModerateMembers", "NONE")

    return ggcfg


def summarize_settings(ggcfg):
    logger.info(f"{ggcfg['name'] = }")
    logger.info(f"{ggcfg['description'] =}")
    logger.info(f"whoCanViewGroup = {ggcfg['whoCanViewGroup']}")
    logger.info(f"whoCanViewMembership = {ggcfg['whoCanViewMembership']}")
    logger.info(f"allowExternalMembers = {ggcfg['allowExternalMembers']}")
    logger.info(f"whoCanPostMessage = {ggcfg['whoCanPostMessage']}")
    logger.info(f"messageModerationLevel = {ggcfg['messageModerationLevel']}")
    logger.info(f"whoCanDiscoverGroup = {ggcfg['whoCanDiscoverGroup']}")
    logger.info(f"whoCanLeaveGroup = {ggcfg['whoCanLeaveGroup']}")
    if ggcfg["whoCanPostMessage"] == "ANYONE_CAN_POST" and ggcfg["messageModerationLevel"] == "MODERATE_NONE":
        logger.warning("!!!  LIST ACCEPTS MESSAGES FROM ANYBODY WITHOUT MODERATION")

def add_alias(aliases, group_email, alias_email):
    try:
        aliases.insert(groupKey=group_email, body={
            "alias": alias_email,
        }).execute()
    except HttpError as e:
        if e.status_code == 409:  # entity already exists
            logger.warning("Group already exists")
        else:
            raise

def create_group(groups_admin, email, name, descr):
    try:
        groups_admin.insert(
            body={"email": email,
                "name": name,
                "description": descr} ).execute()
    except HttpError as e:
        if e.status_code == 409:  # entity already exists
            logger.warning("Group already exists")
        else:
            raise


def insert_member(members, group_email, email, role):
    logger.info(f"Adding {email} as {role}")
    body = {
        "email": email,
        "role": role,
    }
    if role == "OWNER":
        body["delivery_settings"] = "NONE"

    try:
        members.insert(
            groupKey=group_email,
            body=body,
        ).execute()
    except HttpError as e:
        if e.status_code == 409:  # entity already exists
            logger.error(f"User {email} already part of the group")


def main():
    parser = argparse.ArgumentParser(
        description="",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument( "alias_file", metavar="PATH", help="alias file", )
    parser.add_argument( "--sa-creds", metavar="PATH", required=True, help="service account credentials JSON²", )
    parser.add_argument( "--sa-delegate", metavar="EMAIL", required=True, help="the principal whom the service account will impersonate³", )
    parser.add_argument( "--add-owner", metavar="EMAIL", help="make EMAIL list owner that doesn't receive email (to facilitate configuration)", )
    args = parser.parse_args()

    with open(args.alias_file) as f:
        lines = [l.strip() for l in f if l.strip() and not l.startswith('#')]

    aliases = [map(str.strip, l.split(':')) for l in lines]
    aliases = [(alias, member.split()) for alias, member in aliases]
    from pprint import pprint
    #pprint(aliases)

    #for alias, members in aliases:
    #    print(f"sed -i '/^{alias}:/s/^/#/' /etc/aliases")
    #for alias, members in aliases:
    #    print(f"echo {alias} OK >> /etc/postfix/local_recipients")
    #for alias, members in aliases:
    #    print(f"echo {alias}@icecube.wisc.edu relay:aspmx.l.google.com >> /etc/postfix/transport")
    #print(f"postmap hash:/etc/postfix/local_recipients")
    #print(f"postmap hash:/etc/postfix/transport")
    #print("postalias /etc/aliases")
    #print("postfix reload")

    scopes = [
        "https://www.googleapis.com/auth/admin.directory.group",
        "https://www.googleapis.com/auth/admin.directory.group.member",
        "https://www.googleapis.com/auth/apps.groups.settings",
    ]
    creds = service_account.Credentials.from_service_account_file( args.sa_creds, scopes=scopes, subject=args.sa_delegate )
    admin_svc = discovery.build("admin", "directory_v1", credentials=creds, cache_discovery=False)
    groups_admin = admin_svc.groups()
    groups_admin_aliases = groups_admin.aliases()
    groups_admin_members = admin_svc.members()
    settings_svc = discovery.build("groupssettings", "v1", credentials=creds, cache_discovery=False)
    groups_settings = settings_svc.groups()
    for alias, members in aliases:
        print(alias, members)

        if "zoomservice" in members:
            core_name = alias.replace('ic-', '').replace('i3-', '')
            group_prefix = f"zoom-{core_name}"
            group_email = f"{group_prefix}@icecube.wisc.edu"
            group_name = f"Zoom Channel for {core_name.replace('wg-', 'WG-').capitalize()}"
        else:
            group_prefix = alias
            group_email = f"{alias}@icecube.wisc.edu"
            group_name = alias.capitalize()
        logger.info(f"Creating group {group_email}")
        create_group(groups_admin, group_email, group_name, "This used to be an alias on i3mail")

        if "zoomservice" in members:
            logger.info(f"Adding {alias} alias")
            add_alias(groups_admin_aliases, group_email, f"{alias}@icecube.wisc.edu")

        logger.info(f"Configuring Google group {group_email}")
        groups_settings.patch(
            groupUniqueId=group_email,
            body={ "whoCanContactOwner": "ALL_IN_DOMAIN_CAN_CONTACT",
                "isArchived": "true", }, ).execute()

        logger.info(f"Adding owner {args.add_owner}")
        insert_member(groups_admin_members, group_email, args.add_owner, 'OWNER')

        for recipient in members:
            addr = recipient if '@' in recipient else f"{recipient}@icecube.wisc.edu"
            insert_member(groups_admin_members, group_email, addr, 'MANAGER')

        logger.warning( f"Set 'Subject prefix' to '[{group_prefix}]' in the 'Email options' section" )
        logger.warning( f"https://groups.google.com/u/3/a/icecube.wisc.edu/g/{group_prefix}/settings#email" )

        input("Hit enter to proceed")



if __name__ == "__main__":
    sys.exit(main())
