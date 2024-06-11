#!/usr/bin/env python
import argparse
import sys
from pprint import pprint
import textwrap

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
from collections import defaultdict

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
    # 'collaborationmeetings@icecube.wisc.edu': None,
    'efriedman09@gmail.com': 'efriedman',
    # 'i3runcoord@googlemail.com': None,
    'ralf.auer.guest@usap.gov': 'rauer',
    'zsuzsa@astro.columbia.edu': 'zmarka',
    'helpdesk@icecube.wisc.edu': 'helpdesk',  # multiple accounts use this email
    # not sure what is going on. collaborationmeeting is an alias for icecube-collaboration
    'collaborationmeetings@icecube.wisc.edu': 'icecube-collaboration',
    # duplicate canonical addr
    'kai.leffhalm@icecube.wisc.edu': 'kleffhalm',
    'leonard.kosziol@icecube.wisc.edu': 'lkosziol',
}

REDUNDANT_ACCOUNTS = (
    # (not-being-used, being-used)
    ('leffhalm', 'kleffhalm'),
    ('kareem', 'kfarrag'),
    ('sin', 'jin'),
    ('lk000', 'lkosziol'),
    ('eellinge', 'eellinge1'),
    ('zhai', 'xuzhai'),
    ('glevin', 'genalevin'),
    ('swon', 'swon1'),
    ('pschaile', 'pschaile1'),
)

#KNOWN_UNKNOWNS = {
#    'mtakahashi@chiba-u.jp',
#    'vxw@capella2.gsfc.nasa.gov',
#    'mtakahashi@chiba-u.jp',
#    'vxw@capella2.gsfc.nasa.gov',
#    'annarita.margiotta@unibo.it',
#    'aschu@fnal.gov',
#    'javierggt@yahoo.com',
#    'matthieu.heller@gmail.com',
#    'maury.goodman@anl.gov',
#    'mcg@anl.gov',
#    'mirzoyan.razmik@gmail.com',
#    'olivomartino@gmail.com',
#    'pollmann@chiba-u.jp',
#    'smirnov@ictp.it',
#    'wjspindler@gmail.com',
#}


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
    user_from_email = {}
    for email in [e for e in mm_emails]:
        assert email not in user_from_email
        if email in known_mappings:
            user_from_email[email] = known_mappings[email]
            continue
        matches = find_user(all_users, email)
        if len(matches) == 1:
            user_from_email[email] = matches[0]
        elif len(matches) == 0:
            matches = fuzzy_find(all_users, email)
            if len(matches) == 1 and matches[0].ratio >= 85:
                user_from_email[email] = matches[0].result
            else:
                ambiguous_fuzzy.append((email, matches))
        else:  # len(matches) > 1
            raise ValueError("Ambiguous exact match", email, matches)

    email_from_user = defaultdict(list)
    for email, username in user_from_email.items():
        email_from_user[username].append(email)
    unrecognized = set(e[0] for e in ambiguous_fuzzy)
    return user_from_email, email_from_user, unrecognized


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
    mm_emails = sorted(set(email.strip().lower() for email in mm_emails))

    for email in args.skip:
        mm_emails.remove(email)

    mm_user_by_email, mm_email_by_user, mm_unrecognized \
        = build_email_mappings(mm_emails, all_users, MANUAL_EMAIL_MAP)
    for inactive, active in REDUNDANT_ACCOUNTS:
        assert inactive not in mm_email_by_user

    kc = get_rest_client()
    kc_users = set(await get_group_membership(args.group, rest_client=kc))
    for inactive, active in REDUNDANT_ACCOUNTS:
        if inactive in kc_users:
            assert active in kc_users
            kc_users.remove(inactive)

    username_by_email = {}
    for email, username in mm_user_by_email.items():
        username_by_email[email] = username
    for username in kc_users:
        sub_addr = get_sub_addr(all_users[username])
        if username_by_email.get(sub_addr) not in (None, username):
            print('AMBIGUOUS_EMAIL', username, sub_addr, username_by_email.get(sub_addr))
            print(f"{(username_by_email.get(sub_addr), username)}")
            print(f"{(username, username_by_email.get(sub_addr))}")
            assert False
        username_by_email[sub_addr] = username
    assert all(email not in mm_unrecognized for email in username_by_email)

    email_by_username = defaultdict(list)
    for

    switch_date = 'XXX'
    for email in set(list(username_by_email.keys()) + list(mm_unrecognized)):
        username = username_by_email.get(email)
        breadcrumbs = []
        paras = []
        common_intro = f"""
            {all_users.get(username,{}).get('firstName') or username or email}
            
            On {switch_date}, the IceCube Collaboration mailing list
            icecube-c@icecube.wisc.edu will undergo several important changes:
            
            (1) Membership of icecube-c@icecube will be automatically updated to
            match exactly the
            set of all active members of the IceCube experiment, as configured
            by Institution Leads on https://user-management.icecube.aq.
            
            (2) Users will be subscribed to icecube-c@icecube using their
            @icecube email address, unless overridden by "Email for Mailing Lists"
            on https://user-management.icecube.aq.
            
            (3) Message archives will be accessible to members from IceCube's 
            Google Groups page (see https://wiki.icecube.wisc.edu/index.php/Mailing_Lists#Message_Archives)
        """
        paras.append(common_intro)

        if username is None:
            assert email in mm_unrecognized
            breadcrumbs.append('user_unknown')
            user_unknown = f"""
            You are currently subscribed to icecube-c@icecube using {email}
            but we were not able to match that address to an IceCube identity.
            
            If you receive another email with instructions (sent to an email
            associated with an IceCube account), follow instructions
            in that email and ignore this one.
            
            Otherwise, contact help@icecube.wisc.edu. Failure to do so will
            result in you being unsubscribed from icecube-c@icecube.
            """
        else:
            if username in kc_users:
                breadcrumbs.append('user_unknown')
            sub_addr = get_sub_addr(all_users[username])
            primary_to_canonical_addr_change = (email.endswith('@icecube.wisc.edu')
                                    and sub_addr.endswith('@icecube.wisc.edu'))
            no_effective_address_change = ((email == sub_addr
                                       or primary_to_canonical_addr_change)
                                       and (len(email_by_username[username]) == 1
                                            or all(e.endswith('@icecube.wisc.edu')
                                                   for e in email_by_username[username])))
            if email


        print('-'*90)
        print('|', username, email)
        print('%', breadcrumbs)
        msg_parts = []
        for para in [textwrap.dedent(p) for p in paras]:
            for sub_para in para.split('\n\n'):
                text = textwrap.fill(sub_para.strip(), width=70, break_on_hyphens=False)
                msg_parts.append(text + '\n')
        msg = '\n'.join(msg_parts)
        msg = msg.replace('__', ' ')
        msg = msg.replace('\n##', '')
        msg = msg.replace('##\n', '')
        msg = msg.replace('##', '')
        msg = msg.replace('@@', '\n')
        msg = msg.replace('>>', '    ')
        print(msg)
    #for username in kc_users_not_in_mm:
    #    user = all_users[username]
    #    message = f"""
    #    {user['firstName'] or username},
    #
    #    {common_intro} As a result, you will be subscribed to {args.list}.
    #
    #    Please email help@icecube.wisc.edu if you have questions.
    #
    #    Vlad
    #    """

    #for email in mm_emails:
    #    try:
    #        username = mm_user_by_email[email]
    #        user = all_users[username]
    #    except KeyError:
    #        username = None
    #        user = {}
    #    paras = []
    #    intro = f"""
    #        {user.get('firstName') or username or 'Hello'}

    #        You are receiving this message because you are currently subscribed to
    #        the {args.list} mailing list as {', '.join(mm_email_by_user[username])}.
    #
    #        Starting on {switch_date}, membership of the mailing list {args.list} will
    #        be managed automatically based on user group memberships.
    #        """







if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
