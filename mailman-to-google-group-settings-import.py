#!/usr/bin/env python
import argparse
import sys
import pickle
import colorlog
import logging
from pprint import pformat
from google.oauth2 import service_account
from googleapiclient import discovery
from googleapiclient.errors import HttpError

from utils import get_google_group_config_from_mailman_config


handler = colorlog.StreamHandler()
handler.setFormatter(colorlog.ColoredFormatter("%(log_color)s%(levelname)s:%(message)s"))
logger = colorlog.getLogger("settings-import")
logger.propagate = False
logger.addHandler(handler)


def set_controlled_mailing_list_setting(ggcfg):
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
        "Message archives are on https://groups.google.com (log in with your IceCube account)\n"
        "To unsubscribe, use group membership management interface of https://user-management.icecube.aq",
    )
    _override(ggcfg, "whoCanModerateMembers", "NONE")

    return ggcfg


def summarize_settings(ggcfg):
    logger.info(f"whoCanViewGroup = {ggcfg['whoCanViewGroup']}")
    logger.info(f"whoCanViewMembership = {ggcfg['whoCanViewMembership']}")
    logger.info(f"allowExternalMembers = {ggcfg['allowExternalMembers']}")
    logger.info(f"whoCanPostMessage = {ggcfg['whoCanPostMessage']}")
    logger.info(f"messageModerationLevel = {ggcfg['messageModerationLevel']}")
    logger.info(f"whoCanDiscoverGroup = {ggcfg['whoCanDiscoverGroup']}")
    if ggcfg["whoCanPostMessage"] == "ANYONE_CAN_POST" and ggcfg["messageModerationLevel"] == "MODERATE_NONE":
        logger.warning("!!!  LIST ACCEPTS MESSAGES FROM ANYBODY WITHOUT MODERATION")


def main():
    parser = argparse.ArgumentParser(
        description="Import mailman list configuration (only settings) created\n"
        "by `pickle-mailman-list.py` into Google Groups using Google API¹.",
        epilog="Notes:\n"
        "[1] The following APIs must be enabled: Admin SDK, Group Settings.\n"
        "[2] The service account needs to be set up for domain-wide delegation.\n"
        "[3] The delegate account needs to have a Google Workspace admin role.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--mailman-pickle",
        metavar="PATH",
        required=True,
        help="mailman list configuration pickle created by pickle-mailman-list.py",
    )
    parser.add_argument(
        "--controlled-mailing-list",
        action="store_true",
        help="override Google group settings to be compatible with the controlled mailing list paradigm",
    )
    parser.add_argument(
        "--sa-creds",
        metavar="PATH",
        required=True,
        help="service account credentials JSON²",
    )
    parser.add_argument(
        "--sa-delegate",
        metavar="EMAIL",
        required=True,
        help="the principal whom the service account will impersonate³",
    )
    parser.add_argument(
        "--add-owner",
        metavar="EMAIL",
        help="make EMAIL list owner that doesn't receive email (to facilitate configuration)",
    )
    parser.add_argument(
        "--log-level",
        default="info",
        choices=("debug", "info", "warning", "error"),
        help="logging level (default: info)",
    )
    parser.add_argument(
        "--browser-google-account-index",
        metavar="NUM",
        type=int,
        default=0,
        help="index of the account in your browser's list of Google accounts that\n"
        "has permission to edit settings of the group that will be created.\n"
        "This is purely for convenience: group management URL will print out\n"
        "like https://groups.google.com/u/NUM/... (default: 0)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(levelname)s %(message)s",
    )

    logger.info(f"Retrieving mailman list configuration from {args.mailman_pickle}")
    with open(args.mailman_pickle, "rb") as f:
        mmcfg = pickle.load(f)

    logger.debug(pformat(mmcfg))
    logger.info("Converting mailman list settings to google group settings")
    ggcfg = get_google_group_config_from_mailman_config(mmcfg)
    logger.debug(pformat(ggcfg))

    if args.controlled_mailing_list:
        ggcfg = set_controlled_mailing_list_setting(ggcfg)

    summarize_settings(ggcfg)

    scopes = [
        "https://www.googleapis.com/auth/admin.directory.group",
        "https://www.googleapis.com/auth/admin.directory.group.member",
        "https://www.googleapis.com/auth/apps.groups.settings",
    ]
    creds = service_account.Credentials.from_service_account_file(
        args.sa_creds, scopes=scopes, subject=args.sa_delegate
    )

    svc = discovery.build("admin", "directory_v1", credentials=creds, cache_discovery=False)
    try:
        logger.info(f"Creating group {ggcfg['email']}")
        svc.groups().insert(
            body={
                "description": ggcfg["description"],
                "email": ggcfg["email"],
                "name": ggcfg["name"],
            }
        ).execute()
    except HttpError as e:
        if e.status_code == 409:  # entity already exists
            logger.warning("Group already exists")
        else:
            raise
    finally:
        svc.close()

    svc = discovery.build("groupssettings", "v1", credentials=creds, cache_discovery=False)
    try:
        logger.info(f"Configuring Google group {ggcfg['email']}")
        svc.groups().patch(
            groupUniqueId=ggcfg["email"],
            body=ggcfg,
        ).execute()
    finally:
        svc.close()

    if args.add_owner:
        svc = discovery.build("admin", "directory_v1", credentials=creds, cache_discovery=False)
        members = svc.members()
        logger.info(f"Adding owner {args.add_owner}")
        try:
            members.insert(
                groupKey=ggcfg["email"],
                body={
                    "email": args.add_owner,
                    "role": "OWNER",
                    "delivery_settings": "NONE",
                },
            ).execute()
        except HttpError as e:
            if e.status_code == 409:  # entity already exists
                logger.error(f"User {args.add_owner} already part of the group")
        finally:
            svc.close()

    logger.warning("!!!   SOME GOOGLE GROUP OPTIONS CANNOT BE SET PROGRAMMATICALLY")
    logger.warning(
        f"!!!   Set 'Subject prefix' to '{mmcfg['subject_prefix'].strip()}' in the 'Email options' section"
    )
    if not args.controlled_mailing_list:
        logger.warning(
            "!!!   Consider enabling 'Include the standard Groups footer' in the 'Email options' section"
        )
    addr, domain = ggcfg["email"].split("@")
    logger.warning(
        f"!!!   https://groups.google.com/u/{args.browser_google_account_index}/a/{domain}/g/{addr}/settings#email"
    )


if __name__ == "__main__":
    sys.exit(main())
