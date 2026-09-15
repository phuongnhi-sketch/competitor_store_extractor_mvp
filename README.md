# Competitor Store Extractor — MVP

## 1. Cài Python
Khuyến nghị Python 3.11+.

## 2. Cài thư viện

```bash
pip install -r requirements.txt
playwright install chromium
```

## 3. Chạy

```bash
streamlit run app.py
```

Sau đó mở URL mà Streamlit hiển thị, nhập:

- https://www.phuclong.com.vn/
- https://jollibee.com.vn/

## MVP đang làm gì?

1. Mở website bằng Chromium/Playwright.
2. Scroll để kích hoạt lazy loading.
3. Tìm các link có keyword liên quan tới store/location/cửa hàng.
4. Mở một số trang ứng viên.
5. Đọc JSON-LD nếu website cung cấp.
6. Đọc table HTML nếu có.
7. Chuẩn hóa và deduplicate.
8. Preview trên màn hình.
9. Xuất Excel.

## Lưu ý

Đây là MVP generic. Website thực tế có thể dùng API riêng hoặc map động. Khi gặp trường hợp đó, cần thêm API/network extraction cho website cụ thể.

## Hai website test

- Phúc Long: https://www.phuclong.com.vn/
- Jollibee: https://jollibee.com.vn/

Jollibee hiện có một trang danh sách cửa hàng riêng, nên đây là một test case tốt cho bước auto-discovery.
