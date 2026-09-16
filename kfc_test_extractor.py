import asyncio
import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qsl, urlencode, urlunparse

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
    exist_ok=True
)

RAW_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# Tạm thời test 3 tỉnh/thành
SEARCH_PROVINCES = [
    "Hà Nội",
    "Hồ Chí Minh",
    "Đà Nẵng",
]


# ============================================================
# COMMON KFC PHONES
# ============================================================

# Hotline chung của KFC.
# Không được dùng số này để xác định duplicate store.

COMMON_KFC_PHONES = {
    "19006886",
}


# ============================================================
# HELPERS
# ============================================================

def clean_text(value):

    if value is None:
        return ""

    return re.sub(
        r"\s+",
        " ",
        str(value)
    ).strip()


def normalize_phone(value):

    if value is None:
        return ""

    digits = re.sub(
        r"\D",
        "",
        str(value)
    )

    if not digits:
        return ""

    # 84xxxxxxxxx -> 0xxxxxxxxx
    if digits.startswith("84"):

        digits = (
            "0"
            + digits[2:]
        )

    return digits


def normalize_address(value):

    value = clean_text(value)

    if not value:
        return ""

    return value.lower()


def normalize_url(value):

    value = clean_text(value)

    if not value:
        return ""

    # --------------------------------------------------------
    # Nếu API trả slug
    # --------------------------------------------------------

    if not value.startswith(
        ("http://", "https://")
    ):

        value = urljoin(
            BASE_URL,
            value.lstrip("/")
        )

    # --------------------------------------------------------
    # Normalize URL
    # --------------------------------------------------------

    try:

        parsed = urlparse(value)

        query_items = []

        for key, val in parse_qsl(
            parsed.query,
            keep_blank_values=True
        ):

            key_lower = key.lower()

            # Cache-busting params
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
            fragment=""
        )

        value = urlunparse(
            parsed
        )

    except Exception:
        pass

    return value.rstrip(
        "/"
    ).lower()


def get_vi_value(value):

    """
    API KFC dạng:

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
    """

    if not isinstance(
        value,
        list
    ):

        return clean_text(
            value
        )

    # --------------------------------------------------------
    # Ưu tiên tiếng Việt
    # --------------------------------------------------------

    for item in value:

        if not isinstance(
            item,
            dict
        ):
            continue

        if (
            str(
                item.get(
                    "lang",
                    ""
                )
            ).lower()
            == "vi"
        ):

            return clean_text(
                item.get(
                    "value"
                )
            )

    # --------------------------------------------------------
    # Fallback
    # --------------------------------------------------------

    for item in value:

        if not isinstance(
            item,
            dict
        ):
            continue

        if item.get("value"):

            return clean_text(
                item.get(
                    "value"
                )
            )

    return ""


# ============================================================
# STORE EXTRACTION
# ============================================================

def extract_store(
    item,
    search_province,
    source_url
):

    if not isinstance(
        item,
        dict
    ):
        return None

    # --------------------------------------------------------
    # StoreCode
    # --------------------------------------------------------

    store_code = clean_text(
        item.get("id")
    )

    # Không có StoreCode -> bỏ
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
        dict
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

        # Debug
        "_SearchProvince": search_province,

    }


# ============================================================
# FIND COMMON PHONES
# ============================================================

def find_common_phones(
    df,
    min_store_count=3
):

    """
    Tự tìm những số điện thoại xuất hiện
    ở nhiều StoreCode khác nhau.

    Ví dụ:

        19006886 -> 141 stores

    sẽ được xem là hotline chung và KHÔNG
    dùng để deduplicate.

    Chỉ xét phone không rỗng.
    """

    if df.empty:
        return set()

    temp = df.copy()

    temp["_NormalizedPhone"] = (
        temp["Phone"]
        .apply(normalize_phone)
    )

    temp = temp[
        temp["_NormalizedPhone"] != ""
    ]

    if temp.empty:
        return set()

    phone_store_counts = (
        temp
        .groupby("_NormalizedPhone")["StoreCode"]
        .nunique()
    )

    common_phones = set(
        phone_store_counts[
            phone_store_counts
            >= min_store_count
        ].index
    )

    return common_phones


# ============================================================
# DUPLICATE LOGIC
# ============================================================

def deduplicate_stores(df):

    """
    Duplicate nếu TRÙNG BẤT KỲ:

        1. Address
        OR
        2. StoreURL
        OR
        3. Phone

    NHƯNG:

        - Empty value không được duplicate.
        - Phone dùng chung nhiều store được xem
          là hotline và KHÔNG dùng để duplicate.
        - KFC 19006886 luôn được xem là hotline chung.

    StoreCode duplicate được xử lý trước ở main().
    """

    if df.empty:
        return df

    # --------------------------------------------------------
    # Detect common phones automatically
    # --------------------------------------------------------

    common_phones = (
        find_common_phones(
            df,
            min_store_count=3
        )
    )

    # Luôn thêm hotline KFC
    common_phones.update(
        COMMON_KFC_PHONES
    )

    print()
    print(
        "Common / hotline phones:"
    )

    if common_phones:

        for phone in sorted(
            common_phones
        ):

            print(
                f"  {phone}"
            )

    else:

        print(
            "  None"
        )

    # --------------------------------------------------------
    # Seen values
    # --------------------------------------------------------

    seen_address = set()
    seen_phone = set()
    seen_url = set()

    keep_rows = []

    duplicate_reasons = []

    # --------------------------------------------------------
    # Loop
    # --------------------------------------------------------

    for index, row in df.iterrows():

        address = normalize_address(
            row.get("Address")
        )

        phone = normalize_phone(
            row.get("Phone")
        )

        store_url = normalize_url(
            row.get("StoreURL")
        )

        # ----------------------------------------------------
        # Common phone -> KHÔNG dùng để duplicate
        # ----------------------------------------------------

        usable_phone = ""

        if (
            phone
            and phone not in common_phones
        ):

            usable_phone = phone

        # ----------------------------------------------------
        # Check duplicate
        # ----------------------------------------------------

        reasons = []

        if (
            address
            and address in seen_address
        ):

            reasons.append(
                "Address"
            )

        if (
            usable_phone
            and usable_phone in seen_phone
        ):

            reasons.append(
                "Phone"
            )

        if (
            store_url
            and store_url in seen_url
        ):

            reasons.append(
                "StoreURL"
            )

        # ----------------------------------------------------
        # Duplicate
        # ----------------------------------------------------

        if reasons:

            duplicate_reasons.append({

                "StoreCode":
                    row.get(
                        "StoreCode"
                    ),

                "StoreName":
                    row.get(
                        "StoreName"
                    ),

                "Reason":
                    " + ".join(
                        reasons
                    ),

            })

            continue

        # ----------------------------------------------------
        # Keep
        # ----------------------------------------------------

        keep_rows.append(
            index
        )

        if address:

            seen_address.add(
                address
            )

        if usable_phone:

            seen_phone.add(
                usable_phone
            )

        if store_url:

            seen_url.add(
                store_url
            )

    # --------------------------------------------------------
    # Result
    # --------------------------------------------------------

    result = df.loc[
        keep_rows
    ].reset_index(
        drop=True
    )

    # --------------------------------------------------------
    # Save duplicate log
    # --------------------------------------------------------

    if duplicate_reasons:

        duplicate_df = pd.DataFrame(
            duplicate_reasons
        )

        duplicate_path = (
            OUTPUT_DIR
            / "kfc_duplicates_removed.csv"
        )

        duplicate_df.to_csv(
            duplicate_path,
            index=False,
            encoding="utf-8-sig"
        )

        print()
        print(
            "Duplicate log:"
        )

        print(
            duplicate_path.resolve()
        )

        print()
        print(
            "Duplicates removed:"
        )

        print(
            duplicate_df.to_string(
                index=False
            )
        )

    return result


# ============================================================
# MAIN
# ============================================================

async def main():

    print("=" * 80)
    print("KFC TEST EXTRACTOR")
    print("=" * 80)

    print(
        "Target:",
        TARGET_URL
    )

    print(
        "Search provinces:",
        SEARCH_PROVINCES
    )

    all_stores = []

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True
        )

        context = await browser.new_context(

            locale="vi-VN",

            timezone_id="Asia/Ho_Chi_Minh",

            viewport={
                "width": 1600,
                "height": 1000,
            },

            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        )

        # ====================================================
        # LOOP SEARCH
        # ====================================================

        for search_province in SEARCH_PROVINCES:

            print()
            print("=" * 80)
            print(
                "SEARCH:",
                search_province
            )
            print("=" * 80)

            api_responses = []

            page = await context.new_page()

            # ------------------------------------------------
            # Capture API response
            # ------------------------------------------------

            async def handle_response(
                response
            ):

                url = response.url.lower()

                if (
                    "/find-a-kfc/" not in url
                ):
                    return

                try:

                    body = await response.body()

                    if not body:
                        return

                    try:

                        data = json.loads(
                            body.decode(
                                "utf-8",
                                errors="ignore"
                            )
                        )

                    except Exception:

                        return

                    api_responses.append({

                        "url":
                            response.url,

                        "status":
                            response.status,

                        "data":
                            data,

                    })

                    print()
                    print(
                        "[KFC API]",
                        response.status
                    )

                    print(
                        response.url
                    )

                except Exception as e:

                    print(
                        "[API ERROR]",
                        str(e)
                    )

            page.on(
                "response",
                handle_response
            )

            # ------------------------------------------------
            # Open KFC page
            # ------------------------------------------------

            try:

                await page.goto(
                    TARGET_URL,
                    wait_until="domcontentloaded",
                    timeout=90_000
                )

            except Exception as e:

                print(
                    "[PAGE ERROR]",
                    str(e)
                )

                await page.close()

                continue

            # ------------------------------------------------
            # Wait page
            # ------------------------------------------------

            await page.wait_for_timeout(
                8_000
            )

            # ------------------------------------------------
            # Search input
            # ------------------------------------------------

            search_input = page.locator(
                "#RestaurantSearchDesktop"
            )

            if await search_input.count() == 0:

                print(
                    "[ERROR] Search input not found"
                )

                await page.close()

                continue

            # ------------------------------------------------
            # Type province
            # ------------------------------------------------

            try:

                await search_input.click()

                await search_input.fill("")

                await search_input.type(
                    search_province,
                    delay=100
                )

                await page.wait_for_timeout(
                    3_000
                )

            except Exception as e:

                print(
                    "[INPUT ERROR]",
                    str(e)
                )

                await page.close()

                continue

            # ------------------------------------------------
            # Enter
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
                    str(e)
                )

            # ------------------------------------------------
            # Wait API
            # ------------------------------------------------

            await page.wait_for_timeout(
                8_000
            )

            # ------------------------------------------------
            # Fallback:
            # ArrowDown + Enter
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
                        str(e)
                    )

            # ------------------------------------------------
            # Save raw API
            # ------------------------------------------------

            for api_index, api_item in enumerate(
                api_responses,
                start=1
            ):

                safe_province = re.sub(
                    r'[\\/:*?"<>|]',
                    "_",
                    search_province
                )

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
                        indent=2
                    ),
                    encoding="utf-8"
                )

            # ------------------------------------------------
            # Extract stores
            # ------------------------------------------------

            province_store_count = 0

            for api_item in api_responses:

                source_url = api_item[
                    "url"
                ]

                data = api_item[
                    "data"
                ]

                # Expected:
                #
                # {
                #   "key": "...",
                #   "Value": [...]
                # }

                values = []

                if isinstance(
                    data,
                    dict
                ):

                    values = data.get(
                        "Value",
                        []
                    )

                elif isinstance(
                    data,
                    list
                ):

                    values = data

                if not isinstance(
                    values,
                    list
                ):
                    continue

                print(
                    "Stores in API:",
                    len(values)
                )

                for item in values:

                    store = extract_store(
                        item,
                        search_province,
                        source_url
                    )

                    if store is None:
                        continue

                    # ------------------------------------------------
                    # Junk protection
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

                    # Store phải có ít nhất tên hoặc address
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
        len(df)
    )

    # ========================================================
    # STORE CODE DUPLICATE
    # ========================================================

    before_code = len(df)

    df = df.drop_duplicates(
        subset=["StoreCode"],
        keep="first"
    ).reset_index(
        drop=True
    )

    print(
        "After StoreCode duplicate:",
        len(df),
        f"(removed {before_code - len(df)})"
    )

    # ========================================================
    # ADDRESS / PHONE / URL DUPLICATE
    # ========================================================

    before_duplicate = len(df)

    df = deduplicate_stores(
        df
    )

    print(
        "After Address/Phone/URL duplicate:",
        len(df),
        f"(removed "
        f"{before_duplicate - len(df)})"
    )

    # ========================================================
    # SORT
    # ========================================================

    df = df.sort_values(
        by=[
            "Province",
            "StoreName",
            "StoreCode",
        ],
        na_position="last"
    ).reset_index(
        drop=True
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
    # PROVINCE SUMMARY
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
    # PROVINCE IN DATA
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
            ascending=False
        )
    )

    print(
        city_summary.to_string(
            index=False
        )
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
        encoding="utf-8-sig"
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
        index=False
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
        len(df)
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