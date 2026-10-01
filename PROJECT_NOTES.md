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

### Current first-pass code update (2026-09-30)
Commit:
- `b9d30df74e50a97578f661f711c9b6966e6e4b21`
- Message: `Update Long Chau Pharmacity and FPT nationwide locators`

Live-site findings used for this change:
- Long Châu exposes first-level province/city locator routes such as `/he-thong-cua-hang/ho-chi-minh`, `/he-thong-cua-hang/ha-noi`, and `/he-thong-cua-hang/tinh-cao-bang`; province/city pages show a store count and support `Xem thêm nhà thuốc`.
- Pharmacity exposes first-level routes such as `/he-thong-cua-hang/thanh-pho-ha-noi` and `/he-thong-cua-hang/tinh-thanh-hoa`; pages expose store lists.
- FPT Shop exposes first-level routes such as `/cua-hang/ha-noi`, `/cua-hang/hue`, and `/cua-hang/tinh-cao-bang`; pages expose store cards and `Xem thêm cửa hàng`.
- The production crawlers now use explicit first-level location URL lists when no custom URL is supplied. A supplied custom URL is still crawled by itself.
- FPT now parses province/city locator store-card text directly instead of opening every individual store detail page.

This is a FIRST-PASS implementation and is not marked verified yet. Local syntax/direct-crawler testing is required before treating these three brands as stable.

### Long Châu first test result and fix (2026-09-30)
The national URL `/he-thong-cua-hang` does not contain the store list itself. It is a locator landing page; the actual store list is exposed on first-level province/city pages such as `/he-thong-cua-hang/ho-chi-minh` and `/he-thong-cua-hang/ha-noi`. The first-pass crawler incorrectly treated the supplied national URL as the only page, producing 0 records.

Fix commit:
- `25772e89cdd3ef9556ceef6ad6179dc0f547db1e`
- Message: `Fix Long Chau national locator discovery`

The crawler now detects the national Long Châu locator root, discovers first-level location links from the live page, and then crawls those pages with the existing load-more logic. A custom province/city URL remains a single-page crawl.

Live site verification examples: Hồ Chí Minh shows 506 stores and Hà Nội shows 311 stores on their first-level locator pages. citeturn0search1turn0search2

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


### Long Châu API crawler update (2026-10-01, 10:52 GMT+7)

Production update:
- Commit: `d6fa72b107e07f33fd4af3d015d63366e50dd640`
- Message: `Fix Long Chau crawler to use store-list API`

Problem identified:
- The previous Long Châu implementation depended on clicking `Xem thêm nhà thuốc` and parsing rendered page text.
- Live network debugging showed that Long Châu actually loads store records from:
  `/lccus/ecom-prod/store-front/v3/order-promising/location-slug/list-shop`
- The API returns structured store data and pagination fields `locationSlug`, `maxResult`, `skipCount`, `totalCount`.

Production change:
- Only the Long Châu crawler section in `brands/retail.py` was changed.
- The crawler still uses the existing 34 first-level province/city paths.
- A supplied province/city custom URL is still crawled as a single location.
- Each location page is opened first, then the API is called from the Playwright browser context.
- API pagination continues until `totalCount` is reached or no more items are returned.
- Existing `dedupe_records_local()` remains unchanged.
- Existing Long Châu text parser remains in the file for compatibility/fallback.
- The existing Long Châu `click_longchau_load_more()` function was not deleted or modified outside the necessary production flow.

API mapping:
- `shopCode` -> `StoreCode`
- `shopName` -> `StoreName`
- `location.addressDisplay` -> `Address`
- `provinceName` -> `Province`
- `wardName` -> `Ward`
- `location.coordinates.latitude` -> `Lat`
- `location.coordinates.longitude` -> `Long`
- `slugEcom` -> `StoreURL`
- `SourceURL` -> current province/city locator page
- `Method` -> `Long Chau API`
- API `phone` is intentionally left blank because the live response observed during debugging returned the shop code in that field rather than a real customer phone number.

Protected / not changed:
- `crawler.py`
- `app_new.py`
- KFC crawler
- MWG crawlers
- Bách Hóa Xanh crawler
- Pharmacity crawler
- FPT Shop crawler
- generic dedupe logic
- output column structure
- custom URL routing

Verification status:
- The API structure and pagination behavior were verified from the live Long Châu network trace during debugging.
- The production code was updated directly on `main`.
- Full local `py_compile` / direct crawler execution could not be run from this environment because the runtime cannot reach GitHub to pull the updated file. Local verification remains required before marking Long Châu as STABLE.


### Long Châu Cloudflare / API lesson (2026-10-01)

Important reusable rule for future retail crawlers:

- A browser page being able to call an API does **not** mean that Python/Playwright's standalone HTTP request can call the same API.
- During Long Châu testing, the official page's real XHR POST to `https://api.nhathuoclongchau.com.vn/lccus/ecom-prod/store-front/v3/order-promising/location-slug/list-shop` returned HTTP 200.
- The same API called with `page.request.post()` returned HTTP 403 Cloudflare.
- An earlier synthetic `fetch()` from `page.evaluate()` failed with `TypeError: Failed to fetch`.
- Therefore, when a site has Cloudflare / bot protection, prefer this investigation order:
  1. Open the official page in Playwright.
  2. Use DevTools/network tracing to identify the real browser request.
  3. Let the website trigger that request itself.
  4. Capture the real response with Playwright `page.expect_response()` / response listeners.
  5. Parse the captured JSON.
  6. Only use `page.request`, `requests`, or synthetic `fetch()` if a live test proves the site accepts them.
- Do not weaken or bypass Cloudflare. The goal is to reproduce the site's normal browser flow and capture data already delivered to the page.

Long Châu production direction:
- The current crawler now opens the real Long Châu province/city page, reloads it, captures the site's own store-list XHR response, then clicks the real 'Xem thêm nhà thuốc' control and captures each subsequent XHR response.
- API JSON is parsed from those real browser responses.
- The synthetic `page.request.post()` approach is removed.
- The existing API field mapping and local dedupe are preserved.
- This approach should be reused as a pattern for other protected retail sites if they expose data through browser XHR but block synthetic HTTP requests.

Brand investigation playbook:
- MWG (THE GIOI DI DONG / DIEN MAY XANH): use verified locator-page DOM + real 'Xem thêm' flow; do not replace with synthetic API calls unless a new live test requires it.
- BÁCH HÓA XANH: verified browser-context API flow; direct HTTP requests may return 403, so keep the existing browser-session/API approach.
- LONG CHÂU: protected browser-XHR pattern above; capture the site's real requests instead of generating standalone API requests.
- FPT SHOP: current first-level locator-page/store-card parser; inspect live DOM/network again before changing it.
- PHARMACITY: current first-level locator-page + load-more parser; inspect live DOM/network again before changing it.
- KFC: separate dedicated crawler; do not change while debugging retail brands.
