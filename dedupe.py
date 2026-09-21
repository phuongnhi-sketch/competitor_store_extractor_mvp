from common import (
    clean_text,
    normalize_for_compare,
    normalize_phone,
    normalize_url,
    normalize_url_for_compare,
    is_usable_store_url,
    is_generic_store_locator_url,
    is_api_or_ajax_url,
    fill_coordinates_from_url,
)


# ============================================================
# GENERIC VALIDATION
# ============================================================

def is_valid_store_record(record):

    address = clean_text(
        record.get("Address", "")
    )

    name = clean_text(
        record.get("StoreName", "")
    )

    phone = clean_text(
        record.get("Phone", "")
    )

    store_url = clean_text(
        record.get("StoreURL", "")
    )

    method = clean_text(
        record.get("Method", "")
    )

    if not address:
        return False

    if not name and not phone:
        return False

    if (
        method == "HTML Card"
        and is_generic_store_locator_url(
            store_url
        )
    ):
        return False

    if (
        store_url
        and is_api_or_ajax_url(
            store_url
        )
    ):
        return False

    return True


# ============================================================
# GENERIC DEDUPE
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

        if record.get("Phone"):

            record["Phone"] = clean_text(
                record["Phone"]
            )

        store_url = normalize_url(
            record.get(
                "StoreURL",
                ""
            )
        )

        if not is_usable_store_url(
            store_url
        ):

            store_url = ""

        record["StoreURL"] = store_url

        record = fill_coordinates_from_url(
            record
        )

        if not is_valid_store_record(
            record
        ):

            continue

        record["_Priority"] = (
            method_priority.get(
                record.get("Method", ""),
                99
            )
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

    seen_addresses = set()
    seen_phones = set()
    seen_urls = set()

    for record in cleaned:

        brand = normalize_for_compare(
            record.get(
                "Brand",
                ""
            )
        )

        address = normalize_for_compare(
            record.get(
                "Address",
                ""
            )
        )

        phone = normalize_phone(
            record.get(
                "Phone",
                ""
            )
        )

        store_url = normalize_url_for_compare(
            record.get(
                "StoreURL",
                ""
            )
        )

        address_key = (
            brand,
            address
        ) if address else None

        phone_key = (
            brand,
            phone
        ) if phone else None

        url_key = (
            brand,
            store_url
        ) if store_url else None

        duplicate = False

        if (
            address_key
            and address_key in seen_addresses
        ):

            duplicate = True

        if (
            not duplicate
            and phone_key
            and phone_key in seen_phones
        ):

            duplicate = True

        if (
            not duplicate
            and url_key
            and url_key in seen_urls
        ):

            duplicate = True

        if duplicate:
            continue

        if address_key:
            seen_addresses.add(
                address_key
            )

        if phone_key:
            seen_phones.add(
                phone_key
            )

        if url_key:
            seen_urls.add(
                url_key
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
# KFC DEDUPE
# ============================================================

KFC_COMMON_PHONES = {
    "19006886"
}


def normalize_kfc_store_code(value):

    return clean_text(
        value
    ).strip().upper()


def dedupe_kfc_records(records):

    """
    KFC ONLY.

    Duplicate criterion:

        StoreCode ONLY

    NOT used:

        Address
        Phone
        StoreURL
        StoreName
        Lat
        Long

    19006886 is a common hotline and is ignored.
    """

    if not records:
        return []

    result = []

    seen_codes = set()

    for record in records:

        record = {
            key: clean_text(value)
            for key, value in record.items()
        }

        code = normalize_kfc_store_code(
            record.get(
                "StoreCode",
                ""
            )
        )

        phone = normalize_phone(
            record.get(
                "Phone",
                ""
            )
        )

        # ----------------------------------------------------
        # Hotline must NOT be used as duplicate identifier
        # ----------------------------------------------------

        if phone in KFC_COMMON_PHONES:

            record["Phone"] = (
                record.get("Phone", "")
            )

        # ----------------------------------------------------
        # StoreCode duplicate
        # ----------------------------------------------------

        if code:

            if code in seen_codes:
                continue

            seen_codes.add(code)

        # ----------------------------------------------------
        # Missing StoreCode
        #
        # Do NOT dedupe using Address / Phone / URL.
        # Keep the record.
        # ----------------------------------------------------

        record = fill_coordinates_from_url(
            record
        )

        result.append(
            record
        )

    return result