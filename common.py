import json
import re
import unicodedata

from urllib.parse import (
    urlparse,
    parse_qs,
    urlencode,
    urlunparse,
)


# ============================================================
# TEXT
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


def normalize_for_compare(value):

    value = clean_text(value).lower()

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


# ============================================================
# URL
# ============================================================

def normalize_url(url):

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

    return (
        bool(domain1)
        and bool(domain2)
        and domain1 == domain2
    )


def looks_like_http_url(url):

    return clean_text(url).startswith(
        (
            "http://",
            "https://"
        )
    )


def is_generic_store_locator_url(url):

    url = normalize_url(url)

    if not url:
        return False

    try:

        parsed = urlparse(url)

        path = (
            parsed.path
            .rstrip("/")
            .lower()
        )

    except Exception:

        return False

    generic_paths = [

        "/store-locator",
        "/storelocator",
        "/store-locations",
        "/store-location",
        "/locations",
        "/stores",
        "/cua-hang",
        "/cua-hang-cua-chung-toi",
        "/chi-nhanh",
        "/dia-diem",

    ]

    return path in generic_paths


def is_api_or_ajax_url(url):

    url = normalize_url(url)

    if not url:
        return False

    try:

        parsed = urlparse(url)

        path = parsed.path.lower()

        full = url.lower()

    except Exception:

        return False

    api_keywords = [

        "/api/",
        "/ajax/",
        "/graphql",
        "/json/",
        ".json",
        "graphql",

    ]

    return any(
        keyword in path
        or keyword in full
        for keyword in api_keywords
    )


def is_usable_store_url(url):

    url = normalize_url(url)

    if not url:
        return False

    if is_api_or_ajax_url(url):
        return False

    if is_generic_store_locator_url(url):
        return False

    return looks_like_http_url(url)


def normalize_url_for_compare(url):

    url = normalize_url(url)

    if not url:
        return ""

    try:

        parsed = urlparse(url)

        scheme = parsed.scheme.lower()

        netloc = (
            parsed.netloc
            .lower()
            .replace("www.", "")
        )

        path = parsed.path or "/"

        path = re.sub(
            r"/+",
            "/",
            path
        )

        path = path.rstrip("/")

        query_pairs = parse_qs(
            parsed.query,
            keep_blank_values=True
        )

        dynamic_params = {

            "_",
            "timestamp",
            "ts",
            "time",
            "cache",
            "cachebuster",
            "cache_buster",
            "nocache",
            "cb",

        }

        cleaned_pairs = []

        for key, values in query_pairs.items():

            if key.lower() in dynamic_params:
                continue

            for value in values:

                cleaned_pairs.append(
                    (
                        key.lower(),
                        clean_text(value)
                    )
                )

        cleaned_pairs.sort()

        cleaned_query = urlencode(
            cleaned_pairs,
            doseq=True
        )

        return urlunparse(
            (
                scheme,
                netloc,
                path,
                "",
                cleaned_query,
                ""
            )
        ).lower()

    except Exception:

        return normalize_for_compare(url)


# ============================================================
# PHONE
# ============================================================

PHONE_PATTERN = re.compile(
    r"(?:\+84|0)"
    r"(?:\s*[\(\[]?\d{2,3}[\)\]]?)?"
    r"[\s.\-]?"
    r"\d"
    r"[\d\s()./\-]{6,}"
)


def extract_phone(text):

    text = clean_text(text)

    matches = PHONE_PATTERN.findall(
        text
    )

    if not matches:
        return ""

    result = []

    for match in matches:

        value = clean_text(
            match
        )

        digits = re.sub(
            r"\D",
            "",
            value
        )

        if len(digits) >= 9:

            result.append(
                value
            )

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

        digits = (
            "0"
            + digits[2:]
        )

    return digits


# ============================================================
# ADDRESS
# ============================================================

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

    if text.count(",") >= 1:
        score += 1

    return score >= 1


def parse_vietnam_address(address):

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
        r"\bcity\b",

    ]

    for part in reversed(parts):

        lower = normalize_for_compare(
            part
        )

        if any(
            re.search(
                pattern,
                lower
            )
            for pattern in province_patterns
        ):

            province = part

            break

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

        lower = normalize_for_compare(
            part
        )

        if any(
            re.search(
                pattern,
                lower
            )
            for pattern in ward_patterns
        ):

            ward = part

            break

    if not ward and len(parts) >= 2:

        for i in range(
            len(parts) - 1,
            -1,
            -1
        ):

            if normalize_for_compare(
                parts[i]
            ) != normalize_for_compare(
                province
            ):

                ward = parts[i]

                break

    return ward, province


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


def valid_vietnam_coordinate(
    lat,
    lon
):

    try:

        lat_num = float(lat)
        lon_num = float(lon)

        return (
            8 <= lat_num <= 24
            and
            102 <= lon_num <= 110
        )

    except Exception:

        return False


def parse_coordinate_pair(value):

    value = clean_text(
        value
    )

    if not value:
        return "", ""

    value = value.replace(
        "%2C",
        ","
    )

    match = re.search(
        r"(-?\d{1,3}\.\d+)"
        r"\s*[,;]\s*"
        r"(-?\d{1,3}\.\d+)",
        value
    )

    if not match:
        return "", ""

    lat = normalize_coordinate(
        match.group(1)
    )

    lon = normalize_coordinate(
        match.group(2)
    )

    if valid_vietnam_coordinate(
        lat,
        lon
    ):

        return lat, lon

    return "", ""


def extract_coordinates_from_url(url):

    url = clean_text(
        url
    )

    if not url:
        return "", ""

    # --------------------------------------------------------
    # Query
    # --------------------------------------------------------

    try:

        parsed = urlparse(
            url
        )

        query = parse_qs(
            parsed.query,
            keep_blank_values=True
        )

        lat_keys = [
            "lat",
            "latitude",
            "y",
        ]

        lon_keys = [
            "lng",
            "lon",
            "longitude",
            "long",
            "x",
        ]

        lat = ""
        lon = ""

        for key in lat_keys:

            if key in query and query[key]:

                candidate = normalize_coordinate(
                    query[key][0]
                )

                if candidate:

                    lat = candidate

                    break

        for key in lon_keys:

            if key in query and query[key]:

                candidate = normalize_coordinate(
                    query[key][0]
                )

                if candidate:

                    lon = candidate

                    break

        if (
            lat
            and lon
            and valid_vietnam_coordinate(
                lat,
                lon
            )
        ):

            return lat, lon

        combined_keys = [

            "q",
            "ll",
            "query",
            "center",
            "location",
            "coordinates",
            "coord",

        ]

        for key in combined_keys:

            if key not in query:
                continue

            for value in query[key]:

                found_lat, found_lon = (
                    parse_coordinate_pair(
                        value
                    )
                )

                if found_lat and found_lon:

                    return (
                        found_lat,
                        found_lon
                    )

    except Exception:

        pass

    # --------------------------------------------------------
    # Google Maps @LAT,LON
    # --------------------------------------------------------

    match = re.search(
        r"@(-?\d{1,3}\.\d+),"
        r"(-?\d{1,3}\.\d+)",
        url
    )

    if match:

        lat = normalize_coordinate(
            match.group(1)
        )

        lon = normalize_coordinate(
            match.group(2)
        )

        if valid_vietnam_coordinate(
            lat,
            lon
        ):

            return lat, lon

    # --------------------------------------------------------
    # Google Maps !3dLAT!4dLON
    # --------------------------------------------------------

    match = re.search(
        r"!3d(-?\d{1,3}\.\d+)"
        r"!4d(-?\d{1,3}\.\d+)",
        url
    )

    if match:

        lat = normalize_coordinate(
            match.group(1)
        )

        lon = normalize_coordinate(
            match.group(2)
        )

        if valid_vietnam_coordinate(
            lat,
            lon
        ):

            return lat, lon

    # --------------------------------------------------------
    # Generic pair
    # --------------------------------------------------------

    match = re.search(
        r"(?<!\d)"
        r"(-?\d{1,3}\.\d+)"
        r"[,\s]+"
        r"(-?\d{1,3}\.\d+)"
        r"(?!\d)",
        url
    )

    if match:

        lat = normalize_coordinate(
            match.group(1)
        )

        lon = normalize_coordinate(
            match.group(2)
        )

        if valid_vietnam_coordinate(
            lat,
            lon
        ):

            return lat, lon

    return "", ""


def fill_coordinates_from_url(record):

    lat = normalize_coordinate(
        record.get("Lat", "")
    )

    lon = normalize_coordinate(
        record.get("Long", "")
    )

    if lat and lon:

        record["Lat"] = lat
        record["Long"] = lon

        return record

    candidate_urls = [

        record.get(
            "StoreURL",
            ""
        ),

        record.get(
            "SourceURL",
            ""
        ),

    ]

    for url in candidate_urls:

        if not url:
            continue

        found_lat, found_lon = (
            extract_coordinates_from_url(
                url
            )
        )

        if found_lat and found_lon:

            record["Lat"] = (
                lat
                if lat
                else found_lat
            )

            record["Long"] = (
                lon
                if lon
                else found_lon
            )

            return record

    record["Lat"] = lat
    record["Long"] = lon

    return record


# ============================================================
# RECORD
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
# JSON HELPERS
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
                    flatten_json_objects(
                        value
                    )
                )

    elif isinstance(obj, list):

        for item in obj:

            if isinstance(
                item,
                (dict, list)
            ):

                result.extend(
                    flatten_json_objects(
                        item
                    )
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

        normalized[
            normalized_key
        ] = value

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