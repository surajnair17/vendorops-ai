"""Run one local worker. Jobs persist across restart; uncertain deliveries never auto-retry."""

import argparse
import logging
import time

from backend.services.local_ocr import process_local_ocr_once
from backend.services.ocr import poll_ocr_once, start_ocr_once
from backend.services.workflow import process_email_once


def run_once() -> tuple[bool, bool]:
    processed = failed = False
    for task in (process_email_once, process_local_ocr_once, start_ocr_once, poll_ocr_once):
        try:
            processed = task() or processed
        except Exception as error:
            logging.getLogger("vendorops").error(
                "worker_task_failed task=%s exception_type=%s", task.__name__, type(error).__name__
            )
            failed = True
    return processed, failed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    while True:
        processed, failed = run_once()
        if args.once and failed:
            raise SystemExit("Worker tasks failed; inspect sanitized logs.")
        if args.once:
            break
        if not processed:
            time.sleep(2)


if __name__ == "__main__":
    main()
