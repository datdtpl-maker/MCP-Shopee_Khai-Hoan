# BỘ 5 PROMPT TẠO HÌNH SHOPEE (CHATGPT / DALL-E) TRONG TOOL

Tài liệu tổng hợp 5 prompt mẫu chuẩn hóa cho quy trình tạo bộ ảnh sản phẩm sàn Thương mại Điện tử (Shopee) ngành Dược mỹ phẩm / Chăm sóc sức khỏe. Bộ prompt này được thiết kế để nạp vào ChatGPT kèm 2 ảnh đầu vào (Ảnh 1: Sản phẩm gốc, Ảnh 2: Ảnh mẫu tham khảo phong cách).

---

## 📌 CÁC BIẾN NẠP ĐỘNG (DYNAMIC PLACEHOLDERS)
Khi chạy tự động hóa, tool sẽ tự động thay thế các biến sau:
* `{{selected_notion_content}}`: Nội dung chi tiết bài viết và thông tin sản phẩm lấy từ Notion (công dụng, thành phần, đối tượng sử dụng, hướng dẫn).
* `{{selected_keywords}}`: Các từ khóa chính của góc nhìn / Insight đã chọn.
* `{{image_sample}}`: Ảnh mẫu tham khảo bố cục, ánh sáng và phong cách thiết kế.

---

## 1. PROMPT 1: ẢNH BÌA CHÍNH (COVER SHOPEE - 1.PNG)
* **Mục tiêu:** Tạo ảnh bìa chính (Cover) đại diện cho sản phẩm trên sàn, nổi bật nhận diện thương hiệu, thông điệp bán hàng cốt lõi và tỷ lệ click (CTR) cao.
* **Tên file xuất:** `1.png`

```text
Tạo ảnh Shopee tỷ lệ 1:1 cho sản phẩm.

Ảnh đầu vào:
- Ảnh 1 là ảnh sản phẩm gốc. Dùng sản phẩm trong ảnh này làm đối tượng chính.
- Ảnh 2 là ảnh mẫu tham khảo phong cách. Chỉ lấy cảm giác thiết kế, ánh sáng, màu nền, bố cục và hiệu ứng hình ảnh từ ảnh mẫu. (nếu có {{image_sample}} thì dùng làm tham khảo phong cách, nếu không có thì tự thiết kế theo hướng phù hợp với sản phẩm và nội dung)

Yêu cầu bắt buộc:
- Giữ nguyên bao bì, tên sản phẩm, logo, màu sắc, hình dáng và chữ trên sản phẩm gốc.
- Không làm méo sản phẩm.
- Không đổi tên sản phẩm.
- Không tự tạo thêm chữ sai trên bao bì.
- Không sao chép y nguyên ảnh mẫu.
- Không dùng lại logo, watermark, chữ hoặc sản phẩm trong ảnh mẫu.
- Không làm thay đổi nhận diện sản phẩm gốc.

Thông tin sản phẩm lấy từ Notion:
{{selected_notion_content}}

Từ khóa chính của insight:
{{selected_keywords}}

Nhiệm vụ:
- Dựa trên nội dung Notion và từ khóa chính, phân tích để xác định thông điệp nổi bật nhất của sản phẩm.
- Từ đó tự tạo nội dung text đặt trên ảnh gồm:
  - Title: ngắn gọn, nổi bật, mạnh, tối đa 6 từ.
  - Subtitle: làm rõ thêm lợi ích chính hoặc nhóm đối tượng, tối đa 12 từ.
  - Body: 2 đến 4 ý ngắn gọn, dễ đọc, mỗi ý tối đa 8 từ.
- Ưu tiên đưa từ khóa chính quan trọng nhất vào Title hoặc Subtitle.
- Body ưu tiên tóm tắt ngắn gọn thành phần nổi bật, công dụng hỗ trợ hoặc điểm nổi bật của sản phẩm.
- Nội dung text phải đúng chính tả tiếng Việt, dễ đọc, súc tích, rõ ràng và phù hợp ngữ cảnh bán hàng trên Shopee.
- Không viết đoạn văn dài.
- Không nhồi nhét quá nhiều chữ lên ảnh.

Ý tưởng hình ảnh cần thể hiện:
- Dựa trên nội dung Notion và từ khóa chính, tạo bối cảnh phù hợp với insight đã chọn.
- Hình ảnh cần truyền tải cảm giác chuyên nghiệp, sạch, đáng tin cậy, phù hợp đăng sàn Shopee cho ngành nhà thuốc, dược mỹ phẩm, chăm sóc da hoặc chăm sóc sức khỏe.
- Nếu nội dung nghiêng về dưỡng ẩm, làm dịu, phục hồi thì ưu tiên phong cách mềm, sáng, sạch, dịu mắt.
- Nếu nội dung nghiêng về mụn, da dầu, kiểm soát dầu thì ưu tiên phong cách sạch, hiện đại, rõ công dụng.
- Nếu nội dung nghiêng về sức khỏe, bổ sung vi chất, đề kháng thì ưu tiên phong cách nhà thuốc, uy tín, chuyên nghiệp.

Bố cục:
- Ảnh vuông 1:1.
- Sản phẩm đặt ở trung tâm hoặc lệch phải/lệch trái tùy bố cục hợp lý, rõ nét, nổi bật.
- Sản phẩm chiếm khoảng 40–55% khung hình.
- Có thể đặt sản phẩm trên bục tròn, nền trong suốt, nền nước, nền studio hoặc bối cảnh phù hợp với ảnh mẫu.
- Bố cục sạch, sáng, dễ nhìn trên điện thoại.
- Nền có chiều sâu, ánh sáng mềm, tạo cảm giác cao cấp và đáng tin cậy.
- Chừa vùng rõ ràng để đặt text, không để text chèn lên sản phẩm chính.

Thiết kế phần text:
- Text trên ảnh gồm 3 phần rõ ràng: Title, Subtitle, Body.
- Title là phần nổi bật nhất.
- Subtitle nhỏ hơn Title nhưng vẫn dễ đọc.
- Body là các ý ngắn hoặc bullet ngắn, bố trí gọn gàng.
- Sắp xếp text cân đối, không quá nhiều chữ, không rối mắt.
- Font sạch, hiện đại, dễ đọc, phù hợp ảnh thương mại điện tử.
- Màu chữ phải đủ tương phản với nền để dễ nhìn.
- Không để text che khuất sản phẩm.
- Có thể dùng icon nhỏ tinh tế nếu phù hợp với body, nhưng không lạm dụng.

Phong cách:
- Không sao chép y nguyên ảnh mẫu.
- Tông màu, ánh sáng và hiệu ứng phải phù hợp với sản phẩm và insight.
- Phong cách thương mại điện tử cao cấp, sạch, rõ sản phẩm.
- Ưu tiên cảm giác uy tín, gọn gàng, dễ đọc, dễ chốt mua trên Shopee.

Điều cấm:
- Không thêm claim điều trị quá mức.
- Không dùng chữ như: trị khỏi, chữa khỏi, cam kết hết, dứt điểm, khỏi hoàn toàn.
- Không thêm hình ảnh bệnh da nặng, hình ảnh gây sợ hoặc phản cảm.
- Không thêm người mẫu, bác sĩ, kim tiêm, bệnh viện nếu không được yêu cầu.
- Không biến sản phẩm thành thuốc điều trị bệnh quá đà.
- Không thêm logo lạ hoặc thương hiệu khác.
- Không viết sai chính tả.
- Không tạo phần text quá dài hoặc rối.

Kết quả mong muốn:
Một ảnh Shopee sạch, sáng, chuyên nghiệp, sản phẩm nổi bật, đúng tinh thần ảnh mẫu, phù hợp nội dung insight đã chọn, có sẵn Title, Subtitle và Body ngắn được tạo từ việc phân tích nội dung sản phẩm và từ khóa chính, sẵn sàng dùng làm ảnh thương mại điện tử.
```

---

## 2. PROMPT 2: THÀNH PHẦN NỔI BẬT (2.PNG)
* **Mục tiêu:** Nhấn mạnh 3-5 hoạt chất / thành phần chính khoa học, uy tín, tạo niềm tin về chất lượng sản phẩm.
* **Tên file xuất:** `2.png`

```text
Tạo ảnh Shopee tỷ lệ 1:1 cho sản phẩm.

Ảnh đầu vào:
- Ảnh 1 là ảnh sản phẩm gốc. Dùng sản phẩm trong ảnh này làm đối tượng chính.
- Ảnh 2 là ảnh mẫu tham khảo phong cách. Chỉ lấy cảm giác thiết kế, ánh sáng, màu nền, bố cục và hiệu ứng hình ảnh từ ảnh mẫu. (nếu có {{image_sample}} thì dùng làm tham khảo phong cách, nếu không có thì tự thiết kế theo hướng phù hợp với sản phẩm và nội dung)

Yêu cầu bắt buộc:
- Giữ nguyên bao bì, tên sản phẩm, logo, màu sắc, hình dáng và chữ trên sản phẩm gốc.
- Không làm méo sản phẩm.
- Không đổi tên sản phẩm.
- Không tự tạo thêm chữ sai trên bao bì.
- Không sao chép y nguyên ảnh mẫu.
- Không dùng lại logo, watermark, chữ hoặc sản phẩm trong ảnh mẫu.
- Không làm thay đổi nhận diện sản phẩm gốc.

Thông tin sản phẩm lấy từ Notion:
{{selected_notion_content}}

Từ khóa chính của insight:
{{selected_keywords}}

Nhiệm vụ:
- Tạo 1 hình phụ tập trung vào THÀNH PHẦN NỔI BẬT của sản phẩm.
- Dựa trên nội dung Notion và từ khóa chính, chọn ra 3 đến 5 thành phần nổi bật nhất.
- Với mỗi thành phần, tóm tắt ngắn gọn 1 lợi ích chính.
- Nội dung text trên ảnh gồm:
  - Title: ngắn gọn, nổi bật, tối đa 6 từ.
  - Subtitle: làm rõ nhóm thành phần hoặc điểm nổi bật, tối đa 12 từ.
  - Body: 3 đến 5 ý ngắn, mỗi ý gồm tên thành phần + lợi ích ngắn, tối đa 8 từ mỗi ý.
- Không viết dài dòng, không nhồi nhét quá nhiều chữ.
- Nội dung phải đúng chính tả, dễ đọc, súc tích, phù hợp ngữ cảnh bán hàng Shopee.

Ý tưởng hình ảnh cần thể hiện:
- Nhấn mạnh cảm giác sản phẩm có thành phần rõ ràng, đáng tin cậy, chuyên nghiệp.
- Nếu sản phẩm thiên về dưỡng ẩm, phục hồi, làm dịu: ưu tiên phong cách mềm, sạch, dịu mắt.
- Nếu sản phẩm thiên về mụn, dầu, làm sạch: ưu tiên phong cách hiện đại, rõ công dụng.
- Có thể gợi nhẹ yếu tố nguyên liệu, phân tử, giọt tinh chất, texture, lá, nước hoặc nền studio sạch tùy theo insight, nhưng không làm rối bố cục.

Bố cục:
- Ảnh vuông 1:1.
- Giữ đồng bộ phong cách với ảnh cover chính về màu sắc, ánh sáng, font chữ, bố cục và cảm giác thương mại điện tử cao cấp.
- Sản phẩm chiếm khoảng 35–50% khung hình.
- Chừa vùng rõ ràng để đặt text.
- Có thể đặt sản phẩm lệch trái hoặc lệch phải để dành không gian cho phần thành phần.
- Bố cục sạch, sáng, dễ nhìn trên điện thoại.

Thiết kế phần text:
- Text gồm 3 phần rõ ràng: Title, Subtitle, Body.
- Title là nổi bật nhất.
- Subtitle nhỏ hơn nhưng dễ đọc.
- Body trình bày gọn, có thể dùng bullet ngắn hoặc icon nhỏ tinh tế.
- Không để text che khuất sản phẩm.
- Font sạch, hiện đại, dễ đọc.
- Màu chữ tương phản tốt với nền.

Phong cách:
- Không sao chép y nguyên ảnh mẫu.
- Phong cách thương mại điện tử cao cấp, sạch, rõ sản phẩm.
- Ưu tiên cảm giác uy tín, khoa học, gọn gàng.

Điều cấm:
- Không thêm claim điều trị quá mức.
- Không dùng từ như trị khỏi, chữa khỏi, cam kết hết, dứt điểm, khỏi hoàn toàn.
- Không thêm người mẫu, bác sĩ, kim tiêm, bệnh viện nếu không được yêu cầu.
- Không thêm logo lạ hoặc thương hiệu khác.
- Không viết sai chính tả.
- Không biến phần thành phần thành đoạn văn dài.

Kết quả mong muốn:
Một ảnh Shopee hình phụ về THÀNH PHẦN NỔI BẬT, sạch, sáng, chuyên nghiệp, sản phẩm nổi bật, text ngắn gọn dễ đọc, sẵn sàng dùng cho thương mại điện tử.
```

---

## 3. PROMPT 3: CÔNG DỤNG CHÍNH (3.PNG)
* **Mục tiêu:** Thể hiện 3-4 công dụng và lợi ích giải quyết nỗi đau của khách hàng một cách trực quan, tuân thủ chính sách Shopee.
* **Tên file xuất:** `3.png`

```text
Tạo ảnh Shopee tỷ lệ 1:1 cho sản phẩm.

Ảnh đầu vào:
- Ảnh 1 là ảnh sản phẩm gốc. Dùng sản phẩm trong ảnh này làm đối tượng chính.
- Ảnh 2 là ảnh mẫu tham khảo phong cách. Chỉ lấy cảm giác thiết kế, ánh sáng, màu nền, bố cục và hiệu ứng hình ảnh từ ảnh mẫu. (nếu có {{image_sample}} thì dùng làm tham khảo phong cách, nếu không có thì tự thiết kế theo hướng phù hợp với sản phẩm và nội dung)

Yêu cầu bắt buộc:
- Giữ nguyên bao bì, tên sản phẩm, logo, màu sắc, hình dáng và chữ trên sản phẩm gốc.
- Không làm méo sản phẩm.
- Không đổi tên sản phẩm.
- Không tự tạo thêm chữ sai trên bao bì.
- Không sao chép y nguyên ảnh mẫu.
- Không dùng lại logo, watermark, chữ hoặc sản phẩm trong ảnh mẫu.
- Không làm thay đổi nhận diện sản phẩm gốc.

Thông tin sản phẩm lấy từ Notion:
{{selected_notion_content}}

Từ khóa chính của insight:
{{selected_keywords}}

Nhiệm vụ:
- Tạo 1 hình phụ tập trung vào CÔNG DỤNG CHÍNH của sản phẩm.
- Dựa trên nội dung Notion và từ khóa chính, xác định 3 đến 4 công dụng nổi bật nhất.
- Nội dung text trên ảnh gồm:
  - Title: ngắn gọn, mạnh, tối đa 6 từ.
  - Subtitle: làm rõ lợi ích chính hoặc nhóm đối tượng, tối đa 12 từ.
  - Body: 3 đến 4 ý ngắn gọn về công dụng, mỗi ý tối đa 8 từ.
- Ưu tiên đưa từ khóa chính quan trọng nhất vào Title hoặc Subtitle.
- Ngôn ngữ sử dụng phải an toàn, dùng các từ như: hỗ trợ, giúp, góp phần, phù hợp.
- Không viết đoạn văn dài.
- Không nhồi nhét quá nhiều chữ.

Ý tưởng hình ảnh cần thể hiện:
- Hình ảnh cần làm rõ lợi ích chính của sản phẩm một cách trực quan, sạch và đáng tin cậy.
- Nếu insight thiên về dưỡng ẩm, làm dịu, phục hồi: phong cách sáng, mềm, dịu mắt.
- Nếu insight thiên về mụn, dầu, làm sạch: phong cách hiện đại, rõ ràng, sắc nét.
- Nếu insight thiên về sức khỏe, bổ sung: phong cách nhà thuốc, chuyên nghiệp, uy tín.

Bố cục:
- Ảnh vuông 1:1.
- Giữ đồng bộ phong cách với ảnh cover chính về màu sắc, ánh sáng, font chữ, bố cục và cảm giác thương mại điện tử cao cấp.
- Sản phẩm chiếm khoảng 35–50% khung hình.
- Chừa vùng rõ ràng để đặt text.
- Bố cục sạch, sáng, dễ nhìn trên điện thoại.

Thiết kế phần text:
- Text gồm 3 phần rõ ràng: Title, Subtitle, Body.
- Title nổi bật nhất.
- Subtitle nhỏ hơn nhưng vẫn dễ đọc.
- Body là các bullet ngắn, rõ ràng, dễ lướt đọc.
- Có thể dùng icon nhỏ tinh tế nếu phù hợp.
- Không để text che khuất sản phẩm.
- Font sạch, hiện đại, phù hợp ảnh thương mại điện tử.

Phong cách:
- Không sao chép y nguyên ảnh mẫu.
- Tông màu và ánh sáng phù hợp với insight công dụng.
- Phong cách thương mại điện tử cao cấp, sạch, đáng tin cậy.

Điều cấm:
- Không thêm claim điều trị quá mức.
- Không dùng từ như trị khỏi, chữa khỏi, cam kết hết, dứt điểm, khỏi hoàn toàn.
- Không tạo cảm giác sản phẩm là thuốc điều trị quá đà.
- Không thêm hình ảnh gây sợ hoặc phản cảm.
- Không thêm logo lạ hoặc thương hiệu khác.
- Không viết sai chính tả.

Kết quả mong muốn:
Một ảnh Shopee hình phụ về CÔNG DỤNG CHÍNH, sạch, sáng, chuyên nghiệp, làm rõ lợi ích sản phẩm, text ngắn gọn dễ đọc, sẵn sàng dùng làm ảnh thương mại điện tử.
```

---

## 4. PROMPT 4: HƯỚNG DẪN CÁCH DÙNG (4.PNG)
* **Mục tiêu:** Tóm tắt quy trình sử dụng 3 bước ngắn gọn, rõ ràng, dễ áp dụng vào routine hàng ngày của khách hàng.
* **Tên file xuất:** `4.png`

```text
Tạo ảnh Shopee tỷ lệ 1:1 cho sản phẩm.

Ảnh đầu vào:
- Ảnh 1 là ảnh sản phẩm gốc. Dùng sản phẩm trong ảnh này làm đối tượng chính.
- Ảnh 2 là ảnh mẫu tham khảo phong cách. Chỉ lấy cảm giác thiết kế, ánh sáng, màu nền, bố cục và hiệu ứng hình ảnh từ ảnh mẫu. (nếu có {{image_sample}} thì dùng làm tham khảo phong cách, nếu không có thì tự thiết kế theo hướng phù hợp với sản phẩm và nội dung)

Yêu cầu bắt buộc:
- Giữ nguyên bao bì, tên sản phẩm, logo, màu sắc, hình dáng và chữ trên sản phẩm gốc.
- Không làm méo sản phẩm.
- Không đổi tên sản phẩm.
- Không tự tạo thêm chữ sai trên bao bì.
- Không sao chép y nguyên ảnh mẫu.
- Không dùng lại logo, watermark, chữ hoặc sản phẩm trong ảnh mẫu.
- Không làm thay đổi nhận diện sản phẩm gốc.

Thông tin sản phẩm lấy từ Notion:
{{selected_notion_content}}

Từ khóa chính của insight:
{{selected_keywords}}

Nhiệm vụ:
- Tạo 1 hình phụ tập trung vào CÁCH DÙNG sản phẩm.
- Dựa trên nội dung Notion, tóm tắt cách dùng thành 3 bước ngắn gọn, rõ ràng, dễ hiểu.
- Nếu có thông tin về thời điểm dùng, tần suất dùng hoặc lưu ý cơ bản thì tóm tắt ngắn trên ảnh.
- Nội dung text trên ảnh gồm:
  - Title: ngắn gọn, tối đa 6 từ.
  - Subtitle: làm rõ cách dùng hoặc đối tượng phù hợp, tối đa 12 từ.
  - Body: 3 bước ngắn gọn, mỗi bước tối đa 8 từ.
- Có thể thêm 1 dòng lưu ý rất ngắn nếu cần.
- Nội dung đúng chính tả, súc tích, dễ đọc trên điện thoại.

Ý tưởng hình ảnh cần thể hiện:
- Hình ảnh cần tạo cảm giác dễ hiểu, dễ dùng, chuyên nghiệp, đáng tin cậy.
- Có thể dùng bố cục theo bước 1, bước 2, bước 3.
- Có thể dùng icon nhỏ minh họa dạng bước hoặc ký hiệu đơn giản, tinh tế.
- Không làm bố cục quá phức tạp.

Bố cục:
- Ảnh vuông 1:1.
- Giữ đồng bộ phong cách với ảnh cover chính về màu sắc, ánh sáng, font chữ, bố cục và cảm giác thương mại điện tử cao cấp.
- Sản phẩm chiếm khoảng 30–45% khung hình để có đủ chỗ cho phần hướng dẫn.
- Chừa vùng rõ ràng để đặt text.
- Bố cục sạch, sáng, rõ ràng, dễ nhìn trên điện thoại.

Thiết kế phần text:
- Text gồm 3 phần rõ ràng: Title, Subtitle, Body.
- Body trình bày dạng 3 bước.
- Title nổi bật nhất.
- Subtitle nhỏ hơn nhưng vẫn rõ.
- Không để text che khuất sản phẩm.
- Font sạch, hiện đại, dễ đọc.
- Màu chữ đủ tương phản.

Phong cách:
- Không sao chép y nguyên ảnh mẫu.
- Phong cách thương mại điện tử cao cấp, sạch, dễ đọc, dễ hiểu.
- Ưu tiên cảm giác hướng dẫn rõ ràng và uy tín.

Điều cấm:
- Không viết cách dùng sai so với nội dung Notion.
- Không tạo quá nhiều bước.
- Không viết dài dòng.
- Không thêm claim điều trị quá mức.
- Không thêm logo lạ hoặc thương hiệu khác.
- Không viết sai chính tả.

Kết quả mong muốn:
Một ảnh Shopee hình phụ về CÁCH DÙNG, sạch, sáng, dễ hiểu, bố cục rõ ràng, text ngắn gọn, sẵn sàng dùng cho thương mại điện tử.
```

---

## 5. PROMPT 5: ĐIỂM TIN CẬY & FEEDBACK / PROOF (5.PNG)
* **Mục tiêu:** Thể hiện bằng chứng xã hội (Social Proof), nguồn gốc xuất xứ chính hãng, tư vấn chuyên môn dược sĩ giúp chốt đơn nhanh.
* **Tên file xuất:** `5.png`

```text
Tạo ảnh Shopee tỷ lệ 1:1 cho sản phẩm.

Ảnh đầu vào:
- Ảnh 1 là ảnh sản phẩm gốc. Dùng sản phẩm trong ảnh này làm đối tượng chính.
- Ảnh 2 là ảnh mẫu tham khảo phong cách. Chỉ lấy cảm giác thiết kế, ánh sáng, màu nền, bố cục và hiệu ứng hình ảnh từ ảnh mẫu. (nếu có {{image_sample}} thì dùng làm tham khảo phong cách, nếu không có thì tự thiết kế theo hướng phù hợp với sản phẩm và nội dung)

Yêu cầu bắt buộc:
- Giữ nguyên bao bì, tên sản phẩm, logo, màu sắc, hình dáng và chữ trên sản phẩm gốc.
- Không làm méo sản phẩm.
- Không đổi tên sản phẩm.
- Không tự tạo thêm chữ sai trên bao bì.
- Không sao chép y nguyên ảnh mẫu.
- Không dùng lại logo, watermark, chữ hoặc sản phẩm trong ảnh mẫu.
- Không làm thay đổi nhận diện sản phẩm gốc.

Thông tin sản phẩm lấy từ Notion:
{{selected_notion_content}}

Từ khóa chính của insight:
{{selected_keywords}}

Nhiệm vụ:
- Tạo 1 hình phụ tập trung vào FEEDBACK hoặc PROOF của sản phẩm.
- Nếu Notion có feedback thật, đánh giá thật hoặc nội dung proof thật thì tóm tắt lại theo cách ngắn gọn, rõ ràng, dễ đọc.
- Nếu Notion không có feedback thật, hãy chuyển sang dạng PROOF hoặc ĐIỂM TIN CẬY của sản phẩm, ví dụ: nguồn gốc rõ ràng, phù hợp routine chăm sóc, được nhiều người lựa chọn, tư vấn tại nhà thuốc hoặc chuyên gia.
- Không tự tạo feedback giả, không bịa review.
- Nội dung text trên ảnh gồm:
  - Title: ngắn gọn, tối đa 6 từ.
  - Subtitle: làm rõ yếu tố tin cậy hoặc trải nghiệm, tối đa 12 từ.
  - Body: 2 đến 4 ý ngắn gọn, mỗi ý tối đa 8 từ.
- Nội dung phải đúng chính tả, súc tích, phù hợp bối cảnh bán hàng Shopee.

Ý tưởng hình ảnh cần thể hiện:
- Hình ảnh cần tạo cảm giác tin cậy, uy tín, chuyên nghiệp.
- Có thể dùng bố cục dạng review card, khối quote ngắn, biểu tượng sao hoặc điểm nhấn proof tinh tế nếu phù hợp.
- Không làm theo kiểu sàn giả, không mô phỏng feedback rối mắt.
- Không làm quá nhiều chữ.

Bố cục:
- Ảnh vuông 1:1.
- Giữ đồng bộ phong cách với ảnh cover chính về màu sắc, ánh sáng, font chữ, bố cục và cảm giác thương mại điện tử cao cấp.
- Sản phẩm chiếm khoảng 30–45% khung hình.
- Chừa vùng rõ ràng để đặt phần feedback hoặc proof.
- Bố cục sạch, sáng, rõ ràng, dễ nhìn trên điện thoại.

Thiết kế phần text:
- Text gồm 3 phần rõ ràng: Title, Subtitle, Body.
- Title nổi bật nhất.
- Subtitle dễ đọc.
- Body ngắn gọn, có thể trình bày dạng bullet hoặc card nhỏ.
- Không để text che khuất sản phẩm.
- Font sạch, hiện đại, dễ đọc.
- Màu chữ đủ tương phản.

Phong cách:
- Không sao chép y nguyên ảnh mẫu.
- Phong cách thương mại điện tử cao cấp, sạch, đáng tin cậy.
- Ưu tiên cảm giác uy tín, rõ ràng, hỗ trợ chốt mua.

Điều cấm:
- Không tự tạo feedback giả.
- Không thêm claim điều trị quá mức.
- Không dùng từ như trị khỏi, chữa khỏi, cam kết hết, dứt điểm, khỏi hoàn toàn.
- Không thêm logo lạ hoặc thương hiệu khác.
- Không viết sai chính tả.
- Không làm bố cục rối mắt như ảnh chụp màn hình chồng chéo.

Kết quả mong muốn:
Một ảnh Shopee hình phụ về FEEDBACK hoặc PROOF, sạch, sáng, chuyên nghiệp, tạo cảm giác tin cậy, text ngắn gọn dễ đọc, sẵn sàng dùng cho thương mại điện tử.
```
