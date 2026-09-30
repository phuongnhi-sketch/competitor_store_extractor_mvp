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
    lines. Keeping line boundaries prevents the parser from
    treating the whole page as one store.
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
# GENERIC LINK DISCOVERY# ============================================================
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
    """
    store_list = page.locator("div.storeIV.storeaddress")
    if await store_list.count() == 0:
        return

    load_more = store_list.locator("a.seemore")

    for _ in range(max_clicks):
        try:
            if await load_more.count() == 0:
                break

            button = load_more.first
            if not await button.is_visible(timeout=500):
                break

            before = await store_list.locator("li[data-id]").count()
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

            after = await store_list.locator("li[data-id]").count()
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

        # The two MWG brands use different locator URL roots.
        #
        # Điện Máy Xanh:
        #   /he-thong-sieu-thi-dien-may/<province>
        #
        # Thế Giới Di Động:
        #   /sieu-thi-the-gioi-di-dong/<province>
        #
        # The TGDD national URL may redirect to the canonical
        # /sieu-thi-the-gioi-di-dong path, so do not derive the
        # geographic root only from the originally requested URL.
        if brand == "THE GIOI DI DONG":
            main_path = "/sieu-thi-the-gioi-di-dong"
        else:
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

            # IMPORTANT:
            # MWG exposes a geographic hierarchy:
            #
            #   main locator
            #       -> province / city
            #           -> district / ward / commune
            #
            # The province/city pages already load ALL stores
            # through the MWG "Xem thêm" mechanism. Crawling the
            # lower-level ward/commune links causes unnecessary
            # deep crawling and misses stores in the aggregation.
            #
            # Therefore, from the national locator we only follow
            # the first geographic level:
            #   /tinh-...
            #   /thanh-pho-...
            #
            # Do NOT add /xa- or /phuong- here unless the site's
            # structure is re-verified first.

            relative_path = path[len(main_path):].strip("/")

            if not relative_path:
                continue

            # Only one path segment is allowed.
            if "/" in relative_path:
                continue

            if not (
                relative_path.startswith("tinh-")
                or relative_path.startswith("thanh-pho-")
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
    requested_brand,
):
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

    if len(value) > 500:        return ""

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
    # Streamlit may pass the locator URL with a trailing slash.
    # TGDD's locator behaves differently in that case, so normalize
    # the URL before opening it.
    if start_url:
        start_url = start_url.rstrip("/")

    return await _crawl_mwg_brand(
        brand="THE GIOI DI DONG",
        start_url=(
            start_url
            or "https://www.thegioididong.com/"
            "he-thong-sieu-thi-the-gioi-dong"
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
            or "https://www.dienmayxanh.com/"            "he-thong-sieu-thi-dien-may"
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
                    f"{type(e).__name__}: {e}"
                )

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
                href,            ):
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
    Bách Hóa Xanh nationwide crawler.

    BHX exposes store data through browser-accessible APIs:

        /gw/LocationV3/GetFull
            -> province / ward hierarchy

        /gw/Location/V2/GetStoresByLocation
            -> store details by province

    The API is called from inside the Playwright browser context
    because direct requests to the API can return HTTP 403.

    Flow:
        GetFull
          -> all provinces / wards
          -> GetStoresByLocation per province
          -> paginate until province total is reached
          -> local dedupe
    """

    start_url = (
        start_url
        or "https://www.bachhoaxanh.com/he-thong-sieu-thi"
    ).rstrip("/")

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

        # ----------------------------------------------------
        # Open BHX website first.
        #
        # This establishes the browser session required for
        # the BHX APIs. Direct requests.get() may return 403.
        # ----------------------------------------------------

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

        opened_url = page.url

        pages.append(
            opened_url
        )

        logs.append(
            f"Opened: {opened_url}"
        )

        # ----------------------------------------------------
        # Get province / ward hierarchy
        # ----------------------------------------------------

        location_result = await page.evaluate(
            """
            async () => {

                const response = await fetch(
                    'https://api.bachhoaxanh.com/gw/LocationV3/GetFull',
                    {
                        method: 'GET',
                        credentials: 'include',
                        headers: {
                            'Accept':
                                'application/json, text/plain, */*'
                        }
                    }
                );

                const text = await response.text();

                return {
                    status: response.status,
                    text: text
                };
            }
            """
        )

        if location_result.get("status") != 200:

            logs.append(
                "BHX GetFull failed: "
                f"HTTP {location_result.get('status')}"
            )

            await browser.close()

            return records, pages, logs

        try:

            location_data = (
                __import__("json").loads(
                    location_result["text"]
                )
            )

        except Exception as e:

            logs.append(
                "BHX GetFull JSON parse failed: "
                f"{type(e).__name__}: {e}"
            )

            await browser.close()

            return records, pages, logs

        provinces = (
            location_data
            .get("data", {})
            .get("provinces", [])
        )

        if not provinces:

            logs.append(
                "BHX GetFull returned no provinces."
            )

            await browser.close()

            return records, pages, logs

        logs.append(
            f"BHX provinces discovered: "
            f"{len(provinces)}"
        )

        # ----------------------------------------------------
        # Build ward lookup.
        #
        # GetFull already contains ward names, while
        # GetStoresByLocation returns wardId.
        # ----------------------------------------------------

        ward_names = {}

        for province in provinces:

            for ward in province.get(
                "wards",
                []
            ):

                ward_id = ward.get(
                    "id"
                )

                if ward_id is None:
                    continue

                ward_names[str(ward_id)] = (
                    ward.get("name", "")
                )

        # ----------------------------------------------------
        # Crawl every province.
        # ----------------------------------------------------

        stores_seen = set()

        for province in provinces:

            province_id = province.get(
                "id"
            )

            province_name = clean_text(
                province.get(
                    "name",
                    ""
                )
            )

            if province_id is None:
                continue

            province_total = 0
            province_count = 0
            page_index = 0

            logs.append(
                f"BHX province: "
                f"{province_name} "
                f"(ID={province_id})"
            )

            while True:

                api_url = (
                    "https://api.bachhoaxanh.com"
                    "/gw/Location/V2/GetStoresByLocation"
                    f"?provinceId={province_id}"
                    "&wardId=0"
                    "&pageSize=100"
                    f"&pageIndex={page_index}"
                )

                try:

                    result = await page.evaluate(
                        """
                        async (url) => {

                            const response =
                                await fetch(
                                    url,
                                    {
                                        method: 'GET',
                                        credentials: 'include',
                                        headers: {
                                            'Accept':
                                                'application/json, text/plain, */*'
                                        }
                                    }
                                );

                            const text =
                                await response.text();

                            return {
                                status:
                                    response.status,
                                text: text
                            };
                        }
                        """,
                        api_url,
                    )

                except Exception as e:

                    logs.append(
                        "BHX API request error: "
                        f"{province_name} | "
                        f"pageIndex={page_index} | "
                        f"{type(e).__name__}: {e}"
                    )

                    break

                if result.get("status") != 200:

                    logs.append(
                        "BHX API failed: "
                        f"{province_name} | "
                        f"pageIndex={page_index} | "
                        f"HTTP {result.get('status')}"
                    )

                    break

                try:

                    payload = (
                        __import__("json").loads(
                            result["text"]
                        )
                    )

                except Exception as e:

                    logs.append(
                        "BHX API JSON parse failed: "
                        f"{province_name} | "
                        f"pageIndex={page_index} | "
                        f"{type(e).__name__}: {e}"
                    )

                    break

                data = payload.get(
                    "data",
                    {}
                )

                stores = data.get(
                    "stores",
                    []
                )

                total = data.get(
                    "total",
                    0
                )

                try:
                    province_total = int(
                        total or 0
                    )
                except Exception:
                    province_total = 0

                if not stores:
                    break

                new_store_count = 0

                for store in stores:

                    store_id = store.get(
                        "storeId"
                    )

                    if store_id is None:
                        continue

                    store_key = str(
                        store_id
                    )

                    if store_key in stores_seen:
                        continue

                    stores_seen.add(
                        store_key
                    )

                    ward_id = store.get(
                        "wardId"
                    )

                    ward_name = clean_text(
                        ward_names.get(
                            str(ward_id),
                            ""
                        )
                    )

                    store_location = clean_text(
                        store.get(
                            "storeLocation",
                            ""
                        )
                    )

                    store_address = clean_text(
                        store.get(
                            "storeAddress",
                            ""
                        )
                    )

                    lat = store.get(
                        "lat",
                        ""
                    )

                    lon = store.get(
                        "lng",
                        ""
                    )

                    records.append(
                        make_record(
                            brand="BACH HOA XANH",
                            store_code=str(
                                store_id
                            ),
                            store_name=(
                                store_location
                            ),
                            address=(
                                store_address
                            ),
                            province=(
                                province_name
                            ),
                            ward=(
                                ward_name
                            ),
                            lat=str(
                                lat
                                if lat is not None
                                else ""
                            ),
                            lon=str(
                                lon
                                if lon is not None
                                else ""
                            ),
                            source_url=(
                                opened_url
                            ),
                            method=(
                                "Bach Hoa Xanh API"
                            ),
                        )
                    )

                    new_store_count += 1
                    province_count += 1

                # ------------------------------------------------
                # Stop when the province total has been reached.
                # Also stop if the API stops returning new stores.
                # ------------------------------------------------

                if (
                    province_total > 0
                    and province_count
                    >= province_total
                ):
                    break

                if (
                    new_store_count == 0
                ):
                    break

                page_index += 1

            logs.append(
                f"BHX {province_name}: "
                f"{province_count}/{province_total} stores"
            )

        await browser.close()

    records = dedupe_records_local(
        records
    )

    logs.append(
        f"Parsed Bách Hóa Xanh nationwide records after "
        f"local dedupe: {len(records)}"
    )

    return records, pages, logs


def parse_bachhoaxanh_text(
    text,
    source_url,
):
    """
    Kept for backward compatibility with existing tests.

    The production BHX crawler now uses the API directly.
    """

    records = []

    lines = [
        clean_text(x)
        for x in text.splitlines()
        if clean_text(x)
    ]

    for line in lines:

        normalized = normalize_text(
            line
        )

        if (
            "bach hoa xanh"
            not in normalized
        ):
            continue

        address = ""

        # Current BHX locator text normally contains the
        # address in the same store line. Fall back to the
        # following lines for older page formats.
        address = re.sub(
            r"^BHX\s+",
            "",
            line,
            flags=re.I,
        ).strip()

        if not address:

            for next_line in lines[
                lines.index(line) + 1:
                lines.index(line) + 5
            ]:

                candidate = extract_address(
                    next_line
                )

                if candidate:
                    address = candidate
                    break

        if not address:
            continue

        records.append(
            make_record(
                brand="BACH HOA XANH",
                store_name=line,
                address=address,
                source_url=source_url,
                method="Bach Hoa Xanh locator page",
            )
        )

    return records


# ============================================================
# LOCAL DEDUPE
# ============================================================

def dedupe_records_local(
    records
):
    """
    Lightweight parser-level dedupe.

    The main app will still run the project's existing
    dedupe_records() afterward.

    We only remove exact duplicate records generated by
    crawling the same location page multiple times.
    """

    result = []
    seen = set()

    for record in records:

        if not isinstance(
            record,
            dict,
        ):
            continue

        brand = clean_text(
            record.get(
                "Brand",
                "",
            )
        )

        store_code = clean_text(
            record.get(
                "StoreCode",
                "",
            )
        )

        store_url = clean_text(
            record.get(
                "StoreURL",
                "",
            )
        )

        address = clean_text(
            record.get(
                "Address",
                "",
            )
        )

        phone = clean_text(
            record.get(
                "Phone",
                "",
            )
        )

        if store_code:

            key = (
                brand.lower(),
                "code",
                store_code.lower(),
            )

        elif store_url:

            key = (
                brand.lower(),
                "url",
                store_url.lower(),
            )

        elif address:

            key = (
                brand.lower(),
                "address",
                address.lower(),
            )

        elif phone:

            key = (
                brand.lower(),
                "phone",
                phone.lower(),
            )

        else:

            key = tuple(
                sorted(
                    (
                        str(k),
                        str(v),
                    )
                    for k, v in record.items()
                )
            )

        if key in seen:
            continue

        seen.add(key)

        result.append(
            record
        )

    return result


def unique_store_links(
    links
):
    """
    Deduplicate URLs by canonical path.

    Query strings and fragments often point to the same
    geographic locator page.
    """

    result = []
    seen = set()

    for item in links:
        href = clean_text(
            item.get("href", "")
        )

        if not href:
            continue

        parsed = urlparse(href)

        normalized = (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path.rstrip("/").lower(),
        )

        if normalized in seen:
            continue

        seen.add(normalized)

        result.append(
            {
                "text": clean_text(
                    item.get("text", "")
                ),
                "href": href,
            }
        )

    return result