#!/usr/bin/env python
import argparse
import sys

from email.message import EmailMessage

MESSAGES = {
    'BEFORE': """Hi all,

I hope this message find you well!

This message is to let you know that we are migrating this email list to
Google Groups. This changes very little in your day to day use of the
mail list. The biggest change is the location of the archives (now at
groups.google.com).

What do I need to do?
   For the most part, nothing! Email delivery will continue to
   work as it always has.

The new interface for this group, including archives and your settings is
here: https://groups.google.com/a/icecube.wisc.edu/g/{list_name}

This link: https://groups.google.com/my-groups will take you to a list
of the groups in which you are a member.


As always, if there are issues or questions please contact
help@icecube.wisc.edu.

Thanks much!
""",

    'AFTER': """Hi all,

Just a note that the migration of the {list_name} list to Google groups is
complete.

You can now find the archives and your settings here:

https://groups.google.com/a/icecube.wisc.edu/g/{list_name}

If you run into any problems with this, please contact help@icecube.wisc.edu

Thanks much!
"""
}


def main():
    parser = argparse.ArgumentParser(
        description="",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--list-name', required=True,
                        help="list name (part before @icecube.wisc.edu)")
    parser.add_argument('--from-addr', default='help@icecube.wisc.edu',
                        help="from address")
    parser.add_argument('--message-name', required=True, choices=MESSAGES.keys(),
                        help="name of the message to be sent")
    parser.add_argument("--dry-run", action="store_true",
                        help="print contents of the message that would be sent and exit")
    args = parser.parse_args()

    msg = EmailMessage()
    msg["Subject"] = "Mailing list update"
    msg["From"] = args.from_addr
    msg["To"] = f"{args.list_name}@icecube.wisc.edu"
    content = MESSAGES[args.message_name].format(list_name=args.list_name)
    msg.set_content(content)

    if args.dry_run:
        print(msg.as_string())
        return 0

    #with smtplib.SMTP('i3mail.icecube.wisc.edu') as s:
    #    s.send_message(msg)


if __name__ == "__main__":
    sys.exit(main())
