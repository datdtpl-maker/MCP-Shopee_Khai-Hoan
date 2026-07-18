import os
import re
import json
import logging
import requests
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
from notion_client import Client
from dotenv import load_dotenv

logger = logging.getLogger("insight_generator")

# Cố định ID database của Insight Library
INSIGHT_DATABASE_ID = "88159c90-46fb-426d-b3c9-a0d79358e76c"

# Sử dụng cơ chế retry của notion_sync
from .notion_sync import call_notion_with_retry, get_rich_text_content

# Bộ lọc từ cấm của Shopee VN
from .ai_generator import clean_banned_words

def generate_insights_json(product_title: str, price_variant: str, api_key: str) -> List[Dict[str, Any]]:
    """
    Gọi OpenAI hoặc Gemini để tạo 5 Insight sản phẩm dưới dạng JSON chuẩn.
    """
    prompt = f"""
Bạn là chuyên gia tư vấn sản phẩm, nghiên cứu hành vi khách hàng và tối ưu nội dung bán hàng xuất sắc trên các sàn TMĐT tại Việt Nam.
Hãy viết nội dung bán hàng cực kỳ thuyết phục cho sản phẩm sau:
- Tên sản phẩm: "{product_title}"
- Thông tin phân loại/giá (nếu có): "{price_variant}"

NHIỆM VỤ CỦA BẠN:
Hãy viết ra ĐÚNG 5 góc nhìn/insight khách hàng (Angle) khác nhau để phục vụ việc đăng 5 bài viết Shopee khác nhau cho sản phẩm này.
Ví dụ nếu sản phẩm là thực phẩm chức năng trị mụn, 5 góc nhìn có thể bao gồm:
1. Da dầu mụn/mụn nội tiết lâu ngày không khỏi (Bổ sung kẽm uống trong).
2. Phục hồi da yếu, da nhạy cảm sau khi hết mụn.
3. Góc nhìn tư vấn chuyên môn từ Dược sĩ/chuyên viên sức khỏe.
4. Mụn tuổi dậy thì ở học sinh, sinh viên.
5. Nam giới bị mụn do sinh hoạt, thức khuya, dùng rượu bia.
(Bạn hãy tùy biến 5 góc nhìn/insight này sao cho phù hợp nhất với loại sản phẩm "{product_title}").

QUY TẮC TUÂN THỦ CHÍNH SÁCH SHOPEE VIỆT NAM (BẮT BUỘC):
Để tránh bị khóa sản phẩm, bạn BẮT BUỘC:
1. KHÔNG dùng các từ khẳng định y khoa, chữa bệnh như: "đặc trị", "trị mụn", "điều trị", "dứt điểm", "trị dứt điểm", "chữa khỏi", "thuốc".
2. THAY THẾ bằng các từ an toàn thương mại điện tử: "hỗ trợ giảm mụn", "giúp cải thiện da mụn", "chăm sóc da mụn", "viên uống bổ sung", "hiệu quả", "cân bằng dầu nhờn".
3. TUYỆT ĐỐI KHÔNG dùng từ nói quá: "100%", "tốt nhất", "số 1", "cam kết hoàn tiền", "vĩnh viễn".
4. KHÔNG chèn số điện thoại, link website, zalo hay thông tin liên hệ ngoài Shopee.

CẤU TRÚC CHI TIẾT BÀI ĐĂNG CỦA MỖI INSIGHT (Dựa trên cấu trúc ZicumGSV mẫu):
Với mỗi Insight, bài viết chi tiết phải được chuẩn bị đầy đủ các phần:
- Tiêu đề post Shopee: lồng ghép tên sản phẩm gốc và từ khóa phụ (< 120 ký tự).
- Hook (Mở đầu): 2-3 câu ngắn đánh trúng nỗi đau.
- Insight tóm tắt: 2-3 câu tóm tắt tâm lý nhóm khách hàng này.
- Mô tả sản phẩm: 1-2 đoạn văn giới thiệu tổng quan.
- Thành phần nổi bật: 2-3 thành phần chính kèm công dụng.
- Công dụng hỗ trợ: 4-5 dòng công dụng.
- Đối tượng sử dụng: 3-4 nhóm đối tượng phù hợp.
- Cách dùng: hướng dẫn sử dụng.
- Lưu ý: các lưu ý sử dụng an toàn và miễn trừ y khoa.
- Hashtags: 8-10 hashtags liên quan viết liền cách nhau bằng khoảng trắng.

ĐỊNH DẠNG ĐẦU RA BẮT BUỘC (CHỈ TRẢ VỀ JSON):
Trả về kết quả ở định dạng JSON duy nhất, không kèm theo bất kỳ văn bản giải thích nào khác ngoài JSON. JSON phải là một mảng chứa chính xác 5 phần tử tương ứng với 5 insight, cấu trúc như sau:
{{
  "insights": [
    {{
      "order": 1,
      "angle": "Tên góc nhìn (Ví dụ: Da dầu mụn / mụn nội tiết / bổ sung kẽm uống trong)",
      "hook": "Đoạn hook mở đầu đánh trúng tâm lý...",
      "insight_summary": "Tóm tắt ngắn gọn insight khách hàng của góc nhìn này...",
      "keywords": "Từ khóa chính cho insight (cách nhau bằng dấu phẩy)",
      "title": "Tiêu đề tối ưu Shopee (<120 ký tự, ví dụ: {product_title} Kẽm Zinc Vitamin C Hỗ Trợ Da Dầu Mụn...)",
      "body": {{
        "description": "Đoạn văn mô tả sản phẩm chi tiết chuyên nghiệp...",
        "ingredients": [
          "Tên thành phần 1: mô tả công dụng...",
          "Tên thành phần 2: mô tả công dụng..."
        ],
        "benefits": [
          "Công dụng hỗ trợ 1...",
          "Công dụng hỗ trợ 2...",
          "Công dụng hỗ trợ 3...",
          "Công dụng hỗ trợ 4..."
        ],
        "target_users": [
          "Đối tượng sử dụng phù hợp 1...",
          "Đối tượng sử dụng phù hợp 2...",
          "Đối tượng sử dụng phù hợp 3..."
        ],
        "usage": "Hướng dẫn cách dùng ngắn gọn, trực quan...",
        "notes": [
          "Sản phẩm không phải là thuốc và không có tác dụng thay thế thuốc chữa bệnh.",
          "Không dùng các từ cấm y khoa như điều trị khi đăng sản phẩm.",
          "Hiệu quả có thể khác nhau tùy cơ địa từng người."
        ],
        "hashtags": "#TenSanPham #Hashtag1 #Hashtag2..."
      }}
    }},
    ... (Thêm tiếp insight 2, 3, 4, 5)
  ]
}}
"""

    is_openai = api_key.startswith("sk-")
    
    if is_openai:
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {
                    "role": "system",
                    "content": "You are a professional Shopee VN copywriting assistant. You must reply with a valid JSON object matching the requested schema. Do not write anything outside the JSON."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "response_format": {"type": "json_object"}
        }
        
        logger.info(f"Đang gửi yêu cầu sinh 5 Insight tới OpenAI cho sản phẩm '{product_title}'...")
        response = requests.post(url, headers=headers, json=payload, timeout=50)
        response.raise_for_status()
        
        result_json = response.json()
        raw_text = result_json["choices"][0]["message"]["content"].strip()
    else:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json"
            }
        }
        
        logger.info(f"Đang gửi yêu cầu sinh 5 Insight tới Gemini cho sản phẩm '{product_title}'...")
        response = requests.post(url, headers=headers, json=payload, timeout=50)
        response.raise_for_status()
        
        result_json = response.json()
        raw_text = result_json["candidates"][0]["content"]["parts"][0]["text"].strip()
        
        if raw_text.startswith("```"):
            match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw_text)
            if match:
                raw_text = match.group(1).strip()
                
    data = json.loads(raw_text)
    insights_list = data.get("insights", [])
    
    # Làm sạch các từ cấm đối với tất cả bài viết nhận về
    for item in insights_list:
        item["title"] = clean_banned_words(item.get("title", product_title))
        item["angle"] = clean_banned_words(item.get("angle", ""))
        item["hook"] = clean_banned_words(item.get("hook", ""))
        item["insight_summary"] = clean_banned_words(item.get("insight_summary", ""))
        item["keywords"] = clean_banned_words(item.get("keywords", ""))
        
        body = item.get("body", {})
        body["description"] = clean_banned_words(body.get("description", ""))
        body["ingredients"] = [clean_banned_words(x) for x in body.get("ingredients", [])]
        body["benefits"] = [clean_banned_words(x) for x in body.get("benefits", [])]
        body["target_users"] = [clean_banned_words(x) for x in body.get("target_users", [])]
        body["usage"] = clean_banned_words(body.get("usage", ""))
        body["notes"] = [clean_banned_words(x) for x in body.get("notes", [])]
        body["hashtags"] = clean_banned_words(body.get("hashtags", ""))
        
    return insights_list

def generate_and_create_insights(product_page_id: str, progress_callback: Optional[Callable[[str], None]] = None) -> List[str]:
    """
    Quy trình tự động hóa:
    1. Đọc tên sản phẩm từ Notion.
    2. Gọi AI sinh 5 bài viết Insight.
    3. Tạo 5 trang Notion con tương ứng trong database Insight Library.
    4. Cập nhật liên kết mention vào thuộc tính 'Insight Library' trên trang cha.
    5. Tích chọn checkbox 'Bài viết' = True trên trang cha.
    """
    def log_progress(msg: str):
        logger.info(msg)
        if progress_callback:
            progress_callback(msg)
            
    import sys
    if getattr(sys, 'frozen', False):
        load_dotenv(Path(sys.executable).parent / "shopee_sync" / ".env")
    else:
        project_root = Path(__file__).resolve().parent.parent
        load_dotenv(project_root / ".env")
    
    token = os.getenv("NOTION_TOKEN")
    api_key = os.getenv("GEMINI_API_KEY")
    
    if not token:
        raise ValueError("Chưa cấu hình NOTION_TOKEN trong file .env")
    if not api_key:
        raise ValueError("Chưa cấu hình GEMINI_API_KEY (hoặc OpenAI key) trong file .env")
        
    notion = Client(auth=token)
    
    # 1. Đọc thông tin sản phẩm cha
    log_progress("Đang đọc thông tin sản phẩm từ Notion...")
    page_data = call_notion_with_retry(notion.pages.retrieve, page_id=product_page_id)
    properties = page_data.get("properties", {})
    
    title_list = properties.get("Tên sản phẩm", {}).get("title", [])
    product_title = title_list[0].get("plain_text", "").strip() if title_list else ""
    if not product_title:
        raise ValueError(f"Không tìm thấy Tên sản phẩm của Notion Page ID: {product_page_id}")
        
    price_variant = get_rich_text_content(properties.get("Biến thể & giá", {}))
    log_progress(f"Đã lấy thông tin sản phẩm: '{product_title}' (Biến thể & giá: '{price_variant}')")
    
    # 2. Gọi AI sinh 5 Insight
    log_progress("Đang gửi yêu cầu tới AI để sinh 5 bài viết Insight...")
    insights = generate_insights_json(product_title, price_variant, api_key)
    
    if not insights or len(insights) < 5:
        raise ValueError(f"AI không trả về đúng cấu trúc 5 insight. Vui lòng thử lại.")
        
    log_progress("Sinh 5 bài viết thành công! Bắt đầu tạo các trang con trên Notion...")
    
    created_pages_info = []
    
    # 3. Tạo từng trang con và ghi nội dung bài viết
    for idx, item in enumerate(insights):
        order_num = item.get("order", idx + 1)
        angle_name = item.get("angle", f"Insight {order_num}")
        post_title = item.get("title", f"{product_title} - Insight {order_num}")
        
        log_progress(f"Đang tạo trang Insight {order_num}/5: '{angle_name}'...")
        
        # 3.1. Tạo trang con Notion
        page_properties = {
            "Tên post Shopee": {"title": [{"text": {"content": post_title}}]},
            "Angle": {"rich_text": [{"text": {"content": angle_name}}]},
            "Hook": {"rich_text": [{"text": {"content": item.get("hook", "")}}]},
            "Insight": {"rich_text": [{"text": {"content": item.get("insight_summary", "")}}]},
            "Từ khóa chính cho insight": {"rich_text": [{"text": {"content": item.get("keywords", "")}}]},
            "Thứ tự": {"number": order_num},
            "Sản phẩm Shopee": {"relation": [{"id": product_page_id}]},
            "Trạng thái duyệt": {"select": {"name": "Chờ duyệt"}},
            "Trạng thái tạo hình": {"select": {"name": "Chờ tạo hình"}},
            "Format": {"select": {"name": "Shopee Post"}}
        }
        
        new_page = call_notion_with_retry(
            notion.pages.create,
            parent={"database_id": INSIGHT_DATABASE_ID},
            properties=page_properties
        )
        new_page_id = new_page["id"]
        created_pages_info.append({
            "page_id": new_page_id,
            "angle": angle_name
        })
        
        # 3.2. Soạn nội dung Body vào trang con
        body = item.get("body", {})
        blocks = [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"text": {"content": post_title, "link": None}}],
                    "color": "default"
                }
            },
            {
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"text": {"content": "Mô tả sản phẩm"}}]
                }
            },
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"text": {"content": body.get("description", "")}}]
                }
            },
            {
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"text": {"content": "Thành phần nổi bật"}}]
                }
            }
        ]
        
        for ing in body.get("ingredients", []):
            blocks.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{"text": {"content": ing}}]
                }
            })
            
        blocks.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"text": {"content": "Công dung hỗ trợ"}}]
            }
        })
        for ben in body.get("benefits", []):
            blocks.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{"text": {"content": ben}}]
                }
            })
            
        blocks.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"text": {"content": "Đối tượng sử dụng"}}]
            }
        })
        for target in body.get("target_users", []):
            blocks.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{"text": {"content": target}}]
                }
            })
            
        blocks.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"text": {"content": "Cách dùng"}}]
            }
        })
        blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"text": {"content": body.get("usage", "")}}]
            }
        })
        
        blocks.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"text": {"content": "Lưu ý"}}]
            }
        })
        for note in body.get("notes", []):
            blocks.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{"text": {"content": note}}]
                }
            })
            
        blocks.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"text": {"content": "Hashtag"}}]
            }
        })
        blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"text": {"content": body.get("hashtags", "")}}]
            }
        })
        
        call_notion_with_retry(
            notion.blocks.children.append,
            block_id=new_page_id,
            children=blocks
        )
        
    # 4. Cập nhật trang sản phẩm cha
    log_progress("Tất cả 5 trang con đã được tạo thành công! Đang cập nhật liên kết lên trang sản phẩm chính...")
    
    rich_text_list = []
    for idx, created_item in enumerate(created_pages_info):
        rich_text_list.append({
            "type": "text",
            "text": {"content": f"{idx+1}. {created_item['angle']}: "}
        })
        rich_text_list.append({
            "type": "mention",
            "mention": {
                "type": "page",
                "page": {"id": created_item["page_id"]}
            }
        })
        if idx < len(created_pages_info) - 1:
            rich_text_list.append({
                "type": "text",
                "text": {"content": "\n"}
            })
            
    call_notion_with_retry(
        notion.pages.update,
        page_id=product_page_id,
        properties={
            "Insight Library": {"rich_text": rich_text_list},
            "Bài viết": {"checkbox": True}
        }
    )
    
    log_progress(f"🎉 Hoàn tất! Đã tạo xong 5 Insight và cập nhật ô 'Bài viết' trên Notion cho sản phẩm '{product_title}'.")
    return [x["page_id"] for x in created_pages_info]
