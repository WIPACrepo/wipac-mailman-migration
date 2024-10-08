#!/usr/bin/env python
import argparse
import sys
from pprint import pprint

from krs.institutions import *
from krs.token import *
from krs.groups import *
from krs.users import *
import pickle
import asyncio
import datetime
from krs.email import send_email
import textwrap


MSG = """
Hello

You are receiving this email because you are one of the managers of
{institution_path}. 

We are moving toward automating access control to potentially sensitive resources
based on information configured via IceCube's Identity Management Console
https://user-management.icecube.aq.
For that we need institution groups to be kept up-to-date.

Please use https://user-management.icecube.aq/institutions
to remove members who are not actively working in your
institution by Monday, July 15.

To make this task easier, below you will find the list
of all current members of {institution_path} who are not designated as
authors, sorted by the date on
which their account was created.

This message has been automatically generated. Please contact
help@icecube.wisc.edu with questions.
"""

async def main():
    parser = argparse.ArgumentParser(
            description="",
            formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--all-users', required=True)
    args = parser.parse_args()

    kc = get_rest_client()

    try:
        with open(args.all_users, 'rb') as f:
            all_users = pickle.load(f)
    except FileNotFoundError:
        all_users = await list_users(rest_client=kc)
        with open(args.all_users, 'wb') as f:
            pickle.dump(all_users, f)

    i3_insts = await list_insts('IceCube', rest_client=kc)
    i3g2_insts = await list_insts('IceCube-Gen2', rest_client=kc)
    all_insts = i3_insts | i3g2_insts

    authors_i3 = await get_group_membership('/mail/authors', rest_client=kc)
    authors_gen2 = await get_group_membership('/mail/authors-gen2', rest_client=kc)
    authors = set(authors_i3+authors_gen2)

    for inst_path in all_insts:
        usernames = await get_group_membership(inst_path, rest_client=kc)
        ledger = []
        for username in usernames:
            if username in authors:
                continue
            user = all_users[username]
            ts = user.get('attributes', {}).get('createTimestamp', '19000101000000Z')
            year = ts[0:4]
            month = ts[4:6]
            day = ts[6:8]
            c_date = f"={year}-{month}-{day}"
            if c_date == '=2020-09-01':
                c_date = '<2020-09-01'
            ledger.append((c_date, username, user.get('firstName', '') + ' ' + user.get('lastName', '')))
        if not ledger:
            print(inst_path, 'EMPTY')
            continue
        ledger.sort()
        user_tbl = '\n'.join([' '.join((d, f"  {u:_<12}  ", n)) for d,u,n in ledger])

        text = MSG.format(institution_path=inst_path)
        paras = []
        for para in text.split('\n\n'):
            paras.append(textwrap.fill(para.strip(), width=80,  break_on_hyphens=False))
        text = '\n\n'.join(paras)
        msg = f"{text}<br><br><tt>{user_tbl}</tt>"
        print(msg)
        admins = await get_group_membership(inst_path + '/_admin', rest_client=kc)
        print(admins)
        subj=f"Please update active members of {inst_path}"
        for admin in admins:
            email = f"{admin}@icecube.wisc.edu"
            #email = 'vbrik@icecube.wisc.edu'
            print('not doing anything')
            return
            #send_email(email, subj, msg)
        #return



if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
