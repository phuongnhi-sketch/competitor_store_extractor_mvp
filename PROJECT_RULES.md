# PROJECT_RULES.md

# Rules for modifying this project

## Rule 1 — DO NOT DELETE WORKING CODE
If a component is already working and the current task does not require changing it, leave it untouched.

Especially protect:
- KFC dedicated crawler
- existing retail crawlers other than the one being fixed
- working parser functions
- working load-more functions
- Streamlit brand routing
- generic dedupe logic
- custom URL routing

## Rule 2 — Make the smallest possible change
Before editing a file:
1. identify the exact function causing the problem
2. change only that function or the smallest necessary block
3. do not rewrite the whole file unless the file is genuinely corrupted and a verified stable copy is available

Avoid broad search/replace operations across `brands/retail.py`.

## Rule 3 — Never replace a working parser with a generic parser just to make a crawl return data
If records are wrong, duplicated, or incomplete:
- inspect the actual website structure
- inspect the HTML/DOM
- fix the dedicated parser/crawler
- do NOT weaken dedupe to hide the problem

## Rule 4 — Do not change dedupe to compensate for crawler errors
The project has multiple layers of dedupe.

If a crawler returns one giant page-body record or repeated records, fix the crawler/parser.

Do not remove or weaken:
- `dedupe_records_local()`
- project-level `dedupe_records()`

unless the task explicitly concerns dedupe.

## Rule 5 — MWG load-more is verified working
For Điện Máy Xanh HCM, the exact MWG load-more mechanism was tested manually through Playwright:

10 -> 20 -> 30 -> ... -> 420 -> 429

The working selector is:

`div.storeIV.storeaddress a.seemore`

The store cards use:

`li[data-id]`

Do NOT rewrite `click_mwg_store_load_more()` unless a new test proves it is broken.

## Rule 6 — MWG hierarchy rule
The national MWG locator has a hierarchy:

national locator
-> province/city locator
-> ward/commune locator

Province/city pages already load all stores through the "Xem thêm" mechanism.

Current strategy:
- crawl first-level `/tinh-...`
- crawl first-level `/thanh-pho-...`
- do NOT crawl `/xa-...`
- do NOT crawl `/phuong-...`
- do NOT crawl deeper nested geographic URLs

If this strategy needs to change, verify the live HTML/DOM first.

## Rule 7 — Do not assume a URL is valid
Before using a geographic URL in a test, verify it from the site's actual locator links.

A previous test used:
- `/ha-noi`
- `/da-nang`

These returned zero because they were not the actual current geographic URLs.

## Rule 8 — Test locally before changing GitHub again
Preferred workflow:

```powershell
git pull origin main
python -m py_compile brands\retail.py
```

Then run a direct crawler test.

Only after the direct crawler is correct should Streamlit be tested.

## Rule 9 — Preserve known-good commits
Important verified commits:
- `15f0d0235f9080984d1823a83aabf4238573293a` — Vietnamese normalization + MWG address parsing
- `39ae5f3eaecf159f0b08dbd8ac030c9faba1ab71` — repaired retail crawler file + MWG load-more
- `fc52a07f44653bc22f562a98b694356e91eb978f` — limit MWG crawler to province/city locator pages

If a future edit causes syntax corruption, restore from the latest verified stable commit rather than attempting many ad-hoc repairs.

## Rule 10 — After every meaningful code change, verify syntax
Run:

```powershell
python -m py_compile brands\retail.py
```

Do not continue to Streamlit if this fails.

## Rule 11 — Do not claim success from a single total
For store crawlers, validate at least:
- total records
- unique addresses
- duplicate count
- number of pages
- representative geographic pages
- parser correctness

A high record count alone does not prove the crawler is correct.

## Rule 12 — Keep project notes updated
When a major crawler issue is solved or a new verified behavior is discovered, update `PROJECT_NOTES.md`.

The notes should record:
- what was broken
- why it was broken
- what was changed
- what was verified
- what must not be changed casually

## Rule 13 — No unrelated refactoring
When fixing one brand:
- do not refactor all brands
- do not rename unrelated functions
- do not change the Streamlit UI
- do not change generic crawler behavior
- do not change output columns

unless the task explicitly requires it.

## Rule 14 — If unsure, inspect before editing
When the website behavior is unclear:
1. create a temporary debug script
2. inspect actual DOM/text/links
3. identify the exact selector or data structure
4. test the hypothesis
5. then make the smallest production change

## Rule 15 — Temporary debug files
Temporary files such as:
- `debug_*.py`
- `test_*.py`

are for investigation only.

Do not modify production crawler logic merely because a temporary test script succeeds. Translate the verified finding into the smallest production change.

## Golden rule

**If it already works, DO NOT TOUCH IT.**

Fix only the broken part, test it locally, and preserve everything else.
