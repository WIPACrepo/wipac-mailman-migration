#!/usr/bin/env python
import argparse
import sys
import logging
import pickle
import re
from google.oauth2 import service_account
from googleapiclient import discovery
from googleapiclient.errors import HttpError

from utils import get_google_group_config_from_mailman_config


def main():
    parser = argparse.ArgumentParser(
        description="Import mailman list members created by `pickle-mailman-list.py` "
        "into Google Groups using Google API¹.",
        epilog="Notes:\n"
        "[1] The following APIs must be enabled: Admin SDK.\n"
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
        "--ignore",
        metavar="EMAIL",
        default=[],
        nargs="*",
        help="don't add EMAIL to group members",
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
        "has permission to edit setting of the group that will be created.\n"
        "This is purely for convenience: group management URL will print out\n"
        "like https://groups.google.com/u/NUM/... (default: 0)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(levelname)s %(message)s",
    )

    logging.info(f"Retrieving mailman list configuration from {args.mailman_pickle}")
    with open(args.mailman_pickle, "rb") as f:
        mmcfg = pickle.load(f)

    logging.info("Converting mailman list settings to google group settings")
    ggcfg = get_google_group_config_from_mailman_config(mmcfg)

    scopes = ["https://www.googleapis.com/auth/admin.directory.group.member"]
    creds = service_account.Credentials.from_service_account_file(
        args.sa_creds, scopes=scopes, subject=args.sa_delegate
    )

    svc = discovery.build("admin", "directory_v1", credentials=creds, cache_discovery=False)
    members = svc.members()

    # The flow for populating members and designating managers is a little
    # weird to work around a Google API bug where members.get() fails sometimes:
    # https://stackoverflow.com/questions/66992809/google-admin-sdk-directory-api-members-get-returns-a-404-for-member-email-but

    for member in mmcfg["digest_members"]:
        if member in args.ignore:
            logging.info(f"Skipping digest member {member} (on the ignore list)")
            continue
        body = {"email": member, "delivery_settings": "DIGEST"}
        if member in mmcfg["owner"]:
            logging.info(f"Inserting digest member {member} (manager)")
            body["role"] = "MANAGER"
        else:
            logging.info(f"Inserting digest member {member}")
        try:
            members.insert(groupKey=ggcfg["email"], body=body).execute()
        except HttpError as e:
            if e.status_code == 409:  # entity already exists
                logging.error(f"User {member} already part of the group")
            else:
                raise

    for member in mmcfg["regular_members"]:
        if member in args.ignore:
            logging.info(f"Skipping member {member} (on the ignore list)")
            continue
        body = {"email": member, "delivery_settings": "ALL_MAIL"}
        if member in mmcfg["owner"]:
            logging.info(f"Inserting member {member} (manager)")
            body["role"] = "MANAGER"
        else:
            logging.info(f"Inserting member {member}")
        try:
            members.insert(groupKey=ggcfg["email"], body=body).execute()
        except HttpError as e:
            if e.status_code == 409:  # entity already exists
                logging.error(f"User {member} already part of the group")
            else:
                raise

    for owner in set(mmcfg["owner"]) - set(mmcfg["digest_members"] + mmcfg["regular_members"]):
        if owner in args.ignore:
            logging.info(f"Skipping non-member manager {owner} (on the ignore list)")
            continue
        logging.info(f"Inserting non-member manager {owner}")
        try:
            members.insert(
                groupKey=ggcfg["email"],
                body={"email": owner, "role": "MANAGER", "delivery_settings": "NONE"},
            ).execute()
        except HttpError as e:
            if e.status_code == 409:  # entity already exists
                logging.error(f"User {owner} already part of the group")
                logging.warning(f"!!!  CONFIGURE AS MANAGER MANUALLY: {owner}")

    email_regex = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    for nonmember in mmcfg["accept_these_nonmembers"]:
        if nonmember in args.ignore:
            logging.info(f"Skipping non-member {nonmember} (on the ignore list)")
            continue
        if not re.match(email_regex, nonmember):
            logging.warning(f"Ignoring invalid non-member email {nonmember}")
            continue
        logging.info(f"Inserting non-member {nonmember}")
        try:
            members.insert(
                groupKey=ggcfg["email"],
                body={"email": nonmember, "delivery_settings": "NONE"},
            ).execute()
        except HttpError as e:
            if e.status_code == 409:  # entity already exists
                logging.error(f"User {nonmember} already part of the group")
                logging.warning(f"!!!  RESOLVE CONFLICT MANUALLY FOR: {nonmember}")

    svc.close()

    addr, domain = ggcfg["email"].split("@")
    logging.info(
        f"Group member list can be found at https://groups.google.com/u/"
        f"{args.browser_google_account_index}/a/{domain}/g/{addr}/members"
    )


if __name__ == "__main__":
    sys.exit(main())
