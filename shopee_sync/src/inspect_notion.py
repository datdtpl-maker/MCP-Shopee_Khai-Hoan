import os
import sys
import json
from notion_client import Client
from pathlib import Path
from dotenv import load_dotenv

# Tìm file .env
import sys
if getattr(sys, 'frozen', False):
    load_dotenv(Path(sys.executable).parent / "shopee_sync" / ".env")
else:
    project_root = Path(__file__).resolve().parent.parent
    load_dotenv(project_root / ".env")

def inspect():
    token = os.getenv("NOTION_TOKEN")
    db_id = os.getenv("NOTION_DATABASE_ID")
    
    output_lines = []
    
    if not token or not db_id:
        output_lines.append("Loi: Chua cau hinh NOTION_TOKEN hoac NOTION_DATABASE_ID trong file .env")
        with open("notion_inspect_results.txt", "w", encoding="utf-8") as f_out:
            f_out.write("\n".join(output_lines))
        return
        
    output_lines.append(f"Dang kiem tra ket noi toi Database ID: {db_id}...")
    notion = Client(auth=token)
    
    try:
        db = notion.databases.retrieve(database_id=db_id)
        
        # Lấy tên của Database
        db_title = "Khong ten"
        title_list = db.get("title", [])
        if title_list:
            db_title = title_list[0].get("plain_text", "Khong ten")
            
        result = {
            "status": "success",
            "database_name": db_title,
            "properties": {}
        }
        
        output_lines.append(f"\nKet noi thanh cong! Ten bang Notion: {db_title}")
        output_lines.append("\nDanh sach cac cot (Properties) tim thay:")
        for prop_name, prop_val in db.get("properties", {}).items():
            prop_type = prop_val.get("type")
            output_lines.append(f"- {prop_name}: kieu '{prop_type}'")
            result["properties"][prop_name] = prop_type
            
        # Ghi schema JSON
        output_file = project_root / "notion_schema.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=4)
        output_lines.append(f"\nDa luu schema cua Notion Database vao: {output_file}")
        
    except Exception as e:
        output_lines.append(f"\nLOI KET NOI NOTION: {e}")
        output_lines.append("Vui long kiem tra lai:")
        output_lines.append("1. Token notion va Database ID da dien chinh xac chua.")
        output_lines.append("2. Quan trong nhat: Ban da bam dau 3 cham tren trang Notion, chon 'Add connections' va cap quyen cho Integration cua ban chua.")

    with open("notion_inspect_results.txt", "w", encoding="utf-8") as f_out:
        f_out.write("\n".join(output_lines))

if __name__ == "__main__":
    inspect()
