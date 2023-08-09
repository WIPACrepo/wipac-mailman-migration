#!/usr/bin/env python
"""
This script imports email messages stored in the mbox format into a Google
Group's archive. Run with the --help flag for details.

This script implements parallel insertions. Officially Google Groups Migration
API doesn't support parallel insertions. Empirically, sometimes it works, other
times it doesn't work.
"""
import argparse
import logging
import mailbox
import os
import sys

from google.oauth2 import service_account
from googleapiclient import discovery
from googleapiclient.errors import HttpError, MediaUploadSizeError
from multiprocessing import Process, Queue
from pathlib import Path
from time import time, sleep, perf_counter


class WorkingDirectoryNotEmpty(Exception):
    pass


class Timer:
    """Context manager to measure execution time"""

    def __enter__(self):
        self.start = perf_counter()
        return self

    def __exit__(self, type, value, traceback):
        self.elapsed = perf_counter() - self.start

    def __str__(self):
        return str(self.elapsed)

    def __format__(self, fmt):
        return self.elapsed.__format__(fmt)


class RateLimiter:
    """Helper to rate-limit requests"""

    def __init__(self, max_rate, interval):
        """Set class parameters"""
        self.hist = []
        self.max_rate = max_rate
        self.interval = interval

    def wait_for_clearance(self):
        """Wait if rate is too high, and then register time of new request"""
        while len(self.hist) / self.interval >= self.max_rate:
            now = time()
            self.hist = [t for t in self.hist if now - t <= self.interval]
            if self.hist:
                sleep(min(self.hist) + self.interval - now)

    def register(self):
        """Register time of new request"""
        self.hist.append(time())

    def current_rate(self):
        """Report current rate"""
        return len(self.hist) / self.interval


def worker(work_q, feedback_q, ready_q, backoff_q, group, creds, delegator):
    """Read file names of an rfc822 email message from "work_q", attempt to
    insert them into Google group "group", and report result via "feedback_q".
    Repeat until None is read from "work_q".

    work_q and feedback_q are used for input and output with the manager process.

    ready_q and backoff_q are used for scheduling by the manager process.

    Args:
        work_q (Queue): source of file names of messages to insert (read-only).
        feedback_q (Queue): report whether insertion was successful (write-only).
        ready_q (Queue): indicate we are waiting to read from work_q (read-write).
        backoff_q (Queue): indicate we are retrying an insert (read-write).
        group (str): name of the group where to insert messages.
        creds (str): file name of JSON with service account credentials.
        delegator (str): email address of account to impersonate.
    """
    credentials = service_account.Credentials.from_service_account_file(
        creds,
        scopes=["https://www.googleapis.com/auth/apps.groups.migration"],
        subject=delegator,
    )
    service = discovery.build("groupsmigration", "v1", credentials=credentials, cache_discovery=False)
    archive = service.archive()
    pid = os.getpid()

    while True:
        ready_q.put(True)
        msg_file = work_q.get()
        ready_q.get()
        if msg_file is None:
            return
        try:
            req = archive.insert(groupId=group, media_body=msg_file, media_mime_type="message/rfc822")
        except MediaUploadSizeError:
            logging.info(f"{pid} {msg_file} is bigger than maximum allowed size")
            feedback_q.put((False, msg_file))
            continue
        except Exception as e:
            logging.info(f"{pid} caught exception while creating request {repr(e)}")
            feedback_q.put((False, msg_file))
            continue

        num_retries = 0
        max_retries = 5
        while True:
            sleep(2**num_retries - 1)
            try:
                with Timer() as timer:
                    res = req.execute()
            except HttpError as e:
                logging.info(f"{pid} caught HttpError {repr(e)}")
                if e.status_code == 503:
                    perform_retry = True
                    import_success = False
                else:
                    perform_retry = False
                    import_success = False
            except Exception as e:
                logging.info(f"{pid} caught exception while executing request {repr(e)}")
                perform_retry = False
                import_success = False
            else:
                if res["responseCode"] == "SUCCESS":
                    logging.debug(f"{pid} inserted {msg_file} in {timer:.2f}s {num_retries} retries")
                    perform_retry = False
                    import_success = True
                else:
                    logging.info(f"{pid} failed to insert {msg_file} {res}")
                    perform_retry = True
                    import_success = False

            if perform_retry:
                num_retries += 1
                if num_retries == 1:
                    backoff_q.put(True)
                if num_retries <= max_retries:
                    continue
                else:
                    logging.info(f"{pid} giving up on {msg_file} after {num_retries} attempts")
                    backoff_q.get()
                    feedback_q.put((import_success, msg_file))
                    break
            else:
                if num_retries:
                    backoff_q.get()
                feedback_q.put((import_success, msg_file))
                break


def unpack_mbox(mbox_path, workdir_path):
    """Save all messages in mbox mailbox under mbox_path as separate file in workdir_path"""
    workdir = Path(workdir_path)
    workdir.mkdir(exist_ok=True)
    if list(workdir.iterdir()):
        raise WorkingDirectoryNotEmpty

    mbox = mailbox.mbox(mbox_path)
    for key in mbox.iterkeys():
        msg_file = workdir / str(key)
        msg_file.write_bytes(mbox.get_bytes(key))


def main():
    parser = argparse.ArgumentParser(
        description=(
            "%(prog)s is a utility to import email messagges from a mailbox\n"
            "in mbox format into a Google Group archive."
        ),
        epilog=(
            "Notes:\n"
            "[1] The service account needs to be set up for domain-wide delegation.\n"
            "[2] The delegator account needs to have a Google Workspace admin role.\n"
            "[3] Officially, parallel insertions are not supported. However, sometimes\n"
            "    using multiple workers results in significant peformance improvement.\n"
            "\nAlso note that importing the same message (same Message-ID) multiple\n"
            "times will not result in duplicates."
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--sa-creds",
        metavar="PATH",
        required=True,
        help="service account credentials JSON¹",
    )
    parser.add_argument(
        "--sa-delegator",
        metavar="EMAIL",
        required=True,
        help="the principal whom the service account\n        will impersonate²",
    )
    parser.add_argument(
        "--src-mbox",
        metavar="PATH",
        required=True,
        help="source email archive in mbox format",
    )
    parser.add_argument(
        "--dst-group",
        metavar="EMAIL",
        required=True,
        help="destination group ID",
    )
    parser.add_argument(
        "--work-dir",
        metavar="PATH",
        default="./workdir",
        help="storage for unpacked mailbox (default: ./workdir)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="resume using previously unpacked mailbox",
    )
    parser.add_argument(
        "--num-workers",
        metavar="NUM",
        default=1,
        type=int,
        help="number of workers³ (default: 1)",
    )
    parser.add_argument(
        "--log-level",
        default="info",
        choices=("debug", "info", "warning", "error"),
        help="logging level (default: info)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)-23s %(levelname)s %(message)s",
    )

    if args.resume:
        logging.info("ignoring --src-mbox because --resume is specified")
    else:
        try:
            unpack_mbox(args.src_mbox, args.work_dir)
        except WorkingDirectoryNotEmpty:
            parser.exit(1, "Error: working directory is not empty but --resume not given")
    msg_files = [str(f) for f in Path(args.work_dir).iterdir()]
    total_files = len(msg_files)
    processed_files = 0
    logging.info(f"{total_files} messages to work on")

    work_q = Queue()  # message file names for workers to work on (input)
    feedback_q = Queue()  # message file names from workers after they've been imported
    ready_q = Queue()  # qlen is the number of workers ready and waiting for work
    backoff_q = Queue()  # qlen is the number of workers retransmitting and backing off

    args1 = (work_q, feedback_q, ready_q, backoff_q)
    args2 = (args.dst_group, args.sa_creds, args.sa_delegator)
    procs = [Process(target=worker, args=args1 + args2) for i in range(args.num_workers)]
    [p.start() for p in procs]

    MAX_REQ_RATE = 10  # Officially Google Group Migration API calls are limited to 10/s
    ratelimiter = RateLimiter(MAX_REQ_RATE, 1)
    while True:
        if msg_files and ready_q.qsize() and work_q.empty() and backoff_q.empty():
            ratelimiter.wait_for_clearance()
            ratelimiter.register()
            work_q.put(str(msg_files.pop(0)))
        while feedback_q.qsize():
            success, done_msg_file = feedback_q.get()
            if success:
                Path(done_msg_file).unlink()
            processed_files += 1
        if processed_files == total_files:
            break
        sleep(0.01)

    [work_q.put(None) for p in procs]
    [p.join() for p in procs]


if __name__ == "__main__":
    sys.exit(main())
