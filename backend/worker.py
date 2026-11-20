"""Run one local worker. Jobs persist across restart; uncertain deliveries never auto-retry."""
import argparse
import time

from backend.services.workflow import process_email_once


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    while True:
        processed = process_email_once()
        if args.once:
            break
        if not processed:
            time.sleep(2)


if __name__ == "__main__":
    main()
