import asyncio
import json
import re

from playwright.async_api import async_playwright


URL = "https://nhathuoclongchau.com.vn/he-thong/cua-hang/ho-chi-minh"
API = "https://api.nhathuoclongchau.com.vn/lccus/ecom-prod/store-front/v3/order-promising/location-slug/list-shop"


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
            print("LONG CHAU PAGINATION DEBUG")
            print(URL)
            print("=" * 100)

            await page.goto(
                URL,
                wait_until="domcontentloaded",
                timeout=60000,
            )
            await page.wait_for_timeout(5000)

            print("Title:", await page.title())
            print("URL:", page.url)

            for click_no in range(1, 120):
                before = len(responses)

                button = page.get_by_role(
                    "button",
                    name=re.compile(r"Xem thêm nhà thuốc", re.I),
                ).first

                if not await button.is_visible(timeout=1000):
                    print(f"STOP: button not visible at click {click_no}")
                    break

                await button.scroll_into_view_if_needed(timeout=3000)
                await button.click(timeout=5000)

                for _ in range(40):
                    if len(responses) > before:
                        break
                    await page.wait_for_timeout(250)

                if len(responses) == before:
                    print(f"STOP: no new API response after click {click_no}")
                    break

                response = responses[-1]
                body = response["request_body"] or {}
                payload = response["payload"] or {}
                items = payload.get("items") or []

                codes = [
                    str(item.get("shopCode") or "").strip()
                    for item in items
                    if isinstance(item, dict)
                ]

                print(
                    f"CLICK {click_no:03d} | "
                    f"skipCount={body.get('skipCount')} | "
                    f"maxResult={body.get('maxResult')} | "
                    f"items={len(items)} | "
                    f"totalCount={payload.get('totalCount')} | "
                    f"first={codes[0] if codes else ''} | "
                    f"last={codes[-1] if codes else ''}"
                )

                matches = [
                    item for item in items
                    if str(item.get("shopCode") or "").strip() == "80046"
                ]

                for item in matches:
                    location = item.get("location") or {}
                    print("  >>> FOUND 80046")
                    print("      shopName:", item.get("shopName"))
                    print("      address:", location.get("addressDisplay") or location.get("address"))
                    print("      province:", item.get("provinceName"))
                    print("      ward:", item.get("wardName"))
                    print("      slugEcom:", item.get("slugEcom"))

                await page.wait_for_timeout(500)

            print()
            print("=" * 100)
            print("SUMMARY")
            print("=" * 100)
            print("API responses:", len(responses))

            all_items = []
            for index, response in enumerate(responses):
                payload = response["payload"] or {}
                body = response["request_body"] or {}
                for item_index, item in enumerate(payload.get("items") or []):
                    if isinstance(item, dict):
                        all_items.append((index, item_index, body, item))

            occurrences = [
                x for x in all_items
                if str(x[3].get("shopCode") or "").strip() == "80046"
            ]

            print("Raw API items:", len(all_items))
            print("80046 occurrences:", len(occurrences))

            for response_index, item_index, body, item in occurrences:
                location = item.get("location") or {}
                print(
                    json.dumps(
                        {
                            "response_index": response_index,
                            "item_index": item_index,
                            "request_body": body,
                            "shopCode": item.get("shopCode"),
                            "shopName": item.get("shopName"),
                            "address": location.get("addressDisplay") or location.get("address"),
                            "province": item.get("provinceName"),
                            "ward": item.get("wardName"),
                            "slugEcom": item.get("slugEcom"),
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                )

            by_code = {}
            for response_index, item_index, body, item in all_items:
                code = str(item.get("shopCode") or "").strip()
                if code:
                    by_code.setdefault(code, []).append(
                        (response_index, item_index, body)
                    )

            duplicate_codes = {
                code: locations
                for code, locations in by_code.items()
                if len(locations) > 1
            }

            print()
            print("Duplicate shopCodes:", len(duplicate_codes))
            for code, locations in list(duplicate_codes.items())[:20]:
                print(code, locations)

            print()
            print("Browser stays open for 5 seconds...")
            await page.wait_for_timeout(5000)

        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
