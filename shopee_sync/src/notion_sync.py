import os
import re
import logging
import requests
import pandas as pd
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from notion_client import Client
from dotenv import load_dotenv

# Import các hàm nội bộ
from . import config
from . import notion_to_bigseller
from . import convert_zicum
from . import ai_generator

logger = logging.getLogger("notion_sync")

def call_notion_with_retry(func, *args, max_retries=3, backoff_factor=2, **kwargs):
    """Bọc các cuộc gọi Notion API bằng cơ chế tự động thử lại (Retry) khi gặp lỗi mạng hoặc lỗi API."""
    import time
    from notion_client.errors import APIResponseError
    retries = 0
    while retries < max_retries:
        try:
            return func(*args, **kwargs)
        except Exception as e:
            retries += 1
            if retries >= max_retries:
                logger.error(f"Notion API call failed after {max_retries} attempts: {e}")
                raise e
            sleep_time = backoff_factor ** retries
            logger.warning(f"Lỗi kết nối Notion API ({e}). Đang thử lại sau {sleep_time} giây (lần {retries}/{max_retries})...")
            time.sleep(sleep_time)

def get_rich_text_content(property_data: Dict[str, Any]) -> str:
    """Helper trích xuất nội dung văn bản thuần túy từ thuộc tính rich_text của Notion."""
    rich_text_list = property_data.get("rich_text", [])
    if not rich_text_list:
        return ""
    return "".join([t.get("plain_text", "") for t in rich_text_list]).strip()

def parse_price_and_variants(price_variant_text: str) -> List[Dict[str, Any]]:
    """
    Phân tích cột 'Biến thể & giá' để xác định xem sản phẩm có biến thể hay không.
    Trả về danh sách các biến thể kèm giá tương ứng.
    
    Hỗ trợ các dạng ngăn cách:
    - 1 hộp|90.000 (phân tách bằng | hoặc xuống dòng)
    - Hộp 30 viên: 90.000 | Hộp 60 viên: 170.000
    - Hộp 30 viên - 90.000
    """
    if not price_variant_text:
        return []
        
    text = price_variant_text.strip()
    
    # 1. Kiểm tra nếu chỉ là một con số đơn lẻ (không có phân loại)
    number_only_pattern = r'^[0-9.,]+$'
    if re.match(number_only_pattern, text):
        clean_price = text.replace(".", "").replace(",", "").strip()
        try:
            return [{"name": "Mặc định", "price": float(clean_price)}]
        except ValueError:
            pass
            
    # 2. Phân tách theo dòng trước
    lines = [line.strip() for line in re.split(r'\n', text) if line.strip()]
    variants = []
    
    for line in lines:
        # Nếu dòng chứa cả phân loại và giá ngăn cách bởi |, :, hoặc -
        # Ví dụ: "1 hộp|90.000" hoặc "Hộp 30 viên: 90.000"
        match = re.match(r'^(.+?)(?:\||:|-)\s*([0-9.,]+)$', line)
        if match:
            var_name = match.group(1).strip()
            price_str = match.group(2).replace(".", "").replace(",", "").strip()
            try:
                variants.append({
                    "name": var_name,
                    "price": float(price_str)
                })
            except ValueError:
                pass
        else:
            # Nếu dòng không tự khớp, nhưng có thể chứa nhiều cặp phân tách bằng |
            # Ví dụ: "Hộp 30 viên: 90.000 | Hộp 60 viên: 170.000"
            parts = [p.strip() for p in line.split('|') if p.strip()]
            for part in parts:
                part_match = re.match(r'^(.+?)(?::|-)\s*([0-9.,]+)$', part)
                if part_match:
                    var_name = part_match.group(1).strip()
                    price_str = part_match.group(2).replace(".", "").replace(",", "").strip()
                    try:
                        variants.append({
                            "name": var_name,
                            "price": float(price_str)
                        })
                    except ValueError:
                        pass
                        
    # Nếu không parse được theo cấu trúc phân loại, coi toàn bộ text là giá đơn lẻ sau khi làm sạch
    if not variants:
        digits = re.findall(r'[0-9]+', text)
        if digits:
            clean_price = "".join(digits)
            try:
                variants.append({"name": "Mặc định", "price": float(clean_price)})
            except ValueError:
                pass
                
    return variants

def parse_insight_mentions(rich_text_list: list) -> List[Dict[str, str]]:
    """
    Trích xuất tên insight và Page ID từ ô Insight Library dạng text mention.
    Ví dụ: '1. Da dầu mụn / mụn nội tiết: ZicumGSV...' -> {'insight_name': 'Da dầu mụn / mụn nội tiết', 'page_id': 'PAGE_ID'}
    """
    results = []
    buffer = ""
    
    for item in rich_text_list:
        i_type = item.get("type")
        if i_type == "text":
            buffer += item.get("text", {}).get("content", "")
        elif i_type == "mention":
            mention_data = item.get("mention", {})
            if mention_data.get("type") == "page":
                page_id = mention_data.get("page", {}).get("id")
                insight_name = "Mặc định"
                # Tìm dạng số thứ tự: 1. Tên insight:
                match = re.search(r'(?:^|\n)\s*\d+\.\s*([^:]+):', buffer)
                if match:
                    insight_name = match.group(1).strip()
                else:
                    clean_buf = buffer.strip().rstrip(":")
                    if clean_buf:
                        insight_name = clean_buf
                
                results.append({
                    "insight_name": insight_name,
                    "page_id": page_id,
                    "plain_text": item.get("plain_text", "")
                })
                buffer = ""
            else:
                buffer += item.get("plain_text", "")
        else:
            buffer += item.get("plain_text", "")
            
    return results

def fetch_all_blocks_recursive(notion_client, block_id: str) -> list:
    """Tải đệ quy toàn bộ block con của một block để đảm bảo lấy đầy đủ nội dung lồng nhau."""
    all_blocks = []
    has_more = True
    start_cursor = None
    
    while has_more:
        kwargs = {"block_id": block_id}
        if start_cursor:
            kwargs["start_cursor"] = start_cursor
            
        res = call_notion_with_retry(notion_client.blocks.children.list, **kwargs)
        results = res.get("results", [])
        all_blocks.extend(results)
        
        has_more = res.get("has_more", False)
        start_cursor = res.get("next_cursor")
        
    # Duyệt đệ quy nếu block nào có block con
    extended_blocks = []
    for block in all_blocks:
        extended_blocks.append(block)
        if block.get("has_children", False):
            try:
                child_blocks = fetch_all_blocks_recursive(notion_client, block.get("id"))
                block["children_blocks"] = child_blocks
            except Exception as e:
                logger.warning(f"Không thể lấy block con của {block.get('id')}: {e}")
                
    return extended_blocks

def format_notion_blocks_to_text(blocks: list, indent_level: int = 0) -> str:
    """
    Chuyển đổi danh sách blocks của Notion thành chuỗi mô tả sản phẩm dạng text thuần túy.
    Hỗ trợ đệ quy cho các block lồng nhau.
    """
    lines = []
    indent_space = "  " * indent_level
    
    for block in blocks:
        b_type = block.get("type")
        if not b_type:
            continue
            
        rich_text = block.get(b_type, {}).get("rich_text", [])
        text = "".join([t.get("plain_text", "") for t in rich_text]).strip()
        
        # Format block hiện tại
        formatted_line = ""
        if text:
            if b_type == "paragraph":
                formatted_line = f"{indent_space}{text}"
            elif b_type == "heading_1":
                formatted_line = f"\n{indent_space}🍀 {text.upper()}\n"
            elif b_type == "heading_2":
                formatted_line = f"\n{indent_space}⭐ {text.upper()}\n"
            elif b_type == "heading_3":
                formatted_line = f"\n{indent_space}📍 {text}\n"
            elif b_type in ["bulleted_list_item", "numbered_list_item"]:
                formatted_line = f"{indent_space}- {text}"
            elif b_type == "quote":
                formatted_line = f"{indent_space}> {text}"
            elif b_type == "callout":
                formatted_line = f"\n{indent_space}💡 {text}\n"
            else:
                formatted_line = f"{indent_space}{text}"
        else:
            if b_type == "paragraph":
                lines.append("")
                continue
                
        if formatted_line:
            lines.append(formatted_line)
            
        # Nếu có block con, format đệ quy
        if "children_blocks" in block:
            child_text = format_notion_blocks_to_text(block["children_blocks"], indent_level + 1)
            if child_text:
                lines.append(child_text)
                
    content = "\n".join(lines).strip()
    # Rút gọn các dòng trống liên tiếp
    content = re.sub(r'\n{3,}', '\n\n', content)
    return content

def fetch_insight_page_content(notion_client, page_id: str) -> Tuple[str, str, str]:
    """
    Truy xuất tiêu đề trang, nội dung mô tả và thuộc tính Link hình từ Notion Page của Insight.
    """
    page_data = call_notion_with_retry(notion_client.pages.retrieve, page_id=page_id)
    properties = page_data.get("properties", {})
    
    # Tìm thuộc tính tiêu đề (title)
    title = "Sản phẩm không tên"
    for prop_name, prop_val in properties.items():
        if prop_val.get("type") == "title":
            title_list = prop_val.get("title", [])
            if title_list:
                title = title_list[0].get("plain_text", "").strip()
            break
            
    # Lấy thuộc tính Link hình
    link_hinh = ""
    if "Link hình" in properties:
        prop_lh = properties["Link hình"]
        prop_type = prop_lh.get("type")
        if prop_type == "url":
            link_hinh = prop_lh.get("url", "") or ""
        elif prop_type == "rich_text":
            link_hinh = "".join([t.get("plain_text", "") for t in prop_lh.get("rich_text", [])]).strip()
            
    # Lấy đệ quy toàn bộ block con
    blocks = fetch_all_blocks_recursive(notion_client, page_id)
    
    # Format các block thành text
    description = format_notion_blocks_to_text(blocks)
    
    return title, description, link_hinh

def generate_seo_description(product_title: str) -> str:
    """Tự động tạo mô tả sản phẩm mẫu chất lượng cao dựa trên tên sản phẩm."""
    description = f"""✨ {product_title} ✨

Chào mừng bạn đến với gian hàng chính hãng! Chúng tôi tự hào mang đến sản phẩm chất lượng cao, an toàn và hiệu quả hàng đầu cho sức khỏe và sắc đẹp của bạn.

🍀 THÔNG TIN SẢN PHẨM:
- Tên sản phẩm: {product_title}
- Quy cách đóng gói: Hộp tiêu chuẩn nhà sản xuất
- Xuất xứ: Việt Nam chính hãng

⭐ CÔNG DỤNG VÀ ƯU ĐIỂM NỔI BẬT:
- Hỗ trợ tối ưu và cải thiện các tình trạng sức khỏe liên quan.
- Thành phần lành tính, được kiểm nghiệm lâm sàng an toàn, không tác dụng phụ.
- Thích hợp sử dụng chăm sóc sức khỏe hàng ngày cho bản thân và gia đình.

👥 ĐỐI TƯỢNG SỬ DỤNG:
- Người cần bổ sung dưỡng chất thiết yếu nâng cao đề kháng.
- Phù hợp với nhiều lứa tuổi (Đọc kỹ hướng dẫn sử dụng kèm theo hộp).

💊 HƯỚNG DẪN SỬ DỤNG:
- Sử dụng trực tiếp bằng đường uống sau khi ăn.
- Liều lượng: Sử dụng theo khuyến cáo trên bao bì hoặc chỉ định của chuyên gia y tế.

📦 HƯỚNG DẪN BẢO QUẢN:
- Bảo quản nơi khô ráo, thoáng mát, nhiệt độ dưới 30°C.
- Tránh ánh nắng mặt trời chiếu trực tiếp. Để xa tầm tay trẻ em.

👉 CAM KẾT TỪ SHOP:
- Hàng chính hãng 100%, có đầy đủ hóa đơn chứng từ.
- Đổi trả miễn phí trong vòng 7 ngày nếu phát hiện lỗi từ nhà sản xuất.
- Đóng gói cẩn thận, giao hàng nhanh chóng toàn quốc."""
    return description

def parse_media_links(text: str) -> Dict[int, str]:
    """
    Phân tích cú pháp cột 'Link media sản phẩm' để lấy danh sách link Drive cho từng Insight tương ứng.
    Hỗ trợ cả dạng có số thứ tự ở đầu (ví dụ '1. https://drive...') và dạng xuống dòng đơn thuần.
    Trả về dict map từ index của Insight (0-based) sang link Drive tương ứng.
    """
    if not text:
        return {}
    
    lines = text.split('\n')
    results = {}
    
    # Kiểm tra xem có bất kỳ dòng nào chứa số thứ tự ở đầu hay không
    has_numbered_prefix = False
    for line in lines:
        line_str = line.strip()
        if not line_str:
            continue
        if re.match(r'^\s*\d+\s*[\.\-\:\)\s]', line_str):
            has_numbered_prefix = True
            break
            
    if has_numbered_prefix:
        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue
            # Tìm số thứ tự ở đầu và link drive
            match_num = re.match(r'^\s*(\d+)\s*[\.\-\:\)\s]*\s*(https://drive\.google\.com/[^\s]+)', line_str)
            if match_num:
                num = int(match_num.group(1))
                link = match_num.group(2).strip()
                results[num - 1] = link
            else:
                # Nếu không khớp ở đầu, thử tìm xem có số ở đầu và link ở phía sau không
                match_any = re.search(r'^\s*(\d+)\s*[\.\-\:\)\s]+.*?(https://drive\.google\.com/[^\s]+)', line_str)
                if match_any:
                    num = int(match_any.group(1))
                    link = match_any.group(2).strip()
                    results[num - 1] = link
    else:
        # Nếu không có số thứ tự ở đầu, map theo index của dòng (0-based)
        for idx, line in enumerate(lines):
            line_str = line.strip()
            if not line_str:
                continue
            match_link = re.search(r'(https://drive\.google\.com/[^\s]+)', line_str)
            if match_link:
                results[idx] = match_link.group(1).strip()
                
    return results

def sync_notion_to_bigseller_excel(override_drive_url: Optional[str] = None) -> Tuple[str, List[str]]:
    """
    Quét danh sách các sản phẩm mới từ Notion, tải hình ảnh từ Google Drive,
    tách biến thể và xuất ra file Excel chuẩn BigSeller.
    Đồng thời cập nhật cột 'IT' = True trên Notion để đánh dấu hoàn thành.
    
    Returns:
        Tuple[str, List[str]]: (Đường dẫn file Excel kết quả, Danh sách tên các sản phẩm đã xử lý)
    """
    logger.info("Khởi động quy trình đồng bộ Notion -> BigSeller Excel...")
    
    # Nạp cấu hình từ .env
    project_root = Path(__file__).resolve().parent.parent
    load_dotenv(project_root / ".env")
    
    token = os.getenv("NOTION_TOKEN")
    page_id = os.getenv("NOTION_DATABASE_ID")
    template_path = str(project_root / "import_template_VN.xlsx")
    api_key = os.getenv("GEMINI_API_KEY")

    
    if not token or not page_id:
        raise ValueError("Chưa cấu hình NOTION_TOKEN hoặc NOTION_DATABASE_ID trong file .env")
        
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Không tìm thấy file mẫu gốc của BigSeller tại: {template_path}")
        
    notion = Client(auth=token)
    
    # 1. Tự động lấy ID Data Source thực tế từ Page ID
    logger.info(f"Đang đọc cấu trúc trang Page ID: {page_id}")
    db_meta = call_notion_with_retry(notion.databases.retrieve, database_id=page_id)
    data_sources = db_meta.get("data_sources", [])
    if not data_sources:
        raise ValueError("Không tìm thấy Data Source nào liên kết với trang Notion này.")
        
    data_source_id = data_sources[0].get("id")
    logger.info(f"Đã xác định ID Data Source thực tế để truy vấn: {data_source_id}")
    
    # 2. Truy vấn dữ liệu từ Data Source
    res = call_notion_with_retry(notion.data_sources.query, data_source_id=data_source_id)
    records = res.get("results", [])
    
    # 3. Lọc sản phẩm: Bài viết = True và Trạng thái đăng bài shopee = False
    pending_products = []
    for page in records:
        properties = page.get("properties", {})
        
        # Kiểm tra checkbox "Bài viết"
        bai_viet = properties.get("Bài viết", {}).get("checkbox", False)
        # Kiểm tra checkbox "Trạng thái đăng bài shopee"
        it_status = properties.get("Trạng thái đăng bài shopee", {}).get("checkbox", False)
        
        if bai_viet and not it_status:
            pending_products.append(page)
            
    logger.info(f"Tìm thấy {len(pending_products)} sản phẩm mới chờ xử lý.")
    
    if not pending_products:
        return "", []
        
    # 4. Đọc cấu trúc tiêu đề cột của BigSeller mẫu
    df_template = pd.read_excel(template_path, header=None)
    columns = df_template.iloc[0].tolist()
    
    # 5. Xử lý từng sản phẩm và tạo dòng Excel
    rows_to_export = []
    processed_titles = []
    processed_page_ids = []
    page_id_to_desc = {}
    
    # Tạo SKU gốc tăng dần hoặc ngẫu nhiên
    import random
    sku_base_rand = random.randint(1000, 9999)
    
    for idx, page in enumerate(pending_products):
        page_id_str = page.get("id")
        properties = page.get("properties", {})
        
        # Lấy tên sản phẩm
        title_list = properties.get("Tên sản phẩm", {}).get("title", [])
        title = title_list[0].get("plain_text", "Sản phẩm không tên") if title_list else "Sản phẩm không tên"
        
        # Lấy link Drive hình ảnh (Sử dụng link override nếu được nhập từ UI của Web App)
        drive_url = override_drive_url if override_drive_url else (properties.get("Media sản phẩm", {}).get("url", "") or "")
        if not drive_url:
            prop_ms = properties.get("Media sản phẩm", {})
            if prop_ms.get("type") == "rich_text":
                drive_url = "".join([t.get("plain_text", "") for t in prop_ms.get("rich_text", [])]).strip()
        
        # Lấy văn bản biến thể và giá
        price_variant_text = get_rich_text_content(properties.get("Biến thể & giá", {}))
        
        # Không còn sử dụng cột Link media sản phẩm ở bảng cha nữa
        pass
            
        logger.info(f"Đang xử lý sản phẩm: {title} (Giá: {price_variant_text})")
        
        # Tìm thư mục sản phẩm từ thư mục gốc lớn cấu hình trong .env hoặc mặc định
        root_folder_id = os.getenv("DRIVE_ROOT_FOLDER_ID", "1XrOmOCqdZ3xfkeVaBc0Vr77Q7yRW0PxZ").strip()
        product_folder_id = None
        
        # Thử lấy trực tiếp từ thuộc tính "Media sản phẩm" trên Notion trước (hỗ trợ cả URL và rich_text)
        drive_url = properties.get("Media sản phẩm", {}).get("url", "") or ""
        if not drive_url:
            prop_ms = properties.get("Media sản phẩm", {})
            if prop_ms.get("type") == "rich_text":
                drive_url = "".join([t.get("plain_text", "") for t in prop_ms.get("rich_text", [])]).strip()
                
        if drive_url:
            if "drive.google.com" in drive_url:
                folder_match = re.search(r'/folders/([a-zA-Z0-9_-]+)', drive_url)
                if folder_match:
                    product_folder_id = folder_match.group(1)
                    logger.info(f"Sử dụng thư mục của sản phẩm từ thuộc tính 'Media sản phẩm': ID {product_folder_id}")
            else:
                # Trường hợp dán đường dẫn local (ví dụ: G:\My Drive\Hình ảnh Shopee\Imiquad Cream)
                try:
                    local_path = Path(drive_url)
                    folder_name = local_path.name.strip()
                    if folder_name and folder_name.lower() != "my drive":
                        product_folder_id = convert_zicum.find_product_folder(root_folder_id, folder_name)
                        if product_folder_id:
                            logger.info(f"Tìm thấy thư mục của sản phẩm từ đường dẫn local '{drive_url}': ID {product_folder_id}")
                except Exception as e:
                    logger.error(f"Lỗi khi trích xuất tên thư mục từ link local: {e}")

        # Nếu không tìm thấy từ Notion, tự động tìm kiếm thư mục sản phẩm theo tên trong thư mục gốc Drive
        if not product_folder_id:
            try:
                product_folder_id = convert_zicum.find_product_folder(root_folder_id, title)
                if product_folder_id:
                    logger.info(f"Tìm thấy thư mục của sản phẩm '{title}' trên Drive gốc: ID {product_folder_id}")
            except Exception as e:
                logger.error(f"Lỗi khi tìm thư mục sản phẩm '{title}' từ Drive gốc: {e}")

        # Lấy ảnh fallback của sản phẩm chính
        fallback_image_urls = []
        if product_folder_id:
            try:
                fallback_image_urls = convert_zicum.get_images_and_videos_in_folder(product_folder_id)
            except Exception as e:
                logger.error(f"Lỗi khi lấy ảnh fallback cho sản phẩm '{title}': {e}")
        elif drive_url:
            # Fallback cuối cùng nếu không có ID thư mục nhưng có drive_url
            try:
                fallback_image_urls = convert_zicum.get_images_from_drive_folder(drive_url, title)
            except Exception as e:
                logger.error(f"Lỗi khi lấy ảnh qua get_images_from_drive_folder: {e}")
        
        # Phân tích biến thể
        variants = parse_price_and_variants(price_variant_text)
        sku_code = f"PROD-{sku_base_rand}-{idx+1:02d}"
        
        # Đọc danh sách Insight từ ô Insight Library (dạng text mentions)
        insight_prop = properties.get("Insight Library", {})
        insight_items = []
        if insight_prop.get("type") == "rich_text":
            insight_items = parse_insight_mentions(insight_prop.get("rich_text", []))
            
        content_versions = []
        
        # Lấy giá trị cột Biến thể (ví dụ: "số lượng")
        variant_type_name = "Phân loại"
        if "Biến thể" in properties:
            v_prop = properties["Biến thể"]
            prop_type = v_prop.get("type")
            if prop_type == "select":
                sel = v_prop.get("select")
                if sel:
                    variant_type_name = sel.get("name", "Phân loại").strip()
            elif prop_type == "multi_select":
                msel = v_prop.get("multi_select", [])
                if msel:
                    variant_type_name = msel[0].get("name", "Phân loại").strip()
            elif prop_type == "rich_text":
                variant_type_name = get_rich_text_content(v_prop) or "Phân loại"

        if insight_items:
            import concurrent.futures
            
            # Lấy danh sách subfolders của sản phẩm cha
            subfolders = {}
            if product_folder_id:
                try:
                    subfolders = convert_zicum.get_subfolders_of_drive_folder(product_folder_id)
                except Exception as e:
                    logger.error(f"Lỗi khi cào thư mục con từ Drive: {e}")
            
            def process_single_insight(idx_item, subfolders):
                idx, item = idx_item
                ins_name = item["insight_name"]
                ins_page_id = item["page_id"]
                logger.info(f"Đang tải bài viết chuẩn bị sẵn cho Insight '{ins_name}' từ Notion page ID: {ins_page_id}...")
                try:
                    title_from_page, description_from_page, link_hinh_from_page = fetch_insight_page_content(notion, ins_page_id)
                    
                    # Tự động tìm thư mục Drive và cập nhật trường Link hình nếu trên Notion đang rỗng
                    if not link_hinh_from_page and subfolders:
                        clean_insight = convert_zicum.clean_name(ins_name)
                        clean_folder_name = convert_zicum.clean_name(f"Insight {idx+1}")
                        
                        target_folder_id = None
                        if clean_insight in subfolders:
                            target_folder_id = subfolders[clean_insight]
                        else:
                            for sf_name, sf_id in subfolders.items():
                                if clean_folder_name in sf_name or sf_name in clean_folder_name or clean_insight in sf_name or sf_name in clean_insight:
                                    target_folder_id = sf_id
                                    break
                                    
                        if target_folder_id:
                            new_link = f"https://drive.google.com/drive/folders/{target_folder_id}"
                            try:
                                # Kiểm tra kiểu của thuộc tính Link hình để cập nhật chuẩn xác
                                ins_page = call_notion_with_retry(notion.pages.retrieve, page_id=ins_page_id)
                                prop_lh = ins_page.get("properties", {}).get("Link hình", {})
                                prop_type = prop_lh.get("type", "url")
                                
                                if prop_type == "url":
                                    update_props = {"Link hình": {"url": new_link}}
                                else:
                                    update_props = {"Link hình": {"rich_text": [{"text": {"content": new_link}}]}}
                                    
                                call_notion_with_retry(
                                    notion.pages.update,
                                    page_id=ins_page_id,
                                    properties=update_props
                                )
                                logger.info(f"Đã cập nhật thuộc tính 'Link hình' cho trang Insight {ins_name}: {new_link}")
                                link_hinh_from_page = new_link
                            except Exception as e:
                                logger.error(f"Không thể cập nhật thuộc tính 'Link hình' cho trang Insight {ins_name}: {e}")

                    # Kiểm duyệt mô tả qua AI để đảm bảo phù hợp chính sách Shopee
                    logger.info(f"Đang tiến hành kiểm duyệt AI cho mô tả Insight '{ins_name}'...")
                    description_from_page = ai_generator.moderate_and_fix_shopee_description(description_from_page, api_key)
                    return {
                        "insight": ins_name,
                        "title": title_from_page,
                        "description": description_from_page,
                        "link_hinh": link_hinh_from_page,
                        "suffix": f"-IN{idx+1}"
                    }
                except Exception as ex:
                    logger.error(f"Lỗi khi đọc nội dung bài viết từ page {ins_page_id}: {ex}")
                    return {
                        "insight": ins_name,
                        "title": item["plain_text"],
                        "description": generate_seo_description(title),
                        "suffix": f"-IN{idx+1}"
                    }
            
            # Sử dụng ThreadPoolExecutor để xử lý song song các Insight cùng lúc
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(insight_items)) as executor:
                results = list(executor.map(lambda x: process_single_insight(x, subfolders), enumerate(insight_items)))
                
            content_versions.extend(results)
        else:
            # Fallback nếu không có Insight nào
            if "Zicum" in title or "zicum" in title.lower():
                description = """Viên uống bổ sung kẽm ZicumGSV là giải pháp hỗ trợ điều trị mụn trứng cá, mụn viêm và tăng cường sức đề kháng cho cơ thể một cách hiệu quả, an toàn. Sản phẩm được sản xuất bởi Công ty Cổ phần Dược phẩm Hà Tây uy tín hàng đầu Việt Nam.

🍀 THÀNH PHẦN CHI TIẾT
Mỗi viên nang cứng chứa:
- Kẽm gluconat: 105mg (tương đương với 15mg kẽm nguyên tố).
- Tá dược vừa đủ 1 viên: Lactose, amidon, gelatin, magnesi stearat, bột talc.

⭐ CÔNG DỤNG VƯỢT TRỘI
- Hỗ trợ giảm mụn trứng cá, mụn viêm, làm dịu da tổn thương và ngăn ngừa sẹo mụn hiệu quả từ bên trong.
- Kích thích sản sinh tế bào da mới, hỗ trợ làm lành vết thương ngoài da nhanh chóng.
- Tăng cường hệ miễn dịch, nâng cao sức đề kháng trước các bệnh nhiễm trùng đường hô hấp, tiêu hóa.
- Hỗ trợ cải thiện tình trạng tiêu chảy cấp và mãn tính, rối loạn tiêu hóa, kích thích ăn ngon miệng cho người chán ăn, suy nhược thể chất.
- Bổ sung lượng kẽm thiết yếu cho phụ nữ có thai và cho con bú."""
            else:
                description = generate_seo_description(title)
                
            content_versions.append({
                "insight": "Mặc định",
                "title": title,
                "description": description,
                "suffix": ""
            })
            
        # Xuất các dòng Excel và lưu mô tả để cập nhật vào Notion
        desc_logs = []
        for v_idx_ver, version in enumerate(content_versions):
            v_title = version["title"]
            v_desc = version["description"]
            v_suffix = version["suffix"]
            
            # Lấy ảnh/video cho Insight cụ thể hoặc fallback từ thư mục chính
            insight_files = []
            insight_name = version.get("insight", "Mặc định")
            
            # CƠ CHẾ ƯU TIÊN 1: Lấy trực tiếp từ thuộc tính "Link hình" của trang Insight con Notion
            insight_link_hinh = version.get("link_hinh", "")
            if insight_link_hinh:
                try:
                    folder_match = re.search(r'/folders/([a-zA-Z0-9_-]+)', insight_link_hinh)
                    if folder_match:
                        insight_folder_id = folder_match.group(1)
                        insight_files = convert_zicum.get_images_and_videos_in_folder(insight_folder_id)
                        if insight_files:
                            logger.info(f"Lấy trực tiếp {len(insight_files)} file từ thuộc tính 'Link hình' của Insight '{insight_name}'")
                except Exception as e:
                    logger.error(f"Lỗi khi cào Link hình trực tiếp từ Insight '{insight_link_hinh}': {e}")
            
            # Fallback 1: Tìm theo logic phân cấp thư mục con và so khớp
            if not insight_files and product_folder_id and insight_name != "Mặc định":
                try:
                    # Tìm thư mục Insight trùng tên trong thư mục sản phẩm
                    insight_folder_id = convert_zicum.find_insight_folder(product_folder_id, insight_name)
                    if insight_folder_id:
                        insight_files = convert_zicum.get_images_and_videos_in_folder(insight_folder_id)
                        if insight_files:
                            logger.info(f"Tìm thấy {len(insight_files)} file cho Insight '{insight_name}' của sản phẩm '{title}'")
                    if not insight_files:
                        logger.warning(f"Không tìm thấy file cho Insight '{insight_name}' của sản phẩm '{title}'. Sử dụng ảnh sản phẩm chính làm fallback.")
                except Exception as e:
                    logger.error(f"Lỗi khi lấy ảnh/video cho Insight '{insight_name}': {e}")
            
            if not insight_files:
                if product_folder_id:
                    try:
                        insight_files = convert_zicum.get_images_and_videos_in_folder(product_folder_id)
                    except Exception as e:
                        logger.error(f"Lỗi khi lấy file từ thư mục sản phẩm chính: {e}")
                elif fallback_image_urls:
                    insight_files = [{"id": f"fallback_{idx}", "url": url, "name": f"fallback_{idx}.jpg", "mime": "image/jpeg"} for idx, url in enumerate(fallback_image_urls)]
            
            # Phân loại hình ảnh và video
            image_files = [f for f in insight_files if "image" in f["mime"]]
            video_files = [f for f in insight_files if "video" in f["mime"]]
            
            # Sắp xếp ảnh sản phẩm tăng dần theo số thứ tự trong tên file
            def get_file_number(img_item):
                raw_name = img_item.get("name", "")
                name_without_ext = os.path.splitext(raw_name)[0].strip()
                try:
                    decoded_name = convert_zicum.decode_drive_js_string(name_without_ext).strip()
                except Exception:
                    decoded_name = name_without_ext
                match = re.search(r'\d+', decoded_name)
                return int(match.group(0)) if match else 999999
                
            image_files.sort(key=get_file_number)
            
            # Logic Ảnh bìa và Album ảnh: Ảnh nào có tên là số 1 thì làm ảnh bìa
            cover_image = ""
            album_images = []
            
            special_cover_index = -1
            for i, img in enumerate(image_files):
                raw_name = img.get("name", "")
                name_without_ext = os.path.splitext(raw_name)[0].strip()
                try:
                    decoded_name = convert_zicum.decode_drive_js_string(name_without_ext).strip()
                except Exception:
                    decoded_name = name_without_ext
                    
                clean_n = re.sub(r'[^a-zA-Z0-9]', '', decoded_name)
                if clean_n == "1" or decoded_name == "1" or decoded_name.startswith("1.") or decoded_name.startswith("1 ") or decoded_name.startswith("1-") or decoded_name.startswith("1_"):
                    special_cover_index = i
                    break
                    
            if special_cover_index != -1:
                cover_image = image_files[special_cover_index]["url"]
                album_images = [img["url"] for idx, img in enumerate(image_files) if idx != special_cover_index]
            else:
                if image_files:
                    cover_image = image_files[0]["url"]
                    album_images = [img["url"] for img in image_files[1:]]
                    
            if not cover_image:
                cover_image = "https://gsvvietnam.com/wp-content/uploads/2021/04/Zicum-GSV.jpg"
                
            sub_images = [album_images[i] if i < len(album_images) else "" for i in range(8)]
            
            video_url = ""
            if video_files:
                video_url = video_files[0]["url"]
                logger.info(f"Phát hiện video cho Insight '{insight_name}': {video_url}")
            
            # Tóm tắt ngắn gọn mô tả để tránh hiển thị quá dài trên Notion cell
            short_desc = v_desc[:120].strip().replace('\n', ' ')
            if len(v_desc) > 120:
                short_desc += "..."
            desc_logs.append(f"📌 [INSIGHT: {version['insight']}]\n- TIÊU ĐỀ: {v_title}\n- TÓM TẮT: {short_desc}\n*(Xem mô tả đầy đủ trong file Excel)*\n")
            
            # SKU cha của phiên bản này
            version_sku_code = f"{sku_code}{v_suffix}"
            
            # Phân loại danh mục tự động cho sản phẩm dựa trên tên hoặc mô tả
            category_id = ai_generator.classify_product_category(v_title, v_desc, api_key)
            
            # Nếu sản phẩm có phân loại biến thể
            if len(variants) > 1:
                # Danh sách toàn bộ ảnh theo thứ tự để gán cho từng biến thể
                all_variant_images = [cover_image] + album_images if cover_image else album_images
                
                for v_idx, var in enumerate(variants):
                    row = {}
                    for col in columns:
                        row[col] = ""
                        
                    row["ID danh mục*"] = category_id
                    row["Tên sản phẩm*"] = v_title
                    row["SKU sản phẩm"] = ""
                    row["Mô tả sản phẩm*"] = v_desc
                    
                    row["Tên phân loại 1"] = variant_type_name
                    row["Phân loại 1"] = var["name"]
                    row["SKU"] = ""
                    row["Giá*"] = var["price"]
                    row["Tồn kho*"] = 100
                    
                    # Gán ảnh riêng cho từng biến thể (cột Hình ảnh biến thể)
                    # Biến thể thứ v_idx sẽ lấy ảnh thứ v_idx trong danh sách
                    if v_idx < len(all_variant_images):
                        row["Hình ảnh biến thể"] = all_variant_images[v_idx]
                    else:
                        # Fallback: dùng ảnh cuối cùng nếu số ảnh ít hơn số biến thể
                        row["Hình ảnh biến thể"] = all_variant_images[-1] if all_variant_images else cover_image
                    
                    row["Ảnh bìa*"] = cover_image
                    for s_idx, img_url in enumerate(sub_images):
                        row[f"Hình ảnh {s_idx + 1}"] = img_url
                        
                    row["Link nhà cung cấp"] = video_url if video_url else (drive_url if drive_url else "")
                    row["Cân nặng (g)*"] = 150
                    row["Chiều dài (cm)"] = 12
                    row["Chiều rộng (cm)"] = 10
                    row["Chiều cao (cm)"] = 5
                    row["Tình trạng"] = 1
                    rows_to_export.append(row)
            else:
                # Sản phẩm đơn lẻ (Không có biến thể)
                single_price = variants[0]["price"] if len(variants) == 1 else 90000
                
                row = {}
                for col in columns:
                    row[col] = ""
                    
                row["ID danh mục*"] = category_id
                row["Tên sản phẩm*"] = v_title
                row["SKU sản phẩm"] = ""
                row["Mô tả sản phẩm*"] = v_desc
                row["SKU"] = ""
                row["Giá*"] = single_price
                row["Tồn kho*"] = 100
                
                row["Ảnh bìa*"] = cover_image
                for s_idx, img_url in enumerate(sub_images):
                    row[f"Hình ảnh {s_idx + 1}"] = img_url
                    
                row["Link nhà cung cấp"] = video_url if video_url else (drive_url if drive_url else "")
                row["Cân nặng (g)*"] = 150
                row["Chiều dài (cm)"] = 12
                row["Chiều rộng (cm)"] = 10
                row["Chiều cao (cm)"] = 5
                row["Tình trạng"] = 1
                rows_to_export.append(row)
        processed_titles.append(title)
        processed_page_ids.append(page_id_str)
        page_id_to_desc[page_id_str] = "\n==============================\n".join(desc_logs)
        
    # 6. Tạo DataFrame và lưu file Excel
    new_df = pd.DataFrame(rows_to_export, columns=columns)
    export_dir_env = os.getenv("BIGSELLER_EXPORT_DIR")
    if export_dir_env:
        output_dir = Path(export_dir_env)
    else:
        output_dir = project_root / "output"
    output_dir.mkdir(exist_ok=True)
    
    # Tạo tên file kèm timestamp để tránh ghi đè
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    excel_output_path = output_dir / f"bigseller_sync_{timestamp}.xlsx"
    
    new_df.to_excel(excel_output_path, index=False)
    logger.info(f"Đã xuất file Excel đồng bộ thành công tại: {excel_output_path}")
    
    # 7. Cập nhật trạng thái Trạng thái đăng bài shopee = True trên Notion (Bỏ note nội dung đăng theo yêu cầu)
    for p_id in processed_page_ids:
        logger.info(f"Đang đánh dấu hoàn thành trên Notion cho page_id: {p_id}")
        call_notion_with_retry(
            notion.pages.update,
            page_id=p_id,
            properties={
                "Trạng thái đăng bài shopee": {"checkbox": True}
            }
        )
        
    return str(excel_output_path), processed_titles

def check_pending_products() -> List[Dict[str, Any]]:
    """
    Chỉ kiểm tra và trả về danh sách sản phẩm đang chờ xử lý (Bài viết = True và Trạng thái đăng bài shopee = False)
    mà không thực hiện đồng bộ hay thay đổi dữ liệu.
    """
    token = os.getenv("NOTION_TOKEN")
    page_id = os.getenv("NOTION_DATABASE_ID")
    if not token or not page_id:
        return []
        
    try:
        notion = Client(auth=token)
        db_meta = call_notion_with_retry(notion.databases.retrieve, database_id=page_id)
        data_sources = db_meta.get("data_sources", [])
        if not data_sources:
            return []
        data_source_id = data_sources[0].get("id")
        res = call_notion_with_retry(notion.data_sources.query, data_source_id=data_source_id)
        records = res.get("results", [])
        
        pending_items = []
        for page in records:
            properties = page.get("properties", {})
            bai_viet = properties.get("Bài viết", {}).get("checkbox", False)
            it_status = properties.get("Trạng thái đăng bài shopee", {}).get("checkbox", False)
            
            # Lấy tên sản phẩm
            title_list = properties.get("Tên sản phẩm", {}).get("title", [])
            title = title_list[0].get("plain_text", "").strip() if title_list else ""
            
            # Điều kiện: Tên sản phẩm không trống, Bài viết = True, Trạng thái đăng bài shopee = False
            if title and bai_viet and not it_status:
                pending_items.append({
                    "id": page.get("id"),
                    "title": title
                })
        return pending_items
    except Exception as e:
        logger.error(f"Lỗi khi check sản phẩm chờ xử lý: {e}")
        return []

if __name__ == "__main__":
    excel_path, titles = sync_notion_to_bigseller_excel()
    print(f"Sync completed! Excel saved at: {excel_path}")
    print(f"Processed products: {titles}")



def sync_only_image_links_to_notion(override_drive_url: Optional[str] = None) -> List[str]:
    logger.info("Bắt đầu tiến trình chỉ đồng bộ link hình Google Drive sang Notion...")
    
    # Nạp cấu hình từ .env
    project_root = Path(__file__).resolve().parent.parent
    load_dotenv(project_root / ".env")
    
    token = os.getenv("NOTION_TOKEN")
    page_id = os.getenv("NOTION_DATABASE_ID")
    
    if not token or not page_id:
        raise ValueError("Chưa cấu hình NOTION_TOKEN hoặc NOTION_DATABASE_ID trong file .env")
        
    notion = Client(auth=token)
    
    # Tự động lấy ID Data Source thực tế từ Page ID
    db_meta = call_notion_with_retry(notion.databases.retrieve, database_id=page_id)
    data_sources = db_meta.get("data_sources", [])
    if not data_sources:
        raise ValueError("Không tìm thấy Data Source nào liên kết với trang Notion này.")
        
    data_source_id = data_sources[0].get("id")
    res = call_notion_with_retry(notion.data_sources.query, data_source_id=data_source_id)
    records = res.get("results", [])
    
    # Lọc sản phẩm: Trạng thái đăng bài shopee = False (chờ xử lý)
    pending_products = []
    for page in records:
        properties = page.get("properties", {})
        it_status = properties.get("Trạng thái đăng bài shopee", {}).get("checkbox", False)
        if not it_status:
            pending_products.append(page)
            
    logger.info(f"Tìm thấy {len(pending_products)} sản phẩm chưa đăng shopee để quét đồng bộ link hình.")
    
    if not pending_products:
        return []
        
    updated_pages = []
    root_folder_id = os.getenv("DRIVE_ROOT_FOLDER_ID", "1XrOmOCqdZ3xfkeVaBc0Vr77Q7yRW0PxZ").strip()
    
    for page in pending_products:
        properties = page.get("properties", {})
        title_list = properties.get("Tên sản phẩm", {}).get("title", [])
        title = title_list[0].get("plain_text", "Sản phẩm không tên") if title_list else "Sản phẩm không tên"
        
        # Lấy link Drive hình ảnh
        drive_url = override_drive_url if override_drive_url else (properties.get("Media sản phẩm", {}).get("url", "") or "")
        if not drive_url:
            prop_ms = properties.get("Media sản phẩm", {})
            if prop_ms.get("type") == "rich_text":
                drive_url = "".join([t.get("plain_text", "") for t in prop_ms.get("rich_text", [])]).strip()
                
        logger.info(f"Đang xử lý sản phẩm: {title} (Drive URL: {drive_url})")
        
        # Resolve ra product_folder_id
        product_folder_id = None
        if drive_url:
            if "drive.google.com" in drive_url:
                folder_match = re.search(r'/folders/([a-zA-Z0-9_-]+)', drive_url)
                if folder_match:
                    product_folder_id = folder_match.group(1)
            else:
                # Trường hợp dán đường dẫn local (ví dụ: G:\My Drive\Hình ảnh Shopee\Imiquad Cream)
                try:
                    local_path = Path(drive_url)
                    folder_name = local_path.name.strip()
                    if folder_name and folder_name.lower() != "my drive":
                        product_folder_id = convert_zicum.find_product_folder(root_folder_id, folder_name)
                except Exception as e:
                    logger.error(f"Lỗi khi trích xuất tên thư mục từ link local: {e}")
                    
        # Nếu vẫn không có, thử tìm kiếm tự động theo tên sản phẩm
        if not product_folder_id:
            try:
                product_folder_id = convert_zicum.find_product_folder(root_folder_id, title)
            except Exception as e:
                logger.error(f"Lỗi tìm kiếm thư mục tự động: {e}")
                
        if not product_folder_id:
            logger.warning(f"Không thể định vị thư mục Drive cho sản phẩm: {title}")
            continue
            
        # Cào danh sách thư mục con
        subfolders = {}
        try:
            subfolders = convert_zicum.get_subfolders_of_drive_folder(product_folder_id)
        except Exception as e:
            logger.error(f"Lỗi khi cào thư mục con từ Drive: {e}")
            continue
            
        if not subfolders:
            logger.warning(f"Thư mục Drive sản phẩm không có thư mục con nào: {product_folder_id}")
            continue
            
        # Lọc danh sách Insight từ Insight Library
        insight_prop = properties.get("Insight Library", {})
        insight_items = []
        if insight_prop.get("type") == "rich_text":
            insight_items = parse_insight_mentions(insight_prop.get("rich_text", []))
            
        if not insight_items:
            logger.info(f"Sản phẩm {title} không có trang Insight con nào trong Insight Library.")
            continue
            
        for idx, item in enumerate(insight_items):
            ins_name = item["insight_name"]
            ins_page_id = item["page_id"]
            
            # Đọc thuộc tính Link hình hiện tại của trang Insight con
            try:
                ins_page_data = call_notion_with_retry(notion.pages.retrieve, page_id=ins_page_id)
                ins_properties = ins_page_data.get("properties", {})
                
                link_hinh = ""
                prop_lh = ins_properties.get("Link hình", {})
                prop_type = prop_lh.get("type", "url")
                
                if prop_type == "url":
                    link_hinh = prop_lh.get("url", "") or ""
                elif prop_type == "rich_text":
                    link_hinh = "".join([t.get("plain_text", "") for t in prop_lh.get("rich_text", [])]).strip()
                    
                # Nếu đã có link hình rồi thì bỏ qua không ghi đè
                if link_hinh:
                    logger.info(f"Bỏ qua Insight '{ins_name}' (Đã có sẵn link hình: {link_hinh})")
                    continue
                    
                # Tìm thư mục Drive tương ứng
                clean_insight = convert_zicum.clean_name(ins_name)
                clean_folder_name = convert_zicum.clean_name(f"Insight {idx+1}")
                
                target_folder_id = None
                if clean_insight in subfolders:
                    target_folder_id = subfolders[clean_insight]
                else:
                    for sf_name, sf_id in subfolders.items():
                        if clean_folder_name in sf_name or sf_name in clean_folder_name or clean_insight in sf_name or sf_name in clean_insight:
                            target_folder_id = sf_id
                            break
                            
                if target_folder_id:
                    new_link = f"https://drive.google.com/drive/folders/{target_folder_id}"
                    
                    if prop_type == "url":
                        update_props = {"Link hình": {"url": new_link}}
                    else:
                        update_props = {"Link hình": {"rich_text": [{"text": {"content": new_link}}]}}
                        
                    call_notion_with_retry(
                        notion.pages.update,
                        page_id=ins_page_id,
                        properties=update_props
                    )
                    logger.info(f"Đã cập nhật Link hình cho Insight '{ins_name}': {new_link}")
                    updated_pages.append(ins_name)
                else:
                    logger.warning(f"Không tìm thấy thư mục Drive con cho Insight: {ins_name}")
            except Exception as ex:
                logger.error(f"Lỗi khi cập nhật Insight {ins_name}: {ex}")
                
    return updated_pages
