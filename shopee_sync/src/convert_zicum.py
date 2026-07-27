import os
import re
import json
import logging
import requests
import pandas as pd
from pathlib import Path
from typing import List, Optional

# Thiết lập logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("convert_zicum")

def convert_drive_to_direct_link(url: str) -> str:
    """
    Chuyển đổi link file Google Drive thông thường thành Direct Link tải ảnh trực tiếp.
    Ví dụ: https://drive.google.com/file/d/1A2B3C/view -> https://lh3.googleusercontent.com/d/1A2B3C
    """
    if not url or "drive.google.com" not in url:
        return url
        
    # Link file: /file/d/FILE_ID
    file_match = re.search(r'/file/d/([a-zA-Z0-9_-]+)', url)
    if file_match:
        file_id = file_match.group(1)
        return f"https://lh3.googleusercontent.com/d/{file_id}"
        
    # Link open?id=FILE_ID
    id_match = re.search(r'[?&]id=([a-zA-Z0-9_-]+)', url)
    if id_match:
        file_id = id_match.group(1)
        return f"https://lh3.googleusercontent.com/d/{file_id}"
        
    return url

def decode_drive_js_string(s: str) -> str:
    try:
        # Convert \xXX to \u00XX for json.loads compatibility
        s_mod = re.sub(r'\\x([0-9a-fA-F]{2})', r'\\u00\1', s)
        # Handle escaped forward slashes
        s_mod = s_mod.replace(r'\/', '/')
        return json.loads(f'"{s_mod}"')
    except Exception:
        try:
            return s.encode('utf-8').decode('unicode-escape')
        except Exception:
            return s

def clean_name(s: str) -> str:
    if not s:
        return ""
    s = decode_drive_js_string(s)
    s = s.lower()
    import unicodedata
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode('utf-8')
    s = re.sub(r'[^a-z0-9]', '', s)
    return s

def preprocess_drive_html(html: str) -> str:
    # Replace common hex escapes and unicode escapes for easier regex matching
    html = html.replace(r'\x22', '"')
    html = html.replace(r'\x5b', '[')
    html = html.replace(r'\x5d', ']')
    html = html.replace(r'\x2f', '/')
    html = html.replace(r'\/', '/')
    
    html = html.replace(r'\u0022', '"')
    html = html.replace(r'\u005b', '[')
    html = html.replace(r'\u005d', ']')
    html = html.replace(r'\\u0022', '"')
    html = html.replace(r'\\u005b', '[')
    html = html.replace(r'\\u005d', ']')
    
    return html

def get_subfolders_of_drive_folder(folder_id: str) -> dict:
    if not folder_id:
        return {}
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        url = f"https://drive.google.com/drive/folders/{folder_id}"
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code != 200:
            logger.warning(f"Không thể tải thư mục {folder_id}, status code: {res.status_code}")
            return {}
            
        html = preprocess_drive_html(res.text)
        
        # Match folders using robust combined regex
        pattern = r'\[\[null,"([a-zA-Z0-9_-]{25,50})"\],null,null,null,"application/vnd.google-apps.folder".*?\[\[\["([^"]+)",null,1\]\]\]'
        folders = re.findall(pattern, html, re.DOTALL)
        
        subfolders = {}
        for fid, name in folders:
            if fid != folder_id:
                c_name = clean_name(name)
                if c_name:
                    subfolders[c_name] = fid
        
        logger.info(f"Quét thư mục {folder_id} và tìm thấy {len(subfolders)} thư mục con.")
        return subfolders
    except Exception as e:
        logger.error(f"Lỗi khi lấy thư mục con của {folder_id}: {e}")
        return {}

def get_images_and_videos_in_folder(folder_id: str) -> List[dict]:
    if not folder_id:
        return []
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        url = f"https://drive.google.com/drive/folders/{folder_id}"
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code != 200:
            logger.warning(f"Không thể tải thư mục {folder_id}, status code: {res.status_code}")
            return []
            
        html = preprocess_drive_html(res.text)
        files_list = []
        
        # Match files using robust combined regex
        pattern = r'\[\[null,"([a-zA-Z0-9_-]{25,50})"\],null,null,null,"([^"]+)".*?\[\[\["([^"]+)",null,1\]\]\]'
        items = re.findall(pattern, html, re.DOTALL)
        
        for fid, mime, name in items:
            if fid != folder_id and ("image" in mime or "video" in mime):
                if "video" in mime:
                    link = f"https://drive.google.com/uc?export=download&id={fid}"
                else:
                    link = f"https://lh3.googleusercontent.com/d/{fid}"
                filename = decode_drive_js_string(name)
                if not any(f["id"] == fid for f in files_list):
                    files_list.append({
                        "id": fid,
                        "url": link,
                        "name": filename,
                        "mime": mime
                    })
                    
        # Fallback: scan any candidate ID in HTML if list is empty
        if not files_list:
            candidates = re.findall(r'"([a-zA-Z0-9_-]{25,50})"', html)
            for fid in candidates:
                if fid != folder_id:
                    link = f"https://lh3.googleusercontent.com/d/{fid}"
                    if not any(f["id"] == fid for f in files_list):
                        files_list.append({
                            "id": fid,
                            "url": link,
                            "name": f"file_{fid}",
                            "mime": "image/jpeg"
                        })
                        
        logger.info(f"Đã quét thư mục {folder_id} và tìm thấy {len(files_list)} file hình ảnh/video.")
        return files_list
    except Exception as e:
        logger.error(f"Lỗi khi cào file trong thư mục {folder_id}: {e}")
        return []

def find_product_folder(root_folder_id: str, product_title: str) -> Optional[str]:
    subfolders = get_subfolders_of_drive_folder(root_folder_id)
    clean_title = clean_name(product_title)
    if not clean_title:
        return None
        
    # Pass 1: Ưu tiên khớp CHÍNH XÁC 100% tên thư mục
    for sf_clean_name, sf_id in subfolders.items():
        if sf_clean_name == clean_title:
            logger.info(f"Tìm thấy thư mục sản phẩm KHỚP CHÍNH XÁC 100%: '{sf_clean_name}' -> ID: {sf_id}")
            return sf_id
            
    # Pass 2: Nếu không khớp 100%, chọn thư mục có tỉ lệ khớp cao nhất và độ phủ tên lớn nhất
    from difflib import SequenceMatcher
    best_match_id = None
    best_ratio = 0.0
    best_name = ""
    for sf_clean_name, sf_id in subfolders.items():
        ratio = SequenceMatcher(None, sf_clean_name, clean_title).ratio()
        if sf_clean_name in clean_title:
            match_coverage = len(sf_clean_name) / float(len(clean_title))
            ratio = max(ratio, 0.6 + (0.39 * match_coverage))
        elif clean_title in sf_clean_name:
            match_coverage = len(clean_title) / float(len(sf_clean_name))
            ratio = max(ratio, 0.6 + (0.39 * match_coverage))

        if ratio > best_ratio:
            best_ratio = ratio
            best_match_id = sf_id
            best_name = sf_clean_name
            
    if best_ratio >= 0.65 and best_match_id:
        logger.info(f"Tìm thấy thư mục sản phẩm khớp cao nhất '{best_name}' (tương đồng {best_ratio*100:.1f}%): ID {best_match_id}")
        return best_match_id
        
    return None

def find_insight_folder(product_folder_id: str, insight_name: str) -> Optional[str]:
    subfolders = get_subfolders_of_drive_folder(product_folder_id)
    clean_insight = clean_name(insight_name)
    if not clean_insight:
        return None
        
    # 1. Khớp chính xác hoặc substring
    for sf_clean_name, sf_id in subfolders.items():
        if sf_clean_name == clean_insight or sf_clean_name in clean_insight or clean_insight in sf_clean_name:
            logger.info(f"Tìm thấy thư mục Insight khớp chuẩn: '{sf_clean_name}' -> ID: {sf_id}")
            return sf_id
            
    # 2. Khớp mềm bằng SequenceMatcher (trên 50% tương đồng)
    from difflib import SequenceMatcher
    best_match_id = None
    best_ratio = 0.0
    for sf_clean_name, sf_id in subfolders.items():
        ratio = SequenceMatcher(None, sf_clean_name, clean_insight).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_match_id = sf_id
            
    if best_ratio >= 0.5:
        logger.info(f"Tìm thấy thư mục Insight khớp mềm (tương đồng {best_ratio*100:.1f}%): ID {best_match_id}")
        return best_match_id
        
    return None

def get_images_from_drive_folder(folder_url: str, product_title: Optional[str] = None) -> List[str]:
    """
    Quét danh sách các file ID trong thư mục Google Drive công khai và trả về danh sách link tải trực tiếp.
    Hỗ trợ:
    1. Tự động lọc bỏ các file video, tài liệu (chỉ lấy file ảnh/video).
    2. Tự động quét và tìm thư mục con (sub-folder) có tên trùng/khớp với tên sản phẩm.
    """
    if not folder_url:
        return []
        
    if "drive.google.com" not in folder_url or "/folders/" not in folder_url:
        # Nếu là link file đơn lẻ
        direct = convert_drive_to_direct_link(folder_url)
        return [direct] if direct != folder_url else []
        
    try:
        folder_match = re.search(r'/folders/([a-zA-Z0-9_-]+)', folder_url)
        if not folder_match:
            return []
        folder_id = folder_match.group(1)
        
        target_folder_id = folder_id
        if product_title:
            pf_id = find_product_folder(folder_id, product_title)
            if pf_id:
                target_folder_id = pf_id
                
        files = get_images_and_videos_in_folder(target_folder_id)
        # Chỉ trả về link ảnh cho mục đích tương thích ngược
        return [f["url"] for f in files if "image" in f["mime"]][:9]
    except Exception as e:
        logger.error(f"Lỗi khi cào thư mục Google Drive: {e}")
        return []



def generate_zicum_excel(drive_url: Optional[str] = None):
    logger.info("Bắt đầu xử lý dữ liệu sản phẩm ZicumGSV...")
    
    # Đường dẫn file mẫu gốc lấy tương đối từ thư mục project
    project_root = Path(__file__).resolve().parent.parent
    template_path = str(project_root / "import_template_VN.xlsx")

    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Không tìm thấy file mẫu gốc tại: {template_path}")
        
    # Đọc cấu trúc header hàng 1 từ file mẫu
    df_template = pd.read_excel(template_path, header=None)
    columns = df_template.iloc[0].tolist()
    
    # Mô tả sản phẩm chi tiết chuẩn SEO
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
- Bổ sung lượng kẽm thiết yếu cho phụ nữ có thai và cho con bú.

👥 ĐỐI TƯỢNG SỬ DỤNG
- Người bị mụn trứng cá, mụn viêm, viêm da, da khô sừng hóa, chàm, gàu, rôm sảy.
- Người có sức đề kháng kém, dễ bị nhiễm trùng hô hấp hoặc tiêu hóa.
- Trẻ em chậm lớn, còi xương, hay quấy khóc ban đêm.
- Phụ nữ có thai hoặc đang cho con bú cần bổ sung kẽm do chế độ ăn thiếu hụt.

💊 HƯỚNG DẪN SỬ DỤNG & LIỀU DÙNG
- Cách dùng: Uống trực tiếp sau bữa ăn.
- Liều dùng:
  + Người lớn và trẻ em trên 6 tuổi: Uống 1 viên/ngày.
  + Phụ nữ mang thai và cho con bú: Uống 1 - 2 viên/ngày.
  + Trẻ em dưới 6 tuổi: Nên tham khảo ý kiến bác sĩ để chọn dạng bào chế phù hợp hơn (như siro).

⚠️ LƯU Ý
- Không dùng cho người mẫn cảm với bất kỳ thành phần nào của sản phẩm.
- Không uống chung với tetracyclin, ciprofloxacin, sắt hoặc các thuốc điều trị dạ dày dạng sữa vì có thể cản trước hấp thu kẽm.
- Sản phẩm này là thực phẩm bảo vệ sức khỏe, không phải là thuốc và không có tác dụng thay thế thuốc chữa bệnh.

📦 BẢO QUẢN
Bảo quản nơi khô ráo, thoáng mát, nhiệt độ dưới 30°C, tránh ánh nắng trực tiếp."""

    # 3. Lấy danh sách ảnh từ Google Drive nếu được truyền vào
    images = []
    if drive_url:
        logger.info(f"Phát hiện link Google Drive: {drive_url}. Tiến hành trích xuất link tải trực tiếp...")
        images = get_images_from_drive_folder(drive_url)
        
    # Mặc định nếu không lấy được ảnh từ Drive thì dùng ảnh hãng
    cover_image = images[0] if len(images) > 0 else "https://gsvvietnam.com/wp-content/uploads/2021/04/Zicum-GSV.jpg"
    sub_images = [images[i] if i < len(images) else "" for i in range(1, 9)]

    # Xây dựng dòng dữ liệu
    row_data = {}
    for col in columns:
        row_data[col] = ""
        
    row_data["ID danh mục*"] = 101543
    row_data["Tên sản phẩm*"] = "ZicumGSV – Viên Uống Kẽm Giảm Mụn, Tăng Cường Sức Đề Kháng"
    row_data["Link nhà cung cấp"] = drive_url if drive_url else ""
    row_data["SKU sản phẩm"] = "ZICUMGSV-BOX"
    row_data["Mô tả sản phẩm*"] = description
    row_data["SKU"] = "ZICUMGSV-BOX"
    row_data["Tồn kho*"] = 100
    row_data["Giá*"] = 90000
    
    # Điền ảnh bìa và các ảnh con
    row_data["Ảnh bìa*"] = cover_image
    for idx, img_url in enumerate(sub_images):
        row_data[f"Hình ảnh {idx + 1}"] = img_url
        
    row_data["Cân nặng (g)*"] = 150
    row_data["Chiều dài (cm)"] = 12
    row_data["Chiều rộng (cm)"] = 10
    row_data["Chiều cao (cm)"] = 5
    row_data["Tình trạng"] = 1

    # Tạo DataFrame
    new_df = pd.DataFrame([row_data], columns=columns)
    
    # Lưu file
    output_dir = Path(__file__).resolve().parent.parent / "output"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / "bigseller_zicumgsv.xlsx"
    new_df.to_excel(output_file, index=False)
    
    logger.info(f"Đã tạo thành công file Excel BigSeller tại: {output_file}")
    if len(images) > 0:
        logger.info(f"Đã đính kèm {len(images)} ảnh trực tiếp từ Google Drive của bạn.")
    else:
        logger.warning("Không tìm thấy ảnh từ Drive, đã sử dụng ảnh hãng làm mặc định.")
        
    return str(output_file)

if __name__ == "__main__":
    import sys
    # Chấp nhận tham số truyền vào là link Drive từ dòng lệnh
    drive_link = sys.argv[1] if len(sys.argv) > 1 else None
    generate_zicum_excel(drive_link)
