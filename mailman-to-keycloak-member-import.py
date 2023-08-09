#!/usr/bin/env python
import argparse
import asyncio
import logging
import pickle
import re
import smtplib
import sys

from email.message import EmailMessage

from krs.token import get_rest_client
from krs.groups import create_group, add_user_group
from krs.users import list_users

FULL_INSTRUCTIONS_MESSAGE = """
You are receiving this messages because you need to take action to
ensure uninterrupted delivery of messages from mailing list {list_addr}.

Please ignore this email if it is a duplicate and you have already
taken the required actions.

In the near future this mailing list will become restricted to
active members of {experiment_list} experiment(s),
and require subscribers to either use their IceCube email address
or configure a custom email address in their profile to be used
for all mailing lists whose membership management is automated.

You are currently subscribed to {list_addr} using
{user_addr}, which is either a non-IceCube, or a disallowed email
address, or you are not a member of an institution belonging to
{experiment_list} experiment(s).

In order to remain subscribed to {list_addr} after enforcement
of membership restrictions begins you must:

(1) If you prefer to use a non-IceCube email for ALL automatically-
    managed mailing lists, you must configure it in your user profile.
    (Skip this step if you want to use your IceCube address.)
    - Go to https://user-management.icecube.aq and log in using
      your IceCube credentials.
    - Under "My profile", fill in "mailing_list_email" field and
      click "Update".

(2) Ensure that you are a member of an institution belonging to
    one of {experiment_list} experiment(s).
    - Go to https://user-management.icecube.aq and log in using
      your IceCube credentials.
    - Check your experiments under "Experiments/Institutions".
    - If necessary, click "Join an institution", select an experiment
      and an institution, and click "Submit Join Request".
      Wait until your request is approved before proceeding
      to step 3.

(3) Join the mailing list group corresponding to this list.
    - Go to https://user-management.icecube.aq and log in using
      your IceCube credentials.
    - Under "Groups" at the bottom of the page, click "Join a group"
    - Select the appropriate group (look for prefix "/mail/")
    - Click "Submit Join Request"

In order to avoid a disruption in receiving of messages from
{list_addr} once it becomes restricted,
you must complete the steps above, and your requests
must be approved prior to the transition.

Taking the steps above will not affect your current subscription,
so we recommend completing them soon, since it may take some time
for requests to get approved.

If you have questions or need help, please email help@icecube.wisc.edu.
"""

OWNER_INSTRUCTIONS_MESSAGE = """
You are receiving this message because you are registered as an owner of
{list_addr} using {user_addr}, which is either
a non-IceCube or a disallowed email address.

In the near future this mailing list will become restricted to
active members of {experiment_list} experiment(s),
and only allow either IceCube email addresses or addresses registered
in the user profile attribute "mailing_list_email". This will apply
to owners as well.
 
In order to remain an owner of {list_addr}
after the transition, you must send a request to help@icecube.wisc.edu.
For example:

Please make <YOUR_ICECUBE_USERNAME> an administrator of the
controlled mailing list {list_addr}.

Once your reqeust is acted upon and you are added to the mailing list
as an owner, if you would rather not receive {list_addr}
traffic, or if you later set "mailing_list_email" attribute on
https://user-management.icecube.aq and find yourself receiving duplicate
emails, you can selectively stop mail delivery by going to
https://groups.google.com, logging on with your IceCube account and
changing "Subscription" value associated with {list_addr}
from "Each email" to "No Email".

If you have questions or need help, please email help@icecube.wisc.edu.
"""

logger = logging.getLogger("member-import")
logger.propagate = False


class ColorLoggingFormatter(logging.Formatter):
    def __init__(self, /, dryrun):
        super().__init__()

        yellow = "\x1b[33;20m"
        red = "\x1b[31;20m"
        inv_red = "\x1b[31;7m"
        reset = "\x1b[0m"
        fmt = "%(levelname)s: %(message)s"

        self.FORMATS = {
            logging.DEBUG: fmt + f" [dryrun={dryrun}]",
            logging.INFO: fmt + f" [dryrun={dryrun}]",
            logging.WARNING: yellow + fmt + f" [dryrun={dryrun}]" + reset,
            logging.ERROR: red + fmt + f" [dryrun={dryrun}]" + reset,
            logging.CRITICAL: inv_red + fmt + f" [dryrun={dryrun}]" + reset,
        }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


def send_email(smtp_host, to, subj, message):
    msg = EmailMessage()
    msg["Subject"] = subj
    msg["From"] = "no-reply@icecube.wisc.edu"
    msg["To"] = to
    msg.set_content(message)
    with smtplib.SMTP(smtp_host) as s:
        s.send_message(msg)


async def mailman_to_keycloak_member_import(
    mmcfg,
    keycloak_group,
    mail_server,
    required_experiments,
    extra_admins,
    keycloak,
    email_dry_run,
    dryrun,
):
    logger.info("Creating KeyCloak groups")
    if not dryrun:
        await create_group(keycloak_group, rest_client=keycloak)
        await create_group(keycloak_group + "/_admin", rest_client=keycloak)
    for username in extra_admins:
        logger.info(f"Adding extra admin {username}")
        if not dryrun:
            await add_user_group(keycloak_group + "/_admin", username, rest_client=keycloak)

    logger.info(f"Retrieving info of all users from KeyCloak")
    all_users = await list_users(rest_client=keycloak)
    username_from_canon_addr = {
        u["attributes"]["canonical_email"]: u["username"]
        for u in all_users.values()
        if "canonical_email" in u["attributes"]
    }

    allowed_non_members = []
    email_regex = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    for nonmember in mmcfg["accept_these_nonmembers"]:
        if re.match(email_regex, nonmember):
            logger.info(f"Found valid non-member address {nonmember}")
            allowed_non_members.append(nonmember)
        else:
            logger.info(f"Ignoring invalid non-member email {nonmember}")

    send_regular_instructions_to = set()
    for email in mmcfg["digest_members"] + mmcfg["regular_members"] + allowed_non_members:
        username, domain = email.split("@")
        if domain == "icecube.wisc.edu":
            username = username_from_canon_addr.get(email, username)
            if username not in all_users:
                logger.warning(f"Unknown user {email}")
                send_regular_instructions_to.add(email)
                continue
            logger.info(f"Adding {username} as MEMBER")
            if not dryrun:
                await add_user_group(keycloak_group, username, rest_client=keycloak)
        else:
            logger.info(f"Add non-icecube member {email} to list of instructions recipients")
            send_regular_instructions_to.add(email)

    for email in send_regular_instructions_to:
        logger.info(f"Sending MEMBER instructions to {email} [email_dry_run={email_dry_run}]")
        if not dryrun and not email_dry_run:
            send_email(
                mail_server,
                email,
                f"Important information about membership in mailing list {mmcfg['email']}",
                FULL_INSTRUCTIONS_MESSAGE.format(
                    list_addr=mmcfg["email"],
                    user_addr=email,
                    experiment_list=", ".join(required_experiments),
                ),
            )

    send_owner_instructions_to = set()
    for email in mmcfg["owner"]:
        username, domain = email.split("@")
        if domain == "icecube.wisc.edu":
            username = username_from_canon_addr.get(email, username)
            if username not in all_users:
                logger.warning(f"Unknown owner {email}")
                send_owner_instructions_to.add(email)
                continue
            logger.info(f"Adding {username} as OWNER")
            if not dryrun:
                await add_user_group(keycloak_group + "/_admin", username, rest_client=keycloak)
        else:
            logger.info(f"Non-icecube owner {email}")
            send_owner_instructions_to.add(email)

    for email in send_owner_instructions_to:
        logger.info(f"Sending OWNER instructions to {email} [email_dry_run={email_dry_run}]")
        if not dryrun and not email_dry_run:
            send_email(
                mail_server,
                email,
                f"Important information about ownership of mailing list {mmcfg['email']}",
                OWNER_INSTRUCTIONS_MESSAGE.format(
                    list_addr=mmcfg["email"],
                    user_addr=email,
                    experiment_list=", ".join(required_experiments),
                ),
            )


def main():
    def __formatter(max_help_position, width):
        return lambda prog: argparse.ArgumentDefaultsHelpFormatter(
            prog, max_help_position=max_help_position, width=width
        )

    parser = argparse.ArgumentParser(
        description="Import subscribers and owners of a mailman list into a KeyCloak group, "
        "if possible. If not possible (non-IceCube email addresses), send them instructions "
        "on what to do.",
        formatter_class=__formatter(max_help_position=30, width=90),
    )
    parser.add_argument(
        "--mailman-pickle",
        metavar="PATH",
        required=True,
        help="mailman list configuration pickle file created by pickle-mailman-list.py",
    )
    parser.add_argument(
        "--keycloak-group",
        metavar="PATH",
        required=True,
        help="path to the KeyCloak group to populate",
    )
    parser.add_argument(
        "--required-experiments",
        metavar="NAME",
        required=True,
        nargs="+",
        help="experiment(s) to use in instructions emails",
    )
    parser.add_argument(
        "--extra-admins",
        metavar="USER",
        nargs="+",
        default=[],
        help="add USER(s) to the _admin subgroup",
    )
    parser.add_argument(
        "--mail-server",
        metavar="HOST",
        required=True,
        help="use HOST to send instructional emails",
    )
    parser.add_argument(
        "--email-dry-run",
        action="store_true",
        help="don't send any emails",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="perform a trial run with no changes made and now emails sent",
    )
    parser.add_argument(
        "--log-level",
        metavar="LEVEL",
        default="info",
        choices=("debug", "info", "warning", "error"),
        help="logging level: debug, info, warning, error",
    )
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level.upper()))
    handler = logging.StreamHandler()
    handler.setFormatter(ColorLoggingFormatter(dryrun=args.dry_run))
    logger.addHandler(handler)
    if args.log_level == "info":
        ClientCredentialsAuth = logging.getLogger("ClientCredentialsAuth")
        ClientCredentialsAuth.setLevel(logging.WARNING)  # too noisy

    logger.info(f"Loading mailman list configuration from {args.mailman_pickle}")
    with open(args.mailman_pickle, "rb") as f:
        mmcfg = pickle.load(f)

    keycloak = get_rest_client()

    asyncio.run(
        mailman_to_keycloak_member_import(
            mmcfg,
            args.keycloak_group,
            args.mail_server,
            args.required_experiments,
            args.extra_admins,
            keycloak,
            args.email_dry_run,
            args.dry_run,
        )
    )


if __name__ == "__main__":
    sys.exit(main())
