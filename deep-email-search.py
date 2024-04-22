#!/usr/bin/env python
import argparse
import sys
from pprint import pprint
import pickle
import asyncio

import thefuzz.fuzz
from krs.token import get_rest_client
from krs.users import list_users


async def main():
    parser = argparse.ArgumentParser(
            description="clever searching for email",
            formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('all_users_pickle',
                        help='will create if file does not exist')
    parser.add_argument('email',
                        help='address to search for')
    args = parser.parse_args()
    pprint(args)

    try:
        with open(args.all_users_pickle, 'rb') as f:
            all_users = pickle.load(f)
    except FileNotFoundError:
        kc = get_rest_client()
        all_users = await list_users(rest_client=kc)
        with open(args.all_users_pickle, 'wb') as f:
            pickle.dump(all_users, f)

    match_found = False
    for username, userinfo in all_users.items():
        attrs = userinfo.get('attributes', {})
        emails = {userinfo.get('email'), attrs.get('canonical_email'), attrs.get('mailing_list_email'),
                  attrs.get('author_email'), f"{username}@icecube.wisc.edu"}
        if args.email in emails:
            print(userinfo['username'])
            match_found = True

    if not match_found:
        for username, userinfo in all_users.items():
            attrs = userinfo.get('attributes', {})
            emails = list(filter(None, {userinfo.get('email'), attrs.get('canonical_email'),
                                        attrs.get('mailing_list_email'), attrs.get('author_email'),
                                        f"{username}@icecube.wisc.edu"}))
            local_parts = [email.split('@')[0] for email in emails if email and email.split('@')[0]]
            local_part = args.email.split('@')[0]
            ratios = [thefuzz.fuzz.ratio(local_part, lp) for lp in local_parts]
            if any(r > 50 for r in ratios):
                print(username, emails, ratios)


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
