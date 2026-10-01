import asyncio

from playwright.async_api import async_playwright

from brands.retail import (
    LONGCHAU_STORE_API,
    collect_longchau_api_items,
    safe_goto,
)


URLS = [
    "https://nhathuoclongchau.com.vn/he-thong-cua-hang/ha-noi",
    "https://nhathuoclongchau.com.vn/he-thong-cua-hang/hai-phong",
    "https://nhathuoclongchau.com.vn/he-thong-cua-hang/hue",
]


async def test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)

        context = await browser.new_context(
            viewport={"width": 1440, "height": 1000},
            locale="vi-VN",
        )

        page = await context.new_page()

        try:
            for index, url in enumerate(URLS, start=1):
                print()
                print("=" * 80)
                print(f"LOCATION {index}/3")
                print(url)
                print("=" * 80)

                api_responses = []

                def capture_response(response):
                    try:
                        if (
                            response.request.method == "POST"
                            and response.url.split("?", 1)[0]
                            == LONGCHAU_STORE_API
                        ):
                            api_responses.append(response.status)
                    except Exception:
                        pass

                page.on("response", capture_response)

                try:
                    ok = await safe_goto(
                        page,
                        url,
                        wait_ms=3500,
                    )

                    title = await page.title()
                    body = await page.locator("body").inner_text()

                    print(f"Open OK       : {ok}")
                    print(f"Final URL     : {page.url}")
                    print(f"Title         : {title}")
                    print(f"Body chars    : {len(body)}")
                    print(
                        "More button   : "
                        f"{await page.get_by_text('Xem thêm nhà thuốc', exact=True).count()}"
                    )

                    print(f"API responses : {len(api_responses)}")
                    print(f"API statuses  : {api_responses[:10]}")

                    if ok and "Cloudflare" not in title:
                        payloads, duplicates = (
                            await collect_longchau_api_items(
                                page,
                                max_clicks=200,
                            )
                        )

                        item_count = sum(
                            len(payload.get("items") or [])
                            for payload in payloads
                        )

                        total_count = (
                            payloads[0].get("totalCount")
                            if payloads
                            else None
                        )

                        print(f"API pages     : {len(payloads)}")
                        print(f"API items     : {item_count}")
                        print(f"API total     : {total_count}")
                        print(
                            "Duplicates    : "
                            f"{duplicates[:10] if duplicates else 'none'}"
                        )
                    else:
                        print("API test      : SKIPPED (page is blocked)")

                except Exception as e:
                    print(
                        f"ERROR         : "
                        f"{type(e).__name__}: {e}"
                    )

                finally:
                    page.remove_listener(
                        "response",
                        capture_response,
                    )

                print()
                print("Waiting 5 seconds before next location...")
                await page.wait_for_timeout(5000)

        finally:
            await page.close()
            await context.close()
            await browser.close()


if __name__ == "__main__":
    asyncio.run(test())
