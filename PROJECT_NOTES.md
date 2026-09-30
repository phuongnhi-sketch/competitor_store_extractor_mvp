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

### Current status (2026-09-30)
- THE GIOI DI DONG: STABLE / VERIFIED.
- DIEN MAY XANH: STABLE / VERIFIED.
- Do not modify the verified MWG load-more, hierarchy filtering, or parser unless a new issue is explicitly demonstrated.

The MWG crawler is in `brands/retail.py`.

Important functions:
- `click_mwg_store_load_more()`
- `_crawl_mwg_brand()`
- `parse_mwg_locator_text()`
- `extract_mwg_address_from_store_line()`
- `crawl_thegioididong()`
- `crawl_dienmayxanh()`

Verified behavior:
- Province/city locator pages are crawled.
- Lower-level `/xa-` and `/phuong-` pages are intentionally excluded.
- MWG load-more uses the verified `div.storeIV.storeaddress a.seemore` mechanism.
- Vietnamese `đ/Đ` normalization is preserved.

Important verified commits:
- `15f0d0235f9080984d1823a83aabf4238573293a`
- `39ae5f3eaecf159f0b08dbd8ac030c9faba1ab71`
- `fc52a07f44653bc22f562a98b694356e91eb978f`
- `58f8a87337f28d42ba89d4f5fba4dbe04fbc7dfc`
- `0f5464ae4ae3a41268be2650e420364bcfedc099`

## 4. BÁCH HÓA XANH — VERIFIED

### Current status (2026-09-30)
Bách Hóa Xanh is now working with a dedicated nationwide API crawler.

Production commit:
- `fd195268b2a5b6b6fdd0e5f6e05ad283734d3424`
- Message: `Update BHX crawler to nationwide API`

### Verified API behavior
BHX exposes store data through browser-accessible APIs:
- `/gw/LocationV3/GetFull` -> province / ward hierarchy
- `/gw/Location/V2/GetStoresByLocation` -> store details by province

Direct HTTP requests can return HTTP 403, so production calls are made from the Playwright browser context.

The production flow:
1. Open BHX locator page to establish the browser session.
2. Call GetFull.
3. Build ward ID -> ward name lookup.
4. Call GetStoresByLocation for every province with `wardId=0`.
5. Paginate until the province total is reached.
6. Deduplicate by store ID.
7. Apply existing local dedupe.

Verified examples during investigation:
- Ho Chi Minh City: `total = 1104`
- Thành phố Bắc Ninh: `total = 91`

The crawler maps:
- storeId -> StoreCode
- storeLocation -> StoreName
- storeAddress -> Address
- province name -> Province
- wardId -> Ward
- lat -> Lat
- lng -> Long
- Method -> `Bach Hoa Xanh API`

Do not replace this API crawler with the old locator-text parser or generic click-load-more logic unless a new live test proves the API is no longer valid.

## 5. Current retail development status

### Stable / verified
- THE GIOI DI DONG
- DIEN MAY XANH
- BACH HOA XANH
- KFC (separate crawler)

### Next brands to inspect and repair
1. NHA THUOC LONG CHAU
2. PHARMACITY
3. FPT SHOP

For each brand:
1. Read current production code from GitHub.
2. Inspect the live official locator page and network/API behavior.
3. Identify the smallest broken part.
4. Test the dedicated crawler directly.
5. Validate total records, unique addresses, duplicates, pages, and representative locations.
6. Only then update GitHub.

Do not modify stable brands while working on another brand.

## 6. Testing philosophy
Always test in this order:
1. Python syntax
2. direct dedicated crawler
3. parser/load-more/API behavior
4. dedupe behavior
5. Streamlit
6. only then push additional changes if needed

Do not weaken generic dedupe to compensate for bad parsing/crawling.

## 7. Important project rules
- DO NOT DELETE WORKING CODE.
- Make the smallest possible change.
- Do not replace a working parser with a generic parser just to make a crawl return data.
- Do not change dedupe to compensate for crawler errors.
- Do not refactor unrelated brands.
- Do not change KFC while working on retail brands.
- If unsure, inspect the actual DOM/API first.
- Test locally before changing GitHub.
- Run `python -m py_compile brands\\retail.py` after every production change.
- Golden rule: **If it already works, DO NOT TOUCH IT.**
