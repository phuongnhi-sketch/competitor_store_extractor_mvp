import asyncio

from playwright.async_api import async_playwright


URL = "https://nhathuoclongchau.com.vn/he-thong-cua-hang/ho-chi-minh"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False
        )

        context = await browser.new_context(
            viewport={"width": 1440, "height": 1000},
            locale="vi-VN",
        )

        page = await context.new_page()

        try:
            print("=" * 80)
            print("OPENING")
            print(URL)
            print("=" * 80)

            await page.goto(
                URL,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            await page.wait_for_timeout(10000)

            title = await page.title()
            body = await page.locator("body").inner_text()

            print()
            print("=" * 80)
            print("RESULT")
            print("=" * 80)
            print("Title:", title)
            print("URL:", page.url)
            print("Body chars:", len(body))

            print()
            print("=" * 80)
            print("BODY PREVIEW")
            print("=" * 80)
            print(body[:5000])

            print()
            print("=" * 80)
            print("BROWSER WILL STAY OPEN FOR 15 SECONDS")
            print("=" * 80)

            await page.wait_for_timeout(15000)

        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
