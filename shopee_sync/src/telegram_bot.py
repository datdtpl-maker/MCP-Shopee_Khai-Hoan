import os
import time
import socket
import threading
import logging
import telebot
from pathlib import Path
from dotenv import load_dotenv

# Thiết lập socket timeout mặc định là 30 giây để ngăn chặn kết nối treo ngầm
socket.setdefaulttimeout(30)

# Import module nội bộ
from . import notion_sync

# Thiết lập logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("telegram_bot")

# Nạp file .env
project_root = Path(__file__).resolve().parent.parent
import sys
if getattr(sys, 'frozen', False):
    load_dotenv(Path(sys.executable).parent / "shopee_sync" / ".env")
else:
    load_dotenv(project_root / ".env")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("Lỗi: Chưa cấu hình TELEGRAM_BOT_TOKEN trong file .env")

# Khởi tạo TeleBot
bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = """Chào mừng bạn đến với **Shopee - BigSeller Auto Sync Bot**! 🤖

Công cụ này giúp bạn tự động hóa việc đồng bộ dữ liệu sản phẩm từ Notion sang định dạng Excel của BigSeller.

✨ **Các lệnh hỗ trợ:**
- `/sync` : Quét các sản phẩm mới trên Notion (Bài viết = True và Trạng thái đăng bài shopee = False), chuyển đổi hình ảnh từ Google Drive thành link trực tiếp, tách các biến thể và gửi lại file Excel hoàn chỉnh cho bạn.
- `/help` : Hiển thị lại hướng dẫn sử dụng này.

**Cách dùng Notion:**
1. Thêm sản phẩm mới vào bảng Notion của bạn.
2. Bộ phận Content chuẩn bị hình ảnh/mô tả xong thì tích chọn cột **'Bài viết'**.
3. Vào Telegram gõ lệnh `/sync` để lấy file Excel BigSeller tải lên shop!"""
    bot.reply_to(message, welcome_text, parse_mode='Markdown')

@bot.message_handler(commands=['sync'])
def handle_sync(message):
    chat_id = message.chat.id
    logger.info(f"Nhận được yêu cầu /sync từ chat_id: {chat_id}")
    
    # Gửi tin nhắn phản hồi ban đầu
    status_msg = bot.send_message(chat_id, "⏳ Đang quét Notion và xử lý dữ liệu sản phẩm mới. Vui lòng đợi trong giây lát...")
    
    try:
        # Gọi hàm đồng bộ
        excel_path, processed_titles = notion_sync.sync_notion_to_bigseller_excel()
        
        if not processed_titles:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_msg.message_id,
                text="✅ Không có sản phẩm mới nào cần xử lý (Tất cả sản phẩm đã được tick hoàn thành cột Trạng thái đăng bài shopee trên Notion)."
            )
            return
            
        # Gửi file Excel cho người dùng
        with open(excel_path, 'rb') as f:
            bot.send_document(
                chat_id=chat_id,
                document=f,
                caption=f"🎉 Đã xử lý xong {len(processed_titles)} sản phẩm mới!\n\n📦 Danh sách sản phẩm:\n" + "\n".join([f"- {t}" for t in processed_titles]) + "\n\n👉 Tải file này lên BigSeller tại mục Hộp nháp."
            )
            
        # Xóa tin nhắn trạng thái cũ
        bot.delete_message(chat_id, status_msg.message_id)
        logger.info(f"Đã gửi file Excel thành công cho chat_id: {chat_id}")
        
        # Tự động xóa file Excel tạm trên máy tính sau khi gửi xong
        try:
            if os.path.exists(excel_path):
                os.remove(excel_path)
                logger.info(f"Đã tự động dọn dẹp file Excel tạm: {excel_path}")
        except Exception as delete_err:
            logger.warning(f"Lỗi khi xóa file Excel tạm: {delete_err}")
        
    except Exception as e:
        logger.error(f"Lỗi khi thực hiện đồng bộ: {e}")
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=status_msg.message_id,
            text=f"❌ Có lỗi xảy ra trong quá trình xử lý: {str(e)}"
        )

should_stop = False

def stop_bot_process():
    global should_stop
    should_stop = True
    try:
        bot.stop_polling()
    except Exception:
        pass
    logger.info("Đã gửi lệnh dừng Bot Telegram.")

def check_new_products_loop():
    """
    Vòng lặp chạy ngầm để quét Notion định kỳ (2 phút/lần).
    Điều kiện lọc: Có tên sản phẩm mới + ô 'Bài viết' đã click (True) + ô 'Trạng thái đăng bài shopee' chưa tích (False).
    Gửi thông báo chủ động đến Quản lý khi phát hiện sản phẩm mới thỏa mãn.
    """
    already_notified = set()
    logger.info("Bộ quét tìm sản phẩm mới (chạy ngầm) đã bắt đầu khởi chạy...")
    
    while not should_stop:
        try:
            # Load lại env để đề phòng thay đổi cấu hình
            load_dotenv(project_root / ".env")
            manager_chat_id = os.getenv("MANAGER_CHAT_ID")
            
            if manager_chat_id:
                # Gọi kiểm tra Notion
                pending_items = notion_sync.check_pending_products()
                
                # Lọc ra các sản phẩm chưa gửi thông báo
                new_pending = [item for item in pending_items if item["id"] not in already_notified]
                
                if new_pending:
                    titles = [item["title"] for item in new_pending]
                    logger.info(f"Phát hiện {len(titles)} sản phẩm mới thỏa mãn điều kiện chờ đăng Shopee. Gửi thông báo đến Quản lý...")
                    
                    msg = f"🔔 **Shopee MCP Server xin thông báo: CÓ SẢN PHẨM MỚI CHỜ ĐĂNG SHOPEE!**\n\n" \
                          f"Phát hiện {len(titles)} sản phẩm có tên sản phẩm mới, ô 'Bài viết' đã được click chuẩn bị xong nhưng ô 'Trạng thái đăng bài shopee' chưa được tích chọn:\n" + \
                          "\n".join([f"📦 *{t}*" for t in titles]) + \
                          "\n\n👉 Người quản lý vui lòng kiểm tra Notion hoặc gõ lệnh `/sync` tại đây để bot tiến hành chuyển đổi và xuất file Excel BigSeller nhé!"
                          
                    try:
                        bot.send_message(chat_id=int(manager_chat_id), text=msg, parse_mode='Markdown')
                    except Exception as send_err:
                        logger.error(f"Không thể gửi thông báo tới quản lý qua Telegram (Mạng lỗi hoặc Chat ID sai): {send_err}")
                    
                    # Lưu lại trạng thái đã báo để tránh spam
                    for item in new_pending:
                        already_notified.add(item["id"])
                        
                # Dọn dẹp bộ nhớ: giữ lại trong set những sản phẩm vẫn đang trong trạng thái pending
                current_pending_ids = {item["id"] for item in pending_items}
                already_notified = already_notified.intersection(current_pending_ids)
                
        except Exception as loop_err:
            logger.error(f"Lỗi trong tiến trình quét ngầm: {loop_err}")
            
        # Ngủ 120s nhưng chia nhỏ kiểm tra should_stop để dừng ngay lập tức
        for _ in range(120):
            if should_stop:
                break
            time.sleep(1)

def run_bot():
    global should_stop
    should_stop = False
    logger.info("Bot Telegram đang khởi động luồng quét ngầm tìm sản phẩm mới...")
    # Khởi chạy daemon thread quét Notion
    t = threading.Thread(target=check_new_products_loop, daemon=True)
    t.start()
    
    # Khởi chạy bot polling có khả năng chống treo / tự động kết nối lại
    logger.info("Bot Telegram bắt đầu lắng nghe và xử lý tin nhắn...")
    while not should_stop:
        # Cơ chế giám sát (Watchdog): Nếu luồng chạy ngầm bị chết, tự động tạo lại và khởi chạy
        if not t.is_alive() and not should_stop:
            logger.warning("Cảnh báo: Luồng quét ngầm tìm sản phẩm mới bị dừng đột ngột! Đang tự động hồi sinh luồng...")
            t = threading.Thread(target=check_new_products_loop, daemon=True)
            t.start()
            
        try:
            # infinity_polling hỗ trợ tự kết nối lại với timeout
            bot.infinity_polling(timeout=10, long_polling_timeout=5)
        except Exception as e:
            if should_stop:
                break
            logger.error(f"Lỗi kết nối hoặc polling của bot bị treo. Đang tự động kết nối lại sau 5 giây... Chi tiết: {e}")
            time.sleep(5)
    logger.info("Bot Telegram đã dừng hoàn toàn.")

if __name__ == "__main__":
    run_bot()
