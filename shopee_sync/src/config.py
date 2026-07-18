import os
from pathlib import Path
from dotenv import load_dotenv

# Tìm đường dẫn tuyệt đối của file .env
# Nếu có ENV_FILE_PATH từ biến môi trường (khi chạy qua MCP client), ưu tiên sử dụng
env_path = os.getenv("ENV_FILE_PATH")
project_root = Path(__file__).resolve().parent.parent
if env_path:
    load_dotenv(env_path)
else:
    # Mặc định tìm .env ở thư mục gốc của project
    import sys
    if getattr(sys, 'frozen', False):
        load_dotenv(Path(sys.executable).parent / "shopee_sync" / ".env")
    else:
        load_dotenv(project_root / ".env")

PARTNER_ID = int(os.getenv("PARTNER_ID", "0"))
PARTNER_KEY = os.getenv("PARTNER_KEY", "")
SHOP_ID = int(os.getenv("SHOP_ID", "0"))
SHOPEE_API_URL = os.getenv("SHOPEE_API_URL", "https://partner.test-stable.shopeemobile.com").rstrip("/")
REDIRECT_URL = os.getenv("REDIRECT_URL", "https://localhost/callback")
MOCK_MODE = os.getenv("MOCK_MODE", "True").lower() in ("true", "1", "yes")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# File lưu trữ token
token_file_env = os.getenv("TOKEN_FILE_PATH", "tokens.json")
if Path(token_file_env).is_absolute():
    TOKEN_FILE_PATH = Path(token_file_env)
else:
    TOKEN_FILE_PATH = Path(__file__).resolve().parent.parent / token_file_env

def get_config_summary() -> dict:
    """Trả về thông tin cấu hình tóm tắt (không lộ key nhạy cảm) để logging/debugging."""
    return {
        "PARTNER_ID": PARTNER_ID,
        "SHOP_ID": SHOP_ID,
        "SHOPEE_API_URL": SHOPEE_API_URL,
        "REDIRECT_URL": REDIRECT_URL,
        "MOCK_MODE": MOCK_MODE,
        "TOKEN_FILE_PATH": str(TOKEN_FILE_PATH),
        "PARTNER_KEY_LOADED": bool(PARTNER_KEY),
        "GEMINI_API_KEY_LOADED": bool(GEMINI_API_KEY)
    }
