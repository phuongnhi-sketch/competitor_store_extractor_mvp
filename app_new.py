import asyncio
from io import BytesIO

import pandas as pd
import streamlit as st

from crawler import extract_store_data
from dedupe import dedupe_records


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="Competitor Store Extractor",
    page_icon="🏪",
    layout="wide",
)


# ============================================================
# CONFIG
# ============================================================

OUTPUT_COLUMNS = [
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
# LOAD BRAND CONFIG
# ============================================================

def load_brand_config():
    """
    Try to read brand configuration from common.py.

    Supported structures:

        BRAND_URLS = {
            "KFC": "...",
            "LOTTERIA": "...",
        }

    or

        BRAND_MAP = {
            "KFC": "...",
            "LOTTERIA": "...",
        }

    or

        BRAND_CONFIG = {
            "KFC": "...",
            "LOTTERIA": "...",
        }

    The first matching config is used.
    """

    try:
        import common
    except Exception:
        return {}

    possible_names = [
        "BRAND_URLS",
        "BRAND_MAP",
        "BRAND_CONFIG",
    ]

    for name in possible_names:

        config = getattr(
            common,
            name,
            None,
        )

        if not isinstance(
            config,
            dict,
        ):
            continue

        result = {}

        for key, value in config.items():

            if not isinstance(
                key,
                str,
            ):
                continue

            # ------------------------------------------------
            # Simple:
            #
            # "KFC": "https://..."
            # ------------------------------------------------

            if isinstance(
                value,
                str,
            ):

                result[
                    key.strip()
                ] = value.strip()

                continue

            # ------------------------------------------------
            # Nested config:
            #
            # "KFC": {
            #     "url": "...",
            # }
            # ------------------------------------------------

            if isinstance(
                value,
                dict,
            ):

                url = (
                    value.get("url")
                    or value.get("URL")
                    or value.get("website")
                    or value.get("Website")
                    or value.get("start_url")
                    or value.get("StartURL")
                )

                if url:

                    result[
                        key.strip()
                    ] = str(url).strip()

        if result:
            return result

    return {}


BRAND_CONFIG = load_brand_config()


# ============================================================
# BUILT-IN BRAND CONFIG
# ============================================================
# Keep any existing common.py configuration, but always make
# the dedicated retail brands available in the UI.
# ============================================================

BUILTIN_BRAND_CONFIG = {
    "JOLLIBEE": "https://jollibee.com.vn/cua-hang/",
    "PHUC LONG": "https://www.phuclong.com.vn/",
    "HIGHLANDS COFFEE": (
        "https://order.highlandscoffee.com.vn/"
        "he-thong-cua-han"
    ),
    "STARBUCKS": (
        "https://www.starbucks.vn/"
        "store-locator/"
    ),
    "KFC": (
        "https://www.kfcvietnam.com.vn/"
        "he-thong-nha-hang-kfc"
    ),
    "LOTTERIA": (
        "https://www.lotteria.vn/"
        "danh-sach-so-dien-thoai-cua-hang-LOTTERIA"
    ),
    "PIZZA 4P'S": (
        "https://pizza4ps.com/vn/location/"
    ),
    "PIZZA HUT": (
        "https://pizzahut.vn/store-location/"
    ),
    "DOMINO'S": (
        "https://dominos.vn/store-locations/"
    ),

    # Dedicated retail crawlers
    "THE GIOI DI DONG": (
        "https://www.thegioididong.com/"
        "he-thong-sieu-thi-the-gioi-di-dong/"
    ),
    "DIEN MAY XANH": (
        "https://www.dienmayxanh.com/"
        "he-thong-sieu-thi-dien-may"
    ),
    "FPT SHOP": (
        "https://fptshop.com.vn/cua-hang"
    ),
    "NHA THUOC LONG CHAU": (
        "https://nhathuoclongchau.com.vn/"
        "he-thong-cua-hang"
    ),
    "PHARMACITY": (
        "https://www.pharmacity.vn/"
        "he-thong-cua-hang"
    ),
    "BACH HOA XANH": (
        "https://www.bachhoaxanh.com/"
        "he-thong-sieu-thi"
    ),
}

for _brand, _url in BUILTIN_BRAND_CONFIG.items():
    BRAND_CONFIG.setdefault(_brand, _url)


BRANDS = sorted(
    BRAND_CONFIG.keys()
)


# ============================================================
# PROVINCE NORMALIZATION
# ============================================================

def normalize_province(value):
    """
    Normalize Province / City names so that equivalent names
    are grouped together in Summary and exported data.

    Examples:

        Tp.HCM
        TP.HCM
        TP HCM
        Thành phố Hồ Chí Minh
        Thành phố HCM
        TP. Hồ Chí Minh
        Hồ Chí Minh

    -> Hồ Chí Minh
    """

    if value is None:
        return ""

    value = str(value).strip()

    if not value:
        return ""

    # --------------------------------------------------------
    # Basic whitespace normalization
    # --------------------------------------------------------

    value = (
        value
        .replace("\xa0", " ")
        .strip()
    )

    while "  " in value:
        value = value.replace(
            "  ",
            " ",
        )

    # --------------------------------------------------------
    # Case-insensitive matching
    # --------------------------------------------------------

    key = value.lower()

    # Remove spaces around punctuation for matching
    key_compact = (
        key
        .replace(".", "")
        .replace(",", "")
        .replace("  ", " ")
        .strip()
    )

    # --------------------------------------------------------
    # Hồ Chí Minh
    # --------------------------------------------------------

    hcm_variants = {
        "hồ chí minh",
        "ho chi minh",
        "tp hcm",
        "tphcm",
        "tp hcm.",
        "tp.hcm",
        "tp. hcm",
        "tp.hồ chí minh",
        "tp. hồ chí minh",
        "tphồ chí minh",
        "thành phố hcm",
        "thành phố hồ chí minh",
        "thanh pho hcm",
        "thanh pho ho chi minh",
        "sài gòn",
        "sai gon",
        "saigon",
    }

    if (
        key in hcm_variants
        or key_compact in {
            x.replace(".", "")
            for x in hcm_variants
        }
    ):
        return "Hồ Chí Minh"

    # --------------------------------------------------------
    # Hà Nội
    # --------------------------------------------------------

    hanoi_variants = {
        "hà nội",
        "ha noi",
        "tp hà nội",
        "tp. hà nội",
        "tphà nội",
        "thành phố hà nội",
        "thanh pho ha noi",
    }

    if (
        key in hanoi_variants
        or key_compact in {
            x.replace(".", "")
            for x in hanoi_variants
        }
    ):
        return "Hà Nội"

    # --------------------------------------------------------
    # Đà Nẵng
    # --------------------------------------------------------

    danang_variants = {
        "đà nẵng",
        "da nang",
        "tp đà nẵng",
        "tp. đà nẵng",
        "tpđà nẵng",
        "thành phố đà nẵng",
        "thanh pho da nang",
    }

    if (
        key in danang_variants
        or key_compact in {
            x.replace(".", "")
            for x in danang_variants
        }
    ):
        return "Đà Nẵng"

    # --------------------------------------------------------
    # Hải Phòng
    # --------------------------------------------------------

    haiphong_variants = {
        "hải phòng",
        "hai phong",
        "tp hải phòng",
        "tp. hải phòng",
        "thành phố hải phòng",
        "thanh pho hai phong",
    }

    if (
        key in haiphong_variants
        or key_compact in {
            x.replace(".", "")
            for x in haiphong_variants
        }
    ):
        return "Hải Phòng"

    # --------------------------------------------------------
    # Cần Thơ
    # --------------------------------------------------------

    cantho_variants = {
        "cần thơ",
        "can tho",
        "tp cần thơ",
        "tp. cần thơ",
        "thành phố cần thơ",
        "thanh pho can tho",
    }

    if (
        key in cantho_variants
        or key_compact in {
            x.replace(".", "")
            for x in cantho_variants
        }
    ):
        return "Cần Thơ"

    # --------------------------------------------------------
    # Huế
    # --------------------------------------------------------

    hue_variants = {
        "huế",
        "hue",
        "tp huế",
        "tp. huế",
        "thành phố huế",
        "thanh pho hue",
        "thừa thiên huế",
        "thua thien hue",
    }

    if (
        key in hue_variants
        or key_compact in {
            x.replace(".", "")
            for x in hue_variants
        }
    ):
        return "Huế"

    # --------------------------------------------------------
    # Other common city prefixes
    # --------------------------------------------------------

    known_city_names = {
        "hồ chí minh": "Hồ Chí Minh",
        "hà nội": "Hà Nội",
        "đà nẵng": "Đà Nẵng",
        "hải phòng": "Hải Phòng",
        "cần thơ": "Cần Thơ",
        "huế": "Huế",
        "nha trang": "Nha Trang",
        "vũng tàu": "Bà Rịa - Vũng Tàu",
        "bà rịa - vũng tàu": "Bà Rịa - Vũng Tàu",
        "bà rịa-vũng tàu": "Bà Rịa - Vũng Tàu",
    }

    # --------------------------------------------------------
    # Exact normalized city names
    # --------------------------------------------------------

    if key in known_city_names:
        return known_city_names[key]

    # --------------------------------------------------------
    # Remove common prefixes
    # --------------------------------------------------------

    prefixes = [
        "thành phố ",
        "thanh pho ",
        "tp. ",
        "tp ",
        "t.p. ",
        "t.p ",
    ]

    stripped = key

    for prefix in prefixes:

        if stripped.startswith(prefix):

            candidate = (
                stripped[len(prefix):]
                .strip()
            )

            if candidate in known_city_names:

                return known_city_names[
                    candidate
                ]

    # --------------------------------------------------------
    # Preserve original value if unknown
    # --------------------------------------------------------

    return value


# ============================================================
# DATAFRAME CLEANING
# ============================================================

def clean_dataframe(df):
    """
    Prepare dataframe for display/export.
    """

    if df is None or df.empty:

        return pd.DataFrame(
            columns=OUTPUT_COLUMNS
        )

    df = df.copy()

    # --------------------------------------------------------
    # Ensure columns
    # --------------------------------------------------------

    for column in OUTPUT_COLUMNS:

        if column not in df.columns:

            df[column] = ""

    # --------------------------------------------------------
    # Fill null
    # --------------------------------------------------------

    df = df.fillna("")

    # --------------------------------------------------------
    # Clean strings
    # --------------------------------------------------------

    for column in df.columns:

        if df[column].dtype == "object":

            df[column] = (
                df[column]
                .astype(str)
                .replace("nan", "")
                .replace("None", "")
                .str.strip()
            )

    # --------------------------------------------------------
    # Normalize Province
    # --------------------------------------------------------

    if "Province" in df.columns:

        df["Province"] = (
            df["Province"]
            .apply(normalize_province)
        )

    return df


# ============================================================
# EXPORT HELPERS
# ============================================================

def dataframe_to_excel_bytes(df):
    """
    Export dataframe to Excel bytes.
    """

    output = BytesIO()

    with pd.ExcelWriter(
        output,
        engine="openpyxl",
    ) as writer:

        df.to_excel(
            writer,
            index=False,
            sheet_name="Stores",
        )

    output.seek(0)

    return output.getvalue()


def dataframe_to_csv_bytes(df):
    """
    Export dataframe to CSV bytes.
    """

    return df.to_csv(
        index=False,
        encoding="utf-8-sig",
    ).encode(
        "utf-8-sig"
    )


def get_record_brand(record):
    """
    Safely get record brand.
    """

    if not isinstance(
        record,
        dict,
    ):
        return ""

    return str(
        record.get(
            "Brand",
            "",
        )
    ).strip().upper()


# ============================================================
# HEADER
# ============================================================

st.title(
    "🏪 Competitor Store Extractor"
)

st.caption(
    "Extract competitor store information "
    "from official websites."
)


# ============================================================
# MAIN CONFIGURATION
# ============================================================

st.subheader(
    "Configuration"
)


# ============================================================
# BRAND + INPUT METHOD
# ============================================================

brand_col, source_col = st.columns(
    [1, 1]
)


with brand_col:

    # --------------------------------------------------------
    # Add Custom / Other option
    #
    # Existing configured brands are NOT changed.
    # --------------------------------------------------------

    brand_options = [
        "Custom / Other"
    ] + BRANDS

    default_brand_index = (
        brand_options.index("KFC")
        if "KFC" in brand_options
        else 0
    )

    selected_brand = st.selectbox(
        "Brand",
        options=brand_options,
        index=default_brand_index,
    )


with source_col:

    source_type = st.radio(
        "Input method",
        options=[
            "Configured website",
            "Custom URL",
        ],
        horizontal=True,
    )


# ============================================================
# WEBSITE / URL
# ============================================================

custom_brand_name = ""
urls = []


if source_type == "Configured website":

    # --------------------------------------------------------
    # Configured website
    # --------------------------------------------------------

    if selected_brand == "Custom / Other":

        st.warning(
            "Custom / Other does not have a configured website. "
            "Please select Custom URL."
        )

    else:

        configured_url = BRAND_CONFIG.get(
            selected_brand,
            "",
        )

        st.text_input(
            "Website",
            value=configured_url,
            disabled=True,
        )

        if configured_url:

            urls = [
                configured_url
            ]

else:

    # --------------------------------------------------------
    # Custom URL
    # --------------------------------------------------------

    custom_brand_name = st.text_input(
        "Brand name (optional)",
        placeholder=(
            "Example: Burger King"
        ),
        help=(
            "Optional. This name is only used when "
            "the crawler does not detect a Brand."
        ),
    ).strip()

    custom_url = st.text_input(
        "Website URL",
        placeholder=(
            "https://example.com/"
        ),
    ).strip()

    if custom_url:

        urls = [
            custom_url
        ]


# ============================================================
# CRAWL SETTINGS
# ============================================================

st.subheader(
    "Crawl Settings"
)

max_pages = st.number_input(
    "Max pages",
    min_value=3,
    max_value=50,
    value=20,
    step=1,
)


# ============================================================
# DETERMINE CRAWLER MODE
# ============================================================

# IMPORTANT:
#
# Dedicated KFC crawler is used ONLY when:
#
#   1. Brand = KFC
#   2. Input method = Configured website
#
# If user selects Custom URL, EVEN IF Brand = KFC,
# the custom URL MUST go through the generic crawler.
#
# This is the key fix for the previous bug.
# ============================================================

use_kfc_dedicated_crawler = (
    selected_brand == "KFC"
    and source_type == "Configured website"
)


# ============================================================
# INFORMATION BOX
# ============================================================

if use_kfc_dedicated_crawler:

    st.info(
        "KFC uses the existing dedicated KFC crawler. "
        "All available provinces/cities will be searched "
        "automatically. StoreCode deduplication logic "
        "is kept unchanged."
    )

elif (
    selected_brand == "LOTTERIA"
    and source_type == "Configured website"
):

    st.info(
        "Lotteria uses the crawler/parser configured "
        "for this brand."
    )

elif source_type == "Custom URL":

    retail_brand_names = {
        "THE GIOI DI DONG",
        "DIEN MAY XANH",
        "FPT SHOP",
        "NHA THUOC LONG CHAU",
        "PHARMACITY",
        "BACH HOA XANH",
    }

    if selected_brand in retail_brand_names:
        st.info(
            f"{selected_brand} uses its dedicated retail crawler. "
            "The custom URL will be passed to that crawler."
        )
    else:
        st.caption(
            "Custom URL uses the generic crawler for this brand."
        )

else:

    st.caption(
        "This brand will use the generic crawler "
        "and parser."
    )


# ============================================================
# RUN BUTTON
# ============================================================

st.divider()

run_button = st.button(
    "🚀 Extract Stores",
    type="primary",
    use_container_width=True,
)


# ============================================================
# RUN
# ============================================================

if run_button:

    # --------------------------------------------------------
    # Validate URL
    # --------------------------------------------------------

    if not urls:

        st.error(
            "Please provide a website URL."
        )

        st.stop()

    # --------------------------------------------------------
    # Status
    # --------------------------------------------------------

    status_placeholder = st.empty()

    progress = st.progress(
        0
    )

    debug_expander = st.expander(
        "Debug / Crawl Log",
        expanded=False,
    )

    all_records = []
    all_pages = []
    all_logs = []

    # --------------------------------------------------------
    # Process URLs
    # --------------------------------------------------------

    for index, url in enumerate(
        urls,
        start=1,
    ):

        status_placeholder.info(
            f"Processing "
            f"{index}/{len(urls)}: "
            f"{url}"
        )

        debug_lines = []

        debug_lines.append(
            "=" * 80
        )

        debug_lines.append(
            f"Processing URL "
            f"{index}/{len(urls)}"
        )

        debug_lines.append(
            url
        )

        debug_lines.append(
            "=" * 80
        )

        try:

            # =================================================
            # KFC DEDICATED MODE
            # =================================================
            #
            # This is ONLY for:
            #
            # Brand = KFC
            # Input = Configured website
            #
            # crawl_kfc() does NOT receive the custom URL.
            # It uses its own existing KFC logic.
            # =================================================

            if use_kfc_dedicated_crawler:

                debug_lines.append(
                    "Crawler mode: "
                    "KFC dedicated crawler"
                )

                from brands.kfc import crawl_kfc

                records = asyncio.run(
                    crawl_kfc()
                )

                pages = []
                logs = []

            # =================================================
            # GENERIC MODE
            # =================================================
            #
            # This covers:
            #
            # - KFC + Custom URL
            # - Other Brand + Configured website
            # - Other Brand + Custom URL
            # - Custom / Other + Custom URL
            #
            # Most importantly:
            #
            # KFC + Custom URL will NOT call crawl_kfc().
            # =================================================

            else:

                debug_lines.append(
                    "Crawler mode: "
                    "Generic crawler"
                )

                debug_lines.append(
                    f"Generic crawler URL: "
                    f"{url}"
                )

                result = extract_store_data(
                    url,
                    max_pages=int(max_pages),
                )

                if (
                    isinstance(result, tuple)
                    and len(result) == 3
                ):

                    records, pages, logs = result

                else:

                    records = result
                    pages = []
                    logs = []

            # ------------------------------------------------
            # Normalize None
            # ------------------------------------------------

            if records is None:
                records = []

            if pages is None:
                pages = []

            if logs is None:
                logs = []

            # ------------------------------------------------
            # Ensure list
            # ------------------------------------------------

            if not isinstance(
                records,
                list,
            ):

                records = list(
                    records
                )

            if not isinstance(
                pages,
                list,
            ):

                pages = list(
                    pages
                )

            if not isinstance(
                logs,
                list,
            ):

                logs = list(
                    logs
                )

            # =================================================
            # CUSTOM BRAND FALLBACK
            # =================================================
            #
            # If user entered a Brand name for Custom URL,
            # use it ONLY when crawler did not detect Brand.
            #
            # Example:
            #
            # User enters:
            #   Brand name = "ABC Coffee"
            #
            # Crawler returns:
            #   Brand = ""
            #
            # Result becomes:
            #   Brand = "ABC Coffee"
            #
            # But if crawler already detected:
            #   Brand = "ABC"
            #
            # We keep "ABC".
            # =================================================

            if (
                source_type == "Custom URL"
                and custom_brand_name
            ):

                for record in records:

                    if not isinstance(
                        record,
                        dict,
                    ):
                        continue

                    existing_brand = str(
                        record.get(
                            "Brand",
                            "",
                        )
                        or ""
                    ).strip()

                    if not existing_brand:

                        record[
                            "Brand"
                        ] = custom_brand_name

            # ------------------------------------------------
            # Add results
            # ------------------------------------------------

            all_records.extend(
                records
            )

            all_pages.extend(
                pages
            )

            all_logs.extend(
                logs
            )

            # ------------------------------------------------
            # Debug
            # ------------------------------------------------

            debug_lines.append(
                f"Extracted records: "
                f"{len(records)}"
            )

            debug_lines.append(
                f"Crawled pages: "
                f"{len(pages)}"
            )

            # ------------------------------------------------
            # Brand counts
            # ------------------------------------------------

            brand_counts = {}

            for record in records:

                record_brand = (
                    get_record_brand(
                        record
                    )
                )

                if not record_brand:

                    record_brand = (
                        "Unknown"
                    )

                brand_counts[
                    record_brand
                ] = (
                    brand_counts.get(
                        record_brand,
                        0,
                    )
                    + 1
                )

            for (
                record_brand,
                count,
            ) in sorted(
                brand_counts.items()
            ):

                debug_lines.append(
                    f"{record_brand}: "
                    f"{count}"
                )

            # ------------------------------------------------
            # Crawler logs
            # ------------------------------------------------

            if logs:

                debug_lines.append(
                    ""
                )

                debug_lines.append(
                    "--- Crawler log ---"
                )

                debug_lines.extend(
                    str(x)
                    for x in logs
                )

        except Exception as e:

            debug_lines.append(
                f"ERROR: "
                f"{type(e).__name__}: "
                f"{e}"
            )

            st.error(
                f"Error processing "
                f"{url}: {e}"
            )

        # ----------------------------------------------------
        # Debug
        # ----------------------------------------------------

        with debug_expander:

            st.code(
                "\n".join(
                    debug_lines
                ),
                language="text",
            )

        progress.progress(
            int(
                index
                / len(urls)
                * 100
            )
        )

    # ========================================================
    # PROCESSING
    # ========================================================

    st.subheader(
        "Processing"
    )

    raw_count = len(
        all_records
    )

    st.write(
        f"Raw rows: **{raw_count:,}**"
    )

    # ========================================================
    # DEDUPLICATION
    # ========================================================
    #
    # ONLY the real KFC dedicated crawler skips generic
    # dedupe.
    #
    # KFC + Custom URL MUST use generic dedupe.
    #
    # This is controlled by:
    #
    #     use_kfc_dedicated_crawler
    #
    # rather than:
    #
    #     selected_brand == "KFC"
    # ========================================================

    if use_kfc_dedicated_crawler:

        debug_dedupe_message = (
            "KFC dedicated mode: "
            "generic dedupe skipped."
        )

        deduped_records = (
            all_records
        )

    else:

        debug_dedupe_message = (
            "Generic mode: "
            "generic dedupe applied."
        )

        try:

            deduped_records = (
                dedupe_records(
                    all_records
                )
            )

        except Exception as e:

            st.error(
                "Duplicate processing failed: "
                f"{type(e).__name__}: {e}"
            )

            st.stop()

    # --------------------------------------------------------
    # Dedupe debug
    # --------------------------------------------------------

    with debug_expander:

        st.code(
            debug_dedupe_message,
            language="text",
        )

    final_count = len(
        deduped_records
    )

    removed_count = (
        raw_count
        - final_count
    )

    st.write(
        f"After duplicate removal: "
        f"**{final_count:,}** "
        f"(removed **{removed_count:,}**)"
    )

    # ========================================================
    # DATAFRAME
    # ========================================================

    df = pd.DataFrame(
        deduped_records
    )

    df = clean_dataframe(
        df
    )

    # ========================================================
    # KPI
    # ========================================================

    st.subheader(
        "Summary"
    )

    col1, col2, col3, col4 = st.columns(
        4
    )

    with col1:

        st.metric(
            "Total Stores",
            f"{len(df):,}",
        )

    with col2:

        if (
            not df.empty
            and "Province" in df.columns
        ):

            province_count = (
                df["Province"]
                .replace(
                    "",
                    pd.NA,
                )
                .dropna()
                .nunique()
            )

        else:

            province_count = 0

        st.metric(
            "Provinces",
            f"{province_count:,}",
        )

    with col3:

        if (
            not df.empty
            and "Phone" in df.columns
        ):

            phone_count = (
                df["Phone"]
                .replace(
                    "",
                    pd.NA,
                )
                .dropna()
                .nunique()
            )

        else:

            phone_count = 0

        st.metric(
            "Phones",
            f"{phone_count:,}",
        )

    with col4:

        if not df.empty:

            lat_ok = (
                df["Lat"]
                .astype(str)
                .str.strip()
                .ne("")
            )

            long_ok = (
                df["Long"]
                .astype(str)
                .str.strip()
                .ne("")
            )

            coordinate_count = (
                lat_ok
                & long_ok
            ).sum()

        else:

            coordinate_count = 0

        st.metric(
            "Coordinates",
            f"{coordinate_count:,}",
        )

    # ========================================================
    # STORE COUNT BY BRAND
    # ========================================================

    if (
        not df.empty
        and "Brand" in df.columns
    ):

        st.subheader(
            "Store Count by Brand"
        )

        brand_summary = (
            df.groupby(
                "Brand",
                dropna=False,
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

        st.dataframe(
            brand_summary,
            use_container_width=True,
            hide_index=True,
        )

    # ========================================================
    # STORE COUNT BY PROVINCE
    # ========================================================

    if (
        not df.empty
        and "Province" in df.columns
    ):

        st.subheader(
            "Store Count by Province"
        )

        province_summary = (
            df[
                df["Province"]
                .astype(str)
                .str.strip()
                .ne("")
            ]
            .groupby(
                "Province",
                dropna=False,
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

        st.dataframe(
            province_summary,
            use_container_width=True,
            hide_index=True,
        )

    # ========================================================
    # EXTRACTION METHOD
    # ========================================================

    if (
        not df.empty
        and "Method" in df.columns
    ):

        st.subheader(
            "Extraction Method"
        )

        method_summary = (
            df.groupby(
                "Method",
                dropna=False,
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

        st.dataframe(
            method_summary,
            use_container_width=True,
            hide_index=True,
        )

    # ========================================================
    # STORE TABLE
    # ========================================================

    st.subheader(
        "Store Data"
    )

    if df.empty:

        st.warning(
            "No store data found."
        )

    else:

        display_columns = [
            column
            for column in OUTPUT_COLUMNS
            if column in df.columns
        ]

        st.dataframe(
            df[
                display_columns
            ],
            use_container_width=True,
            hide_index=True,
            height=600,
        )

    # ========================================================
    # DOWNLOAD
    # ========================================================

    if not df.empty:

        st.subheader(
            "Download"
        )

        download_col1, download_col2 = (
            st.columns(2)
        )

        export_df = df[
            [
                column
                for column in OUTPUT_COLUMNS
                if column in df.columns
            ]
        ]

        with download_col1:

            st.download_button(
                "⬇️ Download Excel",
                data=dataframe_to_excel_bytes(
                    export_df
                ),
                file_name=(
                    "competitor_store_extractor.xlsx"
                ),
                mime=(
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet"
                ),
                use_container_width=True,
            )

        with download_col2:

            st.download_button(
                "⬇️ Download CSV",
                data=dataframe_to_csv_bytes(
                    export_df
                ),
                file_name=(
                    "competitor_store_extractor.csv"
                ),
                mime="text/csv",
                use_container_width=True,
            )

    # ========================================================
    # FINISHED
    # ========================================================

    status_placeholder.success(
        f"Finished — "
        f"{len(df):,} stores found."
    )