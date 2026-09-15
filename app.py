import asyncio
import json
import re
from datetime import datetime
from io import BytesIO
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse

import pandas as pd
import streamlit as st
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright


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

ADDRESS_KEYWORDS = [
    "address",
    "địa chỉ",
    "dia chi",
    "street",
    "road",
    "đường",
    "phường",
    "phuong",
    "ward",
    "quận",
    "quan",
    "district",
    "huyện",
    "huyen",
    "province",
    "tỉnh",
    "tinh",
    "city",
    "thành phố",
    "thanh pho",
    "hồ chí minh",
    "ho chi minh",
    "hà nội",
    "ha noi",
    "đà nẵng",
    "da nang",
]

PHONE_PATTERN = re.compile(
    r"(?:\+84|0)"
    r"(?:\s*[\(\[]?\d{2,3}[\)\]]?)?"
    r"[\s.\-]?"
    r"\d"
    r"[\d\s()./\-]{6,}"
)


# ============================================================
# BASIC HELPERS
# ============================================================

def clean_text(value):
    if value is None:
        return ""

    if isinstance(value, (dict, list)):
        return json.dumps(
            value,
            ensure_ascii=False
        )

    return re.sub(
        r"\s+",
        " ",
        str(value)
    ).strip()


def normalize_url(url):
    """
    Convert input to clean URL.

    Important:
    Do NOT remove query string such as:
    ?area=north
    """
    url = clean_text(url)

    if not url:
        return ""

    # Remove accidental Markdown link syntax
    if url.startswith("[") and "](" in url:
        match = re.search(
            r"\((https?://[^)]+)\)",
            url
        )
        if match:
            url = match.group(1)

    if not url.startswith(
        ("http://", "https://")
    ):
        url = "https://" + url

    return url.strip()


def normalize_for_compare(value):
    value = clean_text(value).lower()

    # Remove accents only for comparison
    import unicodedata

    value = unicodedata.normalize(
        "NFD",
        value
    )

    value = "".join(
        ch
        for ch in value
        if unicodedata.category(ch) != "Mn"
    )

    value = re.sub(
        r"\s+",
        " ",
        value
    )

    return value.strip()


def same_domain(url1, url2):
    domain1 = (
        urlparse(url1)
        .netloc
        .lower()
        .replace("www.", "")
    )

    domain2 = (
        urlparse(url2)
        .netloc
        .lower()
        .replace("www.", "")
    )

    return domain1 == domain2


def looks_like_http_url(url):
    return clean_text(url).startswith(
        (
            "http://",
            "https://"
        )
    )


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
# ADDRESS
# ============================================================

def looks_like_address(text):
    text = clean_text(text).lower()

    if len(text) < 15:
        return False

    score = 0

    for keyword in ADDRESS_KEYWORDS:
        if keyword in text:
            score += 1

    if re.search(
        r"\b\d{1,5}\s+\S+",
        text
    ):
        score += 1

    # Comma-separated Vietnamese addresses
    if text.count(",") >= 1:
        score += 1

    return score >= 1


def parse_vietnam_address(address):
    """
    Extract Ward / Province from Vietnamese address.

    Examples:

    Số 1 đường số 17A, Khu phố 11, Phường An Lạc,
    Thành phố Hồ Chí Minh

    -> Ward     = Phường An Lạc
    -> Province = Thành phố Hồ Chí Minh

    Another example:

    ... Phường Tiền Châu, Thành Phố Phúc Yên,
    Tỉnh Vĩnh Phúc

    -> Ward     = Phường Tiền Châu
    -> Province = Tỉnh Vĩnh Phúc

    We therefore DO NOT simply take second-from-last
    as Ward.
    """

    address = clean_text(address)

    if not address:
        return "", ""

    parts = [
        clean_text(x)
        for x in address.split(",")
        if clean_text(x)
    ]

    if not parts:
        return "", ""

    # --------------------------------------------------------
    # Province
    # --------------------------------------------------------

    province = ""

    province_patterns = [
        r"\btỉnh\b",
        r"\bthành phố\b",
        r"\bthanh pho\b",
        r"\btp\.?\b",
        r"\btp\b",
        r"\bcity\b",
    ]

    # Search from right to left.
    # Usually province/city is near the end.
    for part in reversed(parts):
        lower = normalize_for_compare(part)

        if any(
            re.search(pattern, lower)
            for pattern in province_patterns
        ):
            province = part
            break

    # If no explicit province keyword:
    # last component is still used.
    if not province:
        province = parts[-1]

    # --------------------------------------------------------
    # Ward
    # --------------------------------------------------------

    ward = ""

    ward_patterns = [
        r"\bphường\b",
        r"\bphuong\b",
        r"\bp\.\s*",
        r"\bward\b",
        r"\bxã\b",
        r"\bxa\b",
        r"\bcommune\b",
        r"\bthị trấn\b",
        r"\bthi tran\b",
    ]

    # Search from right to left,
    # but do not use province itself.
    province_index = len(parts) - 1

    for i in range(
        len(parts) - 1,
        -1,
        -1
    ):
        part = parts[i]

        if (
            province
            and normalize_for_compare(part)
            == normalize_for_compare(province)
        ):
            continue

        lower = normalize_for_compare(part)

        if any(
            re.search(pattern, lower)
            for pattern in ward_patterns
        ):
            ward = part
            break

    # Fallback:
    # If no explicit ward keyword exists,
    # use component immediately before province.
    if not ward and len(parts) >= 2:
        for i in range(
            len(parts) - 1,
            -1,
            -1
        ):
            if normalize_for_compare(parts[i]) != normalize_for_compare(province):
                ward = parts[i]
                break

    return ward, province


# ============================================================
# PHONE
# ============================================================

def extract_phone(text):
    text = clean_text(text)

    matches = PHONE_PATTERN.findall(text)

    if not matches:
        return ""

    result = []

    for match in matches:
        value = clean_text(match)

        digits = re.sub(
            r"\D",
            "",
            value
        )

        if len(digits) >= 9:
            result.append(value)

    return " / ".join(
        dict.fromkeys(result)
    )


def normalize_phone(phone):
    phone = clean_text(phone)

    if not phone:
        return ""

    digits = re.sub(
        r"\D",
        "",
        phone
    )

    if digits.startswith("84"):
        digits = "0" + digits[2:]

    return digits


# ============================================================
# COORDINATE
# ============================================================

def normalize_coordinate(value):
    value = clean_text(value)

    if not value:
        return ""

    try:
        number = float(value)
        return f"{number:.5f}"
    except Exception:
        return ""


# ============================================================
# EMPTY RECORD
# ============================================================

def empty_record(
    brand,
    source_url
):
    return {
        "Brand": brand,
        "StoreCode": "",
        "StoreName": "",
        "Address": "",
        "Province": "",
        "Ward": "",
        "Phone": "",
        "Lat": "",
        "Long": "",
        "StoreURL": "",
        "SourceURL": source_url,
        "Method": "",
    }


# ============================================================
# JSON / API
# ============================================================

def flatten_json_objects(obj):
    result = []

    if isinstance(obj, dict):
        result.append(obj)

        for value in obj.values():
            if isinstance(
                value,
                (dict, list)
            ):
                result.extend(
                    flatten_json_objects(value)
                )

    elif isinstance(obj, list):
        for item in obj:
            if isinstance(
                item,
                (dict, list)
            ):
                result.extend(
                    flatten_json_objects(item)
                )

    return result


def find_value(
    obj,
    possible_keys
):
    if not isinstance(
        obj,
        dict
    ):
        return ""

    normalized = {}

    for key, value in obj.items():

        normalized_key = (
            str(key)
            .lower()
            .replace("_", "")
            .replace("-", "")
            .replace(" ", "")
        )

        normalized[normalized_key] = value

    for key in possible_keys:

        normalized_key = (
            key.lower()
            .replace("_", "")
            .replace("-", "")
            .replace(" ", "")
        )

        if normalized_key in normalized:

            value = normalized[
                normalized_key
            ]

            if isinstance(
                value,
                (
                    str,
                    int,
                    float
                )
            ):
                return value

    return ""


def parse_json_response(
    data,
    brand,
    source_url
):
    records = []

    objects = flatten_json_objects(data)

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

        # ----------------------------------------------------
        # Need at least 2 identifying fields
        # ----------------------------------------------------

        identifying_fields = sum(
            bool(clean_text(x))
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

        ward, province = parse_vietnam_address(
            address_text
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

        record["Method"] = "API/JSON"

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

    for table in soup.find_all("table"):

        rows = table.find_all("tr")

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
                ["th", "td"]
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
                    ["td", "th"]
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

            # If header did not identify address,
            # find address-looking cell.
            if not record["Address"]:

                for cell in cells:

                    if looks_like_address(cell):
                        record["Address"] = cell
                        break

            if not record["Address"]:
                continue

            ward, province = parse_vietnam_address(
                record["Address"]
            )

            record["Province"] = province
            record["Ward"] = ward

            record["Method"] = "HTML Table"

            records.append(
                record
            )

    return records


# ============================================================
# GENERIC HTML STORE CARDS
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

        if not looks_like_address(text):
            continue

        if len(text) > 1000:
            continue

        record = empty_record(
            brand,
            source_url
        )

        # ----------------------------------------------------
        # Store name
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # Phone
        # ----------------------------------------------------

        record["Phone"] = extract_phone(
            text
        )

        # ----------------------------------------------------
        # Address
        # ----------------------------------------------------

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

            address_lines = []

            for line in lines:

                if looks_like_address(line):
                    address_lines.append(line)

            if address_lines:

                record["Address"] = ", ".join(
                    address_lines
                )

        if not record["Address"]:
            continue

        # ----------------------------------------------------
        # Ward / Province
        # ----------------------------------------------------

        ward, province = parse_vietnam_address(
            record["Address"]
        )

        record["Province"] = province
        record["Ward"] = ward

        # ----------------------------------------------------
        # Store URL
        # ----------------------------------------------------

        for link in node.find_all(
            "a",
            href=True
        ):

            href = link.get(
                "href",
                ""
            )

            if any(
                keyword in href.lower()
                for keyword in STORE_KEYWORDS
            ):

                record["StoreURL"] = urljoin(
                    source_url,
                    href
                )

                break

        # ----------------------------------------------------
        # Validation
        # ----------------------------------------------------

        if not (
            record["StoreName"]
            or record["Phone"]
        ):
            continue

        record["Method"] = "HTML Card"

        records.append(
            record
        )

    return records


# ============================================================
# PIZZA HUT PARSER
# ============================================================

def parse_pizza_hut(
    soup,
    brand,
    source_url
):
    """
    Pizza Hut specific parser.

    Pizza Hut store-location pages do not necessarily expose
    stores as <article> or <li>. The store information is
    embedded in the rendered HTML.

    We look for blocks containing:
        - Pizza Hut store name
        - Vietnamese address
    """

    records = []

    # --------------------------------------------------------
    # First strategy:
    # Look for elements containing "Pizza Hut"
    # and an address.
    # --------------------------------------------------------

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

        if not looks_like_address(text):
            continue

        if len(text) > 700:
            continue

        candidates.append(
            element
        )

    # --------------------------------------------------------
    # Prefer the smallest useful DOM blocks.
    # Remove parents that contain another candidate.
    # --------------------------------------------------------

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
                "pizza hut" in child_text.lower()
                and looks_like_address(child_text)
                and len(child_text) <= 700
            ):
                has_candidate_child = True
                break

        if not has_candidate_child:
            unique_candidates.append(
                element
            )

    # --------------------------------------------------------
    # Parse candidates
    # --------------------------------------------------------

    for node in unique_candidates:

        text = clean_text(
            node.get_text(
                " ",
                strip=True
            )
        )

        if not text:
            continue

        # ----------------------------------------------------
        # Store name
        # ----------------------------------------------------

        store_name = ""

        # Heading first
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

            if "pizza hut" in heading_text.lower():
                store_name = heading_text

        # Search text lines
        if not store_name:

            lines = [
                clean_text(x)
                for x in node.stripped_strings
                if clean_text(x)
            ]

            for line in lines:

                if "pizza hut" in line.lower():
                    store_name = line
                    break

        if not store_name:

            # Fallback:
            # find "Pizza Hut ..." phrase
            match = re.search(
                r"(Pizza\s+Hut[^\n,|]{0,100})",
                text,
                flags=re.IGNORECASE
            )

            if match:
                store_name = clean_text(
                    match.group(1)
                )

        # ----------------------------------------------------
        # Address
        # ----------------------------------------------------

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
                if looks_like_address(line)
                and "pizza hut" not in line.lower()
            ]

            if address_candidates:

                # Usually the longest address-like line
                address = max(
                    address_candidates,
                    key=len
                )

        if not address:

            # Search full text for a substring
            # containing Vietnamese location keywords.
            parts = [
                clean_text(x)
                for x in text.split(" | ")
                if clean_text(x)
            ]

            address_candidates = [
                part
                for part in parts
                if looks_like_address(part)
            ]

            if address_candidates:
                address = max(
                    address_candidates,
                    key=len
                )

        if not address:
            continue

        # ----------------------------------------------------
        # Avoid obviously huge container blocks
        # ----------------------------------------------------

        if len(address) > 500:
            continue

        # ----------------------------------------------------
        # Phone
        # ----------------------------------------------------

        phone = extract_phone(
            text
        )

        ward, province = parse_vietnam_address(
            address
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
        record["Method"] = "Pizza Hut HTML"

        # ----------------------------------------------------
        # Store URL
        # ----------------------------------------------------

        for link in node.find_all(
            "a",
            href=True
        ):

            href = link.get(
                "href",
                ""
            )

            if href.startswith(
                ("http://", "https://", "/")
            ):

                full_url = urljoin(
                    source_url,
                    href
                )

                if same_domain(
                    full_url,
                    source_url
                ):
                    record["StoreURL"] = full_url
                    break

        # ----------------------------------------------------
        # Validation
        # ----------------------------------------------------

        if not record["StoreName"]:
            continue

        # Must actually look like Pizza Hut store
        if "pizza hut" not in record["StoreName"].lower():
            continue

        records.append(
            record
        )

    return records


# ============================================================
# DEDUPE
# ============================================================

def dedupe_records(records):

    if not records:
        return []

    method_priority = {
        "API/JSON": 1,
        "HTML Table": 2,
        "Pizza Hut HTML": 3,
        "HTML Card": 4,
    }

    cleaned = []

    for record in records:

        record = {
            key: clean_text(value)
            for key, value in record.items()
        }

        if not record.get("Address"):
            continue

        record["_Priority"] = method_priority.get(
            record.get("Method", ""),
            99
        )

        cleaned.append(
            record
        )

    cleaned.sort(
        key=lambda x: x.get(
            "_Priority",
            99
        )
    )

    result = []

    seen_codes = set()
    seen_phones = set()
    seen_coordinates = set()
    seen_name_address = set()
    seen_addresses = set()

    def norm(value):
        return normalize_for_compare(
            value
        )

    for record in cleaned:

        brand = norm(
            record.get("Brand")
        )

        code = norm(
            record.get("StoreCode")
        )

        name = norm(
            record.get("StoreName")
        )

        address = norm(
            record.get("Address")
        )

        phone = normalize_phone(
            record.get("Phone")
        )

        lat = normalize_coordinate(
            record.get("Lat")
        )

        lon = normalize_coordinate(
            record.get("Long")
        )

        duplicate = False

        # ----------------------------------------------------
        # Store code
        # ----------------------------------------------------

        if code:

            key = (
                brand,
                code
            )

            if key in seen_codes:
                duplicate = True

        # ----------------------------------------------------
        # Phone
        # ----------------------------------------------------

        if (
            not duplicate
            and phone
        ):

            key = (
                brand,
                phone
            )

            if key in seen_phones:
                duplicate = True

        # ----------------------------------------------------
        # Coordinates
        # ----------------------------------------------------

        if (
            not duplicate
            and lat
            and lon
        ):

            key = (
                brand,
                lat,
                lon
            )

            if key in seen_coordinates:
                duplicate = True

        # ----------------------------------------------------
        # Name + address
        # ----------------------------------------------------

        if (
            not duplicate
            and name
            and address
        ):

            key = (
                brand,
                name,
                address
            )

            if key in seen_name_address:
                duplicate = True

        # ----------------------------------------------------
        # Address
        # ----------------------------------------------------

        if (
            not duplicate
            and address
        ):

            key = (
                brand,
                address
            )

            if key in seen_addresses:
                duplicate = True

        if duplicate:
            continue

        # ----------------------------------------------------
        # Save keys
        # ----------------------------------------------------

        if code:
            seen_codes.add(
                (
                    brand,
                    code
                )
            )

        if phone:
            seen_phones.add(
                (
                    brand,
                    phone
                )
            )

        if lat and lon:
            seen_coordinates.add(
                (
                    brand,
                    lat,
                    lon
                )
            )

        if name and address:
            seen_name_address.add(
                (
                    brand,
                    name,
                    address
                )
            )

        if address:
            seen_addresses.add(
                (
                    brand,
                    address
                )
            )

        result.append(
            record
        )

    for record in result:

        record.pop(
            "_Priority",
            None
        )

    return result


# ============================================================
# PIZZA HUT URL EXPANSION
# ============================================================

def get_pizza_hut_urls(start_url):
    """
    If user enters any Pizza Hut store-location URL,
    automatically generate:

        north
        central
        south

    If URL is not store-location, keep original URL only.
    """

    parsed = urlparse(
        start_url
    )

    hostname = (
        parsed.netloc
        .lower()
        .replace("www.", "")
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
            parsed.query
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
# PLAYWRIGHT CRAWLER
#
# EXTRACTION PRIORITY:
#
# 1. API / JSON
# 2. HTML TABLE
# 3. BRAND-SPECIFIC HTML
# 4. HTML CARD
#
# IMPORTANT:
# If API/JSON finds stores on a page,
# HTML methods are NOT used on that page.
# ============================================================

async def crawl_website(
    start_url,
    max_pages
):

    brand = get_brand_from_url(
        start_url
    )

    # --------------------------------------------------------
    # Pizza Hut special:
    # automatically generate 3 regional pages.
    # --------------------------------------------------------

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

        # ----------------------------------------------------
        # API records captured during current page
        # ----------------------------------------------------

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

                lower_url = response_url.lower()

                is_json = (
                    "application/json"
                    in content_type
                    or lower_url.endswith(".json")
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

        # ====================================================
        # PAGE LOOP
        # ====================================================

        while (
            queue
            and len(visited) < max_pages
        ):

            url = queue.pop(0)

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

            # Reset API results
            current_page_api_records.clear()

            debug_logs.append(
                f"OPEN: {url}"
            )

            # ------------------------------------------------
            # Navigate
            # ------------------------------------------------

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
                    f"goto domcontentloaded failed: {first_error}"
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
                        f"goto commit failed: {second_error}"
                    )

            if not navigation_success:

                continue

            # ------------------------------------------------
            # Wait for JS / API
            # ------------------------------------------------

            await page.wait_for_timeout(
                3000
            )

            # ------------------------------------------------
            # Scroll
            # ------------------------------------------------

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
            # Click Store / Location buttons
            # ------------------------------------------------

            try:

                elements = page.locator(
                    "button, a"
                )

                count = await elements.count()

                for i in range(
                    min(count, 150)
                ):

                    element = elements.nth(i)

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

            # ------------------------------------------------
            # Give API calls time to finish
            # ------------------------------------------------

            await page.wait_for_timeout(
                2500
            )

            # =================================================
            # PRIORITY 1: API / JSON
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
                    f"API/JSON → {len(page_records)} stores"
                )

                # IMPORTANT:
                #
                # DO NOT parse HTML Table
                # DO NOT parse Brand HTML
                # DO NOT parse HTML Card
                #
                # because API already worked.

            else:

                # =============================================
                # Get rendered HTML
                # =============================================

                try:

                    html = await page.content()

                except Exception as error:

                    debug_logs.append(
                        f"page.content failed: {error}"
                    )

                    continue

                soup = BeautifulSoup(
                    html,
                    "html.parser"
                )

                page_records = []

                # =============================================
                # PRIORITY 2: HTML TABLE
                # =============================================

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
                        f"HTML Table → {len(table_records)} stores"
                    )

                else:

                    # =========================================
                    # PRIORITY 3: BRAND-SPECIFIC
                    # =========================================

                    if brand == "PIZZA HUT":

                        brand_records = parse_pizza_hut(
                            soup,
                            brand,
                            url
                        )

                        if brand_records:

                            page_records.extend(
                                brand_records
                            )

                            debug_logs.append(
                                f"Pizza Hut HTML → {len(brand_records)} stores"
                            )

                    # =========================================
                    # PRIORITY 4: GENERIC HTML CARD
                    # =========================================

                    if not page_records:

                        card_records = parse_store_cards(
                            soup,
                            brand,
                            url
                        )

                        if card_records:

                            page_records.extend(
                                card_records
                            )

                            debug_logs.append(
                                f"HTML Card → {len(card_records)} stores"
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

    # ========================================================
    # FINAL DEDUPE
    # ========================================================

    final_records = dedupe_records(
        all_records
    )

    return (
        final_records,
        crawled_pages,
        debug_logs
    )


# ============================================================
# SYNC WRAPPER
# ============================================================

def extract_store_data(
    url,
    max_pages
):

    return asyncio.run(
        crawl_website(
            url,
            max_pages
        )
    )


# ============================================================
# STREAMLIT CONFIG
# ============================================================

st.set_page_config(
    page_title="Competitor Store Extractor",
    layout="wide"
)

st.title(
    "🏪 Competitor Store Extractor"
)

st.caption(
    "Website đối thủ → API / JSON → "
    "HTML Table → Brand Parser → HTML Card → Excel"
)


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.header(
        "⚙️ Settings"
    )

    max_pages = st.slider(
        "Số trang tối đa",
        min_value=3,
        max_value=50,
        value=20
    )

    st.markdown(
        """
### Extraction priority

**1. API / JSON**

Nếu API tìm được store:

→ Không lấy HTML.

**2. HTML Table**

Nếu không có API:

→ Lấy Table.

**3. Brand Parser**

Ví dụ Pizza Hut có parser riêng.

**4. HTML Card**

Nếu các phương thức trên không có:

→ Lấy Card.

### Address

**Province**
→ ưu tiên phần cuối có `Tỉnh / Thành phố / TP`

**Ward**
→ tìm phần có `Phường / P. / Ward / Xã`

### Pizza Hut

Nếu nhập:

`store-location?area=north`

tool tự crawl:

- north
- central
- south

"""
    )


# ============================================================
# URL INPUT
# ============================================================

urls_text = st.text_area(
    "🌐 Website đối thủ",
    value=(
        "https://www.phuclong.com.vn/\n"
        "https://jollibee.com.vn/"
    ),
    height=130,
    help="Mỗi dòng một website."
)


# ============================================================
# RUN
# ============================================================

if st.button(
    "🚀 Extract stores",
    type="primary"
):

    urls = [
        normalize_url(x)
        for x in urls_text.splitlines()
        if clean_text(x)
    ]

    if not urls:

        st.error(
            "Hãy nhập ít nhất một website."
        )

        st.stop()

    all_data = []
    all_pages = []
    all_debug_logs = []

    progress = st.progress(
        0
    )

    status = st.empty()

    # ========================================================
    # CRAWL EVERY WEBSITE
    # ========================================================

    for i, url in enumerate(
        urls,
        start=1
    ):

        brand = get_brand_from_url(
            url
        )

        status.write(
            f"🔎 Đang crawl: {url}"
        )

        try:

            records, pages, debug_logs = extract_store_data(
                url,
                max_pages
            )

            all_data.extend(
                records
            )

            all_pages.extend(
                pages
            )

            all_debug_logs.extend(
                [
                    f"[{brand}] {x}"
                    for x in debug_logs
                ]
            )

            if records:

                st.success(
                    f"{brand} → "
                    f"{len(records):,} stores"
                )

            else:

                st.warning(
                    f"{brand} → 0 stores"
                )

        except Exception as e:

            st.error(
                f"{url} → lỗi: {e}"
            )

            all_debug_logs.append(
                f"[{brand}] ERROR → {e}"
            )

        progress.progress(
            i / len(urls)
        )

    # ========================================================
    # DATAFRAME
    # ========================================================

    df = pd.DataFrame(
        all_data
    )

    columns = [
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

    if not df.empty:

        for column in columns:

            if column not in df.columns:
                df[column] = ""

        df = df[
            columns
        ]

        # ====================================================
        # FINAL SAFETY DEDUPE
        # ====================================================

        method_order = {
            "API/JSON": 1,
            "HTML Table": 2,
            "Pizza Hut HTML": 3,
            "HTML Card": 4,
        }

        df["_Priority"] = (
            df["Method"]
            .map(method_order)
            .fillna(99)
        )

        df["_PhoneKey"] = (
            df["Phone"]
            .fillna("")
            .apply(
                normalize_phone
            )
        )

        df["_LatKey"] = (
            df["Lat"]
            .fillna("")
            .apply(
                normalize_coordinate
            )
        )

        df["_LongKey"] = (
            df["Long"]
            .fillna("")
            .apply(
                normalize_coordinate
            )
        )

        df["_AddressKey"] = (
            df["Brand"]
            .fillna("")
            .apply(
                normalize_for_compare
            )
            + "|"
            + df["Address"]
            .fillna("")
            .apply(
                normalize_for_compare
            )
        )

        df = df.sort_values(
            "_Priority"
        )

        # ----------------------------------------------------
        # Store Code
        # ----------------------------------------------------

        has_code = (
            df["StoreCode"]
            .fillna("")
            .str.strip()
            != ""
        )

        duplicate_code = (
            has_code
            &
            df.duplicated(
                subset=[
                    "Brand",
                    "StoreCode",
                ],
                keep="first"
            )
        )

        df = df[
            ~duplicate_code
        ]

        # ----------------------------------------------------
        # Phone
        # ----------------------------------------------------

        has_phone = (
            df["_PhoneKey"] != ""
        )

        duplicate_phone = (
            has_phone
            &
            df.duplicated(
                subset=[
                    "Brand",
                    "_PhoneKey",
                ],
                keep="first"
            )
        )

        df = df[
            ~duplicate_phone
        ]

        # ----------------------------------------------------
        # Coordinates
        # ----------------------------------------------------

        has_coordinates = (
            (df["_LatKey"] != "")
            &
            (df["_LongKey"] != "")
        )

        duplicate_coordinates = (
            has_coordinates
            &
            df.duplicated(
                subset=[
                    "Brand",
                    "_LatKey",
                    "_LongKey",
                ],
                keep="first"
            )
        )

        df = df[
            ~duplicate_coordinates
        ]

        # ----------------------------------------------------
        # Address
        # ----------------------------------------------------

        duplicate_address = (
            df.duplicated(
                subset=[
                    "_AddressKey",
                ],
                keep="first"
            )
            &
            (
                df["_AddressKey"] != "|"
            )
        )

        df = df[
            ~duplicate_address
        ]

        # ----------------------------------------------------
        # Remove helper columns
        # ----------------------------------------------------

        df = (
            df.drop(
                columns=[
                    "_Priority",
                    "_PhoneKey",
                    "_LatKey",
                    "_LongKey",
                    "_AddressKey",
                ]
            )
            .reset_index(
                drop=True
            )
        )

    # ========================================================
    # RESULT
    # ========================================================

    st.subheader(
        "📊 Result"
    )

    if df.empty:

        st.warning(
            """
Chưa lấy được store.

Website có thể dùng:

- API đặc biệt
- iframe
- GraphQL
- Google Maps
- dữ liệu cần chọn tỉnh/thành
- anti-bot
- hoặc cấu trúc HTML đặc biệt.

Xem phần **Debug / Crawl log** bên dưới để biết crawler
đã mở page nào và thử phương thức nào.
"""
        )

    else:

        st.success(
            f"🎉 Tổng cộng "
            f"{len(df):,} stores"
        )

        # ====================================================
        # SUMMARY
        # ====================================================

        summary = (
            df.groupby(
                "Brand"
            )
            .size()
            .reset_index(
                name="StoreCount"
            )
        )

        st.subheader(
            "Store Count"
        )

        st.dataframe(
            summary,
            use_container_width=True
        )

        # ====================================================
        # METHOD SUMMARY
        # ====================================================

        method_summary = (
            df.groupby(
                [
                    "Brand",
                    "Method",
                ]
            )
            .size()
            .reset_index(
                name="StoreCount"
            )
        )

        st.subheader(
            "Extraction Method"
        )

        st.dataframe(
            method_summary,
            use_container_width=True
        )

        # ====================================================
        # MAIN DATA
        # ====================================================

        st.subheader(
            "Store Data"
        )

        st.dataframe(
            df,
            use_container_width=True,
            height=550
        )

        # ====================================================
        # EXPORT
        # ====================================================

        timestamp = datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )

        excel_name = (
            f"competitor_stores_"
            f"{timestamp}.xlsx"
        )

        csv_name = (
            f"competitor_stores_"
            f"{timestamp}.csv"
        )

        output = BytesIO()

        with pd.ExcelWriter(
            output,
            engine="openpyxl"
        ) as writer:

            df.to_excel(
                writer,
                index=False,
                sheet_name="Stores"
            )

            summary.to_excel(
                writer,
                index=False,
                sheet_name="Summary"
            )

            method_summary.to_excel(
                writer,
                index=False,
                sheet_name="Methods"
            )

            pd.DataFrame(
                {
                    "CrawledPages": sorted(
                        set(all_pages)
                    )
                }
            ).to_excel(
                writer,
                index=False,
                sheet_name="CrawledPages"
            )

        # ====================================================
        # DOWNLOAD EXCEL
        # ====================================================

        st.download_button(
            "⬇️ Download Excel",
            data=output.getvalue(),
            file_name=excel_name,
            mime=(
                "application/"
                "vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            )
        )

        # ====================================================
        # DOWNLOAD CSV
        # ====================================================

        st.download_button(
            "⬇️ Download CSV",
            data=df.to_csv(
                index=False
            ).encode(
                "utf-8-sig"
            ),
            file_name=csv_name,
            mime="text/csv"
        )

        # ====================================================
        # CRAWLED PAGES
        # ====================================================

        with st.expander(
            "🔎 Crawled pages"
        ):

            st.write(
                sorted(
                    set(all_pages)
                )
            )

    # ========================================================
    # DEBUG
    # ========================================================

    with st.expander(
        "🛠️ Debug / Crawl log"
    ):

        if all_debug_logs:

            for log in all_debug_logs:

                st.text(
                    log
                )

        else:

            st.write(
                "Không có debug log."
            )