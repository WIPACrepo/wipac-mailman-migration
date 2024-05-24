#!/usr/bin/env python
import argparse
import sys
from pprint import pprint

from attrs import define
import subprocess
import asyncio
import pickle
from krs.token import get_rest_client
from krs.users import list_users
import thefuzz.fuzz
from operator import itemgetter
from krs.groups import get_group_membership
from enum import *
import re

MANUAL_EMAIL_MAP = {
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
    'mcpreston@icecube.wisc.edu': 'mcpreston',
    'carlos.pobes.guest@usap.gov': 'cpobes',
    'collaborationmeetings@icecube.wisc.edu': None,
    'efriedman09@gmail.com': 'efriedman',
    'i3runcoord@googlemail.com': None,
    'ralf.auer.guest@usap.gov': 'rauer',
    'zsuzsa@astro.columbia.edu': 'zmarka',
}

KNOWN_UNKNOWNS = [
    'mtakahashi@chiba-u.jp',
    'vxw@capella2.gsfc.nasa.gov'
]


def get_sub_addr(user):
    user_attrs: dict = user['attributes']
    return (user_attrs.get('mailing_list_email') or user_attrs.get('canonical_email')
            or f"{user['username']}@icecube.wisc.edu").lower()


def find_user(all_users, email):
    ret = []
    for username, userinfo in all_users.items():
        attrs = userinfo.get('attributes', {})
        emails = list(filter(None, {userinfo.get('email'), attrs.get('canonical_email'),
                                    attrs.get('mailing_list_email'), attrs.get('author_email'),
                                    f"{username}@icecube.wisc.edu"}))
        if email.lower() in [addr.strip().lower() for addr in emails]:
            ret.append(userinfo['username'])
    return ret


@define
class FuzzyMatch:
    target: str
    result: str
    ratio: int
    data: tuple

def fuzzy_find(all_users, email):
    best_ratio = -1
    fuzzy_matches = []
    for username, userinfo in all_users.items():
        attrs = userinfo.get('attributes', {})
        candidate_emails = [userinfo.get('email'), attrs.get('canonical_email'),
                            attrs.get('mailing_list_email'), attrs.get('author_email'),
                            f"{username}@icecube.wisc.edu"]
        candidate_local_parts = [em.split('@')[0] for em in candidate_emails
                                 if em and em.split('@')[0]]
        candidate_misc = [f"{userinfo.get('firstName')} {userinfo.get('lastName')}",
                          attrs.get('slack'), attrs.get('author_name'), attrs.get('github')]
        candidates = filter(None, candidate_local_parts + candidate_misc)
        candidates = list(set(str_.strip().lower() for str_ in candidates))
        local_part = email.split('@')[0].lower()
        ratios = [thefuzz.fuzz.ratio(local_part, candidate) for candidate in candidates]
        current_best_ratio = max(ratios)
        match_descr = (current_best_ratio, [username, candidates, ratios])
        match = FuzzyMatch(target=email, result=username, ratio=current_best_ratio, data=match_descr)
        if current_best_ratio > best_ratio:
            best_ratio = current_best_ratio
            fuzzy_matches = [match]
        elif current_best_ratio == best_ratio:
            fuzzy_matches.append(match)
    return fuzzy_matches


def build_email_mappings(mm_emails, all_users, known_mappings):
    ambiguous_fuzzy = []
    email_mapping = {}
    for email in [e for e in mm_emails]:
        assert email not in email_mapping
        if email in known_mappings:
            email_mapping[email] = known_mappings[email]
            continue
        matches = find_user(all_users, email)
        if len(matches) == 1:
            email_mapping[email] = matches[0]
        elif len(matches) == 0:
            matches = fuzzy_find(all_users, email)
            if len(matches) == 1 and matches[0].ratio >= 85:
                email_mapping[email] = matches[0].result
            else:
                #print("ambiguous fuzzy match", matches, file=sys.stderr)
                ambiguous_fuzzy.append((email, matches))
        else:
            raise ValueError("Ambiguous exact match", matches)
            ambiguous_exact.append((email, matches))
    return dict(email_mapping), ambiguous_fuzzy


async def main():
    parser = argparse.ArgumentParser(
            description="",
            formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--list', required=True)
    parser.add_argument('--group', required=True)
    parser.add_argument('--skip', nargs='+', default=[])
    parser.add_argument('--all-users', required=True)
    args = parser.parse_args()

    try:
        with open(args.all_users, 'rb') as f:
            all_users = pickle.load(f)
    except FileNotFoundError:
        kc = get_rest_client()
        all_users = await list_users(rest_client=kc)
        with open(args.all_users, 'wb') as f:
            pickle.dump(all_users, f)

    subprocess.check_output(['ssh', 'mailman', './pickle-mailman-list.py', '--list', args.list])
    subprocess.check_output(['scp', f'mailman:{args.list}.pkl', '.'])
    list_cfg = pickle.load(open(f"{args.list}.pkl", 'rb'))
    email_regex = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    mm_emails = list_cfg['digest_members'] + list_cfg['regular_members'] + \
        [str_ for str_ in list_cfg['accept_these_nonmembers']
         if re.match(email_regex, str_)]


    #mm_emails = subprocess.check_output(
    #    ['ssh', 'mailman', '/usr/lib/mailman/bin/list_members', args.list],
    #    encoding='utf').split()
    mm_emails = sorted(set(email.strip().lower() for email in mm_emails))

    for email in KNOWN_UNKNOWNS + args.skip:
        mm_emails.remove(email)

    mm_email_map, ambiguous_fuzzy = build_email_mappings(mm_emails, all_users, MANUAL_EMAIL_MAP)
    #for email, username in sorted(mm_email_map.items()):
    #    print('MAP', email, username)
    for row in ambiguous_fuzzy:
        print('FAILED_TO_MAP', row[1])

    return

    kc = get_rest_client()
    group_usernames = await get_group_membership(args.group, rest_client=kc)
    username_sub_addr = dict((username, get_sub_addr(all_users[username]))
                             for username in group_usernames)

    mm_usernames_not_in_group = set(mm_email_map[email] for email in mm_emails
                                 if mm_email_map[email] not in group_usernames)
    mm_emails_in_group = [email for email in mm_emails
                          if mm_email_map[email] in group_usernames]
    need_addr_change = [(mm_email_map[email], email, username_sub_addr[mm_email_map[email]])
                        for email in mm_emails_in_group
                        if (
                                email != username_sub_addr[mm_email_map[email]]
                                and not
                                (email.endswith('@icecube.wisc.edu')
                                 and username_sub_addr[mm_email_map[email]].endswith('@icecube.wisc.edu')))]

    for line in sorted(need_addr_change):
        print('ADDR_CHANGE', line)
    for line in sorted(mm_usernames_not_in_group):
        print('NOT_IN_GROUP', line)

if __name__ == '__main__':
    sys.exit(asyncio.run(main()))

