#!/usr/bin/env python
"""
Save in a python pickle file settings and members of a mailman mailing list.

This needs to work with python2.7.
"""
import argparse
import pickle
import subprocess
import sys


def popen_stdout(args):
    p = subprocess.Popen(args, stdout=subprocess.PIPE)
    stdout, stderr = p.communicate()
    return stdout


def main():
    parser = argparse.ArgumentParser(
        description="Save in EMAIL.pkl (python pickle) the settings and members of a "
        "mailman mailing list.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--list", metavar="EMAIL", required=True, help="list email")
    parser.add_argument(
        "--bin-dir",
        metavar="PATH",
        default="/usr/lib/mailman/bin/",
        help="mailman bin directory",
    )
    args = parser.parse_args()

    if "@" not in args.list:
        parser.error("The list argument doesn't look like an email address")

    cfg = {"email": args.list}
    listname = args.list.split("@")[0]

    stdout = popen_stdout([args.bin_dir + "/config_list", "-o", "-", listname])
    exec(stdout, None, cfg)

    stdout = popen_stdout([args.bin_dir + "/list_members", "--digest", listname])
    cfg["digest_members"] = [
        l.strip().decode("ascii") for l in stdout.split("\n") if l.strip()
    ]

    stdout = popen_stdout([args.bin_dir + "/list_members", "--regular", listname])
    cfg["regular_members"] = [
        l.strip().decode("ascii") for l in stdout.split("\n") if l.strip()
    ]

    pickle.dump(cfg, open(args.list + ".pkl", "wb"))


if __name__ == "__main__":
    sys.exit(main())
