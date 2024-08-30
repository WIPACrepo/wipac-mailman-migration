#!/usr/bin/env python
import argparse
import sys
import pickle
import colorlog
import logging
from pprint import pformat
from pprint import pprint

from pathlib import Path
# noinspection PyPackageRequirements
from google.oauth2 import service_account

# noinspection PyPackageRequirements
from googleapiclient import discovery

# noinspection PyPackageRequirements
from googleapiclient.errors import HttpError

#from utils import get_google_group_config_from_mailman_config


handler = colorlog.StreamHandler()
handler.setFormatter(colorlog.ColoredFormatter("%(log_color)s%(levelname)s:%(message)s"))
logger = colorlog.getLogger("settings-import")
logger.propagate = False
logger.addHandler(handler)

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


def main():
    parser = argparse.ArgumentParser(
        description="",
        epilog="",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--mailman-pickle-dir", metavar="PATH", required=True,
        help="dir with mailman list configuration pickles created by pickle-mailman-list.py",)
    parser.add_argument("--sa-creds", metavar="PATH", required=True,
        help="service account credentials JSON²",)
    parser.add_argument("--sa-delegate", metavar="EMAIL", required=True,
        help="the principal whom the service account will impersonate³",)
    args = parser.parse_args()

    scopes = ["https://www.googleapis.com/auth/apps.groups.settings"]
    cred = service_account.Credentials.from_service_account_file(args.sa_creds, scopes=scopes, subject=args.sa_delegate)
    svc = discovery.build("groupssettings", "v1", credentials=cred, cache_discovery=False)
    groups = svc.groups()

    controlled_groups = [f"{g}@icecube.wisc.edu" for g in
                         ("analysis", "authors", "authors-gen2", "icc", "penguins", "wg-leaders")]

    for pkl in Path(args.mailman_pickle_dir).glob('*.pkl'):
        with open(pkl, "rb") as f:
            mmcfg = pickle.load(f)

        #if not mmcfg['archive']:
        #    print(mmcfg['email'])
        #continue

        if mmcfg['email'] in controlled_groups:
            continue
        try:
            ggcfg = groups.get(groupUniqueId=mmcfg["email"]).execute()
        except HttpError as e:
            if e.status_code == 404:
                continue
            else:
                raise
        print(mmcfg['email'])
        who_can_leave = ("NONE_CAN_LEAVE" if mmcfg["unsubscribe_policy"] else "ALL_MEMBERS_CAN_LEAVE")
        if who_can_leave != ggcfg["whoCanLeaveGroup"]:
            print("changing who can leave to", who_can_leave)
            #groups.patch(
            #    groupUniqueId=ggcfg["email"],
            #    body={"whoCanLeaveGroup": who_can_leave,
            #          },
            #).execute()
            if who_can_leave == "NONE_CAN_LEAVE":
                addr, domain = ggcfg["email"].split("@")
                logger.warning("Uncheck standard footers!")
                logger.warning(f"https://groups.google.com/u/3/a/{domain}/g/{addr}/settings#email")

        print()

        # "whoCanLeaveGroup":






if __name__ == "__main__":
    sys.exit(main())
