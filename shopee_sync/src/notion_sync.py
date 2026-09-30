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


def _normalize_page_id(page_id: Optional[str]) -> str:
    return re.sub(r"[^a-zA-Z0-9]", "", str(page_id or "")).lower()


def _count_product_insights(properties: Dict[str, Any], notion_client=None) -> int:
    so_insight_prop = properties.get("Số Insight", {})
    if so_insight_prop.get("type") == "rollup":
        num = so_insight_prop.get("rollup", {}).get("number")
        if num is not None:
            return int(num)
    ds_prop = properties.get("Danh sách Insight", {})
    if ds_prop.get("type") == "relation":
        return len(ds_prop.get("relation", []))
    insight_prop = properties.get("Insight Library", {})
    prop_type = insight_prop.get("type")
    if prop_type == "relation":
        rel_list = insight_prop.get("relation", [])
        if not rel_list:
            return 0
        if notion_client:
            try:
                lib_id = rel_list[0].get("id")
                lib_page = call_notion_with_retry(notion_client.pages.retrieve, page_id=lib_id)
                sub_rels = lib_page.get("properties", {}).get("Danh sách Insight", {}).get("relation", [])
                if sub_rels:
                    return len(sub_rels)
            except Exception:
                pass
        return len(rel_list)
    if prop_type == "rich_text":
        return len(parse_insight_mentions(insight_prop.get("rich_text", [])))
    return 0


def find_local_product_folder(drive_root_path: Path, product_title: str) -> Optional[Path]:
    """Tìm thư mục local theo tên đầy đủ hoặc tên rút gọn duy nhất của sản phẩm, hỗ trợ cả thư mục gốc và thư mục shop con."""
    if not drive_root_path or not drive_root_path.is_dir() or not product_title:
        return None

    target_clean = convert_zicum.clean_name(product_title)
    if not target_clean:
        return None

    prefix_matches = []
    
    # Quét cả thư mục gốc và các thư mục shop con (nhathuockh.pharma, khaihoanpharmacy, v.v.)
    search_dirs = [drive_root_path]
    try:
        for sub in drive_root_path.iterdir():
            if sub.is_dir() and not sub.name.startswith("."):
                search_dirs.append(sub)
    except Exception:
        pass

    for base in search_dirs:
        try:
            for item in base.iterdir():
                if not item.is_dir() or item.name.startswith("."):
                    continue
                item_clean = convert_zicum.clean_name(item.name)
                if not item_clean:
                    continue

                # 1. Trùng khớp tuyệt đối
                if item_clean == target_clean:
                    return item

                # 2. Bóc tách tiền tố thông dụng như 'insight', 'anh', 'hinh', 'sp', 'sanpham'
                stripped_clean = re.sub(r'^(insight|anh|hinh|sp|sanpham)', '', item_clean)
                if stripped_clean and stripped_clean == target_clean:
                    return item

                # 3. So khớp tiền tố trực tiếp
                if len(item_clean) >= 4 and (target_clean.startswith(item_clean) or item_clean.startswith(target_clean)):
                    prefix_matches.append((800 + len(item_clean), item))

                # 4. So khớp tiền tố hoặc từ khóa chính sau khi tách 'insight'
                if stripped_clean and len(stripped_clean) >= 4:
                    if target_clean.startswith(stripped_clean) or stripped_clean.startswith(target_clean):
                        prefix_matches.append((700 + len(stripped_clean), item))
                    elif len(stripped_clean) >= 5 and (stripped_clean in target_clean or target_clean in stripped_clean):
                        prefix_matches.append((500 + len(stripped_clean), item))
        except Exception:
            continue

    if not prefix_matches:
        return None
    prefix_matches.sort(key=lambda match: match[0], reverse=True)
    return prefix_matches[0][1]



def map_insights_to_drive_folders(
    insight_items: List[Dict[str, str]],
    subfolders: Dict[str, str],
) -> List[Dict[str, Any]]:
    """Ánh xạ Insight N sang đúng thư mục Drive theo tên insight con hoặc Insight N."""
    if len(insight_items) < 1:
        raise ValueError(f"Cần ít nhất 1 Insight để đồng bộ link hình; hiện tìm thấy {len(insight_items)}.")

    normalized_subfolders = {
        convert_zicum.clean_name(folder_name): (folder_id, folder_name)
        for folder_name, folder_id in subfolders.items()
    }
    mapping = []
    used_folder_ids = set()
    for index, insight_item in enumerate(insight_items, 1):
        clean_insight_name = convert_zicum.clean_name(insight_item.get("insight_name", ""))
        folder_match = normalized_subfolders.get(clean_insight_name) if clean_insight_name else None

        if not folder_match:
            numbered_folder_name = convert_zicum.clean_name(f"Insight {index}")
            folder_match = normalized_subfolders.get(numbered_folder_name)

        if not folder_match and clean_insight_name:
            for k, (f_id, orig_name) in normalized_subfolders.items():
                if f_id not in used_folder_ids and (k.startswith(clean_insight_name) or clean_insight_name.startswith(k)):
                    folder_match = (f_id, orig_name)
                    break

        if not folder_match:
            available = [(f_id, orig_name) for k, (f_id, orig_name) in normalized_subfolders.items() if f_id not in used_folder_ids]
            if available:
                folder_match = available[0]

        if not folder_match:
            raise ValueError(f"Không tìm thấy thư mục Drive tương ứng cho Insight {index} ('{insight_item.get('insight_name', '')}').")

        folder_id = folder_match[0]
        if folder_id in used_folder_ids and len(subfolders) >= len(insight_items):
            raise ValueError(f"Thư mục Drive của Insight {index} đang bị trùng với Insight khác.")
        used_folder_ids.add(folder_id)
        mapping.append({
            "order": index,
            "insight": insight_item,
            "folder_id": folder_id,
        })
    return mapping


def select_products_for_export(
    records: List[Dict[str, Any]],
    target_page_id: Optional[str] = None,
    override_drive_url: Optional[str] = None,
    notion_client=None,
) -> List[Dict[str, Any]]:
    """Lọc sản phẩm xuất Excel; khi có page_id thì chỉ chấp nhận đúng bản ghi đó."""
    normalized_target_id = _normalize_page_id(target_page_id)
    target_drive_folder_id = None
    if override_drive_url and "drive.google.com" in override_drive_url:
        match = re.search(r"/folders/([a-zA-Z0-9_-]+)", override_drive_url)
        if match:
            target_drive_folder_id = match.group(1)

    selected = []
    target_was_found = False
    for page in records:
        if normalized_target_id:
            if _normalize_page_id(page.get("id")) != normalized_target_id:
                continue
            target_was_found = True

        properties = page.get("properties", {})
        title_list = properties.get("Tên sản phẩm", {}).get("title", [])
        title = title_list[0].get("plain_text", "").strip() if title_list else ""
        if not title:
            continue

        insight_count = _count_product_insights(properties, notion_client=notion_client)
        if normalized_target_id:
            if insight_count < 1:
                raise ValueError(
                    f"Sản phẩm '{title}' chưa có Insight nào trước khi xuất Excel."
                )
            selected.append(page)
            continue

        if insight_count == 0:
            continue

        status_name = ""
        status_select = properties.get("Trạng thái xử lý", {}).get("select")
        if status_select:
            status_name = status_select.get("name", "").strip()

        if target_drive_folder_id:
            media_url = properties.get("Media sản phẩm", {}).get("url", "") or ""
            if not media_url:
                media_prop = properties.get("Media sản phẩm", {})
                if media_prop.get("type") == "rich_text":
                    media_url = "".join(
                        item.get("plain_text", "") for item in media_prop.get("rich_text", [])
                    ).strip()
            page_folder_match = re.search(r"/folders/([a-zA-Z0-9_-]+)", media_url)
            if page_folder_match and page_folder_match.group(1) != target_drive_folder_id:
                continue

        if not target_drive_folder_id and status_name in ["Đã đăng", "Chờ đăng"]:
            continue
        selected.append(page)

    if normalized_target_id and not target_was_found:
        raise ValueError("Không tìm thấy sản phẩm đã chọn trong dữ liệu Notion hiện tại.")
    return selected

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
            
    # Lấy thuộc tính Link hình / Link Drive bộ ảnh
    link_hinh = ""
    for k, v in properties.items():
        if "link drive" in k.lower() or "link hình" in k.lower() or "link hinh" in k.lower() or k.lower() == "url":
            if v.get("type") == "url":
                link_hinh = v.get("url", "") or ""
            elif v.get("type") == "rich_text":
                link_hinh = "".join([t.get("plain_text", "") for t in v.get("rich_text", [])]).strip()
            if link_hinh:
                break

    # 1. Đọc toàn văn bài viết từ các blocks con của trang Notion (nơi lưu trữ đầy đủ nội dung và hashtag)
    block_description = ""
    try:
        blocks = fetch_all_blocks_recursive(notion_client, page_id)
        if blocks:
            block_description = format_notion_blocks_to_text(blocks).strip()
    except Exception as e:
        logger.warning(f"Lỗi khi đọc blocks của page {page_id}: {e}")

    # 2. Đọc thuộc tính "Nội dung đăng Shopee" hoặc "Mô tả sản phẩm"
    prop_description = ""
    for k, v in properties.items():
        if k.lower() in ["nội dung đăng shopee", "mô tả sản phẩm", "nội dung bài viết", "mô tả", "content"]:
            if v.get("type") == "rich_text":
                prop_description = "".join([t.get("plain_text", "") for t in v.get("rich_text", [])]).strip()
                if prop_description:
                    break

    # 3. Ưu tiên bản có nội dung đầy đủ nhất (chứa Hashtag hoặc có độ dài lớn hơn)
    if block_description and ("#" in block_description or len(block_description) >= len(prop_description)):
        description = block_description
    elif prop_description:
        description = prop_description
    else:
        description = block_description

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


def adapt_insight_library_product(
    notion_client,
    target_page_id: str,
    master_records: List[Dict[str, Any]],
    override_drive_url: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Chuyển đổi một bản ghi từ Shopee Insight Library (88159c9046fb426db3c9a0d79358e76c)
    kết hợp với dữ liệu giá/biến thể từ Master DB (ca055a7742824b9598abde7a7686d144)
    thành dạng sản phẩm để xuất BigSeller Excel.
    """
    try:
        page = call_notion_with_retry(notion_client.pages.retrieve, page_id=target_page_id)
        parent_db = page.get("parent", {}).get("database_id", "").replace("-", "")
        props = page.get("properties", {})
        has_insights = bool(props.get("Danh sách Insight", {}).get("relation", []))
        is_insight_db = "88159c9046fb426db3c9a0d79358e76c".replace("-", "") in parent_db or has_insights
        if not is_insight_db:
            return None

        # 1. Lấy tên sản phẩm từ Shopee Insight Library
        title_list = props.get("Tên post Shopee", {}).get("title", [])
        insight_title = title_list[0].get("plain_text", "").strip() if title_list else ""
        if not insight_title:
            for pv in props.values():
                if pv.get("type") == "title":
                    tl = pv.get("title", [])
                    if tl:
                        insight_title = tl[0].get("plain_text", "").strip()
                    break

        drive_url = override_drive_url if override_drive_url else (
            props.get("URL", {}).get("url", "") or
            props.get("Link Drive bộ ảnh", {}).get("url", "") or
            props.get("Media sản phẩm", {}).get("url", "") or ""
        )

        # 2. Tìm bản ghi tương ứng trong Master DB ca055a7742824b9598abde7a7686d144 để lấy giá và biến thể
        norm_target_id = target_page_id.replace("-", "")
        master_page = None
        for mp in master_records:
            mp_props = mp.get("properties", {})
            rel_list = mp_props.get("Insight Library", {}).get("relation", [])
            for r in rel_list:
                if r.get("id", "").replace("-", "") == norm_target_id:
                    master_page = mp
                    break
            if master_page:
                break

        if not master_page:
            clean_ins_title = convert_zicum.clean_name(insight_title)
            for mp in master_records:
                mp_props = mp.get("properties", {})
                m_title = "".join([t.get("plain_text", "") for t in mp_props.get("Tên sản phẩm", {}).get("title", [])])
                clean_m_title = convert_zicum.clean_name(m_title)
                if clean_ins_title and (clean_ins_title in clean_m_title or clean_m_title in clean_ins_title):
                    master_page = mp
                    break

        master_title = ""
        price_lines = []
        variant_prop = {}
        if master_page:
            mp_props = master_page.get("properties", {})
            master_title = "".join([t.get("plain_text", "") for t in mp_props.get("Tên sản phẩm", {}).get("title", [])]).strip()
            v1 = "".join([t.get("plain_text", "") for t in mp_props.get("Biến thể 1", {}).get("rich_text", [])]).strip()
            p1 = mp_props.get("Giá biến thể 1", {}).get("number")
            v2 = "".join([t.get("plain_text", "") for t in mp_props.get("Biến thể 2", {}).get("rich_text", [])]).strip()
            p2 = mp_props.get("Giá biến thể 2", {}).get("number")
            if not p1 and v1:
                digits = re.sub(r"\D", "", v1)
                if len(digits) >= 4:
                    p1 = int(digits)
                    v1 = "Mặc định"
            if v1 and p1:
                price_lines.append(f"{v1}: {int(p1)}")
            elif p1:
                price_lines.append(f"Mặc định: {int(p1)}")
            if v2 and p2:
                price_lines.append(f"{v2}: {int(p2)}")
            variant_prop = mp_props.get("Biến thể", {})

        if not price_lines:
            price_lines.append("Mặc định: 150000")

        final_title = master_title if master_title else insight_title
        price_variant_text = "\n".join(price_lines)

        detected_shop = master_page.get("shop", "") if master_page else ""
        if not detected_shop:
            if "02441166322448d9b596aea64410bb06" in parent_db or "af2820ea" in parent_db or "a1daa389" in parent_db:
                detected_shop = "khaihoanpharmacy"
            else:
                detected_shop = "nhathuockh.pharma"

        adapted_page = {
            "id": target_page_id,
            "original_insight_title": insight_title,
            "shop": detected_shop,
            "properties": {
                "Tên sản phẩm": {"type": "title", "title": [{"plain_text": final_title}]},
                "Biến thể & giá": {"type": "rich_text", "rich_text": [{"plain_text": price_variant_text}]},
                "Media sản phẩm": {"type": "url", "url": drive_url},
                "Danh sách Insight": props.get("Danh sách Insight", {}),
                "Insight Library": props.get("Danh sách Insight", {}),
                "Content xong": {"type": "checkbox", "checkbox": True},
                "Bài viết": {"type": "checkbox", "checkbox": False},
                "Biến thể": variant_prop
            },
            "master_page": master_page
        }
        return adapted_page
    except Exception as e:
        logger.error(f"Lỗi chuyển đổi sản phẩm Insight Library: {e}")
        return None


def sync_notion_to_bigseller_excel(
    override_drive_url: Optional[str] = None,
    target_page_id: Optional[str] = None,
) -> Tuple[str, List[str]]:
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
    import sys
    if getattr(sys, 'frozen', False):
        load_dotenv(Path(sys.executable).parent / "shopee_sync" / ".env")
    else:
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
    
    # 1. Tự động lấy danh sách sản phẩm từ các Master DB của các Shop (nhathuockh.pharma & khaihoanpharmacy)
    master_db_configs = [
        ("nhathuockh.pharma", page_id),
        ("khaihoanpharmacy", os.getenv("NOTION_DATABASE_ID_KHAIHOAN", "").strip() or "af2820eaa1594d8ca928da36a0f10e48")
    ]
    records = []
    for s_name, m_db_id in master_db_configs:
        try:
            logger.info(f"Đang đọc cấu trúc Master DB [{s_name}] ID: {m_db_id}")
            db_meta = call_notion_with_retry(notion.databases.retrieve, database_id=m_db_id)
            data_sources = db_meta.get("data_sources", [])
            if data_sources:
                for ds in data_sources:
                    res = call_notion_with_retry(notion.data_sources.query, data_source_id=ds["id"])
                    for rec in res.get("results", []):
                        rec["shop"] = s_name
                        records.append(rec)
            else:
                res = call_notion_with_retry(notion.databases.query, database_id=m_db_id)
                for rec in res.get("results", []):
                    rec["shop"] = s_name
                    records.append(rec)
        except Exception as e:
            logger.warning(f"Lỗi khi đọc Master DB [{s_name}] ({m_db_id}): {e}")

    if not records:
        raise ValueError("Không tìm thấy bản ghi sản phẩm nào trong các database Master Notion.")
    logger.info(f"Tổng số bản ghi Master DB thu thập được: {len(records)}")
    
    # 3. Khóa theo page_id khi người dùng chọn sản phẩm; không suy đoán bằng tên hay link Drive.
    adapted_product = None
    if target_page_id:
        norm_t_id = _normalize_page_id(target_page_id)
        if not any(_normalize_page_id(r.get("id")) == norm_t_id for r in records):
            try:
                direct_page = call_notion_with_retry(notion.pages.retrieve, page_id=target_page_id)
                if direct_page:
                    p_db = direct_page.get("parent", {}).get("database_id", "").replace("-", "")
                    if "02441166322448d9b596aea64410bb06" in p_db or "af2820ea" in p_db or "a1daa389" in p_db:
                        direct_page["shop"] = "khaihoanpharmacy"
                    else:
                        direct_page["shop"] = "nhathuockh.pharma"
                    records.append(direct_page)
            except Exception as e:
                logger.warning(f"Không thể đọc trực tiếp page ID {target_page_id}: {e}")

        adapted_product = adapt_insight_library_product(notion, target_page_id, records, override_drive_url)

    if adapted_product:
        pending_products = [adapted_product]
    else:
        pending_products = select_products_for_export(
            records,
            target_page_id=target_page_id,
            override_drive_url=override_drive_url,
            notion_client=notion,
        )
            
    logger.info(f"Tìm thấy {len(pending_products)} sản phẩm có đầy đủ Insight để xuất Excel.")
    
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
        
        # Lấy giá và biến thể từ properties của Notion DB1
        p1 = properties.get("Giá biến thể 1", {}).get("number")
        v1 = "".join([t.get("plain_text", "") for t in properties.get("Biến thể 1", {}).get("rich_text", [])]).strip()
        p2 = properties.get("Giá biến thể 2", {}).get("number")
        v2 = "".join([t.get("plain_text", "") for t in properties.get("Biến thể 2", {}).get("rich_text", [])]).strip()

        # Tự động chuẩn hóa nếu người dùng điền giá vào cột Biến thể 1
        if not p1 and v1:
            digits = re.sub(r"\D", "", v1)
            if len(digits) >= 4:
                p1 = int(digits)
                v_prop = properties.get("Biến thể", {})
                v_name = ""
                if v_prop.get("type") == "select" and v_prop.get("select"):
                    v_name = v_prop["select"].get("name", "")
                elif v_prop.get("type") == "multi_select" and v_prop.get("multi_select"):
                    v_name = v_prop["multi_select"][0].get("name", "")
                v1 = v_name or ("Tuýp 25g" if "25g" in title else "Mặc định")

        # Lấy văn bản biến thể và giá (cột legacy nếu có)
        price_variant_text = get_rich_text_content(properties.get("Biến thể & giá", {}))
        variants = parse_price_and_variants(price_variant_text)
        if not variants:
            if p1 and p2:
                variants = [
                    {"name": v1 or "Phân loại 1", "price": int(p1)},
                    {"name": v2 or "Phân loại 2", "price": int(p2)}
                ]
            elif p1:
                variants = [{"name": v1 or "Mặc định", "price": int(p1)}]
            
        logger.info(f"Đang xử lý sản phẩm: {title} (Giá biến thể: {variants})")
        
        # Tìm thư mục sản phẩm từ thư mục gốc lớn cấu hình trong .env hoặc mặc định
        root_folder_id = os.getenv("DRIVE_ROOT_FOLDER_ID", "1XrOmOCqdZ3xfkeVaBc0Vr77Q7yRW0PxZ").strip()
        product_folder_id = None
        
        # Trích xuất shop_hint từ drive_url hoặc từ thông tin shop của sản phẩm
        shop_hint = None
        if drive_url:
            low_url = drive_url.lower()
            if "nhathuockh" in low_url or "pharma" in low_url:
                shop_hint = "nhathuockhpharma"
            elif "khaihoan" in low_url or "derma" in low_url:
                shop_hint = "khaihoanpharmacy"

        if not shop_hint:
            shop_val = page.get("shop", "")
            if not shop_val and page.get("master_page"):
                shop_val = page["master_page"].get("shop", "")
            if shop_val:
                if "khaihoan" in shop_val.lower() or "derma" in shop_val.lower():
                    shop_hint = "khaihoanpharmacy"
                elif "nhathuockh" in shop_val.lower() or "pharma" in shop_val.lower():
                    shop_hint = "nhathuockhpharma"

        if drive_url:
            if "drive.google.com" in drive_url:
                folder_match = re.search(r'/folders/([a-zA-Z0-9_-]+)', drive_url)
                if folder_match:
                    product_folder_id = folder_match.group(1)
                    logger.info(f"Sử dụng thư mục của sản phẩm từ thuộc tính 'Media sản phẩm': ID {product_folder_id}")
            else:
                # Trường hợp dán đường dẫn local (ví dụ: G:\My Drive\Hình ảnh Shopee\nhathuockh.pharma\Insight Oximin)
                try:
                    local_path = Path(drive_url)
                    folder_name = local_path.name.strip()
                    if folder_name and folder_name.lower() != "my drive":
                        product_folder_id = convert_zicum.find_product_folder(root_folder_id, folder_name, shop_hint=shop_hint)
                        if product_folder_id:
                            logger.info(f"Tìm thấy thư mục của sản phẩm từ đường dẫn local '{drive_url}': ID {product_folder_id}")
                except Exception as e:
                    logger.error(f"Lỗi khi trích xuất tên thư mục từ link local: {e}")

        # Nếu không tìm thấy từ Notion, tự động tìm kiếm thư mục sản phẩm theo tên trong thư mục gốc Drive
        if not product_folder_id:
            try:
                product_folder_id = convert_zicum.find_product_folder(root_folder_id, title, shop_hint=shop_hint)
                if product_folder_id:
                    logger.info(f"Tìm thấy thư mục của sản phẩm '{title}' trên Drive gốc: ID {product_folder_id}")
            except Exception as e:
                logger.error(f"Lỗi khi tìm thư mục sản phẩm '{title}' từ Drive gốc: {e}")
                
        if not product_folder_id:
            if drive_url and "drive.google.com" not in drive_url:
                logger.error(f"❌ Bạn đang dán đường dẫn local: '{drive_url}'. Để sử dụng đường dẫn local, vui lòng cấu hình DRIVE_ROOT_FOLDER_ID trong file .env hoặc dán trực tiếp link Google Drive trên web của thư mục sản phẩm.")
            else:
                logger.warning(f"Không thể định vị thư mục Drive cho sản phẩm: {title}. Vui lòng kiểm tra lại link Drive sản phẩm.")

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
        
        sku_code = f"PROD-{sku_base_rand}-{idx+1:02d}"
        
        # Đọc danh sách Insight từ ô Insight Library (dạng text mentions) hoặc relation (Danh sách Insight / Insight Library)
        insight_prop = properties.get("Insight Library", {})
        insight_items = []
        if insight_prop.get("type") == "rich_text":
            insight_items = parse_insight_mentions(insight_prop.get("rich_text", []))
        elif insight_prop.get("type") == "relation":
            for rel in insight_prop.get("relation", []):
                rel_id = rel.get("id")
                try:
                    rel_page = call_notion_with_retry(notion.pages.retrieve, page_id=rel_id)
                    rel_props = rel_page.get("properties", {})
                    rel_title = ""
                    for p_val in rel_props.values():
                        if p_val.get("type") == "title":
                            t_list = p_val.get("title", [])
                            if t_list:
                                rel_title = t_list[0].get("plain_text", "").strip()
                            break

                    # Kiểm tra xem rel_page này có relation "Danh sách Insight" trỏ tới các insight con không
                    sub_relations = rel_props.get("Danh sách Insight", {}).get("relation", [])
                    if sub_relations:
                        logger.info(f"Phát hiện thư viện '{rel_title}' có {len(sub_relations)} Insight con.")
                        for sub_r in sub_relations:
                            sub_id = sub_r.get("id")
                            try:
                                sub_page = call_notion_with_retry(notion.pages.retrieve, page_id=sub_id)
                                sub_props = sub_page.get("properties", {})
                                sub_title = ""
                                for sp_val in sub_props.values():
                                    if sp_val.get("type") == "title":
                                        st_list = sp_val.get("title", [])
                                        if st_list:
                                            sub_title = st_list[0].get("plain_text", "").strip()
                                        break
                                clean_sub_title = sub_title.replace("|", "-").strip()
                                insight_items.append({
                                    "insight_name": clean_sub_title or sub_title,
                                    "page_id": sub_id,
                                    "plain_text": sub_title
                                })
                            except Exception as sub_e:
                                logger.error(f"Lỗi khi đọc Insight con {sub_id}: {sub_e}")
                    else:
                        clean_title = rel_title.replace("|", "-").strip()
                        insight_items.append({
                            "insight_name": clean_title or rel_title,
                            "page_id": rel_id,
                            "plain_text": rel_title
                        })
                except Exception as e:
                    logger.error(f"Lỗi khi đọc relation Insight Library {rel_id}: {e}")

        # Fallback sang "Danh sách Insight" nếu chưa có items
        if not insight_items:
            ds_prop = properties.get("Danh sách Insight", {})
            if ds_prop.get("type") == "relation":
                for rel in ds_prop.get("relation", []):
                    rel_id = rel.get("id")
                    try:
                        rel_page = call_notion_with_retry(notion.pages.retrieve, page_id=rel_id)
                        rel_props = rel_page.get("properties", {})
                        rel_title = ""
                        for p_val in rel_props.values():
                            if p_val.get("type") == "title":
                                t_list = p_val.get("title", [])
                                if t_list:
                                    rel_title = t_list[0].get("plain_text", "").strip()
                                break
                        clean_title = rel_title.replace("|", "-").strip()
                        insight_items.append({
                            "insight_name": clean_title or rel_title,
                            "page_id": rel_id,
                            "plain_text": rel_title
                        })
                    except Exception as e:
                        logger.error(f"Lỗi khi đọc relation Danh sách Insight {rel_id}: {e}")
            
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
                    if not link_hinh_from_page and product_folder_id:
                        target_folder_id = convert_zicum.find_insight_folder(product_folder_id, ins_name)
                        if not target_folder_id and subfolders:
                            clean_insight = convert_zicum.clean_name(ins_name)
                            clean_folder_name = convert_zicum.clean_name(f"Insight {idx+1}")
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
                                # Kiểm tra kiểu của thuộc tính Link hình / Link Drive bộ ảnh để cập nhật chuẩn xác
                                ins_page = call_notion_with_retry(notion.pages.retrieve, page_id=ins_page_id)
                                ins_props = ins_page.get("properties", {})
                                prop_name_found = None
                                for k in ins_props.keys():
                                    if "link drive" in k.lower() or "link hình" in k.lower() or "link hinh" in k.lower() or k.lower() == "url":
                                        prop_name_found = k
                                        break
                                if not prop_name_found:
                                    prop_name_found = "Link hình"

                                prop_lh = ins_props.get(prop_name_found, {})
                                prop_type = prop_lh.get("type", "url")
                                
                                if prop_type == "url":
                                    update_props = {prop_name_found: {"url": new_link}}
                                else:
                                    update_props = {prop_name_found: {"rich_text": [{"text": {"content": new_link}}]}}
                                    
                                update_notion_page_safe(
                                    notion,
                                    page_id=ins_page_id,
                                    properties=update_props
                                )
                                logger.info(f"Đã cập nhật thuộc tính '{prop_name_found}' cho trang Insight {ins_name}: {new_link}")
                                link_hinh_from_page = new_link
                            except Exception as e:
                                logger.error(f"Không thể cập nhật thuộc tính '{prop_name_found}' cho trang Insight {ins_name}: {e}")

                    # Sử dụng nội dung bài viết đã chuẩn bị sẵn từ Notion, lọc từ cấm cơ bản nếu cần
                    logger.info(f"Sử dụng nội dung bài viết đã chuẩn bị cho Insight '{ins_name}'...")
                    if description_from_page:
                        description_from_page = ai_generator.clean_banned_words(description_from_page)
                    else:
                        description_from_page = generate_seo_description(title)

                    return {
                        "insight": ins_name,
                        "title": title_from_page or ins_name,
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
            logger.warning(f"Sản phẩm '{title}' không có bài viết Insight nào trong Insight Library. Bỏ qua không xuất Excel.")
            continue
            
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
                    
            if not cover_image and image_files:
                cover_image = image_files[0]["url"]
                
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
                single_price = variants[0]["price"] if variants else (int(p1) if p1 else 90000)
                
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
    
    # Tự động lưu 1 bản sao file Excel trực tiếp vào thư mục Drive cục bộ của từng sản phẩm
    try:
        cfg_path = project_root.parent / "config.json"
        drive_root_dir = None
        if cfg_path.exists():
            try:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    cfg_data = json.load(f)
                    drive_root_dir = cfg_data.get("paths", {}).get("drive_root_dir")
            except Exception:
                pass
        if not drive_root_dir:
            drive_root_dir = "G:\\My Drive\\Hình ảnh Shopee"
            
        drive_root_path = Path(drive_root_dir)
        if drive_root_path.exists():
            import shutil
            selected_local_folder = None
            if target_page_id and override_drive_url and "drive.google.com" not in override_drive_url:
                candidate = Path(override_drive_url).resolve()
                root_resolved = drive_root_path.resolve()
                if candidate.is_dir() and candidate.is_relative_to(root_resolved):
                    selected_local_folder = candidate

            for p_page_dict in pending_products:
                p_title = ""
                t_list = p_page_dict.get("properties", {}).get("Tên sản phẩm", {}).get("title", [])
                if t_list:
                    p_title = t_list[0].get("plain_text", "").strip()
                p_orig_title = p_page_dict.get("original_insight_title", "")

                matched_folder = selected_local_folder
                if not matched_folder and p_orig_title:
                    matched_folder = find_local_product_folder(drive_root_path, p_orig_title)
                if not matched_folder and p_title:
                    matched_folder = find_local_product_folder(drive_root_path, p_title)
                if not matched_folder:
                    matched_folder = drive_root_path / (p_orig_title or p_title or "Sản phẩm")
                    matched_folder.mkdir(parents=True, exist_ok=True)
                    
                prod_excel_path = matched_folder / f"bigseller_sync_{timestamp}.xlsx"
                if excel_output_path.resolve() == prod_excel_path.resolve():
                    logger.info(f"📁 File Excel đã được xuất đúng thư mục chính của sản phẩm: {prod_excel_path}")
                else:
                    shutil.copy2(excel_output_path, prod_excel_path)
                    logger.info(f"📁 Đã lưu bản sao file Excel vào thư mục chính của sản phẩm: {prod_excel_path}")
    except Exception as drive_cp_err:
        logger.warning(f"Không thể sao chép file Excel vào thư mục Drive cục bộ: {drive_cp_err}")
    
    # 7. Cập nhật trạng thái hoàn thành trên Notion an toàn theo kiểu dữ liệu
    for p_page_dict in pending_products:
        p_id = p_page_dict.get("id")
        if not p_id:
            continue
        logger.info(f"Đang cập nhật trạng thái hoàn thành trên Notion cho page_id: {p_id}")
        try:
            p_data = call_notion_with_retry(notion.pages.retrieve, page_id=p_id)
            p_props = p_data.get("properties", {})
            update_payload = {}
            if "Trạng thái" in p_props and p_props["Trạng thái"].get("type") == "select":
                update_payload["Trạng thái"] = {"select": {"name": "Hoàn thành"}}
            if "Trạng thái xử lý" in p_props and p_props["Trạng thái xử lý"].get("type") == "select":
                update_payload["Trạng thái xử lý"] = {"select": {"name": "Chờ đăng"}}
            if "Content xong" in p_props and p_props["Content xong"].get("type") == "checkbox":
                update_payload["Content xong"] = {"checkbox": True}
            if "Bài viết" in p_props and p_props["Bài viết"].get("type") == "checkbox":
                update_payload["Bài viết"] = {"checkbox": True}
            if "Trạng thái đăng bài Shopee" in p_props and p_props["Trạng thái đăng bài Shopee"].get("type") == "checkbox":
                update_payload["Trạng thái đăng bài Shopee"] = {"checkbox": True}
            if "Trạng thái đăng bài shopee" in p_props and p_props["Trạng thái đăng bài shopee"].get("type") == "checkbox":
                update_payload["Trạng thái đăng bài shopee"] = {"checkbox": True}

            if update_payload:
                update_notion_page_safe(
                    notion,
                    page_id=p_id,
                    properties=update_payload
                )

            # Đồng thời cập nhật trạng thái cho trang Master tương ứng nếu có
            master_page = p_page_dict.get("master_page") if isinstance(p_page_dict, dict) else None
            if master_page:
                m_id = master_page.get("id")
                try:
                    m_data = call_notion_with_retry(notion.pages.retrieve, page_id=m_id)
                    m_props = m_data.get("properties", {})
                    m_update = {}
                    if "Trạng thái xử lý" in m_props and m_props["Trạng thái xử lý"].get("type") == "select":
                        m_update["Trạng thái xử lý"] = {"select": {"name": "Chờ đăng"}}
                    if "Content xong" in m_props and m_props["Content xong"].get("type") == "checkbox":
                        m_update["Content xong"] = {"checkbox": True}
                    if "Bài viết" in m_props and m_props["Bài viết"].get("type") == "checkbox":
                        m_update["Bài viết"] = {"checkbox": True}
                    if m_update:
                        update_notion_page_safe(notion, page_id=m_id, properties=m_update)
                except Exception as m_err:
                    logger.warning(f"Lỗi cập nhật master page {m_id}: {m_err}")
        except Exception as update_err:
            logger.warning(f"Không thể cập nhật thuộc tính hoàn thành trên Notion cho {p_id}: {update_err}")
        
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



def sync_only_image_links_to_notion(
    override_drive_url: Optional[str] = None,
    target_page_id: Optional[str] = None,
    replace_existing: bool = False,
) -> List[str]:
    logger.info("Bắt đầu tiến trình chỉ đồng bộ link hình Google Drive sang Notion...")
    
    # Nạp cấu hình từ .env
    project_root = Path(__file__).resolve().parent.parent
    import sys
    if getattr(sys, 'frozen', False):
        load_dotenv(Path(sys.executable).parent / "shopee_sync" / ".env")
    else:
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
    
    # Khi thao tác từ UI, khóa tuyệt đối vào page_id sản phẩm đang chọn.
    pending_products = []
    normalized_target_id = _normalize_page_id(target_page_id)
    for page in records:
        if normalized_target_id:
            if _normalize_page_id(page.get("id")) == normalized_target_id:
                pending_products.append(page)
            continue
        properties = page.get("properties", {})
        it_status = properties.get("Trạng thái đăng bài shopee", {}).get("checkbox", False)
        if not it_status:
            pending_products.append(page)

    if normalized_target_id and not pending_products:
        raise ValueError("Không tìm thấy sản phẩm đã chọn để đồng bộ link hình.")
            
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
            if drive_url and "drive.google.com" not in drive_url:
                logger.error(f"❌ Bạn đang dán đường dẫn local: '{drive_url}'. Để sử dụng đường dẫn local, vui lòng cấu hình DRIVE_ROOT_FOLDER_ID trong file .env hoặc dán trực tiếp link Google Drive trên web của thư mục sản phẩm.")
            else:
                logger.warning(f"Không thể định vị thư mục Drive cho sản phẩm: {title}. Vui lòng kiểm tra lại link Drive sản phẩm.")
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

        folder_mapping = map_insights_to_drive_folders(insight_items, subfolders)
        for mapped_item in folder_mapping:
            media_files = convert_zicum.get_images_and_videos_in_folder(mapped_item["folder_id"])
            if not media_files:
                raise ValueError(
                    f"Thư mục Drive Insight {mapped_item['order']} của sản phẩm '{title}' không có hình hoặc video."
                )

        for mapped_item in folder_mapping:
            item = mapped_item["insight"]
            ins_name = item["insight_name"]
            ins_page_id = item["page_id"]
            target_folder_id = mapped_item["folder_id"]
            new_link = f"https://drive.google.com/drive/folders/{target_folder_id}"
            
            # Đọc thuộc tính Link hình hiện tại của trang Insight con
            ins_page_data = call_notion_with_retry(notion.pages.retrieve, page_id=ins_page_id)
            ins_properties = ins_page_data.get("properties", {})
            prop_lh = ins_properties.get("Link hình", {})
            prop_type = prop_lh.get("type", "url")

            if prop_type == "url":
                link_hinh = prop_lh.get("url", "") or ""
            elif prop_type == "rich_text":
                link_hinh = "".join([t.get("plain_text", "") for t in prop_lh.get("rich_text", [])]).strip()
            else:
                link_hinh = ""

            if link_hinh == new_link:
                logger.info(f"Insight '{ins_name}' đã có đúng link hình: {new_link}")
                continue
            if link_hinh and not replace_existing:
                logger.info(f"Bỏ qua Insight '{ins_name}' vì đã có link hình và chưa bật ghi đè.")
                continue

            if prop_type == "url":
                update_props = {"Link hình": {"url": new_link}}
            else:
                update_props = {"Link hình": {"rich_text": [{"text": {"content": new_link}}]}}

            update_notion_page_safe(
                notion,
                page_id=ins_page_id,
                properties=update_props,
            )
            logger.info(f"Đã cập nhật Link hình cho Insight '{ins_name}': {new_link}")
            updated_pages.append(ins_name)
                
    return updated_pages


def create_notion_page_safe(notion_client, parent_db_id: str, properties: Dict[str, Any]) -> Dict[str, Any]:
    """Tạo trang Notion an toàn, tự động dò tìm/bỏ qua các thuộc tính không tồn tại trong DB schema hoặc sai kiểu dữ liệu."""
    import re
    props = dict(properties)

    # 1. Kiểm tra schema của Database để tự động điều chỉnh tên trường Relation nếu bị đổi tên
    try:
        db_meta = notion_client.databases.retrieve(database_id=parent_db_id)
        db_props = db_meta.get("properties", {})
        
        # Nếu "Sản phẩm Shopee" có trong props, map sang tất cả các cột relation sản phẩm có trong db_props
        if "Sản phẩm Shopee" in props:
            rel_val = props.pop("Sản phẩm Shopee")
            relation_keys = ["Công việc Shopee", "Sản phẩm quản lý", "Sản phẩm Shopee", "Sản phẩm", "Product"]
            matched_any = False
            for key in relation_keys:
                if key in db_props and db_props[key].get("type") == "relation":
                    props[key] = rel_val
                    matched_any = True
                    logger.info(f"Đã tự động liên kết sản phẩm vào cột relation '{key}'.")
            if not matched_any:
                for p_name, p_info in db_props.items():
                    if p_info.get("type") == "relation":
                        props[p_name] = rel_val
                        logger.info(f"Đã tự động liên kết sản phẩm vào cột relation '{p_name}'.")
                        break
    except Exception as err:
        logger.warning(f"Không thể kiểm tra schema Notion Database: {err}")

    # 2. Thử tạo page, nếu gặp lỗi thuộc tính không tồn tại thì tự động loại bỏ trường đó và thử lại
    attempt_props = dict(props)
    while True:
        try:
            return call_notion_with_retry(
                notion_client.pages.create,
                parent={"database_id": parent_db_id},
                properties=attempt_props,
                max_retries=2
            )
        except Exception as e:
            err_msg = str(e)
            if "is not a property that exists" in err_msg:
                match = re.search(r"([^'\"]+?)\s+is not a property that exists", err_msg)
                if match:
                    missing_prop = match.group(1).strip()
                    if "properties." in missing_prop:
                        missing_prop = missing_prop.split("properties.")[-1]
                    if missing_prop in attempt_props:
                        logger.warning(f"Thuộc tính '{missing_prop}' không tồn tại trong Notion Database, tự động loại bỏ và thử lại...")
                        attempt_props.pop(missing_prop, None)
                        continue
            
            # Xử lý trường hợp "Link hình" sai kiểu dữ liệu (url vs rich_text)
            if "Link hình" in attempt_props:
                link_val = attempt_props["Link hình"]
                if "url" in link_val and link_val["url"]:
                    logger.warning("Đổi kiểu dữ liệu 'Link hình' sang rich_text và thử lại...")
                    attempt_props["Link hình"] = {"rich_text": [{"text": {"content": link_val["url"]}}]}
                    continue
                elif "rich_text" in link_val:
                    logger.warning("Loại bỏ 'Link hình' và thử lại...")
                    attempt_props.pop("Link hình", None)
                    continue
            
            raise e


def update_notion_page_safe(notion_client, page_id: str, properties: Dict[str, Any]):
    """Cập nhật trang Notion an toàn, tự động thử lại nếu sai thuộc tính/kiểu dữ liệu."""
    import re
    props = dict(properties)
    while True:
        try:
            return call_notion_with_retry(
                notion_client.pages.update,
                page_id=page_id,
                properties=props,
                max_retries=2
            )
        except Exception as e:
            err_msg = str(e)
            if "is not a property that exists" in err_msg:
                match = re.search(r"([^'\"]+?)\s+is not a property that exists", err_msg)
                if match:
                    missing_prop = match.group(1).strip()
                    if "properties." in missing_prop:
                        missing_prop = missing_prop.split("properties.")[-1]
                    if missing_prop in props:
                        logger.warning(f"Thuộc tính '{missing_prop}' không tồn tại trong Notion Page, tự động bỏ qua...")
                        props.pop(missing_prop, None)
                        if not props:
                            return None
                        continue
            
            # Xử lý Link hình type mismatch
            if "Link hình" in props:
                link_val = props["Link hình"]
                if "url" in link_val and link_val["url"]:
                    props["Link hình"] = {"rich_text": [{"text": {"content": link_val["url"]}}]}
                    continue
                elif "rich_text" in link_val:
                    props.pop("Link hình", None)
                    if not props:
                        return None
                    continue
            
            raise e
