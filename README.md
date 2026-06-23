# MCP Shopee - Khải Hoàn & AI Edit Image / Video (Gemini & ChatGPT Helper)

Ứng dụng Web cục bộ (Local Web App) tích hợp đa năng: Điều khiển điện thoại Google Pixel chụp ảnh sản phẩm, tự động đồng bộ Google Drive, **đồng bộ Notion sang BigSeller với 5 AI Insights**, **tách nền ghép ảnh sản phẩm lai (Hybrid Composition)** vẽ poster quảng cáo AI chuyên nghiệp, và công cụ **AI Edit Image / Video tự động hóa ChatGPT & Gemini Web (Gemini Omni)** để xử lý hình ảnh và video sản phẩm nhanh chóng, dễ dàng.

Giao diện ứng dụng được thiết kế hoàn toàn theo phong cách **Material Design 3 (MD3)** hiện đại, mượt mà (hỗ trợ chuyển đổi Dark/Light Mode), tối ưu hóa 100% quy trình làm việc từ khâu chụp sản phẩm thô cho đến khi hoàn thiện dữ liệu đăng bán Shopee.

---

## ✨ Tính Năng Nổi Bật

### 1. Đồng Bộ Shopee / BigSeller & AI Insights (Mới)
- **Tích hợp Notion:** Lấy nhanh danh sách sản phẩm chờ viết bài trực tiếp từ Notion database.
- **Phân tích hình ảnh bằng AI:** Sử dụng Gemini để phân tích hình ảnh sản phẩm và tự động sinh ra **5 Insights bán hàng** chất lượng cao bao gồm:
  - Góc viết (Angle)
  - Tiêu đề post gợi ý
  - Nội dung Insight chi tiết
  - Từ khóa SEO gợi ý
  - Comment chỉnh sửa
- **Bảng Review & Chỉnh sửa trực tiếp:** Giao diện bảng tiện lợi cho phép người dùng chỉnh sửa thủ công nội dung AI sinh ra trước khi lưu.
- **Ghi nhận Notion một chạm:** Tự động ghi ngược lại toàn bộ 5 insight và thông tin sản phẩm hoàn thiện vào cơ sở dữ liệu Notion.
- **Xuất bản Excel BigSeller:** Tạo các file Excel mẫu chuẩn của BigSeller để import hàng loạt sản phẩm trực tiếp lên Shopee một cách dễ dàng.

### 2. Điều Khiển Pixel & Đồng Bộ Drive Tự Động
- **Kết nối linh hoạt**: Điều khiển Pixel chụp ảnh/quay phim thông qua cáp USB hoặc Wi-Fi không dây.
- **Tự động tạo 5 thư mục con**: Khi tạo một thư mục sản phẩm mới, hệ thống tự động tạo thêm 5 thư mục con `Insight 1` đến `Insight 5` bên trong để tổ chức hình ảnh. Ảnh chụp thực tế của sản phẩm vẫn được lưu trực tiếp tại thư mục sản phẩm chính.
- **Cơ chế xóa thư mục cưỡng bức**: Hỗ trợ nút xóa thư mục đang chọn cùng toàn bộ các thư mục con và file bên trong (`shutil.rmtree`) chỉ với 1 click, giúp dọn dẹp không gian làm việc nhanh chóng.
- **Tự động đánh thức & Mở khóa (Auto-Wake & Unlock)**: Tự động kiểm tra trạng thái màn hình Pixel trước khi chụp/quay. Nếu màn hình đang tắt, hệ thống tự động đánh thức (`keyevent 224`) và giả lập thao tác vuốt lên để vượt qua màn hình khóa.
- **Nút Dừng khẩn cấp (Stop Operation)**: Kết thúc cưỡng bức (`taskkill /F`) tiến trình `adb.exe` hoặc `scrcpy.exe` ngầm bị treo, đưa hệ thống về trạng thái "Sẵn sàng" tức thì.
- **Đồng bộ bảo mật**: Tự động đưa ảnh chụp vào đúng thư mục sản phẩm được chọn trên Google Drive for Desktop. Xác minh dung lượng byte nghiêm ngặt trước khi xóa ảnh gốc trên điện thoại.

### 3. Tạo Poster AI Với Sản Phẩm Thật (Hybrid Composition)
- **Bảo toàn sản phẩm thật 100%**: Sử dụng thư viện `rembg` cục bộ để tách nền sản phẩm thực tế, tự ghép đè sản phẩm lên bối cảnh được AI vẽ ra.
- **Vẽ bóng đổ tự nhiên**: Tự động vẽ bóng đổ đen mờ semi-transparent và làm mịn bóng bằng Gaussian Blur dưới chân sản phẩm giúp ảnh ghép hòa hợp 100% với ánh sáng bối cảnh.
- **Tối ưu chi phí & Tốc độ**: Sử dụng mô hình `gpt-image-1-mini` với chất lượng `quality="medium"` giúp tối ưu hóa chi phí API OpenAI ở mức thấp nhất, tạo nhiều ảnh song song chỉ mất 10-15 giây thông qua xử lý bất đồng bộ ThreadPool.
- **Tự động hóa prompt**: GPT-4o Vision tự động phân tích màu sắc, nhãn hiệu sản phẩm và viết lại prompt tiếng Anh tối ưu nhất cho mô hình sinh ảnh vẽ nền.

### 4. Công Cụ AI Edit Image / Video (Tự Động Hóa Qua ChatGPT & Gemini)
- **Tiết kiệm chi phí**: Kết nối trực tiếp vào tab ChatGPT (cổng 9222) hoặc Gemini (cổng 9223) đang mở trên trình duyệt Chrome thật của bạn để ra lệnh tạo/sửa ảnh và video miễn phí.
- **Hỗ trợ dán URL ảnh mẫu trực tiếp**: Cho phép dán trực tiếp link ảnh mẫu trên internet vào ô URL ảnh mẫu. Hệ thống sử dụng một API Image Proxy ở backend để bypass 100% lỗi CORS hoặc chính sách chặn hotlink của các bên thứ ba.
- **Tự động hóa Playwright**: 
  - Tự động click focus, upload tệp tin sản phẩm (hỗ trợ cả ảnh và video).
  - Tự động điền prompt mẫu và gửi tin nhắn (giả lập click nút gửi hoặc gõ phím Enter bằng keyboard thật, tương thích React state).
  - Tải ảnh/video kết quả về máy: Tự động tải ảnh kết quả bằng cơ chế `fetch` nội bộ để tránh lỗi CORS. Đối với video dạng `blob:` trên Gemini, hệ thống tự động chạy Javascript qua Playwright để chuyển đổi blob video sang định dạng Base64 và lưu thành file `.mp4` trực tiếp vào thư mục Downloads của người dùng.
- **Thao tác kéo thả siêu tốc**: Tích hợp nút **"Mở thư mục"** tự động kích hoạt Windows Explorer và bôi đen sẵn (highlight) tệp kết quả vừa tải về để bạn kéo thả trực tiếp vào Photoshop hoặc Canva Web.
- **Thư viện Prompt & Danh mục động**: Quản lý prompts mẫu theo danh mục động (Shopee, Facebook, TikTok Shop...). Giao diện quản lý danh mục (Thêm/Sửa/Xóa) trực quan, tự động đồng bộ danh mục và hỗ trợ **nhập (import) hàng loạt prompt từ file `.txt`** siêu tốc.

---

## 💻 Yêu Cầu Hệ Thống

- **Hệ điều hành**: Windows 10 / 11.
- **Môi trường**: Python 3.10 trở lên.
- **Công cụ đi kèm**:
  - Google Drive for Desktop (đã đăng nhập tài khoản).
  - Android SDK Platform Tools (đã thêm lệnh `adb` vào PATH).
  - [scrcpy](https://github.com/Genymobile/scrcpy) (để chiếu màn hình).
  - Trình duyệt Google Chrome (đăng nhập tài khoản ChatGPT / Gemini).

---

## 🚀 Hướng Dẫn Cài Đặt Nhanh

1. **Tải mã nguồn và cài đặt thư viện**:
   ```powershell
   git clone https://github.com/datdtpl-maker/MCP-Shopee_Khai-Hoan.git
   cd MCP-Shopee_Khai-Hoan
   python -m pip install -r requirements.txt
   ```

2. **Khởi tạo tệp cấu hình**:
   ```powershell
   Copy-Item config.example.json config.json
   ```

3. **Thiết lập điện thoại Pixel**:
   * Bật **Tùy chọn nhà phát triển** và kích hoạt **Gỡ lỗi USB** trên Pixel.
   * Cắm cáp USB vào máy tính và xác nhận tin cậy thiết bị.

---

## ⚙️ Hướng Dẫn Vận Hành

### 1. Khởi chạy ứng dụng Web
Chạy lệnh để khởi chạy máy chủ Flask:
```powershell
python .\web_app.py
```
Mở trình duyệt và truy cập: **`http://127.0.0.1:8765`** (hoặc tên miền nội bộ `http://mcp-shopee-khai-hoan:8765`).

### 2. Sử dụng tính năng AI Edit Image / Video (ChatGPT & Gemini Web)
* **Đối với ChatGPT Web (cổng 9222):**
  1. Đóng hoàn toàn các cửa sổ Chrome bình thường nếu bị lỗi xung đột hoặc kẹt tiến trình.
  2. Bấm nút **"Mở Chrome ChatGPT"** trên giao diện (hoặc chạy tệp `run_debug_chrome.bat`) để mở cửa sổ Chrome debug ChatGPT. Trình duyệt debug này sử dụng một profile cô lập riêng biệt (`chrome_profile_debug` nằm ngay trong thư mục dự án) để tránh đụng độ với tài khoản Chrome cá nhân.
  3. Đăng nhập tài khoản ChatGPT của bạn ở lần đầu tiên.
  4. Quay lại giao diện Web Helper, chọn file, dán URL ảnh mẫu (nếu có) và điền prompt rồi bấm **"Gửi Lên ChatGPT"**.

* **Đối với Gemini Web (cổng 9223 - Chỉnh sửa Video/Hình ảnh):**
  1. Bấm nút **"Mở Chrome Gemini"** trên giao diện (hoặc chạy tệp `run_debug_chrome_gemini.bat`) để mở cửa sổ Chrome debug Gemini cô lập (`chrome_profile_debug_gemini` trong thư mục dự án).
  2. Đăng nhập tài khoản Google để sử dụng Gemini Omni tại địa chỉ `https://gemini.google.com`.
  3. Kéo thả hoặc chọn tệp tin sản phẩm (hỗ trợ cả ảnh `.jpg`/`.png` và video `.mp4`/`.mov`), nhập prompt chỉnh sửa hoặc dán URL ảnh mẫu.
  4. Bấm nút **"Gửi Lên Gemini"** để tự động hóa đính kèm tệp và ra lệnh chỉnh sửa.
  5. Sau khi Gemini xử lý xong, tệp kết quả sẽ tự động tải về thư mục Downloads và xuất hiện trong cột **Ảnh kết quả** để mở thư mục hoặc đưa sang Canva.

### 3. Vận hành thông qua File EXE Đóng Gói (Windows)
Ứng dụng hỗ trợ đóng gói hoàn chỉnh sang thư mục chạy độc lập (không cần cài Python ở máy đích):
1. **Biên dịch**: Tại thư mục dự án, chạy lệnh:
   ```powershell
   python .\build_exe.py
   ```
2. **Triển khai**: Copy thư mục `dist/MCPShopee` sang máy tính khác.
3. **Khởi chạy**: Click đúp tệp **`MCPShopee.exe`** để chạy trực tiếp Flask server. Các tệp cấu hình (`config.json`, `content_prompts.json`, `run_debug_chrome.bat`, `run_debug_chrome_gemini.bat`) sẽ tự động được sinh ra ở ngoài thư mục root để bạn dễ dàng chỉnh sửa cấu hình.

---

## 📤 Hướng Dẫn Nhập (Import) Prompt Mẫu Hàng Loạt

Tính năng **"+ Nhập file"** cho phép bạn import hàng loạt prompt từ một tệp `.txt` vào thư viện. 

### 1. Cú pháp tệp tin `.txt` mẫu
Mỗi prompt được ngăn cách bằng dòng chứa ba dấu gạch ngang `---` hoặc dấu bằng `===`. Cấu trúc cụ thể bao gồm các từ khóa `Danh mục:`, `Tiêu đề:`, và `Nội dung:` như sau:

```text
Danh mục: Shopee
Tiêu đề: Bối cảnh Studio Xanh Lá
Nội dung: Vui lòng vẽ một bối cảnh studio quảng cáo cao cấp cho sản phẩm trong ảnh này. Đặt sản phẩm trên bệ đá cẩm thạch trắng, xung quanh là các lá cây nhiệt đới màu xanh mướt...
---
Danh mục: Facebook
Tiêu đề: Bối cảnh bãi cát mùa hè
Nội dung: Vui lòng vẽ một bối cảnh mùa hè năng động cho sản phẩm này. Đặt sản phẩm trên bãi cát mịn màu vàng nhạt, có sóng biển xanh trong...
---
Danh mục: Tiktok Shop
Tiêu đề: Bối cảnh Livestream Đỏ Rực
Nội dung: Vẽ một bối cảnh sân khấu livestream đỏ rực rỡ, ánh đèn LED rực rỡ chiếu sáng...
Nội dung có thể xuống dòng viết tiếp ở đây thoải mái
```

> [!NOTE]
> * **Tự đăng ký danh mục**: Nếu tên danh mục trong file import chưa có trong hệ thống (ví dụ: `Tiktok Shop`), hệ thống sẽ **tự động thêm danh mục** này vào file cấu hình `config.json` và hiển thị trên giao diện lọc.
> * **Xử lý nội dung nhiều dòng**: Toàn bộ văn bản bên dưới dòng `Nội dung:` sẽ được gom đầy đủ (bao gồm cả các ký tự xuống dòng) cho tới khi gặp prompt tiếp theo.

### 2. Các bước thực hiện
1. Trên giao diện Web app, nhìn vào panel **Thư viện Prompt** (cột 1) -> Chọn nút **`+ Nhập file`** (màu xanh lá).
2. Chọn tệp tin `.txt` chứa danh sách prompt của bạn.
3. Nhật ký hệ thống sẽ thông báo số lượng prompt đã import thành công, giao diện Thư viện Prompt và bộ lọc sẽ tự động làm mới để cập nhật dữ liệu.

---

## 🔄 Tự Động Cập Nhật Phần Mềm (Auto-Update)

Ứng dụng hỗ trợ kiểm tra và cập nhật tự động trực tiếp từ GitHub Releases:

1. **Hiển thị phiên bản**: Phiên bản hiện tại của phần mềm được hiển thị trên nút ở góc trên bên phải (ví dụ: `v2.2.4`).
2. **Kiểm tra tự động**: Mỗi khi mở ứng dụng, phần mềm sẽ tự động kiểm tra ngầm phiên bản mới trên GitHub Releases. Nếu phát hiện có phiên bản mới hơn trên GitHub, nút phiên bản sẽ tự động đổi màu và **nhấp nháy nhịp thở (`pulse-warn`)** để báo hiệu cho bạn.
3. **Quy trình cập nhật cài đè an toàn nâng cao**: 
   - Khi click vào nút phiên bản, một hộp thoại thông tin bản cập nhật mới sẽ hiển thị.
   - Nếu bạn chọn đồng ý, ứng dụng sẽ tải tệp tin cập nhật dạng `.zip` từ GitHub Releases về thư mục tạm, tự động giải nén và kích hoạt một tiến trình `updater.bat` chạy độc lập.
   - Tiến trình updater sẽ ghi đè toàn bộ các file mới vào thư mục hiện tại (ngoại trừ tệp `config.json` và `config.example.json` để **giữ lại nguyên vẹn cấu hình của bạn**), sau đó tự khởi động lại phiên bản mới và dọn dẹp các tệp tạm.

---

## ⚙️ Cấu Hình Hệ Thống (`config.json`)

Mẫu cấu hình cơ bản (các thông tin nhạy cảm đã được bỏ qua qua `.gitignore`):

```json
{
  "paths": {
    "inbox_dir": "inbox",
    "processed_dir": "processed",
    "drive_root_dir": "G:\\My Drive\\Ten_Thu_Muc_Chinh",
    "selected_drive_folder": ""
  },
  "pixel": {
    "adb_serial": "",
    "camera_dir": "/sdcard/DCIM/Camera",
    "connection_mode": "usb",
    "wifi_ip": ""
  },
  "openai": {
    "api_key": "sk-...",
    "export_dir": "C:\\Users\\datdt\\Downloads"
  },
  "content_categories": ["Shopee", "Facebook", "General"]
}
```

---

## 🔒 Quy Trình Bảo Vệ Tệp Tin (Chống Mất File)

Nhằm đảm bảo an toàn tuyệt đối cho dữ liệu ảnh và video sản phẩm, ứng dụng áp dụng quy trình xử lý 6 bước nghiêm ngặt:
1. **Định vị thời gian**: Ghi nhận mốc thời gian bắt đầu thao tác chụp/quay.
2. **Kéo tệp tạm**: Sao chép tệp tin mới nhất từ điện thoại vào thư mục tạm `inbox` on máy tính.
3. **Đồng bộ Drive**: Chép tệp tin sang thư mục Google Drive đích dưới định dạng tệp tạm thời `.part`.
4. **Xác minh dung lượng**: So sánh dung lượng byte của tệp tin đích và tệp tin gốc để đảm bảo quá trình đồng bộ hoàn tất 100%.
5. **Chốt tệp**: Đổi tên tệp tin tạm `.part` thành tên chính thức trên Google Drive.
6. **Giải phóng bộ nhớ**: Xóa tệp tin gốc trên điện thoại Pixel và tệp tạm trong thư mục `inbox`.

---

## 🛡️ Bảo Mật & Riêng Tư

Các tệp cấu hình chứa API key, token hoặc thông tin cá nhân được bỏ qua hoàn toàn thông qua `.gitignore` và không bao giờ được đẩy lên kho chứa công cộng:
- `.env`
- `config.json`
- `client_secret.json` / `token.json`
- Các thư mục dữ liệu cục bộ (`inbox/`, `processed/`, `logs/`)

---

**✍️ Người thực hiện / Author:** Danny DT
