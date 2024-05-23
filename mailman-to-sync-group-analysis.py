#!/usr/bin/env python
import argparse
import sys
from pprint import pprint

import subprocess
import asyncio
import pickle
from krs.token import get_rest_client
from krs.users import list_users
import thefuzz.fuzz
from operator import itemgetter
from krs.groups import get_group_membership
from enum import *

user_by_email_manual = {
    # It looks like this person has 2 accounts: sin and jin.
    # They are probably using jin, and that's the account that has
    # authors_email set to sin@icecube.wisc.edu
    'sin@icecube.wisc.edu': 'jin',
    # it looks like she uses 'sofia', not sathanasiadou
    'sofia.athanasiadou@icecube.wisc.edu': 'sofia',
    # person uses sbash, but subscribed as sbash1 to some lists
    'sbash1@icecube.wisc.edu': 'sbash',
    # multiple accounts have barnet@icecube email
    'barnet@icecube.wisc.edu': 'barnet',
    'cchan42@wisc.edu': 'jchan',
    'cfk5343@psu.edu': 'cklare',
    'csspier@ifh.de': 'cspiering',
    'fvaracar@uni-muenster.de': 'jvara',
    'gabrielc@mit.edu': 'gcollin',
    'iwakiri@hepburn.s.chiba-u.ac.jp': 'buz.iwakiri',
    'javierg@udel.edu': 'jgonzalez',
    'john.evans@icecube.wisc.edu': 'jevans96',
    'mrameezphysics@gmail.com': 'mrameez',
    'msutherl@mps.ohio-state.edu': 'msutherland',
    'rprocter@umd.edu': 'rpmurphy',
    'salaza82@msu.edu': 'dsalazar-gallegos',
    'vandenbrouck@wisc.edu': 'justin',
    'vladimir.brik@icecube.wisc.edu': 'vbrik',
    'xu.zhai@icecube.wisc.edu': 'xuzhai',
}

known_unknowns = [
    'mtakahashi@chiba-u.jp',
    'vxw@capella2.gsfc.nasa.gov'
]

def find_user(all_users, email):
    ret = []
    for username, userinfo in all_users.items():
        attrs = userinfo.get('attributes', {})
        emails = list(filter(None, {userinfo.get('email'), attrs.get('canonical_email'),
                                    attrs.get('mailing_list_email'), attrs.get('author_email'),
                                    f"{username}@icecube.wisc.edu"}))
        if email in emails:
            ret.append(userinfo['username'])
    return ret


def fuzzy_find(all_users, email, ratio):
    ret = []
    for username, userinfo in all_users.items():
        attrs = userinfo.get('attributes', {})
        emails = list(filter(None, {userinfo.get('email'), attrs.get('canonical_email'),
                                    attrs.get('mailing_list_email'), attrs.get('author_email'),
                                    f"{username}@icecube.wisc.edu"}))
        local_parts = [em.split('@')[0] for em in emails if em and em.split('@')[0]]
        local_part = email.split('@')[0]
        full_name = f"{userinfo.get('firstName')} {userinfo.get('lastName')}"
        slack = attrs.get('slack')
        github = attrs.get('github')
        author_name = attrs.get('author_name')
        author_first = attrs.get('author_firstName')
        author_last = attrs.get('author_lastName')
        ratios = [thefuzz.fuzz.ratio(local_part, lp)
                  for lp in local_parts + [full_name, slack, github, author_name, ]]
        if any(r > ratio for r in ratios):
            ret.append([username, full_name, emails, slack, ratios])
    return ret


def get_mailing_list_sub_addr(user):
    user_attrs: dict = user['attributes']
    return (user_attrs.get('mailing_list_email') or user_attrs.get('canonical_email')
            or f"{user['username']}@icecube.wisc.edu")


def build_email_mappings(mm_emails, all_users, skip, known_mappings):
    email_mapping = []
    for email in [e for e in mm_emails]:
        if email in known_unknowns:
            print(f'SKIPPING {email}')
            continue
        for s in skip:
            if s in email:
                continue
        if email in known_mappings:
            email_mapping.append((email, known_mappings[email]))
            continue

        matches = find_user(all_users, email)
        if len(matches) == 2:
            if [u for u in matches if u.endswith('-local')]:
                email_mapping.append((email, [u for u in matches if not u.endswith('-local')][0]))
                continue
        assert len(matches) < 2
        if matches:
            email_mapping.append((email, matches[0]))
        else:
            fuzzy_matches = fuzzy_find(all_users, email, 70)
            assert fuzzy_matches
            if len(fuzzy_matches) > 1:
                fuzzy_matches = fuzzy_find(all_users, email, 90)
                if len(fuzzy_matches) > 1:
                    fuzzy_matches = fuzzy_find(all_users, email, 99)
                    assert len(fuzzy_matches) == 1
            email_mapping.append((email, fuzzy_matches[0][0]))
    return dict(email_mapping)


async def main():
    parser = argparse.ArgumentParser(
            description="",
            formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--list', required=True)
    parser.add_argument('--group', required=True)
    parser.add_argument('--skip', nargs='+', default=[])
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

    mm_emails = subprocess.check_output(
        ['ssh', 'mailman', '/usr/lib/mailman/bin/list_members', args.list],
        encoding='utf').split()

    for email in known_unknowns:
        mm_emails.remove(email)

    usernames_by_mm_email = build_email_mappings(mm_emails, all_users, args.skip, user_by_email_manual)

    #print('\n'.join(' '.join(e) for e in sorted(usernames_by_mm_email, key=itemgetter(1))))

    kc_group_usernames = await get_group_membership(args.group, rest_client=kc)
    effective_addrs_for_lists = dict((username, get_mailing_list_sub_addr(all_users[username]))
                     for username in kc_group_usernames)

    mm_usernames_not_in_group = [usernames_by_mm_email[email] for email in mm_emails
                    if usernames_by_mm_email[email] not in kc_group_usernames]
    mm_emails_in_group = [email for email in mm_emails
                    if usernames_by_mm_email[email] in kc_group_usernames]
    need_addr_change = [(usernames_by_mm_email[email], email, effective_addrs_for_lists[usernames_by_mm_email[email]])
                   for email in mm_emails_in_group
                   if email != effective_addrs_for_lists[usernames_by_mm_email[email]]]

    pprint(need_addr_change)
    pprint(mm_usernames_not_in_group)

if __name__ == '__main__':
    sys.exit(asyncio.run(main()))

