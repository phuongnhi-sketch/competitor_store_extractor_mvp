import re
import unicodedata
from urllib.parse import urljoin, urlparse

from playwright.async_api import async_playwright


# ============================================================
# COMMON CONSTANTS
# ============================================================

OUTPUT_FIELDS = [
    "Brand",
    "StoreCode",
    "StoreName",
    "Address",
    "Province",
    "Ward",
    "Phone",
    "Lat",
    "Long",
    "StoreURL",
    "SourceURL",
    "Method",
]


# ============================================================
# TEXT HELPERS
# ============================================================

def clean_text(value):
    if value is None:
        return ""

    value = str(value)

    value = (
        value
        .replace("\xa0", " ")
        .replace("\r", " ")
        .replace("\n", " ")
        .strip()
    )

    value = re.sub(r"\s+", " ", value)

    return value.strip()


def normalize_text(value):
    """
    Lowercase + remove Vietnamese accents.

    Vietnamese "đ/Đ" does not decompose under Unicode NFD,
    so it is normalized explicitly as well.
    """

    value = clean_text(value)

    value = value.replace("đ", "d").replace("Đ", "D")

    value = unicodedata.normalize(
        "NFD",
        value,
    )

    value = "".join(
        char
        for char in value
        if unicodedata.category(char) != "Mn"
    )

    return value.lower().strip()


def unique_preserve(items):
    result = []
    seen = set()

    for item in items:

        item = clean_text(item)

        if not item:
            continue

        key = item.lower()

        if key in seen:
            continue

        seen.add(key)
        result.append(item)

    return result


def absolute_url(base_url, href):
    if not href:
        return ""

    href = href.strip()

    if href.startswith("#"):
        return ""

    if href.startswith(
        (
            "javascript:",
            "mailto:",
            "tel:",
        )
    ):
        return ""

    return urljoin(
        base_url,
        href,
    )


def extract_phone(text):
    """
    Find Vietnamese phone numbers.

    Avoid treating short numbers as store phone.
    """

    text = clean_text(text)

    patterns = [
        r"(?:0|\+84)\d[\d\s.\-]{7,12}\d",
        r"1\d{3}\s?\d{3}\s?\d{3}",
    ]

    candidates = []

    for pattern in patterns:

        matches = re.findall(
            pattern,
            text,
        )

        candidates.extend(
            matches
        )

    for value in candidates:

        value = re.sub(
            r"[^\d+]",
            "",
            value,
        )

        # +84 -> 0
        if value.startswith("+84"):
            value = "0" + value[3:]

        if (
            len(value) >= 9
            and len(value) <= 12
        ):
            return value

    return ""


def extract_coordinates_from_text(text):
    """
    Extract simple latitude / longitude pairs
    if they appear in page text.
    """

    text = clean_text(text)

    pattern = (
        r"(-?\d{1,3}\.\d{4,})"
        r"\s*[,;]\s*"
        r"(-?\d{1,3}\.\d{4,})"
    )

    match = re.search(
        pattern,
        text,
    )

    if not match:
        return "", ""

    lat = match.group(1)
    lon = match.group(2)

    try:

        lat_float = float(lat)
        lon_float = float(lon)

        if (
            -90 <= lat_float <= 90
            and -180 <= lon_float <= 180
        ):
            return lat, lon

    except Exception:
        pass

    return "", ""


def extract_store_code(url):
    """
    Try to derive a stable store code from URL.

    We intentionally do not invent a code when none exists.
    """

    if not url:
        return ""

    path = urlparse(url).path.strip("/")

    if not path:
        return ""

    last_part = path.split("/")[-1]

    # Common ID patterns
    patterns = [
        r"(?:store|shop|cua-hang|sieu-thi|nha-thuoc)[-_]?(\d+)",
        r"[-_/](\d{2,6})[-_/]?$",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            path,
            flags=re.I,
        )

        if match:
            return match.group(1)

    return ""


# ============================================================
# GENERIC STORE RECORD
# ============================================================

def make_record(
    brand,
    store_name="",
    address="",
    province="",
    ward="",
    phone="",
    lat="",
    lon="",
    store_url="",
    source_url="",
    method="",
    store_code="",
):
    return {
        "Brand": clean_text(brand),
        "StoreCode": clean_text(store_code),
        "StoreName": clean_text(store_name),
        "Address": clean_text(address),
        "Province": clean_text(province),
        "Ward": clean_text(ward),
        "Phone": clean_text(phone),
        "Lat": clean_text(lat),
        "Long": clean_text(lon),
        "StoreURL": clean_text(store_url),
        "SourceURL": clean_text(source_url),
        "Method": clean_text(method),
    }


# ============================================================
# EXTRACT ADDRESS FROM TEXT
# ============================================================

def extract_address(text):
    """
    Try to identify address-like text.

    This is intentionally conservative.
    """

    text = clean_text(text)

    if not text:
        return ""

    # Remove obvious phone fragments
    text = re.sub(
        r"(?:Hotline|Điện thoại|Tel|Phone|Gọi mua|Liên hệ)"
        r"\s*:?\s*(?:0|\+84)?[\d\s.\-]{8,15}",
        "",
        text,
        flags=re.I,
    )

    # Address often contains:
    # số nhà / đường / phường / xã / quận / huyện /
    # thành phố / tỉnh
    address_keywords = [
        "đường",
        "phường",
        "xã",
        "thị trấn",
        "quận",
        "huyện",
        "thành phố",
        "tỉnh",
        "tp.",
        "tp ",
    ]

    normalized = normalize_text(
        text
    )

    if any(
        keyword in normalized
        for keyword in [
            normalize_text(x)
            for x in address_keywords
        ]
    ):
        return text

    return ""


# ============================================================
# PLAYWRIGHT PAGE HELPERS
# ============================================================

async def get_page_links(
    page,
    base_url,
):
    """
    Return all useful links from page.
    """

    try:

        links = await page.locator(
            "a[href]"
        ).evaluate_all(
            """
            els => els.map(a => ({
                text: (a.innerText || a.textContent || '').trim(),
                href: a.href || a.getAttribute('href') || ''
            }))
            """
        )

    except Exception:
        return []

    result = []

    for item in links:

        text = clean_text(
            item.get("text", "")
        )

        href = absolute_url(
            base_url,
            item.get("href", ""),
        )

        if not href:
            continue

        result.append(
            {
                "text": text,
                "href": href,
            }
        )

    return result


async def get_body_text(page):
    """
    Read body text while preserving line boundaries.

    MWG locator pages expose store cards as separate text
    lines. Keeping line boundaries prevents the parser from    treating the whole page as one store.
    """
    try:
        raw = await page.locator("body").inner_text()

        lines = []

        for line in raw.splitlines():
            line = clean_text(line)

            if line:
                lines.append(line)

        return "\n".join(lines)

    except Exception:
        return ""

async def safe_goto(
    page,
    url,
    wait_ms=2500,
):
    try:

        await page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=60000,
        )

        await page.wait_for_timeout(
            wait_ms
        )

        return True

    except Exception:
        return False


async def click_load_more(
    page,
    max_clicks=30,
):
    """
    Try common 'load more' buttons.

    This is useful for store locator pages.
    """

    selectors = [
        "text=Xem thêm",
        "text=Xem thêm nhà thuốc",
        "text=Xem thêm cửa hàng",
        "text=Load more",
        "text=Show more",
        "button:has-text('Xem thêm')",
        "button:has-text('Xem thêm cửa hàng')",
        "button:has-text('Xem thêm nhà thuốc')",
        "a:has-text('Xem thêm')",
    ]

    for _ in range(max_clicks):

        clicked = False

        for selector in selectors:

            try:

                locator = page.locator(
                    selector
                ).first

                if not await locator.is_visible(
                    timeout=500
                ):
                    continue

                await locator.click(
                    timeout=2000
                )

                await page.wait_for_timeout(
                    1000
                )

                clicked = True
                break

            except Exception:
                continue

        if not clicked:
            break


# ============================================================
# GENERIC LINK DISCOVERY
# ============================================================

def is_same_domain(
    base_url,
    target_url,
):
    try:

        base_host = urlparse(
            base_url
        ).netloc.lower()

        target_host = urlparse(
            target_url
        ).netloc.lower()

        return (
            base_host == target_host
            or target_host.endswith(
                "." + base_host
            )
        )

    except Exception:
        return False


def looks_like_store_url(
    url,
    keywords,
):
    path = normalize_text(
        urlparse(url).path
    )

    return any(
        normalize_text(keyword)
        in path
        for keyword in keywords
    )


# ============================================================
# THẾ GIỚI DI ĐỘNG + ĐIỆN MÁY XANH
# ============================================================

async def click_mwg_store_load_more(
    page,
    max_clicks=100,
):
    """
    Load all MWG store cards on a geographic locator page.

    MWG uses:
        <a class="seemore" onclick="GetMoreStore(...)">Xem thêm</a>

    The generic click_load_more() cannot safely target this button
    because MWG pages contain several unrelated "Xem thêm" links.
    """
    store_list = page.locator(
        "div.storeIV.storeaddress"
    )

    if await store_list.count() == 0:
        return

    load_more = store_list.locator(
        "a.seemore"
    )

    for _ in range(max_clicks):
        try:
            if await load_more.count() == 0:
                break

            button = load_more.first

            if not await button.is_visible(timeout=500):
                break

            before = await store_list.locator(
                "li[data-id]"
            ).count()

            await button.click(timeout=3000)

            try:
                await page.wait_for_function(
                    """(before) => {
                        const list = document.querySelector(
                            'div.storeIV.storeaddress'
                        );
                        if (!list) return false;
                        return list.querySelectorAll(
                            'li[data-id]'
                        ).length > before;
                    }""",
                    before,
                    timeout=8000,
                )
            except Exception:
                await page.wait_for_timeout(1500)

            after = await store_list.locator(
                "li[data-id]"
            ).count()

            if after <= before:
                break

        except Exception:
            break


async def _crawl_mwg_brand(
    brand,
    start_url,
    brand_keywords,
    store_url_keywords,
):
    """
    Crawl MWG locator pages through the site's geographic hierarchy.

    The MWG locator links are geographic pages rather than
    individual store detail pages. We therefore parse the store
    cards directly from the locator-page text.
    """

    records = []
    pages = []
    logs = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        context = await browser.new_context(
            viewport={"width": 1440, "height": 1000},
            locale="vi-VN",
        )

        page = await context.new_page()

        ok = await safe_goto(
            page,
            start_url,
            wait_ms=3000,
        )

        if not ok:
            logs.append(f"Failed to open: {start_url}")
            await browser.close()
            return records, pages, logs

        opened_url = page.url
        pages.append(opened_url)
        logs.append(f"Opened: {opened_url}")

        await click_mwg_store_load_more(
            page,
            max_clicks=100,
        )

        links = await get_page_links(
            page,
            page.url,
        )

        locator_links = []

        main_path = normalize_text(
            urlparse(opened_url).path
        ).rstrip("/")

        for item in links:
            href = item.get("href", "")

            if not href:
                continue

            if not is_same_domain(
                opened_url,
                href,
            ):
                continue

            path = normalize_text(
                urlparse(href).path
            ).rstrip("/")

            if not path.startswith(main_path):
                continue

            if path == main_path:
                continue

            if (
                "/tinh-" not in path
                and "/thanh-pho-" not in path
                and "/xa-" not in path
                and "/phuong-" not in path
            ):
                continue

            locator_links.append(item)

        locator_links = unique_store_links(
            locator_links
        )

        logs.append(
            f"Discovered geographic locator links: "
            f"{len(locator_links)}"
        )

        pages_to_visit = [
            {
                "href": opened_url,
                "text": "",
            }
        ]

        pages_to_visit.extend(
            locator_links
        )

        visited = set()

        for item in pages_to_visit:
            location_url = item["href"]

            parsed = urlparse(location_url)

            visit_key = (
                parsed.scheme.lower(),
                parsed.netloc.lower(),
                parsed.path.rstrip("/").lower(),
            )

            if visit_key in visited:
                continue

            visited.add(visit_key)

            location_page = (
                page
                if location_url == opened_url
                else await context.new_page()
            )

            try:
                if location_url != opened_url:
                    ok = await safe_goto(
                        location_page,
                        location_url,
                        wait_ms=1800,
                    )

                    if not ok:
                        logs.append(
                            f"Could not open locator page: "
                            f"{location_url}"
                        )
                        continue

                    pages.append(
                        location_page.url
                    )

                await click_mwg_store_load_more(
                    location_page,
                    max_clicks=100,
                )

                text = await get_body_text(
                    location_page
                )

                location_records = parse_mwg_locator_text(
                    text,
                    location_url,
                    brand,
                )

                records.extend(
                    location_records
                )

            except Exception as e:
                logs.append(
                    f"MWG locator error: "
                    f"{location_url} | "
                    f"{type(e).__name__}: {e}"
                )

            finally:
                if location_page is not page:
                    await location_page.close()

        await browser.close()

    records = dedupe_records_local(
        records
    )

    logs.append(
        f"Parsed MWG store records before app dedupe: "
        f"{len(records)}"
    )

    return records, pages, logs

def detect_mwg_brand(
    store_name,
    text,
):
    combined = normalize_text(
        f"{store_name} {text}"
    )

    if (
        "dien may xanh"
        in combined
    ):
        return "DIEN MAY XANH"

    if (
        "the gioi di dong"
        in combined
    ):
        return "THE GIOI DI DONG"

    return ""


def extract_store_name_from_text(
    text,
    brand_keywords,
):
    lines = [
        clean_text(x)
        for x in text.splitlines()
    ]

    lines = [
        x for x in lines
        if x
    ]

    for line in lines:

        normalized = normalize_text(
            line
        )

        if any(
            normalize_text(keyword)
            in normalized
            for keyword in brand_keywords
        ):
            return line

    return ""


def parse_mwg_locator_text(
    body_text,
    source_url,
    requested_brand,):
    """
    Parse MWG locator-page store cards.

    Current MWG pages expose records as text lines such as:
        Điện máy Xanh 137 Quốc Lộ 13, Phường Hiệp Bình, ...
        Thế giới di động 708 Nguyễn Trãi, Phường Chợ Lớn, ...

    Only lines containing the requested brand and address-like
    information are accepted.
    """

    records = []

    lines = [
        clean_text(line)
        for line in body_text.splitlines()
        if clean_text(line)
    ]

    requested_normalized = normalize_text(
        requested_brand
    )

    brand_patterns = [
        (
            "DIEN MAY XANH",
            [
                "dien may xanh",
            ],
        ),
        (
            "THE GIOI DI DONG",
            [
                "the gioi di dong",
            ],
        ),
    ]

    for line in lines:
        normalized = normalize_text(line)

        detected_brand = ""

        for candidate_brand, patterns in brand_patterns:
            if any(
                normalize_text(pattern) in normalized
                for pattern in patterns
            ):
                detected_brand = candidate_brand
                break

        if not detected_brand:
            continue

        if (
            normalize_text(detected_brand)
            != requested_normalized
        ):
            continue

        if any(
            phrase in normalized
            for phrase in [
                "tim sieu thi",
                "he thong sieu thi",
                "cac tien ich",
                "tuyen dung",
                "website cung tap doan",
                "goi mua",
                "bao hanh",
                "xem them",
            ]
        ):
            continue

        address = extract_mwg_address_from_store_line(
            line,
            detected_brand,
        )

        if not address:
            continue

        store_name = (
            "Điện máy Xanh"
            if detected_brand == "DIEN MAY XANH"
            else "Thế giới di động"
        )

        phone = extract_phone(line)

        records.append(
            make_record(
                brand=detected_brand,
                store_name=store_name,
                address=address,
                phone=phone,
                source_url=source_url,
                method="MWG geographic locator page",
            )
        )

    return records


def extract_mwg_address_from_store_line(
    line,
    detected_brand,
):
    """
    Extract the address from one MWG store-card line.

    Example:
        Điện máy Xanh 137 Quốc Lộ 13, Phường Hiệp Bình,
        Thành phố Hồ Chí Minh, Việt Nam - Xem bản đồ

    Returns only the address portion.
    """

    value = clean_text(line)

    if detected_brand == "DIEN MAY XANH":
        brand_regex = r"^\s*Điện\s+máy\s+Xanh\b"
    else:
        brand_regex = r"^\s*Thế\s+giới\s+di\s+động\b"

    value = re.sub(
        brand_regex,
        "",
        value,
        count=1,
        flags=re.I,
    ).strip(" -:|")

    # Remove the map UI suffix.
    value = re.sub(
        r"\s*-\s*Xem\s+bản\s+đồ.*$",
        "",
        value,
        count=1,
        flags=re.I,
    ).strip(" -:|")

    if not value:
        return ""

    if len(value) > 500:
        return ""

    normalized_value = normalize_text(value)
    padded = f" {normalized_value} "

    address_markers = [
        " duong ",
        " phuong ",
        " xa ",
        " tinh ",
        " thanh pho ",
        " quoc lo ",
        " khu pho ",
        " ap ",
        " thon ",
        " so ",
        " km ",
    ]

    if not any(
        marker in padded
        for marker in address_markers
    ):
        return ""

    return value

async def crawl_thegioididong(start_url=None):
    return await _crawl_mwg_brand(
        brand="THE GIOI DI DONG",
        start_url=(
            start_url
            or "https://www.thegioididong.com/"
            "he-thong-sieu-thi-the-gioi-di-dong/"
        ),
        brand_keywords=[
            "Thế giới di động",
            "thegioididong",
        ],
        store_url_keywords=[
            "sieu-thi-the-gioi-di-dong",
            "cua-hang-the-gioi-di-dong",
        ],
    )


async def crawl_dienmayxanh(start_url=None):
    return await _crawl_mwg_brand(
        brand="DIEN MAY XANH",
        start_url=(
            start_url
            or "https://www.dienmayxanh.com/"
            "he-thong-sieu-thi-dien-may"
        ),
        brand_keywords=[
            "Điện máy Xanh",
            "dien may xanh",
        ],
        store_url_keywords=[
            "he-thong-sieu-thi-dien-may",
            "sieu-thi-dien-may",
        ],
    )


# ============================================================
# FPT SHOP
# ============================================================

async def crawl_fptshop(start_url=None):
    """
    Crawl FPT Shop store locator.

    FPT currently exposes a nationwide store system and
    province-level / store-level pages.
    """

    start_url = (
        start_url
        or "https://fptshop.com.vn/cua-hang"
    )

    records = []
    pages = []
    logs = []

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True
        )

        context = await browser.new_context(
            viewport={
                "width": 1440,
                "height": 1000,
            },
            locale="vi-VN",
        )

        page = await context.new_page()

        ok = await safe_goto(
            page,
            start_url,
            wait_ms=3000,
        )

        if not ok:

            logs.append(
                f"Failed to open: {start_url}"
            )

            await browser.close()

            return records, pages, logs

        pages.append(
            page.url
        )

        logs.append(
            f"Opened: {page.url}"
        )

        await click_load_more(
            page,
            max_clicks=50,
        )

        links = await get_page_links(
            page,
            page.url,
        )

        store_links = []

        for item in links:

            href = item["href"]

            if not is_same_domain(
                start_url,
                href,
            ):
                continue

            path = normalize_text(
                urlparse(href).path
            )

            # FPT store detail pages normally contain
            # /cua-hang/
            if (
                "/cua-hang/"
                not in path
            ):
                continue

            # Exclude the locator root itself
            if path.rstrip(
                "/"
            ) == "/cua-hang":
                continue

            store_links.append(
                item
            )

        store_links = unique_store_links(
            store_links
        )

        logs.append(
            f"FPT store links: "
            f"{len(store_links)}"
        )

        for item in store_links:

            store_url = item["href"]

            detail = await context.new_page()

            try:

                ok = await safe_goto(
                    detail,
                    store_url,
                    wait_ms=1200,
                )

                if not ok:
                    continue

                text = await get_body_text(
                    detail
                )

                store_name = (
                    extract_fpt_store_name(
                        text,
                        item["text"],
                    )
                )

                address = extract_fpt_address(
                    text
                )

                phone = extract_phone(
                    text
                )

                lat, lon = (
                    extract_coordinates_from_text(
                        text
                    )
                )

                if not store_name:
                    store_name = item["text"]

                if not address:
                    address = extract_address(
                        text
                    )

                records.append(
                    make_record(
                        brand="FPT SHOP",
                        store_name=store_name,
                        address=address,
                        phone=phone,
                        lat=lat,
                        lon=lon,
                        store_url=store_url,
                        source_url=start_url,
                        method="FPT store detail",
                        store_code=extract_store_code(
                            store_url
                        ),
                    )
                )

            except Exception as e:

                logs.append(
                    f"FPT error: "
                    f"{store_url} | "
                    f"{type(e).__name__}: {e}"                )

            finally:

                await detail.close()

        # ----------------------------------------------------
        # Fallback
        # ----------------------------------------------------

        if not records:

            text = await get_body_text(
                page
            )

            records.extend(
                parse_fpt_locator_text(
                    text,
                    start_url,
                )
            )

        await browser.close()

    records = dedupe_records_local(
        records
    )

    return records, pages, logs


def extract_fpt_store_name(
    text,
    anchor_text="",
):
    anchor_text = clean_text(
        anchor_text
    )

    if anchor_text:
        if (
            "fpt"
            in normalize_text(
                anchor_text
            )
        ):
            return anchor_text

    lines = [
        clean_text(x)
        for x in text.splitlines()
    ]

    for line in lines:

        normalized = normalize_text(
            line
        )

        if (
            "cua hang fpt shop"
            in normalized
            or "fpt shop"
            in normalized
        ):
            return line

    return anchor_text


def extract_fpt_address(text):
    lines = [
        clean_text(x)
        for x in text.splitlines()
    ]

    for index, line in enumerate(
        lines
    ):

        normalized = normalize_text(
            line
        )

        if (
            normalized == "dia chi:"
            or normalized.startswith(
                "dia chi:"
            )
        ):

            value = re.sub(
                r"^địa chỉ\s*:?\s*",
                "",
                line,
                flags=re.I,
            )

            if value:
                return value

            if index + 1 < len(lines):

                return lines[
                    index + 1
                ]

    return ""


def parse_fpt_locator_text(
    text,
    source_url,
):
    records = []

    lines = [
        clean_text(x)
        for x in text.splitlines()
        if clean_text(x)
    ]

    for index, line in enumerate(
        lines
    ):

        normalized = normalize_text(
            line
        )

        if (
            "fpt shop"
            not in normalized
        ):
            continue

        address = ""

        for next_line in lines[
            index + 1:index + 5
        ]:

            candidate = extract_address(
                next_line
            )

            if candidate:

                address = candidate
                break

        records.append(
            make_record(
                brand="FPT SHOP",
                store_name=line,
                address=address,
                source_url=source_url,
                method="FPT locator page",
            )
        )

    return records


# ============================================================
# LONG CHÂU
# ============================================================

async def crawl_longchau(start_url=None):
    """
    Crawl Long Châu store system.

    Current Long Châu pages use:

        /he-thong-cua-hang/<province>

    and can go further into ward/district pages.
    """

    start_url = (
        start_url
        or "https://nhathuoclongchau.com.vn/"
        "he-thong-cua-hang"
    )

    records = []
    pages = []
    logs = []

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True
        )

        context = await browser.new_context(
            viewport={
                "width": 1440,
                "height": 1000,
            },
            locale="vi-VN",
        )

        page = await context.new_page()

        ok = await safe_goto(
            page,
            start_url,
            wait_ms=3000,
        )

        if not ok:

            logs.append(
                f"Failed to open: {start_url}"
            )

            await browser.close()

            return records, pages, logs

        pages.append(
            page.url
        )

        await click_load_more(
            page,
            max_clicks=50,
        )

        links = await get_page_links(
            page,
            page.url,
        )

        # ----------------------------------------------------
        # Find province / district / store pages
        # ----------------------------------------------------

        location_links = []

        for item in links:

            href = item["href"]

            if not is_same_domain(
                start_url,
                href,
            ):
                continue

            path = normalize_text(
                urlparse(href).path
            )

            if (
                "/he-thong-cua-hang/"
                not in path
            ):
                continue

            location_links.append(
                item
            )

        location_links = unique_store_links(
            location_links
        )

        logs.append(
            f"Long Chau location links: "
            f"{len(location_links)}"
        )

        # ----------------------------------------------------
        # Open location pages
        # ----------------------------------------------------

        visited = set()

        # Start page first
        location_urls = [
            start_url
        ]

        location_urls.extend(
            item["href"]
            for item in location_links
        )

        for location_url in location_urls:

            if location_url in visited:
                continue

            visited.add(
                location_url
            )

            location_page = (
                await context.new_page()
            )

            try:

                ok = await safe_goto(
                    location_page,
                    location_url,
                    wait_ms=1500,
                )

                if not ok:
                    continue

                pages.append(
                    location_page.url
                )

                await click_load_more(
                    location_page,
                    max_clicks=30,
                )

                text = await get_body_text(
                    location_page
                )

                # ------------------------------------------------
                # Extract Long Châu addresses from location page
                # ------------------------------------------------

                location_records = (
                    parse_longchau_text(
                        text,
                        location_url,
                    )
                )

                records.extend(
                    location_records
                )

            except Exception as e:

                logs.append(
                    f"Long Chau error: "
                    f"{location_url} | "
                    f"{type(e).__name__}: {e}"
                )

            finally:

                await location_page.close()

        await browser.close()

    records = dedupe_records_local(
        records
    )

    return records, pages, logs


def parse_longchau_text(
    text,
    source_url,
):
    """
    Long Châu location pages expose:

        Có X nhà thuốc...

    followed by store addresses.

    We extract address-like lines and create one record
    per unique address.
    """

    records = []

    lines = [
        clean_text(x)
        for x in text.splitlines()
        if clean_text(x)
    ]

    # Province / ward information from page title/context
    province = ""
    ward = ""

    for line in lines:

        normalized = normalize_text(
            line
        )

        if (
            normalized.startswith(
                "ho chi minh"            )
            or normalized.startswith(
                "ha noi"
            )
        ):
            province = line

        if (
            "phuong " in normalized
            or "xa " in normalized
        ):
            # Keep as potential ward,
            # but don't overwrite province.
            if len(line) < 100:
                ward = line

    for line in lines:

        # Ignore obvious UI text
        normalized = normalize_text(
            line
        )

        if any(
            phrase in normalized
            for phrase in [
                "he thong nha thuoc",
                "tim kiem nha thuoc",
                "xem them nha thuoc",
                "nha thuoc gan ban",
                "thoi gian hoat dong",
            ]
        ):
            continue

        address = extract_address(
            line
        )

        if not address:
            continue

        # Avoid old-address lines
        if normalized.startswith(
            "dia chi cu"
        ):
            continue

        phone = extract_phone(
            line
        )

        records.append(
            make_record(
                brand="NHA THUOC LONG CHAU",
                store_name=(
                    "Nhà thuốc Long Châu"
                ),
                address=address,
                province=province,
                ward=ward,
                phone=phone,
                source_url=source_url,
                method="Long Chau location page",
            )
        )

    return records


# ============================================================
# PHARMACITY
# ============================================================

async def crawl_pharmacity(start_url=None):
    """
    Pharmacity store locator parser.

    Uses the /he-thong-cua-hang/ hierarchy.
    """

    start_url = (
        start_url
        or "https://www.pharmacity.vn/"
        "he-thong-cua-hang"
    )

    records = []
    pages = []
    logs = []

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True
        )

        context = await browser.new_context(
            viewport={
                "width": 1440,
                "height": 1000,
            },
            locale="vi-VN",
        )

        page = await context.new_page()

        ok = await safe_goto(
            page,
            start_url,
            wait_ms=3500,
        )

        if not ok:

            logs.append(
                f"Failed to open: {start_url}"
            )

            await browser.close()

            return records, pages, logs

        pages.append(
            page.url
        )

        await click_load_more(
            page,
            max_clicks=50,
        )

        links = await get_page_links(
            page,
            page.url,
        )

        location_links = []

        for item in links:

            href = item["href"]

            if not is_same_domain(
                start_url,
                href,
            ):
                continue

            path = normalize_text(
                urlparse(href).path
            )

            if (
                "/he-thong-cua-hang/"
                not in path
            ):
                continue

            location_links.append(
                item
            )

        location_links = unique_store_links(
            location_links
        )

        logs.append(
            f"Pharmacity location links: "
            f"{len(location_links)}"
        )

        visited = set()

        urls_to_visit = [
            start_url
        ]

        urls_to_visit.extend(
            item["href"]
            for item in location_links
        )

        for location_url in urls_to_visit:

            if location_url in visited:
                continue

            visited.add(
                location_url
            )

            location_page = (
                await context.new_page()
            )

            try:

                ok = await safe_goto(
                    location_page,
                    location_url,
                    wait_ms=1500,
                )

                if not ok:
                    continue

                pages.append(
                    location_page.url
                )

                await click_load_more(
                    location_page,
                    max_clicks=30,
                )

                text = await get_body_text(
                    location_page
                )

                records.extend(
                    parse_pharmacity_text(
                        text,
                        location_url,
                    )
                )

            except Exception as e:

                logs.append(
                    f"Pharmacity error: "
                    f"{location_url} | "
                    f"{type(e).__name__}: {e}"
                )

            finally:

                await location_page.close()

        await browser.close()

    records = dedupe_records_local(
        records
    )

    return records, pages, logs


def parse_pharmacity_text(
    text,
    source_url,
):
    records = []

    lines = [
        clean_text(x)
        for x in text.splitlines()
        if clean_text(x)
    ]

    province = ""
    ward = ""

    for line in lines:

        normalized = normalize_text(
            line
        )

        if (
            normalized.startswith(
                "ho chi minh"
            )
            or normalized.startswith(
                "ha noi"
            )
        ):
            province = line

        if (
            "phuong " in normalized
            or "xa " in normalized
        ):
            if len(line) < 100:
                ward = line

    for line in lines:

        normalized = normalize_text(
            line
        )

        if any(
            phrase in normalized
            for phrase in [
                "pharmacity",
                "he thong cua hang",
                "tim cua hang",
                "cua hang gan ban",
                "xem them",
            ]
        ):
            continue

        address = extract_address(
            line
        )

        if not address:
            continue

        phone = extract_phone(
            line
        )

        records.append(
            make_record(
                brand="PHARMACITY",
                store_name="Pharmacity",
                address=address,
                province=province,
                ward=ward,
                phone=phone,
                source_url=source_url,
                method="Pharmacity location page",
            )
        )

    return records


# ============================================================
# BÁCH HÓA XANH
# ============================================================

async def crawl_bachhoaxanh(start_url=None):
    """
    Bách Hóa Xanh store locator.

    Uses the locator page and store/location links exposed
    by the site.
    """

    start_urls = []

    if start_url:
        start_urls.append(start_url)

    start_urls.extend([
        "https://www.bachhoaxanh.com/he-thong-sieu-thi",
        "https://www.bachhoaxanh.com/",
    ])

    records = []
    pages = []
    logs = []

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True
        )

        context = await browser.new_context(
            viewport={
                "width": 1440,
                "height": 1000,
            },
            locale="vi-VN",
        )

        page = await context.new_page()

        opened_url = ""

        for start_url in start_urls:

            ok = await safe_goto(
                page,
                start_url,
                wait_ms=3000,
            )

            if ok:

                opened_url = page.url
                break

        if not opened_url:

            logs.append(
                "Could not open Bách Hóa Xanh locator."
            )

            await browser.close()

            return records, pages, logs

        pages.append(
            opened_url
        )

        logs.append(
            f"Opened: {opened_url}"
        )

        await click_load_more(
            page,
            max_clicks=50,
        )

        links = await get_page_links(
            page,
            page.url,
        )

        store_links = []

        for item in links:

            href = item["href"]

            if not is_same_domain(
                page.url,
                href,
            ):
                continue

            path = normalize_text(
                urlparse(href).path
            )

            if any(
                keyword in path
                for keyword in [
                    "cua-hang",
                    "sieu-thi",
                    "bach-hoa-xanh",
                ]
            ):

                store_links.append(
                    item
                )

        store_links = unique_store_links(
            store_links
        )

        logs.append(
            f"Bach Hoa Xanh store links: "
            f"{len(store_links)}"
        )

        # ----------------------------------------------------
        # Detail pages
        # ----------------------------------------------------

        for item in store_links:

            store_url = item["href"]

            detail = await context.new_page()

            try:

                ok = await safe_goto(
                    detail,
                    store_url,
                    wait_ms=1200,
                )

                if not ok:
                    continue

                text = await get_body_text(
                    detail
                )

                store_name = (
                    item["text"]
                    or "Bách Hóa Xanh"
                )

                address = extract_address(
                    text
                )

                phone = extract_phone(
                    text
                )

                lat, lon = (
                    extract_coordinates_from_text(
                        text
                    )
                )

                records.append(
                    make_record(
                        brand="BACH HOA XANH",
                        store_name=store_name,
                        address=address,
                        phone=phone,
                        lat=lat,
                        lon=lon,
                        store_url=store_url,
                        source_url=opened_url,
                        method="Bach Hoa Xanh store detail",
                        store_code=extract_store_code(
                            store_url
                        ),
                    )
                )

            except Exception as e:

                logs.append(
                    f"Bach Hoa Xanh error: "
                    f"{store_url} | "
                    f"{type(e).__name__}: {e}"
                )

            finally:

                await detail.close()

        # ----------------------------------------------------
        # Fallback page parser
        # ----------------------------------------------------

        if not records:

            text = await get_body_text(
                page
            )

            records.extend(
                parse_bachhoaxanh_text(
                    text,
                    opened_url,
                )
            )

        await browser.close()

    records = dedupe_records_local(
        records
    )

    return records, pages, logs


def parse_bachhoaxanh_text(
    text,
    source_url,
):
    records = []

    lines = [
        clean_text(x)
        for x in text.splitlines()
        if clean_text(x)
    ]

    for index, line in enumerate(
        lines
    ):

        normalized = normalize_text(
            line
        )

        if (
            "bach hoa xanh"
            not in normalized
        ):
            continue

        address = ""

        for next_line in lines[
            index + 1:index + 5
        ]:

            candidate = extract_address(
                next_line
            )

            if candidate:

                address = candidate
                break

        records.append(
            make_record(
                brand="BACH HOA XANH",
                store_name=line,
                address=address,
                source_url=source_url,