# 🏪 Competitor Store Extractor

Tool được xây dựng bằng **Python + Streamlit + Playwright** để tự động trích xuất thông tin cửa hàng từ website chính thức của các thương hiệu F&B.

Tool hỗ trợ:

* Crawl thông tin cửa hàng từ website chính thức.
* Tự động lấy:

  * Brand
  * Store Code
  * Store Name
  * Address
  * Province
  * Ward
  * Phone
  * Latitude
  * Longitude
  * Store URL
  * Source URL
  * Extraction Method
* Xử lý duplicate store.
* Xuất kết quả ra **Excel** và **CSV**.
* Hỗ trợ crawler riêng cho một số website có cấu trúc đặc biệt.
* Có giao diện Streamlit để người dùng không cần chạy Python code trực tiếp.

---

# 1. Project Structure

Cấu trúc project:

```text
competitor_store_extractor_mvp/
│
├── app_new.py
├── crawler.py
├── common.py
├── dedupe.py
│
├── brands/
│   ├── __init__.py
│   ├── kfc.py
│   └── ...
│
├── requirements.txt
│
├── README.md
│
└── kfc_test_output/
    ├── raw_api/
    ├── kfc_test_stores.csv
    ├── kfc_test_stores.xlsx
    ├── kfc_storecode_duplicates_removed.csv
    └── kfc_cross_province_check.csv
```

> Tên file/thư mục có thể khác tùy phiên bản project. Khi triển khai thực tế, cần đảm bảo các file Python được import đúng vị trí.

---

# 2. Requirements

## 2.1. Operating System

Khuyến nghị:

* Windows 10 / Windows 11
* Python 3.10 trở lên

Có thể sử dụng project trên các hệ điều hành khác nếu Python và Playwright được cài đặt đúng.

---

# 3. Kiểm tra Python

Mở **Command Prompt** hoặc terminal trong VS Code:

```bash
python --version
```

Ví dụ:

```text
Python 3.12.10
```

Nếu máy sử dụng Windows và lệnh `python` không hoạt động, thử:

```bash
py --version
```

---

# 4. Mở Project

Mở thư mục project bằng VS Code.

Ví dụ:

```text
C:\Users\PC\Downloads\competitor_store_extractor_mvp
```

Trong VS Code:

**File → Open Folder → chọn thư mục project**

Sau đó mở Terminal:

**Terminal → New Terminal**

Kiểm tra thư mục hiện tại:

```bash
cd
```

Hoặc trên PowerShell:

```powershell
Get-Location
```

Đảm bảo terminal đang đứng trong thư mục:

```text
competitor_store_extractor_mvp
```

---

# 5. Tạo Virtual Environment

Khuyến nghị sử dụng virtual environment để tránh xung đột package với các project Python khác.

Chạy:

```bash
python -m venv .venv
```

Sau khi tạo xong, kích hoạt environment.

## Windows PowerShell

```powershell
.venv\Scripts\Activate.ps1
```

## Windows CMD

```cmd
.venv\Scripts\activate
```

Nếu thành công, terminal sẽ hiển thị:

```text
(.venv)
```

ở đầu dòng.

Ví dụ:

```text
(.venv) PS C:\Users\PC\Downloads\competitor_store_extractor_mvp>
```

---

# 6. Cài Python Packages

Nếu project có `requirements.txt`, chạy:

```bash
pip install -r requirements.txt
```

Các package chính của project gồm:

* Streamlit
* Pandas
* Playwright
* BeautifulSoup
* OpenPyXL

Nếu chưa có `requirements.txt`, có thể cài:

```bash
pip install streamlit pandas playwright beautifulsoup4 openpyxl
```

---

# 7. Cài Playwright Browser

Đây là bước **bắt buộc** vì crawler sử dụng Playwright để mở website và xử lý JavaScript.

Sau khi cài package:

```bash
python -m playwright install chromium
```

Nếu chỉ sử dụng Chromium:

```bash
playwright install chromium
```

Khuyến nghị dùng:

```bash
python -m playwright install chromium
```

để đảm bảo lệnh sử dụng đúng Python environment hiện tại.

---

# 8. Chạy Application

Sau khi cài đặt xong, chạy:

```bash
streamlit run app_new.py
```

Terminal sẽ hiển thị tương tự:

```text
You can now view your Streamlit app in your browser.

Local URL: http://localhost:8501
```

Mở trình duyệt và truy cập:

```text
http://localhost:8501
```

---

# 9. Sử dụng Tool

## 9.1. Chọn Brand

Trong giao diện **Competitor Store Extractor**, chọn brand cần crawl.

Các brand hiện được cấu hình có thể bao gồm:

* KFC
* Pizza Hut
* Pizza 4P's
* Domino's
* Lotteria
* Jollibee
* Starbucks
* Highlands Coffee
* Phúc Long

Danh sách thực tế phụ thuộc vào `BRAND_CONFIG`.

---

# 10. Brand Configuration

Cấu hình website nằm trong `common.py` hoặc file configuration tương ứng.

Ví dụ:

```python
BRAND_CONFIG = {

    "KFC": {
        "crawler": "kfc",
        "urls": [
            "https://www.kfcvietnam.com.vn/he-thong-nha-hang-kfc"
        ],
    },

    "PIZZA HUT": {
        "crawler": "pizza_hut",
        "urls": [
            "https://pizzahut.vn/store-location"
        ],
    },

    "LOTTERIA": {
        "crawler": "generic",
        "urls": [
            "https://www.lotteria.vn/danh-sach-so-dien-thoai-cua-hang-LOTTERIA"
        ],
    },

    "JOLLIBEE": {
        "crawler": "generic",
        "urls": [
            "https://jollibee.com.vn/cua-hang"
        ],
    },

}
```

## Important

**URL phải là trang chứa thông tin cửa hàng hoặc trang store locator chính thức của brand.**

Không nên tùy tiện sử dụng homepage.

Ví dụ Lotteria:

```text
https://www.lotteria.vn/
```

không phải URL crawler đang sử dụng.

URL hiện tại:

```text
https://www.lotteria.vn/danh-sach-so-dien-thoai-cua-hang-LOTTERIA
```

---

# 11. Generic Crawler và Dedicated Crawler

Project sử dụng hai loại crawler.

## 11.1. Generic Crawler

Dùng cho những website có cấu trúc tương đối phổ biến.

Ví dụ:

```text
Jollibee
Phúc Long
Starbucks
Lotteria
Domino's
Pizza 4P's
Highlands Coffee
```

Generic crawler có thể xử lý:

```text
API / JSON
HTML Table
HTML Card
```

và một số parser đặc biệt như Pizza Hut.

---

# 12. Dedicated Crawler

Một số website có logic đặc biệt nên sử dụng crawler riêng.

Ví dụ:

```text
KFC
```

KFC sử dụng:

```text
brands/kfc.py
```

Crawler KFC:

1. Mở website KFC.
2. Tìm kiếm từng tỉnh/thành.
3. Capture API `/find-a-kfc/`.
4. Parse dữ liệu API.
5. Sử dụng `StoreCode` làm unique identifier.
6. Dedupe theo `StoreCode`.

### Lưu ý

Không nên đưa KFC quay lại generic crawler nếu không có lý do rõ ràng, vì KFC có logic xử lý dữ liệu riêng.

---

# 13. Duplicate Handling

File:

```text
dedupe.py
```

chứa logic duplicate cho generic crawler.

Generic crawler có thể kiểm tra duplicate dựa trên:

* Address
* Phone
* Store URL

và ưu tiên record theo phương thức extraction.

Ví dụ:

```text
API/JSON
HTML Table
Pizza Hut HTML
HTML Card
```

## KFC

KFC không sử dụng generic duplicate logic.

KFC sử dụng:

```text
StoreCode
```

làm unique identifier.

Do đó không nên áp dụng generic `dedupe_records()` cho KFC.

---

# 14. Crawl Settings

Trong giao diện có phần:

```text
Crawl Settings
```

với:

```text
Max pages
```

Thiết lập này chủ yếu áp dụng cho generic crawler.

Ví dụ:

```text
Max pages = 20
```

Crawler sẽ không crawl quá số lượng page được cấu hình.

### KFC

KFC có dedicated crawler và tự động tìm kiếm các tỉnh/thành được cấu hình.

Do đó `Max pages` không kiểm soát số tỉnh của KFC.

---

# 15. Output

Sau khi crawl xong, tool hiển thị:

```text
Processing
```

và:

```text
Summary
```

Các thông tin chính:

* Total Stores
* Provinces
* Phones
* Coordinates
* Store Count by Brand
* Store Count by Province
* Extraction Method

Sau đó hiển thị bảng:

```text
Store Data
```

---

# 16. Output Columns

Output chuẩn gồm:

```text
Brand
StoreCode
StoreName
Address
Province
Ward
Phone
Lat
Long
StoreURL
SourceURL
Method
```

---

# 17. Export

Tool hỗ trợ:

### Excel

```text
.xlsx
```

### CSV

```text
.csv
```

CSV sử dụng:

```text
UTF-8-SIG
```

để đảm bảo tiếng Việt hiển thị đúng khi mở bằng Microsoft Excel.

---

# 18. Debugging

Nếu crawler không tìm được store, kiểm tra phần:

```text
Debug / Crawl Log
```

Ví dụ:

```text
OPEN: https://example.com/
HTTP 200: https://example.com/
NO STORE FOUND
```

Điều này có nghĩa:

* Website đã mở thành công.
* HTTP response thành công.
* Nhưng crawler không tìm được dữ liệu store phù hợp.

---

# 19. Các lỗi thường gặp

## 19.1. `ModuleNotFoundError`

Ví dụ:

```text
ModuleNotFoundError: No module named 'playwright'
```

Cài package:

```bash
pip install playwright
```

Sau đó:

```bash
python -m playwright install chromium
```

---

## 19.2. Streamlit không chạy

Kiểm tra:

```bash
streamlit --version
```

Nếu chưa có:

```bash
pip install streamlit
```

Sau đó:

```bash
streamlit run app_new.py
```

---

## 19.3. Playwright không tìm thấy browser

Ví dụ:

```text
Executable doesn't exist
```

Chạy:

```bash
python -m playwright install chromium
```

---

## 19.4. Website trả về 0 stores

Kiểm tra theo thứ tự:

### Step 1 — Kiểm tra URL

URL phải là URL store locator hoặc trang danh sách cửa hàng.

### Step 2 — Mở URL bằng Chrome

Xác nhận website thực sự có danh sách cửa hàng.

### Step 3 — Kiểm tra Debug / Crawl Log

Xem crawler có:

```text
HTTP 200
```

hay không.

### Step 4 — Kiểm tra website có sử dụng API

Nếu website lấy dữ liệu bằng JavaScript/API, generic crawler có thể cần parser hoặc dedicated crawler riêng.

---

# 20. Thêm Brand mới

Để thêm brand mới, trước tiên thêm website vào `BRAND_CONFIG`.

Ví dụ:

```python
"NEW BRAND": {
    "crawler": "generic",
    "urls": [
        "https://example.com/store-locator"
    ],
},
```

Sau đó chạy lại application.

Nếu generic crawler có thể đọc được website:

```text
→ Không cần viết crawler mới.
```

Nếu website có cấu trúc/API đặc biệt:

```text
→ Có thể tạo dedicated crawler trong brands/.
```

---

# 21. Nguyên tắc phát triển

Khi sửa crawler, nên ưu tiên:

```text
1. Không làm thay đổi các brand đang chạy ổn định.
2. Tạo parser/dedicated crawler riêng nếu website có cấu trúc đặc biệt.
3. Không áp dụng generic dedupe cho brand có logic unique identifier riêng.
4. Luôn kiểm tra output trước và sau khi thay đổi code.
5. Kiểm tra duplicate theo từng brand.
```

Đặc biệt, khi sửa một brand cụ thể, hạn chế thay đổi logic dùng chung trong:

```text
crawler.py
dedupe.py
common.py
```

nếu không thực sự cần thiết.

---

# 22. Quy trình chạy hàng ngày

Khi project đã được cài đặt, lần sau chỉ cần:

### Step 1

Mở project bằng VS Code.

### Step 2

Mở Terminal.

### Step 3

Activate virtual environment:

```bash
.venv\Scripts\activate
```

### Step 4

Chạy application:

```bash
streamlit run app_new.py
```

### Step 5

Mở:

```text
http://localhost:8501
```

### Step 6

Chọn Brand → Run Crawl → kiểm tra kết quả → Export Excel/CSV.

---

# 23. Stop Application

Để dừng Streamlit:

```text
Ctrl + C
```

trong Terminal.

---

# 24. Git / Version Control

Nếu project được quản lý bằng Git, không nên commit virtual environment.

Thêm vào `.gitignore`:

```text
.venv/
__pycache__/
*.pyc
kfc_test_output/
```

Có thể kiểm tra:

```bash
git status
```

Sau đó:

```bash
git add .
git commit -m "Update competitor store extractor"
git push
```

---

# 25. Quick Start

Nếu máy đã cài Python, toàn bộ quá trình cài đặt có thể thực hiện bằng:

```bash
git clone <repository-url>

cd competitor_store_extractor_mvp

python -m venv .venv

.venv\Scripts\activate

pip install -r requirements.txt

python -m playwright install chromium

streamlit run app_new.py
```

Sau đó mở:

```text
http://localhost:8501
```

---

# 26. Maintenance Checklist

Khi website của competitor thay đổi, kiểm tra:

* [ ] Store locator URL còn hoạt động?
* [ ] Website có đổi cấu trúc HTML?
* [ ] API endpoint có thay đổi?
* [ ] Store Code có thay đổi?
* [ ] Address có thay đổi format?
* [ ] Phone có thay đổi format?
* [ ] Province/Ward có thay đổi?
* [ ] Store URL có thay đổi?
* [ ] Có phát sinh duplicate?
* [ ] Số lượng store có hợp lý?
* [ ] Lat/Long có được lấy đầy đủ?

Nếu chỉ một brand bị lỗi trong khi các brand khác vẫn hoạt động, **ưu tiên xử lý riêng brand đó** thay vì thay đổi generic crawler.

---

# 27. Current Architecture

```text
                         ┌─────────────────────┐
                         │      Streamlit      │
                         │      app_new.py     │
                         └──────────┬──────────┘
                                    │
                    ┌───────────────┼────────────────┐
                    │               │                │
                    ▼               ▼                ▼
                  KFC           Pizza Hut        Generic
                    │               │                │
                    ▼               ▼                ▼
             brands/kfc.py    Special Parser     crawler.py
                    │                                │
                    │                                ▼
                    │                           dedupe.py
                    │                                │
                    └───────────────┬────────────────┘
                                    │
                                    ▼
                              Clean DataFrame
                                    │
                         ┌──────────┴──────────┐
                         ▼                     ▼
                       CSV                   Excel
```

---

# 28. Important Notes

* Chỉ crawl dữ liệu từ website chính thức của brand.
* Website có thể thay đổi cấu trúc bất kỳ lúc nào.
* Số lượng store thực tế có thể thay đổi theo thời điểm crawl.
* Một số website có thể yêu cầu JavaScript để hiển thị dữ liệu.
* Một số website có thể sử dụng API hoặc cơ chế chống bot.
* Khi crawler trả về 0 records, cần kiểm tra website và Debug Log trước khi thay đổi code.
