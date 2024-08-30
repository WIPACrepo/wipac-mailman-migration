#!/usr/bin/env python
import argparse
import sys
import smtplib

from email.message import EmailMessage

MESSAGES = {
    'BEFORE_BARNET': """Hi all,

I hope this message find you well!

This message is to let you know that we are migrating this email list to
Google Groups. This changes very little in your day to day use of the
mail list. The biggest change is the location of the archives (now at
groups.google.com).

What do I need to do?
   For the most part, nothing! Email delivery will continue to
   work as it always has.

The new interface for this group, including archives and your settings is
here: https://groups.google.com/a/{domain}/g/{list_name}

This link: https://groups.google.com/my-groups will take you to a list
of the groups in which you are a member.


As always, if there are issues or questions please contact
help@icecube.wisc.edu.

Thanks much!""",
    #################################################
    'AFTER_BARNET': """Hi all,

Just a note that the migration of the {list_name} list to Google groups is
complete.

You can now find the archives and your settings here:

https://groups.google.com/a/{domain}/g/{list_name}

If you run into any problems with this, please contact help@icecube.wisc.edu

Thanks much!""",
    #################################################
    'SINGLE_VBRIK': """Hello

This mailing list has been converted to a Google Group.

No action on your part is necessary.

List archives and your subscription settings can now be found at
https://groups.google.com/a/{domain}/g/{list_name}
(The archive migration process is ongoing and should finish soon.)


If you run into any problems, please contact help@icecube.wisc.edu.
"""
}


def main():
    parser = argparse.ArgumentParser(
        description="",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--list-addr', required=True,
                        help="list address")
    parser.add_argument('--from-field', required=True, metavar='USERNAME',
                        help="RFC-compliant from field, e.g. John Doe <jdoe@i.w.e>"
                             " (has be subscribed to the mailing list!)")
    parser.add_argument('--message-name', required=True, choices=MESSAGES.keys(),
                        help="name of the message to be sent")
    parser.add_argument("--dry-run", action="store_true",
                        help="print contents of the message that would be sent and exit")
    args = parser.parse_args()

    local_part, domain = args.list_addr.split('@')

    msg = EmailMessage()
    msg["Subject"] = "Mailing list update"
    msg["From"] = args.from_field
    msg["To"] = args.list_addr
    content = MESSAGES[args.message_name].format(list_name=local_part, domain=domain)
    msg.set_content(content)

    if args.dry_run:
        print(msg.as_string())
        return 0

    with smtplib.SMTP('i3mail.icecube.wisc.edu') as s:
        s.send_message(msg)


if __name__ == "__main__":
    sys.exit(main())
