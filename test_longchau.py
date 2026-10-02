"""
Isolated Long Châu diagnostic runner.

This file intentionally does NOT modify any production crawler code.
It runs the existing crawl_longchau() and then checks whether the
existing project-level dedupe_records() removes any Long Châu records.

Run:
    python test_longchau.py

Optional:
    python test_longchau.py https://nhathuoclongchau.com.vn/he-thong-cua-hang/ho-chi-minh

The test is intentionally limited to Long Châu so existing KFC,
Lotteria, DMX, TGDD, FPT Shop, Pharmacity and BHX crawlers are untouched.
"""

import sys

from brands.retail import crawl_longchau
from dedupe import dedupe_records


DEFAULT_URL = (
    "https://nhathuoclongchau.com.vn/he-thong-cua-hang/ho-chi-minh"
)


def print_log_lines(logs):
    print("\n" + "=" * 100)
    print("LONG CHÂU CRAWLER LOG")
    print("=" * 100)

    for line in logs:
        print(line)


def main():
    start_url = (
        sys.argv[1].rstrip("/")
        if len(sys.argv) > 1
        else DEFAULT_URL
    )

    print("=" * 100)
    print("LONG CHÂU ISOLATED TEST")
    print("=" * 100)
    print(f"URL: {start_url}")
    print()
    print("Production crawler code is NOT modified by this test.")
    print("Only the existing crawl_longchau() is executed.")
    print()

    records, pages, logs = crawl_longchau(start_url)

    print_log_lines(logs)

    print("\n" + "=" * 100)
    print("CHECKPOINT 1 - crawl_longchau()")
    print("=" * 100)
    print(f"Pages returned              : {len(pages)}")
    print(f"Records after local dedupe  : {len(records)}")

    # The existing generic app-level dedupe is intentionally tested
    # AFTER crawl_longchau(), without changing dedupe.py.
    final_records = dedupe_records(records)

    print("\n" + "=" * 100)
    print("CHECKPOINT 2 - generic dedupe_records()")
    print("=" * 100)
    print(f"Before generic dedupe       : {len(records)}")
    print(f"After generic dedupe        : {len(final_records)}")
    print(f"Records removed             : {len(records) - len(final_records)}")

    print("\n" + "=" * 100)
    print("DIAGNOSTIC INTERPRETATION")
    print("=" * 100)

    if len(records) == 506 and len(final_records) == 506:
        print("PASS: 506 records survive both Long Châu local dedupe and generic dedupe.")

    elif len(records) == 506 and len(final_records) < 506:
        print(
            "FOUND: Long Châu reaches 506 records, but generic dedupe_records() "
            "removes records."
        )
        print(
            "This is the exact case we need to inspect before changing production code."
        )

    else:
        print(
            "The result is not the expected 506-record checkpoint. "
            "Inspect the crawler logs above first."
        )

    print("\nNo files other than this test runner are changed by this diagnostic.")


if __name__ == "__main__":
    main()
