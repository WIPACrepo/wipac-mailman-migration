#!/usr/bin/env python
import argparse
import sys
from pprint import pprint

import subprocess
import asyncio
import pickle
from krs.token import get_rest_client
from krs.users import list_users, user_info
from krs.groups import get_group_membership

from inspect import currentframe, getframeinfo
import thefuzz.fuzz
from operator import itemgetter

from collections import defaultdict
import textwrap


from email.message import EmailMessage
import smtplib

def reflow_text(text, para_sep="\n\n", **kwargs):
    """Try to make the message look nice by re-wrapping lines

    Args:
        text (str): Text to re-flow.
        para_sep (str): paragraph separator
        kwargs: kwargs to pass to textwrap.wrap

    Returns:
        Re-wrapped text
    """
    import textwrap
    # .strip() removes possible newlines if paragraphs are separated by too
    # many newlines (which otherwise would be converted to spaces and make
    # everything look weird)
    paragraphs = [para.strip() for para in text.split(para_sep)]
    wrapped_paras = [textwrap.fill(para, **kwargs) for para in paragraphs]
    return para_sep.join(wrapped_paras)

def get_sub_addr(user):
    user_attrs: dict = user['attributes']
    return (user_attrs.get('mailing_list_email') or user_attrs.get('canonical_email')
            or f"{user['username']}@icecube.wisc.edu").strip().lower()

def find_user(all_users, email):
    ret = []
    for username, userinfo in all_users.items():
        attrs = userinfo.get('attributes', {})
        emails = [e.strip().lower()
                  for e in filter(None, {userinfo.get('email'), attrs.get('canonical_email'),
                                         attrs.get('mailing_list_email'), attrs.get('author_email'),
                                         f"{username}@icecube.wisc.edu"})]
        if email.strip().lower() in emails:
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
        ratios = [thefuzz.fuzz.ratio(local_part, lp) for lp in local_parts + [full_name, slack]]
        if any(r > ratio for r in ratios):
            ret.append([username, full_name, emails, slack, ratios])
    return ret


def generate_email_mappings(all_users, mm_emails):
    email_mapping = []
    for email in [e for e in mm_emails]:
        if 'barnet' in email:
            continue
        if email == 'sin@icecube.wisc.edu':
            # It looks like this person has 2 accounts: sin and jin.
            # They are probably using jin, and that's the account that has
            # authors_email set to sin@icecube.wisc.edu
            email_mapping.append((email, 'jin'))
            continue
        if email == 'sofia.athanasiadou@icecube.wisc.edu':
            # it looks like she uses 'sofia', not sathanasiadou
            email_mapping.append((email, 'sofia'))
            continue
        if email == 'sbash1@icecube.wisc.edu':
            # not sure what is going on with this one
            # both exist in GWS. in KC only sbash, in LDAP only sbash
            # both logged in to GWS (!), but sbash more recently
            email_mapping.append((email, 'sbash'))
            continue

        matches = find_user(all_users, email)
        assert len(matches) < 2
        if matches:
            email_mapping.append((email, matches[0]))
        else:
            fuzzy_matches = fuzzy_find(all_users, email, 70)
            assert fuzzy_matches
            if len(fuzzy_matches) > 1:
                fuzzy_matches = fuzzy_find(all_users, email, 90)
                assert len(fuzzy_matches) == 1
            email_mapping.append((email, fuzzy_matches[0][0]))

    username_by_email = dict()
    for email, username in email_mapping:
        assert email not in username_by_email
        username_by_email[email] = username

    email_by_username = defaultdict(list)
    for email, username in email_mapping:
        email_by_username[username].append(email)

    return username_by_email, email_by_username

async def main():
    parser = argparse.ArgumentParser(
            description="",
            formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    args = parser.parse_args()
    pprint(args)

    mm_emails = subprocess.check_output(['ssh', 'mailman', '/usr/lib/mailman/bin/list_members', 'authors'],
                                        encoding='utf').split()
    mm_emails = [e.strip().lower() for e in mm_emails
                 if e not in ('barnet@icecube.wisc.edu',
                              'akingklemp@icecube.wisc.edu',
                              'jean.demerit@icecube.wisc.edu')]

    kc = get_rest_client()
    authors_members = await get_group_membership('/mail/authors', rest_client=kc)
    authors_gen2_members = await get_group_membership('/mail/authors-gen2', rest_client=kc)

    try:
        with open('all_users.pkl', 'rb') as f:
            all_users = pickle.load(f)
    except FileNotFoundError:
        kc = get_rest_client()
        all_users = await list_users(rest_client=kc)
        with open('all_users.pkl', 'wb') as f:
            pickle.dump(all_users, f)

    username_by_email, email_by_username = generate_email_mappings(all_users, mm_emails)

    mm_usernames = set(username_by_email[email] for email in mm_emails)

    kc_only_usernames = set(authors_members+authors_gen2_members) - mm_usernames
    kc_only_emails = [get_sub_addr(all_users[username]) for username in kc_only_usernames
                      if username not in ('akingklemp', 'jdemerit')]
    for username in kc_only_usernames:
        list_email = get_sub_addr(all_users[username])
        username_by_email[list_email] = username
        email_by_username[username].append(list_email)

    switch_date = 'Monday, June 17'
    processed_usernames = set()
    for email in mm_emails + kc_only_emails:
        username = username_by_email[email]
        if username in processed_usernames:
            print('handled-already', username)
            continue
        else:
            processed_usernames.add(username)

        user = all_users[username]
        canon = user['attributes'].get('canonical_email', '').strip().lower()
        ext = user.get('email', '').strip().lower()
        author = user['attributes'].get('author_email', '').strip().lower()
        ml = user['attributes'].get('mailing_list_email', '').strip().lower()
        default = f"{username}@icecube.wisc.edu"
        sub_addr = get_sub_addr(all_users[username])
        sub_addr_is_i3 = sub_addr.endswith('@icecube.wisc.edu')

        in_auth = username in authors_members
        in_auth_gen2 = username in authors_gen2_members
        in_both = in_auth and in_auth_gen2
        in_neither = not in_auth and not in_auth_gen2
        in_auth_only = username in authors_members and username not in authors_gen2_members
        in_auth_gen2_only = username not in authors_members and username in authors_gen2_members
        uses_ml_email = email == ml
        uses_ic_email = email == canon or email == default
        in_kc_only = email in kc_only_emails
        primary_to_canonical_addr_change = (email.endswith('@icecube.wisc.edu')
                                    and sub_addr.endswith('@icecube.wisc.edu'))
        no_effective_address_change = ((email == sub_addr
                                       or primary_to_canonical_addr_change)
                                       and (len(email_by_username[username]) == 1
                                            or all(e.endswith('@icecube.wisc.edu')
                                                   for e in email_by_username[username])))
        effective_address_change = not no_effective_address_change

        display_sub_addr = ("your @icecube email address" if sub_addr_is_i3 else sub_addr)

        multiple_emails = len(email_by_username[username]) > 1

        breadcrumbs = []
        paras = []
        intro = f"""
        {user['firstName'] or username}
        
        You are receiving this message because you are
        {'''designated as an IceCube or IceCube Gen2 author'''
        if in_kc_only else 
        f'''subscribed to authors@icecube.wisc.edu'''
        }.

        On {switch_date}, the authors@icecube.wisc.edu mailing list will undergo
        two big changes:
         
        (1) IceCube Gen2 authors will be moved from
        authors@icecube.wisc.edu into a new mailing list
        authors-gen2@icecube.wisc.edu.
        
        (2) Memberships in both mailing lists will be managed automatically
        based on authorlist designations set by institution leads."""
        paras.append(intro)

        authorlist_status = f"""
        These are your author list designations according to our records:
        ##@@>>IceCube__author:__{'yes' if in_auth else 'no'}
        @@>>IceCubeGen2__author:__{'yes' if in_auth_gen2 else 'no'}##"""
        paras.append(authorlist_status)
        if in_auth_only:
            breadcrumbs.append('in_auth_only')
            membership_change = """
            Based on this, you will remain subscribed to authors@icecube
            and won't be subscribed to authors-gen2@icecube."""
        elif in_auth_gen2_only:
            breadcrumbs.append('in_auth_gen2_only')
            membership_change = """
            Based on this, you will be to be unsubscribed from authors@icecube
            and subscribed to authors-gen2@icecube."""
        elif in_both:
            breadcrumbs.append('in_both')
            membership_change = """
            Based on this, you will remain subscribed to
            authors@icecube and will be subscribed to authors-gen2@icecube."""
        else: # not in /mail/authors[-gen2]
            breadcrumbs.append('in_neither')
            membership_change = """
            Based on this you will be unsubscribed from authors@icecube and you
            won't be subscribed to authors-gen2@icecube."""
        paras.append(membership_change)

#        if no_effective_address_change and (in_auth or in_auth_gen2):
#            breadcrumbs.append('can_skip')
#            no_change_can_skip = f"""
#            If that is correct and you want to be subscribed using {display_sub_addr},
#            then no action on your part is necessary and you can skip the rest of this
#            message.
#            """
#            paras.append(no_change_can_skip)

        how_to_change_author_status = """
        If our records are incorrect, please have your
        institution lead(s) update your author list status on
        https://user-management.icecube.aq."""
        paras.append(how_to_change_author_status)

        if effective_address_change:
            # implies currently subscribed, primary->canonical not included
            breadcrumbs.append('effective_addr_change')
            # standard_addr_required = f"""
            # The authors mailing lists will require their members to be subscribed
            # using their @icecube address, unless they have configured a non-IceCube
            # address for use with mailing lists."""
            # paras.append(standard_addr_required)

            current_sub_addr = f"""
            You are currently subscribed to authors@icecube using email
            address{' ' if len(email_by_username[username]) == 1 else 'es '}
            {', and '.join(email_by_username[username])}. """
            if in_auth or in_auth_gen2:
                breadcrumbs.append('in_Either')
                current_sub_addr_tail = f"""
                If you take no action, {display_sub_addr}
                will be used to subscribe you to the author list(s)."""
            else:
                breadcrumbs.append('in_Neither')
                current_sub_addr_tail = f"""
                If you become designated as an author,
                you will be subscribed to the appropriate list(s) using
                {display_sub_addr}."""
            paras.append(textwrap.dedent(current_sub_addr)
                         + textwrap.dedent(current_sub_addr_tail).strip())
        else:
            breadcrumbs.append('no_eff_a_c')
            if in_auth or in_auth_gen2:
                breadcrumbs.append('in_Either')
                # no effective addr change; either subscribed using the "correct" address,
                # or is author but not currently subscribed to authors@icecube
                # or subscribed using username@icecube but should be subscribed
                # using first.last@icecubes
                sub_addrs_no_change = f"""
                You will be subscribed to author list(s) using {display_sub_addr}."""
                paras.append(sub_addrs_no_change)
            else:
                breadcrumbs.append('in_Neither')
                # currently subscribed with the correct address, but not an author
                sub_addr_if_becomes_author = f"""
                If you become designated as an author, you will be subscribed to the
                appropriate
                list(s) using {display_sub_addr}."""
                paras.append(sub_addr_if_becomes_author)

        if sub_addr_is_i3:
            breadcrumbs.append('sub_addr_is_i3')
        else:
            breadcrumbs.append('sub_addr_is_ext')

        how_to_change_addr = f"""
        If you want to use a different address,
        log in to https://user-management.icecube.aq,
        change your "Email for Mailing Lists" and click "Update".
        Note that the address you choose will be used for all
        mailing lists with automated membership management."""
        paras[-1] = textwrap.dedent(paras[-1]) + textwrap.dedent(how_to_change_addr)

        epilog = """
        @@Please contact help@icecube.wisc.edu if you run into problems.
        
        Vladimir
        """
        paras.append(epilog)

        print('-'*90)
        print('|', username, email, sub_addr, email_by_username[username])
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

        try:

            external_addrs = [a for a in email_by_username[username]
                              if not a.endswith('@icecube.wisc.edu')]
            addrs = [f'{username}@icecube.wisc.edu'] + external_addrs
            #addrs = ['vbrik@icecube.wisc.edu']
            email = EmailMessage()
            email["Subject"] = "authors@icecube.wisc.edu transition instructions"
            email["From"] = "no-reply@icecube.wisc.edu"
            email["To"] = addrs
            email.set_content(msg)
            #with smtplib.SMTP('i3mail') as s:
            #    s.send_message(email)
        except Exception as exc:
            print(exc)
            print('==', username, email_by_username[username])









if __name__ == '__main__':
    sys.exit(asyncio.run(main()))

