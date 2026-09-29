import asyncio
import pandas as pd

from retail import crawl_pharmacity


async def main():
    print("=" * 80)
    print("TEST PHARMACITY")
    print("=" * 80)

    records = await crawl_pharmacity()

    print(f"\nTotal records: {len(records)}")

    if not records:
        print("❌ Không tìm thấy cửa hàng.")
        return

    df = pd.DataFrame(records)

    print("\nColumns:")
    print(df.columns.tolist())

    print("\nFirst 20 records:")
    print(df.head(20).to_string(index=False))

    print("\nProvince count:")
    if "Province" in df.columns:
        print(df["Province"].value_counts(dropna=False).to_string())

    print("\nBrand count:")
    if "Brand" in df.columns:
        print(df["Brand"].value_counts(dropna=False).to_string())

    output = "pharmacity_test_output.xlsx"
    df.to_excel(output, index=False)

    print(f"\n✅ Saved: {output}")


if __name__ == "__main__":
    asyncio.run(main())