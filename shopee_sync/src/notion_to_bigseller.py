import os
import re
import json
import logging
from typing import List, Dict, Any, Optional
import requests
from bs4 import BeautifulSoup
from pathlib import Path

# Thiết lập logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("notion_to_bigseller")

def parse_notion_public_page(url: str) -> Dict[str, Any]:
    """
    Cào và phân tích thông tin từ một trang Notion được chia sẻ công khai (Share to web).
    Trích xuất tên sản phẩm, nội dung mô tả và danh sách link hình ảnh.
    """
    logger.info(f"Bắt đầu đọc dữ liệu từ Notion URL: {url}")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()
    except Exception as e:
        logger.error(f"Không thể truy cập trang Notion: {e}")
        raise Exception(f"Lỗi truy cập link Notion: {e}. Hãy đảm bảo bạn đã bật 'Share to web'.")

    soup = BeautifulSoup(response.text, "html.parser")
    
    # 1. Lấy tên sản phẩm (Title)
    title = ""
    title_tag = soup.find("title")
    if title_tag:
        title = title_tag.text.strip()
    
    # Loại bỏ hậu tố " - Notion" hoặc các ký tự Notion mặc định nếu có
    title = re.sub(r"\s*-\s*Notion$", "", title, flags=re.IGNORECASE)
    
    # 2. Tìm kiếm hình ảnh (Images)
    image_urls: List[str] = []
    
    # Notion lưu ảnh trong các thẻ img, ta sẽ lọc các ảnh hợp lệ
    # Tránh các icon nhỏ hoặc ảnh avatar/logo của Notion
    img_tags = soup.find_all("img")
    for img in img_tags:
        src = img.get("src") or img.get("data-src")
        if src:
            # Chuyển đổi link tương đối thành tuyệt đối nếu cần
            if src.startswith("/"):
                src = f"https://www.notion.so{src}"
                
            # Loại bỏ các ảnh icon/emoji hoặc ảnh hệ thống của Notion
            if "notion-emojis" in src or "emoji" in src or "avatar" in src or "logo" in src:
                continue
                
            # Lọc trùng lặp
            if src not in image_urls:
                image_urls.append(src)
                
    logger.info(f"Đã tìm thấy {len(image_urls)} hình ảnh từ Notion.")

    # 3. Lấy nội dung văn bản làm Mô tả sản phẩm (Description)
    paragraphs = []
    # Notion render text qua các thẻ class block chứa văn bản hoặc các thẻ p, div thông thường
    # Tìm các thẻ chứa chữ trong cấu trúc trang Notion
    page_content_div = soup.find(class_="notion-page-content")
    
    if page_content_div:
        # Nếu tìm thấy div nội dung chính của Notion
        text_blocks = page_content_div.find_all(["p", "div", "li", "h2", "h3"])
        for block in text_blocks:
            text = block.text.strip()
            if text and text not in paragraphs:
                paragraphs.append(text)
    else:
        # Fallback nếu cấu trúc class của Notion thay đổi
        for p in soup.find_all(["p", "li"]):
            text = p.text.strip()
            if text and text not in paragraphs:
                paragraphs.append(text)

    # Nối các đoạn văn thành một bài mô tả hoàn chỉnh
    description = "\n".join(paragraphs)
    
    # Làm sạch mô tả
    description = re.sub(r"\n+", "\n", description) # Bỏ các dòng trống thừa

    return {
        "title": title or "Sản phẩm từ Notion",
        "description": description or "Mô tả sản phẩm đang được cập nhật.",
        "image_urls": image_urls
    }

def export_to_bigseller_excel(products: List[Dict[str, Any]], output_path: str) -> str:
    """
    Xuất danh sách sản phẩm thành file Excel tương thích với mẫu Import sản phẩm của BigSeller.
    """
    logger.info(f"Bắt đầu xuất dữ liệu sang Excel BigSeller tại: {output_path}")
    
    # Định nghĩa cấu trúc cột tiêu chuẩn của mẫu BigSeller (Thông tin cơ bản)
    # Mẫu BigSeller thường có 2 hàng tiêu đề (Hàng 1 là tên tiếng Anh/Việt, Hàng 2 là định dạng gợi ý)
    # Ở đây chúng ta sẽ tạo cấu trúc cột chuẩn
    
    columns = [
        "Product Name", "Product SKU", "Description", "Price", "Stock", 
        "Weight(g)", "Length(cm)", "Width(cm)", "Height(cm)",
        "Image 1", "Image 2", "Image 3", "Image 4", "Image 5", "Image 6", "Image 7", "Image 8", "Image 9"
    ]
    
    rows = []
    
    for index, prod in enumerate(products):
        # Tạo mã SKU ngẫu nhiên nếu không có
        sku = prod.get("sku") or f"NOTION-{index+1:04d}"
        
        # Lấy danh sách ảnh, điền tối đa 9 ảnh
        images = prod.get("image_urls", [])
        image_cols = [images[i] if i < len(images) else "" for i in range(9)]
        
        row = [
            prod.get("title", "Tên sản phẩm"),
            sku,
            prod.get("description", "Mô tả"),
            prod.get("price", 100000),      # Mặc định 100k nếu không có giá
            prod.get("stock", 100),         # Mặc định tồn kho 100
            prod.get("weight", 200),        # Mặc định 200g
            prod.get("length", 10),         # Kích thước mặc định
            prod.get("width", 10),
            prod.get("height", 10),
            *image_cols
        ]
        rows.append(row)
        
    try:
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(list(columns))
        for r in rows:
            ws.append(list(r))
        wb.save(output_path)
    except Exception as e_xl:
        logger.warning(f"Lưu file Excel bằng openpyxl không thành công ({e_xl}), thử lazy pandas...")
        import pandas as pd
        df = pd.DataFrame(rows, columns=columns)
        df.to_excel(output_path, index=False)
        
    logger.info("Đã ghi file Excel thành công.")
    return output_path

def generate_mock_notion_data() -> Dict[str, Any]:
    """
    Tạo dữ liệu Notion giả lập để chạy thử nghiệm xuất file Excel khi chưa có link Notion thật.
    """
    return {
        "title": "Áo Khoác Hoodie Unisex Nỉ Bông Dày Dặn Phong Cách Hàn Quốc",
        "description": "Thông tin chi tiết sản phẩm:\n"
                       "- Chất liệu: Nỉ bông cotton dày dặn, ấm áp, không xù lông.\n"
                       "- Thiết kế: Hoodie unisex phom rộng thoải mái, bo chun tay và gấu áo chắc chắn.\n"
                       "- Phù hợp cho cả nam và nữ mặc đi chơi, đi học, dạo phố cực xinh.\n"
                       "- Hướng dẫn chọn size:\n"
                       "  + Size M: 45kg - 55kg (dưới 1m65)\n"
                       "  + Size L: 56kg - 68kg (1m65 - 1m72)\n"
                       "  + Size XL: 69kg - 80kg (1m72 - 1m80)",
        "price": 189000,
        "stock": 250,
        "sku": "HD-UNISEX-01",
        "weight": 400,
        "length": 30,
        "width": 25,
        "height": 5,
        "image_urls": [
            "https://cf.shopee.vn/file/vn-11134207-7r98o-lsmg3e0a12cd34",
            "https://cf.shopee.vn/file/vn-11134207-7r98o-lsmg3e0a56ef78"
        ]
    }

def run_local_mock_export() -> str:
    """
    Hàm chạy thử nghiệm tạo file Excel BigSeller từ dữ liệu mock.
    """
    logger.info("=== CHẠY THỬ NGHIỆM XUẤT EXCEL BIGSELLER ===")
    mock_prod = generate_mock_notion_data()
    
    # Đường dẫn xuất file
    output_dir = Path(__file__).resolve().parent.parent / "output"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / "bigseller_products_mock.xlsx"
    
    export_to_bigseller_excel([mock_prod], str(output_file))
    logger.info(f"File Excel chạy thử đã được tạo tại: {output_file}")
    return str(output_file)

if __name__ == "__main__":
    run_local_mock_export()
