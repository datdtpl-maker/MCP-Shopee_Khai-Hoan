import io
import unittest
from web_app import SafeStreamWrapper, enforce_safe_io


class TestStreamEncoding(unittest.TestCase):
    def test_cp1252_vietnamese_text_does_not_crash(self):
        buf = io.BytesIO()
        raw_stream = io.TextIOWrapper(buf, encoding="cp1252", errors="strict")
        wrapped = SafeStreamWrapper(raw_stream)

        # Characters that previously crashed in cp1252: \u0110 ('Đ'), \u1ec3 ('ể')
        test_text = "Đang khởi động cửa sổ Desktop ứng dụng Native...\nKhông thể khởi chạy pywebview\n"
        wrapped.write(test_text)
        wrapped.flush()

        result = buf.getvalue().decode("cp1252")
        self.assertIn("Desktop", result)

    def test_safe_stream_none_target_does_not_crash(self):
        wrapped = SafeStreamWrapper(None)
        wrapped.write("Khởi động ứng dụng")
        wrapped.flush()


if __name__ == "__main__":
    unittest.main()
