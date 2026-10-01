import asyncio

from playwright.async_api import async_playwright

from brands.retail import safe_goto


URLS = [
    ("Hà Nội", "https://nhathuoclongchau.com.vn/he-thong-cua-hang/ha-noi"),
    ("Hải Phòng", "https://nhathuoclongchau.com.vn/he-thong-cua-hang/hai-phong"),
    ("Huế", "https://nhathuoclongchau.com.vn/he-thong-cua-hang/hue"),
]


async def inspect_page(page, name, url):
    print()
    print(f"--- {name} ---")
    print(url)

    try:
        ok = await safe_goto(
            page,
            url,
            wait_ms=3500,
        )

        title = await page.title()
        body = await page.locator("body").inner_text()

        blocked = "Cloudflare" in title or "Attention Required" in title

        print(f"Open OK    : {ok}")
        print(f"Final URL  : {page.url}")
        print(f"Title      : {title}")
        print(f"Body chars : {len(body)}")
        print(
            "More button: "
            f"{await page.get_by_text('Xem thêm nhà thuốc', exact=True).count()}"
        )
        print(f"STATUS     : {'CF' if blocked else 'PASS'}")

    except Exception as e:
        print(f"ERROR      : {type(e).__name__}: {e}")
        print("STATUS     : ERROR")


async def new_context(browser):
    return await browser.new_context(
        viewport={"width": 1440, "height": 1000},
        locale="vi-VN",
    )


async def test_mode_a(browser):
    print()
    print("=" * 80)
    print("MODE A: 1 browser / 1 context / 1 page")
    print("=" * 80)

    context = await new_context(browser)
    page = await context.new_page()

    try:
        for name, url in URLS:
            await inspect_page(page, name, url)
            await page.wait_for_timeout(5000)
    finally:
        await page.close()
        await context.close()


async def test_mode_b(browser):
    print()
    print("=" * 80)
    print("MODE B: 1 browser / 1 context / NEW PAGE per location")
    print("=" * 80)

    context = await new_context(browser)

    try:
        for name, url in URLS:
            page = await context.new_page()
            try:
                await inspect_page(page, name, url)
            finally:
                await page.close()

            await asyncio.sleep(5)
    finally:
        await context.close()


async def test_mode_c(browser):
    print()
    print("=" * 80)
    print("MODE C: 1 browser / NEW CONTEXT per location")
    print("=" * 80)

    for name, url in URLS:
        context = await new_context(browser)
        page = await context.new_page()

        try:
            await inspect_page(page, name, url)
        finally:
            await page.close()
            await context.close()

        await asyncio.sleep(5)


async def test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)

        try:
            await test_mode_a(browser)
            await test_mode_b(browser)
            await test_mode_c(browser)
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(test())
