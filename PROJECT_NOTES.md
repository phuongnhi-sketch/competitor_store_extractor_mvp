# PROJECT_NOTES.md

## 1. Project
Competitor Store Extractor MVP — Streamlit app for extracting competitor store locations from official websites.

Repository:
- GitHub: phuongnhi-sketch/competitor_store_extractor_mvp
- Main UI: `app_new.py`
- Generic crawler: `crawler.py`
- Retail dedicated crawlers: `brands/retail.py`
- Shared helpers/config: `common.py`
- Deduplication: `dedupe.py`

## 2. Current target retail brands
- THE GIOI DI DONG
- DIEN MAY XANH
- FPT SHOP
- NHA THUOC LONG CHAU
- PHARMACITY
- BACH HOA XANH

KFC has a separate dedicated crawler and should not be changed while working on the retail crawlers unless the task explicitly concerns KFC.

## 3. Current MWG work: THE GIOI DI DONG + DIEN MAY XANH

The MWG crawler is in `brands/retail.py`.

Important functions:
- `click_mwg_store_load_more()`
- `_crawl_mwg_brand()`
- `parse_mwg_locator_text()`
- `extract_mwg_address_from_store_line()`
- `crawl_thegioididong()`
- `crawl_dienmayxanh()`

### Verified MWG page behavior
The Điện Máy Xanh locator exposes store cards like:

`Điện máy Xanh 137 Quốc Lộ 13, Phường Hiệp Bình, Thành phố Hồ Chí Minh, Việt Nam - Xem bản đồ`

The store list uses:
- `div.storeIV.storeaddress`
- `li[data-id]`
- `a.seemore`
- `data-total`
- JavaScript handler similar to `GetMoreStore(...)`

### Verified load-more behavior
For HCM:

Initial:
- 10 store cards
- `data-total="419"`

After repeated clicks:
- 10, 20, 30, ...
- 420
- final: **429**

Final test result:
`FINAL STORE COUNT = 429`

Therefore `click_mwg_store_load_more()` is currently WORKING and must not be rewritten casually.

### Verified parser behavior
A direct parser test for:

`Điện máy Xanh 137 Quốc Lộ 13, Phường Hiệp Bình, Thành phố Hồ Chí Minh, Việt Nam - Xem bản đồ`

returns one valid record with:
- Brand = DIEN MAY XANH
- StoreName = Điện máy Xanh
- Address = 137 Quốc Lộ 13, Phường Hiệp Bình, Thành phố Hồ Chí Minh, Việt Nam

Vietnamese `đ/Đ` normalization was explicitly fixed in `normalize_text()`.

### Previous crawler result before current hierarchy fix
From the national locator:
- 34 geographic links
- 35 pages total
- 2,043 records
- 2,043 unique addresses
- 0 duplicate addresses

This proved the parser was producing distinct addresses, but the crawler was following too deep into the geographic hierarchy.

### Root cause discovered
The national MWG locator contains a hierarchy:

main locator
-> province/city pages
-> lower-level ward/commune pages

The province/city page itself can load all stores with the MWG "Xem thêm" button.

Example HCM:
- direct HCM page = 429 stores after load-more
- the old crawler followed 167 lower-level geographic links and only produced 240 records for that direct HCM crawl

Therefore the crawler should NOT crawl all `/xa-` and `/phuong-` pages.

### Current code change
Commit:
`fc52a07f44653bc22f562a98b694356e91eb978f`

Message:
`Limit MWG crawler to province and city locator pages`

The current `_crawl_mwg_brand()` follows only first-level geographic links from the national locator:
- `/tinh-...`
- `/thanh-pho-...`

It deliberately excludes:
- `/xa-...`
- `/phuong-...`
- deeper nested paths

The load-more function and parser were left unchanged.

### TGDD test finding
The first direct test of `crawl_thegioididong()` returned only 4 records and 0 geographic locator links.

Root cause:
- The current TGDD national URL can redirect/use the canonical locator root: `/sieu-thi-the-gioi-di-dong`
- Geographic province/city pages are under: `/sieu-thi-the-gioi-di-dong/<province-or-city>`
- The shared MWG crawler was deriving the geographic root from the opened URL, which did not match the canonical TGDD link root.

Fix:
- Commit `b8cf3afb0a648e22f597d2ed3e0cb821f4d2ac08`
- Message: `Fix TGDD locator root in MWG crawler`
- For `THE GIOI DI DONG`, the crawler now explicitly uses `/sieu-thi-the-gioi-di-dong` as the locator root.
- DMX logic remains unchanged.

Next:
- Pull this commit locally.
- Run syntax check.
- Re-test TGDD direct crawler.
- If direct crawler is correct, test TGDD in Streamlit.
- Then apply the same inspect -> minimally fix -> direct test -> Streamlit test workflow to FPT Shop, Long Châu, Pharmacity, and Bách Hóa Xanh.

## 4. Next test after pulling
Do NOT run Streamlit first.

Run:

```powershell
git pull origin main
python -m py_compile brands\retail.py
```

Then test:

```powershell
python -c "import asyncio; from brands.retail import crawl_dienmayxanh; r=asyncio.run(crawl_dienmayxanh('https://www.dienmayxanh.com/he-thong-sieu-thi-dien-may')); print('RECORDS=',len(r[0])); print('PAGES=',len(r[1])); print('\\n'.join(r[2]))"
```

Expected direction:
- geographic pages should be around the first-level province/city count, not hundreds of ward pages
- each province/city page should use MWG load-more
- total records should move substantially above the old 2,043 result

The exact final total must be verified from the live site; do not invent an expected number.

## 5. Important project history
There were previous accidental structural corruptions of `brands/retail.py` caused by partial/manual edits. The file was restored from a stable commit before reapplying the MWG parser changes.

Because of that history, protect the existing working code and make small, targeted changes only.

## 6. Other known working pieces
- Retail domain detection was added to `crawler.py` for the six target retail brands.
- Streamlit correctly dispatches these brands to dedicated retail crawlers.
- KFC uses its separate dedicated crawler.
- Lotteria custom URL routing was previously fixed; do not change unrelated routing while working on MWG.

## 7. Testing philosophy
Always test in this order:
1. Python syntax
2. direct dedicated crawler
3. parser/load-more behavior
4. dedupe behavior
5. Streamlit
6. only then push additional changes if needed

Do not weaken generic dedupe to compensate for bad parsing/crawling. Fix the source parser/crawler instead.
