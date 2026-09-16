
import asyncio
import json
import re
from pathlib import Path
from urllib.parse import (
    urljoin,
    urlparse,
    parse_qsl,
    urlencode,
    urlunparse,
)

import pandas as pd
from playwright.async_api import async_playwright


# ============================================================
# CONFIG
# ============================================================

TARGET_URL = (
    "https://www.kfcvietnam.com.vn/"
    "he-thong-nha-hang-kfc"
)

BASE_URL = "https://www.kfcvietnam.com.vn/"

OUTPUT_DIR = Path("kfc_test_output")
RAW_DIR = OUTPUT_DIR / "raw_api"

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

RAW_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# TEST PROVINCES
# ============================================================

SEARCH_PROVINCES = [
    # --------------------------------------------------------
    # NORTH
    # --------------------------------------------------------
    "Hà Nội",
    "Hải Phòng",
    "Quảng Ninh",
    "Bắc Giang",
    "Bắc Kạn",
    "Bắc Ninh",
    "Cao Bằng",
    "Điện Biên",
    "Hà Giang",
    "Hòa Bình",
    "Hưng Yên",
    "Lai Châu",
    "Lạng Sơn",
    "Lào Cai",
    "Nam Định",
    "Ninh Bình",
    "Phú Thọ",
    "Sơn La",
    "Thái Bình",
    "Thái Nguyên",
    "Tuyên Quang",
    "Vĩnh Phúc",

    # --------------------------------------------------------
    # NORTH CENTRAL
    # --------------------------------------------------------
    "Thanh Hóa",
    "Nghệ An",
    "Hà Tĩnh",
    "Quảng Bình",
    "Quảng Trị",
    "Thừa Thiên Huế",

    # --------------------------------------------------------
    # CENTRAL
    # --------------------------------------------------------
    "Đà Nẵng",
    "Quảng Nam",
    "Quảng Ngãi",
    "Bình Định",
    "Phú Yên",
    "Khánh Hòa",
    "Ninh Thuận",
    "Bình Thuận",
    "Kon Tum",
    "Gia Lai",
    "Đắk Lắk",
    "Đắk Nông",
    "Lâm Đồng",

    # --------------------------------------------------------
    # SOUTHEAST
    # --------------------------------------------------------
    "Hồ Chí Minh",
    "Bình Dương",
    "Bà Rịa - Vũng Tàu",
    "Bình Phước",
    "Đồng Nai",
    "Tây Ninh",

    # --------------------------------------------------------
    # SOUTHWEST / MEKONG DELTA
    # --------------------------------------------------------
    "Long An",
    "Tiền Giang",
    "Bến Tre",
    "Trà Vinh",
    "Vĩnh Long",
    "Đồng Tháp",
    "An Giang",
    "Kiên Giang",
    "Cần Thơ",
    "Hậu Giang",
    "Sóc Trăng",
    "Bạc Liêu",
    "Cà Mau",
]


# ============================================================
# HELPERS
# ============================================================

def clean_text(value):
    """
    Normalize text:
    - None -> ""
    - collapse whitespace
    - strip
    """

    if value is None:
        return ""

    return re.sub(
        r"\s+",
        " ",
        str(value),
    ).strip()


def normalize_phone(value):
    """
    Normalize phone number.

    Example:
        84xxxxxxxxx
        ->
        0xxxxxxxxx
    """

    if value is None:
        return ""

    digits = re.sub(
        r"\D",
        "",
        str(value),
    )

    if not digits:
        return ""

    if digits.startswith("84"):
        digits = "0" + digits[2:]

    return digits


def normalize_url(value):
    """
    Normalize store URL.

    Handles:
    - relative URL
    - absolute URL
    - cache-busting query parameters
    - trailing slash
    """

    value = clean_text(value)

    if not value:
        return ""

    # --------------------------------------------------------
    # Relative URL -> absolute URL
    # --------------------------------------------------------

    if not value.startswith(
        ("http://", "https://")
    ):
        value = urljoin(
            BASE_URL,
            value.lstrip("/"),
        )

    # --------------------------------------------------------
    # Normalize URL
    # --------------------------------------------------------

    try:
        parsed = urlparse(value)

        query_items = []

        for key, val in parse_qsl(
            parsed.query,
            keep_blank_values=True,
        ):
            key_lower = key.lower()

            # Remove cache-busting parameters
            if key_lower in {
                "_",
                "timestamp",
                "ts",
                "cachebust",
                "cachebuster",
            }:
                continue

            query_items.append(
                (key, val)
            )

        normalized_query = urlencode(
            query_items
        )

        parsed = parsed._replace(
            query=normalized_query,
            fragment="",
        )

        value = urlunparse(parsed)

    except Exception:
        pass

    return value.rstrip("/").lower()


def get_vi_value(value):
    """
    KFC API may return multilingual values:

    [
        {
            "lang": "en",
            "value": "..."
        },
        {
            "lang": "vi",
            "value": "..."
        }
    ]

    Priority:
        1. Vietnamese
        2. First non-empty value
    """

    # --------------------------------------------------------
    # Normal string
    # --------------------------------------------------------

    if not isinstance(value, list):
        return clean_text(value)

    # --------------------------------------------------------
    # Vietnamese
    # --------------------------------------------------------

    for item in value:

        if not isinstance(
            item,
            dict,
        ):
            continue

        if (
            str(
                item.get(
                    "lang",
                    "",
                )
            ).lower()
            == "vi"
        ):
            return clean_text(
                item.get("value")
            )

    # --------------------------------------------------------
    # Fallback
    # --------------------------------------------------------

    for item in value:

        if not isinstance(
            item,
            dict,
        ):
            continue

        if item.get("value"):
            return clean_text(
                item.get("value")
            )

    return ""


# ============================================================
# STORE EXTRACTION
# ============================================================

def extract_store(
    item,
    search_province,
    source_url,
):
    """
    Convert one KFC API item into one store record.

    IMPORTANT:
    StoreCode comes directly from API "id".
    """

    if not isinstance(
        item,
        dict,
    ):
        return None

    # --------------------------------------------------------
    # StoreCode
    # --------------------------------------------------------

    store_code = clean_text(
        item.get("id")
    )

    # StoreCode is mandatory
    if not store_code:
        return None

    # --------------------------------------------------------
    # StoreName
    # --------------------------------------------------------

    store_name = get_vi_value(
        item.get("name")
    )

    # --------------------------------------------------------
    # Address
    # --------------------------------------------------------

    address = get_vi_value(
        item.get("address")
    )

    # --------------------------------------------------------
    # Province
    # --------------------------------------------------------

    province = get_vi_value(
        item.get("city")
    )

    # --------------------------------------------------------
    # Phone
    # --------------------------------------------------------

    phone = normalize_phone(
        item.get("phone")
    )

    # --------------------------------------------------------
    # Location
    # --------------------------------------------------------

    location = item.get(
        "location"
    )

    if not isinstance(
        location,
        dict,
    ):
        location = {}

    lat = location.get(
        "latitude"
    )

    lon = location.get(
        "longitude"
    )

    # --------------------------------------------------------
    # Store URL
    # --------------------------------------------------------

    store_slug = clean_text(
        item.get("url")
    )

    store_url = normalize_url(
        store_slug
    )

    # --------------------------------------------------------
    # Return
    # --------------------------------------------------------

    return {
        "Brand": "KFC",

        "StoreCode": store_code,

        "StoreName": store_name,

        "Address": address,

        "Province": province,

        "Ward": "",

        "Phone": phone,

        "Lat": lat,

        "Long": lon,

        "StoreURL": store_url,

        "SourceURL": source_url,

        "Method": "KFC API",

        # Debug:
        "_SearchProvince": search_province,
    }


# ============================================================
# SAVE RAW API
# ============================================================

def save_raw_api(
    search_province,
    api_responses,
):
    """
    Save every captured API response.
    """

    safe_province = re.sub(
        r'[\\/:*?"<>|]',
        "_",
        search_province,
    )

    for api_index, api_item in enumerate(
        api_responses,
        start=1,
    ):

        raw_file = (
            RAW_DIR
            / (
                f"{safe_province}_"
                f"{api_index}.json"
            )
        )

        raw_file.write_text(
            json.dumps(
                api_item,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )


# ============================================================
# MAIN
# ============================================================

async def main():

    print("=" * 80)
    print("KFC TEST EXTRACTOR")
    print("=" * 80)

    print(
        "Target:",
        TARGET_URL,
    )

    print(
        "Search provinces:",
        SEARCH_PROVINCES,
    )

    all_stores = []

    # ========================================================
    # PLAYWRIGHT
    # ========================================================

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True,
        )

        context = await browser.new_context(
            locale="vi-VN",

            timezone_id="Asia/Ho_Chi_Minh",

            viewport={
                "width": 1600,
                "height": 1000,
            },

            user_agent=(
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/131.0.0.0 "
                "Safari/537.36"
            ),
        )

        # ====================================================
        # LOOP SEARCH PROVINCES
        # ====================================================

        for search_province in SEARCH_PROVINCES:

            print()
            print("=" * 80)
            print(
                "SEARCH:",
                search_province,
            )
            print("=" * 80)

            api_responses = []

            page = await context.new_page()

            # ------------------------------------------------
            # CAPTURE KFC API
            # ------------------------------------------------

            async def handle_response(
                response,
            ):

                url = response.url.lower()

                if "/find-a-kfc/" not in url:
                    return

                try:

                    body = await response.body()

                    if not body:
                        return

                    try:

                        data = json.loads(
                            body.decode(
                                "utf-8",
                                errors="ignore",
                            )
                        )

                    except Exception:

                        return

                    api_responses.append(
                        {
                            "url": response.url,
                            "status": response.status,
                            "data": data,
                        }
                    )

                    print()
                    print(
                        "[KFC API]",
                        response.status,
                    )

                    print(
                        response.url,
                    )

                except Exception as e:

                    print(
                        "[API ERROR]",
                        str(e),
                    )

            page.on(
                "response",
                handle_response,
            )

            # ------------------------------------------------
            # OPEN KFC PAGE
            # ------------------------------------------------

            try:

                await page.goto(
                    TARGET_URL,
                    wait_until="domcontentloaded",
                    timeout=90_000,
                )

            except Exception as e:

                print(
                    "[PAGE ERROR]",
                    str(e),
                )

                await page.close()

                continue

            # ------------------------------------------------
            # WAIT PAGE
            # ------------------------------------------------

            await page.wait_for_timeout(
                8_000
            )

            # ------------------------------------------------
            # SEARCH INPUT
            # ------------------------------------------------

            search_input = page.locator(
                "#RestaurantSearchDesktop"
            )

            if await search_input.count() == 0:

                print(
                    "[ERROR] "
                    "Search input not found"
                )

                await page.close()

                continue

            # ------------------------------------------------
            # TYPE PROVINCE
            # ------------------------------------------------

            try:

                await search_input.click()

                await search_input.fill("")

                await search_input.type(
                    search_province,
                    delay=100,
                )

                await page.wait_for_timeout(
                    3_000
                )

            except Exception as e:

                print(
                    "[INPUT ERROR]",
                    str(e),
                )

                await page.close()

                continue

            # ------------------------------------------------
            # ENTER
            # ------------------------------------------------

            print(
                "Pressing Enter..."
            )

            try:

                await search_input.press(
                    "Enter"
                )

            except Exception as e:

                print(
                    "[ENTER ERROR]",
                    str(e),
                )

            # ------------------------------------------------
            # WAIT API
            # ------------------------------------------------

            await page.wait_for_timeout(
                8_000
            )

            # ------------------------------------------------
            # FALLBACK
            # ------------------------------------------------

            if not api_responses:

                print(
                    "No API response. "
                    "Trying ArrowDown + Enter..."
                )

                try:

                    await search_input.click()

                    await search_input.press(
                        "ArrowDown"
                    )

                    await page.wait_for_timeout(
                        500
                    )

                    await search_input.press(
                        "Enter"
                    )

                    await page.wait_for_timeout(
                        8_000
                    )

                except Exception as e:

                    print(
                        "[SECOND SEARCH ERROR]",
                        str(e),
                    )

            # ------------------------------------------------
            # SAVE RAW API
            # ------------------------------------------------

            save_raw_api(
                search_province,
                api_responses,
            )

            # ------------------------------------------------
            # EXTRACT STORES
            # ------------------------------------------------

            province_store_count = 0

            for api_item in api_responses:

                source_url = api_item[
                    "url"
                ]

                data = api_item[
                    "data"
                ]

                # ------------------------------------------------
                # Expected:
                #
                # {
                #   "key": "...",
                #   "Value": [...]
                # }
                # ------------------------------------------------

                values = []

                if isinstance(
                    data,
                    dict,
                ):

                    values = data.get(
                        "Value",
                        [],
                    )

                elif isinstance(
                    data,
                    list,
                ):

                    values = data

                if not isinstance(
                    values,
                    list,
                ):
                    continue

                print(
                    "Stores in API:",
                    len(values),
                )

                for item in values:

                    store = extract_store(
                        item,
                        search_province,
                        source_url,
                    )

                    if store is None:
                        continue

                    # ------------------------------------------------
                    # JUNK PROTECTION
                    # ------------------------------------------------
                    #
                    # StoreCode bắt buộc.
                    #
                    # Store phải có ít nhất:
                    #   StoreName
                    # OR
                    #   Address
                    #
                    # ------------------------------------------------

                    store_name = clean_text(
                        store.get(
                            "StoreName"
                        )
                    )

                    address = clean_text(
                        store.get(
                            "Address"
                        )
                    )

                    if (
                        not store_name
                        and not address
                    ):
                        continue

                    all_stores.append(
                        store
                    )

                    province_store_count += 1

                    print(
                        f"  {store['StoreCode']} | "
                        f"{store['StoreName']} | "
                        f"{store['Province']} | "
                        f"{store['Phone']} | "
                        f"{store['Lat']}, "
                        f"{store['Long']}"
                    )

            print()

            print(
                f"Extracted from "
                f"{search_province}: "
                f"{province_store_count}"
            )

            await page.close()

        await browser.close()

    # ========================================================
    # CREATE DATAFRAME
    # ========================================================

    print()
    print("=" * 80)
    print("PROCESSING")
    print("=" * 80)

    if not all_stores:

        print(
            "!!! NO STORE FOUND !!!"
        )

        return

    df = pd.DataFrame(
        all_stores
    )

    print(
        "Raw rows:",
        len(df),
    )

    # ========================================================
    # STORE CODE DUPLICATE ONLY
    # ========================================================
    #
    # IMPORTANT:
    #
    # KFC StoreCode / API id is the unique identifier.
    #
    # We DO NOT remove stores because:
    #
    # - Address is duplicated
    # - Phone is duplicated
    # - StoreURL is duplicated
    #
    # Example:
    #
    # StoreCode A | Address X
    # StoreCode B | Address X
    #
    # -> KEEP BOTH
    #
    # ========================================================

    before_code = len(df)

    duplicate_code_mask = (
        df["StoreCode"]
        .duplicated(
            keep="first"
        )
    )

    duplicate_code_df = (
        df.loc[
            duplicate_code_mask,
            [
                "StoreCode",
                "StoreName",
                "Address",
                "Province",
                "_SearchProvince",
            ],
        ]
        .copy()
    )

    df = (
        df.drop_duplicates(
            subset=["StoreCode"],
            keep="first",
        )
        .reset_index(
            drop=True
        )
    )

    removed_code_count = (
        before_code - len(df)
    )

    print(
        "After StoreCode duplicate:",
        len(df),
        f"(removed {removed_code_count})",
    )

    # --------------------------------------------------------
    # Save StoreCode duplicate log
    # --------------------------------------------------------

    if not duplicate_code_df.empty:

        duplicate_code_path = (
            OUTPUT_DIR
            / "kfc_storecode_duplicates_removed.csv"
        )

        duplicate_code_df.to_csv(
            duplicate_code_path,
            index=False,
            encoding="utf-8-sig",
        )

        print()
        print(
            "StoreCode duplicate log:"
        )

        print(
            duplicate_code_path.resolve()
        )

        print()

        print(
            duplicate_code_df.to_string(
                index=False
            )
        )

    else:

        print(
            "StoreCode duplicates: None"
        )

    # ========================================================
    # SORT
    # ========================================================

    df = (
        df.sort_values(
            by=[
                "Province",
                "StoreName",
                "StoreCode",
            ],
            na_position="last",
        )
        .reset_index(
            drop=True
        )
    )

    # ========================================================
    # DATA QUALITY
    # ========================================================

    print()
    print("=" * 80)
    print("DATA QUALITY")
    print("=" * 80)

    for column in [
        "StoreCode",
        "StoreName",
        "Address",
        "Province",
        "Phone",
        "Lat",
        "Long",
        "StoreURL",
    ]:

        if column not in df.columns:
            continue

        filled = (
            df[column]
            .notna()
            &
            (
                df[column]
                .astype(str)
                .str.strip()
                != ""
            )
        ).sum()

        print(
            f"{column:<15}: "
            f"{filled} filled / "
            f"{len(df)} total"
        )

    # ========================================================
    # STORE COUNT BY SEARCH PROVINCE
    # ========================================================

    print()
    print("=" * 80)
    print("STORE COUNT BY SEARCH PROVINCE")
    print("=" * 80)

    province_summary = (
        df
        .groupby(
            "_SearchProvince"
        )
        .size()
        .reset_index(
            name="StoreCount"
        )
    )

    print(
        province_summary.to_string(
            index=False
        )
    )

    # ========================================================
    # STORE COUNT BY API PROVINCE
    # ========================================================

    print()
    print("=" * 80)
    print("STORE COUNT BY API CITY")
    print("=" * 80)

    city_summary = (
        df
        .groupby(
            "Province"
        )
        .size()
        .reset_index(
            name="StoreCount"
        )
        .sort_values(
            "StoreCount",
            ascending=False,
        )
    )

    print(
        city_summary.to_string(
            index=False
        )
    )

    # ========================================================
    # CHECK CROSS-PROVINCE SEARCH RESULT
    # ========================================================
    #
    # Đây chỉ là cảnh báo.
    #
    # KHÔNG REMOVE STORE.
    #
    # Nếu search "Hà Nội" nhưng API trả Province khác,
    # chúng ta vẫn giữ store để tránh mất dữ liệu.
    #
    # ========================================================

    cross_province = df[
        (
            df["_SearchProvince"]
            .str.strip()
            .str.lower()
            !=
            df["Province"]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.lower()
        )
    ].copy()

    print()
    print("=" * 80)
    print("CROSS-PROVINCE API CHECK")
    print("=" * 80)

    if cross_province.empty:

        print(
            "No cross-province records."
        )

    else:

        print(
            f"Found {len(cross_province)} "
            "records where SearchProvince "
            "!= API Province."
        )

        print()

        print(
            cross_province[
                [
                    "StoreCode",
                    "StoreName",
                    "Province",
                    "_SearchProvince",
                ]
            ].to_string(
                index=False
            )
        )

        cross_province_path = (
            OUTPUT_DIR
            / "kfc_cross_province_check.csv"
        )

        cross_province.to_csv(
            cross_province_path,
            index=False,
            encoding="utf-8-sig",
        )

        print()

        print(
            "Cross-province log:"
        )

        print(
            cross_province_path.resolve()
        )

    # ========================================================
    # OUTPUT COLUMNS
    # ========================================================

    output_columns = [
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
        "_SearchProvince",
    ]

    df = df[
        [
            col
            for col in output_columns
            if col in df.columns
        ]
    ]

    # ========================================================
    # SAVE CSV
    # ========================================================

    csv_path = (
        OUTPUT_DIR
        / "kfc_test_stores.csv"
    )

    df.to_csv(
        csv_path,
        index=False,
        encoding="utf-8-sig",
    )

    # ========================================================
    # SAVE EXCEL
    # ========================================================

    excel_path = (
        OUTPUT_DIR
        / "kfc_test_stores.xlsx"
    )

    df.to_excel(
        excel_path,
        index=False,
    )

    # ========================================================
    # FINAL RESULT
    # ========================================================

    print()
    print("=" * 80)
    print("FINAL RESULT")
    print("=" * 80)

    print(
        "Total stores:",
        len(df),
    )

    print()

    print(
        df[
            [
                "StoreCode",
                "StoreName",
                "Address",
                "Province",
                "Phone",
                "Lat",
                "Long",
                "StoreURL",
            ]
        ].to_string(
            index=False
        )
    )

    print()

    print(
        "CSV:",
        csv_path.resolve()
    )

    print(
        "Excel:",
        excel_path.resolve()
    )

    print(
        "Raw API:",
        RAW_DIR.resolve()
    )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    asyncio.run(
        main()
    )

