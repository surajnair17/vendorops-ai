"""Run one local worker. Jobs persist across restart; uncertain deliveries never auto-retry."""

import argparse
import logging
import time

from backend.services.local_ocr import process_local_ocr_once
from backend.services.ocr import poll_ocr_once, start_ocr_once
from backend.services.workflow import process_email_once


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    while True:
        try:
            processed = process_email_once()
            processed = process_local_ocr_once() or processed
            processed = start_ocr_once() or processed
            processed = poll_ocr_once() or processed
        except Exception as error:
            logging.getLogger("vendorops").error(
                "worker_failed exception_type=%s", type(error).__name__
            )
            if args.once:
                raise
            time.sleep(2)
            continue
        if args.once:
            break
        if not processed:
            time.sleep(2)


if __name__ == "__main__":
    main()
