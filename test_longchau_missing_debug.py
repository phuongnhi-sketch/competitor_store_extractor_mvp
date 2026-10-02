import asyncio
import json
import re
from urllib.parse import urljoin

from playwright.async_api import async_playwright


URL = "https://nhathuoclongchau.com.vn/he-thong-cua-hang/ho-chi-minh"
API = "https://api.nhathuoclongchau.com.vn/lccus/ecom-prod/store-front/v3/order-promising/location-slug/list-shop"
BASE = "https://nhathuoclongchau.com.vn/"


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
                "request_body": body,
                "payload": payload,
            })

        page.on("response", capture)

        try:
            print("=" * 100)
            print("LONG CHAU MISSING STORE DEBUG")
            print(URL)
            print("=" * 100)

            await page.goto(
                URL,
                wait_until="domcontentloaded",
                timeout=60000,
            )
            await page.wait_for_timeout(5000)

            print("Title:", await page.title())

            for click_no in range(1, 120):
                before = len(responses)

                button = page.get_by_role(
                    "button",
                    name=re.compile(r"Xem thêm nhà thuốc", re.I),
                ).first

                if not await button.is_visible(timeout=1000):
                    break

                await button.scroll_into_view_if_needed(timeout=3000)
                await button.click(timeout=5000)

                for _ in range(40):
                    if len(responses) > before:
                        break
                    await page.wait_for_timeout(250)

                if len(responses) == before:
                    break

                await page.wait_for_timeout(500)

            print()
            print("=" * 100)
            print("API ANALYSIS")
            print("=" * 100)

            all_items = []

            for response_index, response in enumerate(responses):
                payload = response["payload"] or {}
                body = response["request_body"] or {}

                for item_index, item in enumerate(payload.get("items") or []):
                    if isinstance(item, dict):
                        all_items.append(
                            (response_index, item_index, body, item)
                        )

            api_by_code = {}

            for response_index, item_index, body, item in all_items:
                code = str(item.get("shopCode") or "").strip()
                if code:
                    api_by_code.setdefault(
                        code,
                        {
                            "response_index": response_index,
                            "item_index": item_index,
                            "request_body": body,
                            "item": item,
                        },
                    )

            total_count = None
            for response in responses:
                value = (response["payload"] or {}).get("totalCount")
                if value is not None:
                    total_count = int(value)
                    break

            print("API responses:", len(responses))
            print("API raw items:", len(all_items))
            print("API unique shopCodes:", len(api_by_code))
            print("API totalCount:", total_count)

            duplicates = {}
            for response_index, item_index, body, item in all_items:
                code = str(item.get("shopCode") or "").strip()
                if not code:
                    continue
                duplicates.setdefault(code, []).append(
                    (response_index, item_index, body)
                )

            duplicates = {
                code: rows
                for code, rows in duplicates.items()
                if len(rows) > 1
            }

            print("API duplicate shopCodes:", len(duplicates))
            for code, rows in duplicates.items():
                print(" ", code, rows)

            print()
            print("=" * 100)
            print("DOM STORE LINK ANALYSIS")
            print("=" * 100)

            # After all clicks, inspect store-detail links rendered by the
            # official page. This gives us an independent list of stores
            # that the page itself has rendered, instead of trusting only
            # the captured API pagination.
            links = await page.locator(
                "a[href*='/he-thong-cua-hang/']"
            ).evaluate_all(
                """els => els.map(a => ({
                    href: a.href,
                    text: (a.innerText || a.textContent || '').trim()
                }))"""
            )

            dom_links = []
            seen_hrefs = set()

            for link in links:
                href = str(link.get("href") or "").strip()
                if not href:
                    continue

                # Exclude the province/location page itself.
                if href.rstrip("/") == URL.rstrip("/"):
                    continue

                if href in seen_hrefs:
                    continue

                seen_hrefs.add(href)

                dom_links.append(link)

            print("DOM store links:", len(dom_links))

            for link in dom_links[:20]:
                print(
                    " ",
                    link["href"],
                    "|",
                    link["text"][:120],
                )

            api_slugs = {}

            for code, data in api_by_code.items():
                item = data["item"]
                slug = (
                    item.get("slugEcom")
                    or item.get("slug_Ecom")
                    or ""
                )

                if slug:
                    api_slugs[slug.rstrip("/")] = code

            dom_store_links = {}

            for link in dom_links:
                href = link["href"].rstrip("/")
                prefix = BASE.rstrip("/") + "/"

                if href.startswith(prefix):
                    slug = href[len(prefix):]
                    dom_store_links[slug] = link

            missing_from_dom = [
                code
                for slug, code in api_slugs.items()
                if slug.rstrip("/") not in dom_store_links
            ]

            api_not_dom_details = []

            for code in missing_from_dom:
                data = api_by_code.get(code)
                if not data:
                    continue

                item = data["item"]
                location = item.get("location") or {}

                api_not_dom_details.append({
                    "shopCode": code,
                    "shopName": item.get("shopName"),
                    "address": (
                        location.get("addressDisplay")
                        or location.get("address")
                    ),
                    "slugEcom": (
                        item.get("slugEcom")
                        or item.get("slug_Ecom")
                    ),
                })

            print()
            print("API unique stores NOT found as DOM detail links:",
                  len(api_not_dom_details))

            for row in api_not_dom_details:
                print(json.dumps(row, ensure_ascii=False))

            print()
            print("=" * 100)
            print("COUNT RECONCILIATION")
            print("=" * 100)
            print("Expected totalCount:", total_count)
            print("API unique:", len(api_by_code))
            print("DOM detail links:", len(dom_store_links))
            print("API duplicates:", len(duplicates))
            print(
                "Expected missing from API unique:",
                max((total_count or 0) - len(api_by_code), 0),
            )

            print()
            print("NOTE:")
            print(
                "If DOM detail links are close to totalCount, the missing "
                "stores can be identified by comparing DOM slugs against API slugs."
            )
            print(
                "If DOM links are also below totalCount, Long Châu itself "
                "is not rendering all stores in this session."
            )

            print()
            print("Browser stays open for 5 seconds...")
            await page.wait_for_timeout(5000)

        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
