# PENDING_HANDOVER.md

# Long Châu — Pending / Handover
Updated: 2026-10-02

## 1. Current problem

The Hồ Chí Minh Long Châu locator reports 506 stores.

Observed browser pagination:
- maxResult = 5
- skipCount = 5, 10, 15, ... , 505
- totalCount = 506
- 101 API responses
- 501 raw API items
- 499 unique shopCodes
- 2 duplicate shopCodes were observed across pagination batches

The current production/test result can therefore end at 504 records when the initial 5 DOM records are combined with the 499 unique API records.

Do NOT treat 506 - 499 = 7 as seven missing stores. The first 5 stores are already rendered in the page before the captured API pagination starts at skipCount=5.

## 2. What has already been fixed

Long Châu Cloudflare/session issue:
- Headed Chromium is required in the current environment.
- A fresh browser context is used per location in production.
- The production collector captures the real browser XHR instead of using synthetic page.request.post() or page.evaluate(fetch()).
- These approaches were verified because standalone requests triggered Cloudflare while the site's real browser XHR returned HTTP 200.

Production code is NOT being changed during the current missing-record investigation.

## 3. Debug files

Run these only for Long Châu investigation:

### test_longchau_pagination_debug.py
Purpose:
- Capture request body
- Capture skipCount/maxResult
- Capture response item counts
- Detect duplicate shopCodes
- Confirm pagination sequence

Known result:
- Sequential skipCount is correct.
- Overlap exists between adjacent API batches.

### test_longchau_missing_debug.py
Purpose:
- Tried comparing API slugs with rendered DOM links.

Known limitation:
- DOM store links returned 0.
- This test cannot identify the missing stores.
- Do not use its 499 API-not-DOM result as a missing-store count.

### test_longchau_reconcile.py
Commit:
28cc2e086927b9c28edc1f4e19587d911a1c8276

This is the CURRENT test to run.

It:
1. Parses the initial page with the existing parse_longchau_text().
2. Captures real browser XHR responses during Xem thêm nhà thuốc.
3. Parses the final page body after all clicks.
4. Compares API and DOM parser stores by normalized address.
5. Prints API-only stores.
6. Prints DOM-only stores.
7. Checks whether the initial 5 DOM records overlap with API records.

## 4. What the next person must do

Run:

python test_longchau_reconcile.py

Then record these values:
- Initial DOM parser records
- Final DOM parser records
- API raw items
- API unique shopCodes
- API unique addresses
- API totalCount
- API-only stores
- DOM-only stores
- Initial DOM addresses also in API

### Decision logic

A. If Final DOM parser records = 506:
- The page itself has all 506.
- Use DOM/API comparison to identify which 2 are missing from API pagination.
- Investigate the exact pagination overlap causing those records to be skipped.

B. If Final DOM parser records = 504:
- The page itself also exposes only 504 through the current click session.
- Investigate whether the Long Châu API pagination is itself inconsistent or whether the website's totalCount is stale.

C. If Final DOM parser records is another number:
- Do not patch production yet.
- Compare that number against API unique count and totalCount first.

## 5. Production change that may eventually be needed

Do NOT implement this until the test proves the cause.

Potential solutions, depending on evidence:
- Continue pagination using the site's returned pagination state instead of assuming each click produces a clean non-overlapping batch.
- If the browser API consistently overlaps records, collect all browser responses and reconcile by shopCode.
- If the website exposes missing records in the final DOM but not in captured XHR, use the page's rendered data only if it can be parsed reliably.
- Never add fake/manual store records just to make the count equal 506.

## 6. Files that must not be changed for this issue

Unless a separate issue is found:
- dedupe.py
- crawler.py
- app_new.py
- KFC crawler
- MWG crawlers
- Bách Hóa Xanh crawler
- Pharmacity crawler
- FPT Shop crawler
- generic crawler

## 7. Final verification after production fix

Run:

python -m py_compile brands\retail.py

Then run the direct Long Châu HCMC crawler.

Verify:
- Store count
- Unique StoreCode count
- Duplicate StoreCode count
- StoreCode completeness
- Address completeness
- Province/Ward
- Lat/Long
- StoreURL
- SourceURL
- Method = Long Chau API

Only after the direct crawler is correct:
- test Streamlit
- test the national Long Châu URL
- test at least one other province/city

## 8. Golden rule

Do not modify working code before the missing-store root cause is proven.
