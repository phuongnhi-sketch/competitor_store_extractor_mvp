import asyncio
import json
import re

from playwright.async_api import async_playwright

from brands.retail import parse_longchau_text, normalize_text, clean_text


URL = "https://nhathuoclongchau.com.vn/he-thong-cua-hang/ho-chi-minh"
API = (
    "https://api.nhathuoclongchau.com.vn/"
    "lccus/ecom-prod/store-front/v3/"
    "order-promising/location-slug/list-shop"
)


def norm_address(value):
    value = normalize_text(value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def api_item_to_row(item):
    location = item.get("location") or {}
    return {
        "shopCode": clean_text(item.get("shopCode") or ""),
        "shopName": clean_text(item.get("shopName") or ""),
        "address": clean_text(
            location.get("addressDisplay")
            or location.get("address")
            or ""
        ),
        "slugEcom": clean_text(
            item.get("slugEcom")
            or item.get("slug_Ecom")
            or ""
        ),
    }


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            viewport={"width": 1440, "height": 1000},
            locale="vi-VN",
        )
        page = await context.new_page()

        responses = []

        async def capture(response):
            if response.request.method != "POST":
                return
            if response.url.split("?", 1)[0] != API:
                return

            try:
                payload = await response.json()
            except Exception:
                return

            try:
                body = response.request.post_data_json
            except Exception:
                body = None

            responses.append({
                "body": body,
                "payload": payload,
            })

        page.on("response", capture)

        try:
            print("=" * 100)
            print("LONG CHAU FINAL RECONCILIATION DEBUG")
            print(URL)
            print("=" * 100)

            await page.goto(
                URL,
                wait_until="domcontentloaded",
                timeout=60000,
            )
            await page.wait_for_timeout(5000)

            initial_body = await page.locator("body").inner_text()
            initial_records = parse_longchau_text(
                initial_body,
                URL,
            )

            print("Initial parser records:", len(initial_records))
            for row in initial_records:
                print(
                    " INITIAL |",
                    row.get("Address", ""),
                )

            for click_no in range(1, 120):
                before = len(responses)

                button = page.get_by_role(
                    "button",
                    name=re.compile(r"Xem thêm nhà thuốc", re.I),
                ).first

                if not await button.is_visible(timeout=1000):
                    print("STOP: button not visible at click", click_no)
                    break

                await button.scroll_into_view_if_needed(timeout=3000)
                await button.click(timeout=5000)

                for _ in range(40):
                    if len(responses) > before:
                        break
                    await page.wait_for_timeout(250)

                if len(responses) == before:
                    print("STOP: no new API response at click", click_no)
                    break

                await page.wait_for_timeout(500)

            final_body = await page.locator("body").inner_text()
            final_records = parse_longchau_text(
                final_body,
                URL,
            )

            all_items = []
            for response_index, response in enumerate(responses):
                payload = response["payload"] or {}
                body = response["body"] or {}

                for item_index, item in enumerate(
                    payload.get("items") or []
                ):
                    if isinstance(item, dict):
                        all_items.append(
                            (response_index, item_index, body, item)
                        )

            api_by_code = {}
            for response_index, item_index, body, item in all_items:
                code = clean_text(item.get("shopCode") or "")
                if code:
                    api_by_code.setdefault(
                        code,
                        api_item_to_row(item),
                    )

            total_count = None
            for response in responses:
                value = (response["payload"] or {}).get("totalCount")
                if value is not None:
                    total_count = int(value)
                    break

            api_rows = list(api_by_code.values())

            # API can contain duplicate/overlapping pages. Compare by
            # normalized address so the parser and API can be reconciled
            # even though parse_longchau_text does not have shopCode.
            api_by_address = {}
            for row in api_rows:
                key = norm_address(row["address"])
                if key:
                    api_by_address.setdefault(key, []).append(row)

            dom_rows = []
            seen_dom_addresses = set()
            for row in final_records:
                address = clean_text(row.get("Address", ""))
                key = norm_address(address)
                if not key or key in seen_dom_addresses:
                    continue
                seen_dom_addresses.add(key)
                dom_rows.append({
                    "address": address,
                    "storeName": clean_text(row.get("StoreName", "")),
                })

            dom_by_address = {
                norm_address(row["address"]): row
                for row in dom_rows
            }

            api_only = []
            for key, rows in api_by_address.items():
                if key not in dom_by_address:
                    api_only.extend(rows)

            dom_only = []
            for key, row in dom_by_address.items():
                if key not in api_by_address:
                    dom_only.append(row)

            print()
            print("=" * 100)
            print("RECONCILIATION")
            print("=" * 100)
            print("API responses:", len(responses))
            print("API raw items:", len(all_items))
            print("API unique shopCodes:", len(api_rows))
            print("API unique addresses:", len(api_by_address))
            print("API totalCount:", total_count)
            print("Initial DOM parser records:", len(initial_records))
            print("Final DOM parser records:", len(final_records))
            print("Final DOM unique addresses:", len(dom_by_address))
            print("API-only stores:", len(api_only))
            print("DOM-only stores:", len(dom_only))

            print()
            print("=" * 100)
            print("API-ONLY STORES")
            print("=" * 100)
            if not api_only:
                print("NONE")
            else:
                for row in api_only:
                    print(json.dumps(row, ensure_ascii=False))

            print()
            print("=" * 100)
            print("DOM-ONLY STORES")
            print("=" * 100)
            if not dom_only:
                print("NONE")
            else:
                for row in dom_only:
                    print(json.dumps(row, ensure_ascii=False))

            print()
            print("=" * 100)
            print("INITIAL DOM VS API")
            print("=" * 100)

            initial_keys = {
                norm_address(row.get("Address", ""))
                for row in initial_records
                if row.get("Address")
            }

            initial_in_api = sum(
                1 for key in initial_keys
                if key in api_by_address
            )

            print("Initial DOM addresses:", len(initial_keys))
            print("Initial DOM addresses also in API:", initial_in_api)
            print(
                "Expected total if initial DOM + API unique are disjoint:",
                len(initial_keys) + len(api_rows),
            )

            print()
            print("Browser stays open for 5 seconds...")
            await page.wait_for_timeout(5000)

        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
