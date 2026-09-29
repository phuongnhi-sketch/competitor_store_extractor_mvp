import asyncio
import inspect
import re
from urllib.parse import (
    urljoin,
    urlparse,
    parse_qs,
    urlencode,
    urlunparse,
)

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from common import (
    clean_text,
    normalize_url,
    same_domain,
    looks_like_http_url,
    is_usable_store_url,
    is_api_or_ajax_url,
    fill_coordinates_from_url,
    extract_phone,
    looks_like_address,
    parse_vietnam_address,
    normalize_coordinate,
    empty_record,
    flatten_json_objects,
    find_value,
)

from dedupe import dedupe_records


# ============================================================
# CONFIG
# ============================================================

STORE_KEYWORDS = [

    "store",
    "stores",
    "storelocator",
    "store-locator",
    "store_locator",
    "location",
    "locations",
    "branch",
    "branches",
    "cua-hang",
    "cua hang",
    "cửa hàng",
    "chi-nhanh",
    "chi nhanh",
    "chi nhánh",
    "dia-diem",
    "dia diem",
    "địa điểm",

]


# ============================================================
# BRAND
# ============================================================

def get_brand_from_url(url):

    hostname = (
        urlparse(url)
        .netloc
        .lower()
        .replace("www.", "")
    )

    known_brands = {

        "jollibee.com.vn": "JOLLIBEE",

        "phuclong.com.vn": "PHUC LONG",

        "thecoffeehouse.com": "THE COFFEE HOUSE",

        "highlandscoffee.com.vn": "HIGHLANDS COFFEE",

        "starbucks.vn": "STARBUCKS",

        "starbucks.com.vn": "STARBUCKS",

        "starbucks.com": "STARBUCKS",

        "kfcvietnam.com.vn": "KFC",

        "lotteria.vn": "LOTTERIA",

        "pizza4ps.com": "PIZZA 4P'S",

        "pizzahut.vn": "PIZZA HUT",

        "dominos.vn": "DOMINO'S",

        "burgerking.vn": "BURGER KING",

        "galaxypremium.com.vn": "GALAXY",

    }

    if hostname in known_brands:

        return known_brands[hostname]

    parts = hostname.split(".")

    if len(parts) >= 2:

        return parts[-2].upper()

    return hostname.upper()


# ============================================================
# JSON PARSER
# ============================================================

def parse_json_response(
    data,
    brand,
    source_url
):

    records = []

    objects = flatten_json_objects(
        data
    )

    for obj in objects:

        name = find_value(
            obj,
            [
                "name",
                "storename",
                "branchname",
                "restaurantname",
                "title",
            ]
        )

        store_code = find_value(
            obj,
            [
                "code",
                "storecode",
                "branchcode",
                "restaurantcode",
                "storeid",
                "branchid",
            ]
        )

        address = find_value(
            obj,
            [
                "address",
                "fulladdress",
                "addressline",
                "formattedaddress",
                "locationaddress",
            ]
        )

        phone = find_value(
            obj,
            [
                "phone",
                "telephone",
                "phonenumber",
                "contactnumber",
            ]
        )

        lat = find_value(
            obj,
            [
                "lat",
                "latitude",
            ]
        )

        lon = find_value(
            obj,
            [
                "lng",
                "lon",
                "longitude",
            ]
        )

        store_url = find_value(
            obj,
            [
                "url",
                "storeurl",
                "store_url",
                "locationurl",
                "branchurl",
                "detailurl",
                "detail_url",
                "link",
                "href",
            ]
        )

        store_url = normalize_url(
            store_url
        )

        if not is_usable_store_url(
            store_url
        ):

            store_url = ""

        # ----------------------------------------------------
        # Nested address
        # ----------------------------------------------------

        if isinstance(
            obj.get("address"),
            dict
        ):

            address_obj = obj.get(
                "address"
            )

            address = find_value(
                address_obj,
                [
                    "formatted",
                    "formattedaddress",
                    "streetAddress",
                    "address",
                ]
            )

            if not address:

                address = ", ".join(

                    str(x)

                    for x in [

                        address_obj.get(
                            "streetAddress"
                        ),

                        address_obj.get(
                            "addressLocality"
                        ),

                        address_obj.get(
                            "addressRegion"
                        ),

                    ]

                    if x

                )

        # ----------------------------------------------------
        # Nested location
        # ----------------------------------------------------

        if not address:

            location = obj.get(
                "location"
            )

            if isinstance(
                location,
                dict
            ):

                address = find_value(
                    location,
                    [
                        "address",
                        "formattedaddress",
                    ]
                )

                if not lat:

                    lat = find_value(
                        location,
                        [
                            "lat",
                            "latitude",
                        ]
                    )

                if not lon:

                    lon = find_value(
                        location,
                        [
                            "lng",
                            "longitude",
                        ]
                    )

        if not address:
            continue

        address_text = clean_text(
            address
        )

        if not looks_like_address(
            address_text
        ):

            continue

        identifying_fields = sum(

            bool(
                clean_text(x)
            )

            for x in [

                name,
                store_code,
                phone,
                lat,
                lon,

            ]

        )

        if identifying_fields < 2:
            continue

        ward, province = (
            parse_vietnam_address(
                address_text
            )
        )

        record = empty_record(
            brand,
            source_url
        )

        record["StoreCode"] = clean_text(
            store_code
        )

        record["StoreName"] = clean_text(
            name
        )

        record["Address"] = address_text

        record["Province"] = province

        record["Ward"] = ward

        record["Phone"] = clean_text(
            phone
        )

        record["Lat"] = normalize_coordinate(
            lat
        )

        record["Long"] = normalize_coordinate(
            lon
        )

        record["StoreURL"] = store_url

        record["Method"] = "API/JSON"

        record = fill_coordinates_from_url(
            record
        )

        records.append(
            record
        )

    return records


# ============================================================
# HTML TABLE
# ============================================================

def parse_tables(
    soup,
    brand,
    source_url
):

    records = []

    for table in soup.find_all(
        "table"
    ):

        rows = table.find_all(
            "tr"
        )

        if len(rows) < 2:
            continue

        headers = [

            clean_text(
                cell.get_text(
                    " ",
                    strip=True
                )
            ).lower()

            for cell in rows[0].find_all(
                [
                    "th",
                    "td"
                ]
            )

        ]

        if not headers:
            continue

        for row in rows[1:]:

            cells = [

                clean_text(
                    cell.get_text(
                        " ",
                        strip=True
                    )
                )

                for cell in row.find_all(
                    [
                        "td",
                        "th"
                    ]
                )

            ]

            if not cells:
                continue

            joined = " | ".join(
                cells
            )

            if not looks_like_address(
                joined
            ):

                continue

            record = empty_record(
                brand,
                source_url
            )

            for i, header in enumerate(
                headers
            ):

                if i >= len(cells):
                    continue

                value = cells[i]

                if any(
                    x in header
                    for x in [
                        "code",
                        "mã",
                    ]
                ):

                    record["StoreCode"] = value

                elif any(
                    x in header
                    for x in [
                        "store",
                        "cửa hàng",
                        "chi nhánh",
                        "branch",
                        "name",
                        "tên",
                    ]
                ):

                    record["StoreName"] = value

                elif any(
                    x in header
                    for x in [
                        "address",
                        "địa chỉ",
                        "location",
                    ]
                ):

                    record["Address"] = value

                elif any(
                    x in header
                    for x in [
                        "phone",
                        "tel",
                        "telephone",
                        "điện thoại",
                    ]
                ):

                    record["Phone"] = value

            if not record["Address"]:

                for cell in cells:

                    if looks_like_address(
                        cell
                    ):

                        record["Address"] = cell

                        break

            if not record["Address"]:
                continue

            for link in row.find_all(
                "a",
                href=True
            ):

                href = clean_text(
                    link.get(
                        "href",
                        ""
                    )
                )

                if not href:
                    continue

                full_url = urljoin(
                    source_url,
                    href
                )

                if not same_domain(
                    full_url,
                    source_url
                ):

                    continue

                if is_usable_store_url(
                    full_url
                ):

                    record["StoreURL"] = (
                        full_url
                    )

                    break

            ward, province = (
                parse_vietnam_address(
                    record["Address"]
                )
            )

            record["Province"] = province

            record["Ward"] = ward

            record["Phone"] = (
                record["Phone"]
                or extract_phone(
                    joined
                )
            )

            record["Method"] = (
                "HTML Table"
            )

            record = fill_coordinates_from_url(
                record
            )

            records.append(
                record
            )

    return records


# ============================================================
# GENERIC CARD
# ============================================================

def parse_store_cards(
    soup,
    brand,
    source_url
):

    records = []

    nodes = soup.find_all(
        [
            "article",
            "li",
        ]
    )

    for node in nodes:

        text = clean_text(
            node.get_text(
                " ",
                strip=True
            )
        )

        if not looks_like_address(
            text
        ):

            continue

        if len(text) > 1000:
            continue

        record = empty_record(
            brand,
            source_url
        )

        heading = node.find(
            [
                "h1",
                "h2",
                "h3",
                "h4",
                "h5",
                "strong",
            ]
        )

        if heading:

            record["StoreName"] = clean_text(
                heading.get_text(
                    " ",
                    strip=True
                )
            )

        record["Phone"] = extract_phone(
            text
        )

        address_element = node.find(
            "address"
        )

        if address_element:

            record["Address"] = clean_text(
                address_element.get_text(
                    " ",
                    strip=True
                )
            )

        else:

            lines = [

                clean_text(x)

                for x in node.stripped_strings

            ]

            address_lines = [

                line

                for line in lines

                if looks_like_address(
                    line
                )

            ]

            if address_lines:

                record["Address"] = ", ".join(
                    address_lines
                )

        if not record["Address"]:
            continue

        ward, province = (
            parse_vietnam_address(
                record["Address"]
            )
        )

        record["Province"] = province

        record["Ward"] = ward

        for link in node.find_all(
            "a",
            href=True
        ):

            href = clean_text(
                link.get(
                    "href",
                    ""
                )
            )

            if not href:
                continue

            full_url = urljoin(
                source_url,
                href
            )

            if not same_domain(
                full_url,
                source_url
            ):

                continue

            href_lower = href.lower()

            if any(
                keyword in href_lower
                for keyword in STORE_KEYWORDS
            ):

                if is_usable_store_url(
                    full_url
                ):

                    record["StoreURL"] = (
                        full_url
                    )

                    break

        if not (
            record["StoreName"]
            or record["Phone"]
        ):

            continue

        record["Method"] = "HTML Card"

        record = fill_coordinates_from_url(
            record
        )

        records.append(
            record
        )

    return records


# ============================================================
# PIZZA HUT
# ============================================================

def parse_pizza_hut(
    soup,
    brand,
    source_url
):

    records = []

    candidates = []

    for element in soup.find_all(
        [
            "div",
            "section",
            "a",
            "span",
            "p",
        ]
    ):

        text = clean_text(
            element.get_text(
                " ",
                strip=True
            )
        )

        if not text:
            continue

        lower = text.lower()

        if "pizza hut" not in lower:
            continue

        if not looks_like_address(
            text
        ):

            continue

        if len(text) > 700:
            continue

        candidates.append(
            element
        )

    unique_candidates = []

    for element in candidates:

        has_candidate_child = False

        for child in element.find_all(
            [
                "div",
                "section",
                "a",
                "span",
                "p",
            ]
        ):

            if child is element:
                continue

            child_text = clean_text(
                child.get_text(
                    " ",
                    strip=True
                )
            )

            if (
                "pizza hut"
                in child_text.lower()
                and looks_like_address(
                    child_text
                )
                and len(child_text) <= 700
            ):

                has_candidate_child = True

                break

        if not has_candidate_child:

            unique_candidates.append(
                element
            )

    for node in unique_candidates:

        text = clean_text(
            node.get_text(
                " ",
                strip=True
            )
        )

        if not text:
            continue

        store_name = ""

        heading = node.find(
            [
                "h1",
                "h2",
                "h3",
                "h4",
                "h5",
                "strong",
                "b",
            ]
        )

        if heading:

            heading_text = clean_text(
                heading.get_text(
                    " ",
                    strip=True
                )
            )

            if (
                "pizza hut"
                in heading_text.lower()
            ):

                store_name = heading_text

        if not store_name:

            lines = [

                clean_text(x)

                for x in node.stripped_strings

                if clean_text(x)

            ]

            for line in lines:

                if (
                    "pizza hut"
                    in line.lower()
                ):

                    store_name = line

                    break

        if not store_name:

            match = re.search(
                r"(Pizza\s+Hut[^\n,|]{0,100})",
                text,
                flags=re.IGNORECASE
            )

            if match:

                store_name = clean_text(
                    match.group(1)
                )

        address = ""

        address_element = node.find(
            "address"
        )

        if address_element:

            address = clean_text(
                address_element.get_text(
                    " ",
                    strip=True
                )
            )

        if not address:

            lines = [

                clean_text(x)

                for x in node.stripped_strings

                if clean_text(x)

            ]

            address_candidates = [

                line

                for line in lines

                if looks_like_address(
                    line
                )

                and
                "pizza hut"
                not in line.lower()

            ]

            if address_candidates:

                address = max(
                    address_candidates,
                    key=len
                )

        if not address:

            parts = [

                clean_text(x)

                for x in text.split(
                    " | "
                )

                if clean_text(x)

            ]

            address_candidates = [

                part

                for part in parts

                if looks_like_address(
                    part
                )

            ]

            if address_candidates:

                address = max(
                    address_candidates,
                    key=len
                )

        if not address:
            continue

        if len(address) > 500:
            continue

        phone = extract_phone(
            text
        )

        ward, province = (
            parse_vietnam_address(
                address
            )
        )

        record = empty_record(
            brand,
            source_url
        )

        record["StoreName"] = store_name

        record["Address"] = address

        record["Province"] = province

        record["Ward"] = ward

        record["Phone"] = phone

        record["Method"] = (
            "Pizza Hut HTML"
        )

        for link in node.find_all(
            "a",
            href=True
        ):

            href = clean_text(
                link.get(
                    "href",
                    ""
                )
            )

            full_url = urljoin(
                source_url,
                href
            )

            if not same_domain(
                full_url,
                source_url
            ):

                continue

            if is_usable_store_url(
                full_url
            ):

                record["StoreURL"] = (
                    full_url
                )

                break

        if not record["StoreName"]:
            continue

        if (
            "pizza hut"
            not in record["StoreName"].lower()
        ):

            continue

        record = fill_coordinates_from_url(
            record
        )

        records.append(
            record
        )

    return records


# ============================================================
# PIZZA HUT URL EXPANSION
# ============================================================

def get_pizza_hut_urls(
    start_url
):

    parsed = urlparse(
        start_url
    )

    hostname = (
        parsed.netloc
        .lower()
        .replace(
            "www.",
            ""
        )
    )

    path = parsed.path.lower()

    if (
        hostname != "pizzahut.vn"
        or "store-location" not in path
    ):

        return [
            start_url
        ]

    urls = []

    for area in [
        "north",
        "central",
        "south",
    ]:

        query = parse_qs(
            parsed.query,
            keep_blank_values=True
        )

        query["area"] = [
            area
        ]

        new_query = urlencode(
            query,
            doseq=True
        )

        new_url = urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                parsed.params,
                new_query,
                parsed.fragment,
            )
        )

        urls.append(
            new_url
        )

    return urls


# ============================================================
# CRAWLER
# ============================================================

async def crawl_website(
    start_url,
    max_pages
):

    brand = get_brand_from_url(
        start_url
    )

    initial_urls = get_pizza_hut_urls(
        start_url
    )

    visited = set()

    queue = list(
        initial_urls
    )

    all_records = []

    crawled_pages = []

    debug_logs = []

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True
        )

        context = await browser.new_context(

            locale="vi-VN",

            user_agent=(
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/130 Safari/537.36"
            ),

        )

        page = await context.new_page()

        current_page_api_records = []

        async def handle_response(
            response
        ):

            try:

                content_type = (
                    response.headers
                    .get(
                        "content-type",
                        ""
                    )
                    .lower()
                )

                response_url = response.url

                lower_url = (
                    response_url.lower()
                )

                is_json = (

                    "application/json"
                    in content_type

                    or lower_url.endswith(
                        ".json"
                    )

                    or "/api/" in lower_url

                    or "graphql" in lower_url

                    or "ajax" in lower_url

                )

                if not is_json:
                    return

                ignored = [

                    "analytics",
                    "google-analytics",
                    "facebook",
                    "doubleclick",
                    "hotjar",
                    "tracking",
                    "pixel",

                ]

                if any(
                    x in lower_url
                    for x in ignored
                ):

                    return

                try:

                    data = await response.json()

                except Exception:

                    return

                parsed = parse_json_response(
                    data,
                    brand,
                    response_url
                )

                if parsed:

                    current_page_api_records.extend(
                        parsed
                    )

            except Exception:

                pass

        page.on(
            "response",
            handle_response
        )

        while (
            queue
            and len(visited) < max_pages
        ):

            url = queue.pop(
                0
            )

            if url in visited:
                continue

            if not same_domain(
                url,
                start_url
            ):

                continue

            visited.add(
                url
            )

            current_page_api_records.clear()

            debug_logs.append(
                f"OPEN: {url}"
            )

            navigation_success = False

            try:

                response = await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=45000
                )

                navigation_success = True

                if response:

                    debug_logs.append(
                        f"HTTP {response.status}: {url}"
                    )

            except Exception as first_error:

                debug_logs.append(
                    "goto domcontentloaded failed: "
                    f"{first_error}"
                )

                try:

                    response = await page.goto(
                        url,
                        wait_until="commit",
                        timeout=30000
                    )

                    navigation_success = True

                    if response:

                        debug_logs.append(
                            f"HTTP {response.status}: {url}"
                        )

                except Exception as second_error:

                    debug_logs.append(
                        "goto commit failed: "
                        f"{second_error}"
                    )

            if not navigation_success:
                continue

            await page.wait_for_timeout(
                3000
            )

            for _ in range(8):

                try:

                    await page.mouse.wheel(
                        0,
                        1800
                    )

                    await page.wait_for_timeout(
                        500
                    )

                except Exception:

                    break

            # ------------------------------------------------
            # Store/location buttons
            # ------------------------------------------------

            try:

                elements = page.locator(
                    "button, a"
                )

                count = await elements.count()

                for i in range(
                    min(
                        count,
                        150
                    )
                ):

                    element = elements.nth(
                        i
                    )

                    try:

                        text = clean_text(
                            await element.inner_text()
                        ).lower()

                        if any(
                            keyword in text
                            for keyword in STORE_KEYWORDS
                        ):

                            await element.click(
                                timeout=1200
                            )

                            await page.wait_for_timeout(
                                1000
                            )

                    except Exception:

                        pass

            except Exception:

                pass

            await page.wait_for_timeout(
                2500
            )

            # =================================================
            # API
            # =================================================

            if current_page_api_records:

                page_records = dedupe_records(
                    current_page_api_records
                )

                all_records.extend(
                    page_records
                )

                crawled_pages.append(
                    url
                )

                debug_logs.append(
                    f"API/JSON → "
                    f"{len(page_records)} stores"
                )

            else:

                try:

                    html = await page.content()

                except Exception as error:

                    debug_logs.append(
                        "page.content failed: "
                        f"{error}"
                    )

                    continue

                soup = BeautifulSoup(
                    html,
                    "html.parser"
                )

                page_records = []

                table_records = parse_tables(
                    soup,
                    brand,
                    url
                )

                if table_records:

                    page_records.extend(
                        table_records
                    )

                    debug_logs.append(
                        f"HTML Table → "
                        f"{len(table_records)} stores"
                    )

                else:

                    if brand == "PIZZA HUT":

                        brand_records = (
                            parse_pizza_hut(
                                soup,
                                brand,
                                url
                            )
                        )

                        if brand_records:

                            page_records.extend(
                                brand_records
                            )

                            debug_logs.append(
                                "Pizza Hut HTML → "
                                f"{len(brand_records)} stores"
                            )

                    if not page_records:

                        card_records = (
                            parse_store_cards(
                                soup,
                                brand,
                                url
                            )
                        )

                        if card_records:

                            page_records.extend(
                                card_records
                            )

                            debug_logs.append(
                                "HTML Card → "
                                f"{len(card_records)} stores"
                            )

                page_records = dedupe_records(
                    page_records
                )

                all_records.extend(
                    page_records
                )

                crawled_pages.append(
                    url
                )

                if not page_records:

                    debug_logs.append(
                        f"NO STORE FOUND → {url}"
                    )

            # =================================================
            # DISCOVER INTERNAL STORE LINKS
            # =================================================

            try:

                links = await page.locator(
                    "a[href]"
                ).evaluate_all(
                    """
                    els => els.map(a => ({
                        href: a.href,
                        text: (a.innerText || '').trim()
                    }))
                    """
                )

            except Exception:

                links = []

            for item in links:

                href = item.get(
                    "href",
                    ""
                )

                text = clean_text(
                    item.get(
                        "text",
                        ""
                    )
                ).lower()

                if not looks_like_http_url(
                    href
                ):

                    continue

                if not same_domain(
                    href,
                    start_url
                ):

                    continue

                combined = (
                    href.lower()
                    + " "
                    + text
                )

                if any(
                    keyword in combined
                    for keyword in STORE_KEYWORDS
                ):

                    if (
                        href not in visited
                        and href not in queue
                    ):

                        queue.append(
                            href
                        )

        await browser.close()

    final_records = dedupe_records(
        all_records
    )

    return (
        final_records,
        crawled_pages,
        debug_logs
    )


# ============================================================
# SYNC
# ============================================================

import inspect


def extract_store_data(
    url,
    max_pages,
):
    """
    Entry point cho app_new.py.

    KFC:
        Dùng crawler riêng trong brands/kfc.py.

    Các brand khác:
        Dùng generic crawler hiện tại.

    Return:
        (
            records,
            crawled_pages,
            debug_logs
        )
    """

    brand = get_brand_from_url(url)

    # ========================================================
    # KFC
    # ========================================================

    if brand == "KFC":

        from brands.kfc import crawl_kfc

        print("DEBUG KFC: calling crawl_kfc()")

        # crawl_kfc() có thể là async function
        result = crawl_kfc(
            search_provinces=None
        )

        print(
            "DEBUG KFC: result type =",
            type(result)
        )

        # ----------------------------------------------------
        # Nếu là coroutine -> chạy coroutine
        # ----------------------------------------------------

        if inspect.isawaitable(result):

            print(
                "DEBUG KFC: result is awaitable -> asyncio.run()"
            )

            result = asyncio.run(result)

            print(
                "DEBUG KFC: awaited result type =",
                type(result)
            )

        # ----------------------------------------------------
        # Không có dữ liệu
        # ----------------------------------------------------

        if result is None:

            print(
                "DEBUG KFC: result is None"
            )

            records = []

        # ----------------------------------------------------
        # Nếu sau khi await vẫn là coroutine
        # ----------------------------------------------------

        elif inspect.isawaitable(result):

            raise TypeError(
                "KFC crawler returned a coroutine after await"
            )

        # ----------------------------------------------------
        # Nếu là list
        # ----------------------------------------------------

        elif isinstance(result, list):

            records = result

        # ----------------------------------------------------
        # Nếu là tuple
        #
        # Một số crawler có thể trả:
        #
        # (records, pages, logs)
        # ----------------------------------------------------

        elif isinstance(result, tuple):

            if len(result) == 3:

                records = result[0]

            else:

                records = list(result)

        # ----------------------------------------------------
        # Các iterable khác
        # ----------------------------------------------------

        else:

            try:

                records = list(result)

            except TypeError:

                raise TypeError(
                    "KFC crawler returned unsupported type: "
                    + str(type(result))
                )

        # ----------------------------------------------------
        # Safety check
        # ----------------------------------------------------

        if records is None:
            records = []

        if inspect.isawaitable(records):

            raise TypeError(
                "KFC records is still a coroutine"
            )

        if not isinstance(records, list):

            records = list(records)

        print(
            "DEBUG KFC: final records =",
            len(records)
        )

        return (
            records,
            [],
            [],
        )

    # ========================================================
    # DEDICATED RETAIL CRAWLERS
    # ========================================================
    # These brands already have dedicated parsers in
    # brands/retail.py. Do NOT send them through the generic
    # crawler, because their store locators are JS-driven and
    # often do not expose store data as normal HTML links/cards.

    retail_crawlers = {
        "THE GIOI DI DONG": "crawl_thegioididong",
        "DIEN MAY XANH": "crawl_dienmayxanh",
        "FPT SHOP": "crawl_fptshop",
        "NHA THUOC LONG CHAU": "crawl_longchau",
        "PHARMACITY": "crawl_pharmacity",
        "BACH HOA XANH": "crawl_bachhoaxanh",
    }

    crawler_name = retail_crawlers.get(brand)

    if crawler_name:

        from brands import retail

        print(
            f"DEBUG RETAIL: brand={brand}, "
            f"crawler={crawler_name}"
        )

        crawler_func = getattr(
            retail,
            crawler_name,
            None,
        )

        if crawler_func is None:
            raise AttributeError(
                f"Retail crawler not found: {crawler_name}"
            )

        # Pass the URL selected/found by the user into the
        # dedicated retail crawler. Each retail crawler keeps
        # its own default URL when start_url is omitted.
        try:
            result = crawler_func(start_url=url)
        except TypeError:
            # Backward compatibility for a crawler that still
            # exposes the old no-argument signature.
            result = crawler_func()

        if inspect.isawaitable(result):
            result = asyncio.run(result)

        if result is None:
            return [], [], [
                f"Retail crawler returned no result: {brand}"
            ]

        # Dedicated retail crawlers return:
        # (records, crawled_pages, debug_logs)
        if isinstance(result, tuple):
            if len(result) == 3:
                records, crawled_pages, debug_logs = result
            elif len(result) == 1:
                records = result[0]
                crawled_pages = []
                debug_logs = []
            else:
                records = list(result)
                crawled_pages = []
                debug_logs = []
        elif isinstance(result, list):
            records = result
            crawled_pages = []
            debug_logs = []
        else:
            records = list(result)
            crawled_pages = []
            debug_logs = []

        records = records or []

        # Keep the dedicated parser's Brand value. This matters
        # for MWG because TGDD and DMX can share locator pages.
        for record in records:
            if isinstance(record, dict) and not record.get("Brand"):
                record["Brand"] = brand

        print(
            f"DEBUG RETAIL: final records={len(records)}"
        )

        return (
            records,
            crawled_pages or [],
            debug_logs or [],
        )

    # ========================================================
    # OTHER BRANDS
    # ========================================================
    # Preserve the existing generic crawler for all brands that
    # do not have a dedicated parser.

    return asyncio.run(
        crawl_website(
            url,
            max_pages,
        )
    )


# ============================================================
# GENERIC ASYNC
# ============================================================

async def crawl_generic_async(
    brand,
    urls,
    max_pages,
):

    all_records = []
    all_pages = []
    all_logs = []

    for url in urls:

        records, pages, logs = await crawl_website(
            url,
            max_pages,
        )

        for record in records:

            if isinstance(record, dict):

                record["Brand"] = brand

        all_records.extend(
            records
        )

        all_pages.extend(
            pages
        )

        all_logs.extend(
            logs
        )

    return (
        dedupe_records(
            all_records
        ),
        all_pages,
        all_logs,
    )


# ============================================================
# GENERIC SYNC
# ============================================================

def crawl_generic(
    brand,
    urls,
    max_pages,
):

    return asyncio.run(
        crawl_generic_async(
            brand,
            urls,
            max_pages,
        )
    )