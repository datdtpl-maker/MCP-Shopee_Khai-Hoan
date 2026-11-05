import unittest
from shopee_sync.src.notion_sync import extract_selling_price_from_note

class PriceExtractionTest(unittest.TestCase):
    def test_selling_price_formats(self):
        cases = [
            ("Giá bán: 450.000₫/biến thể. Giá vốn: 190.000₫/biến thể.", 450000),
            ("Giá vốn: 190.000₫/biến thể. Giá bán: 450.000₫/biến thể.", 450000),
            ("Giá bán: 450.000. Giá vốn: 190.000", 450000),
            ("Giá bán: 450000. Giá vốn: 190000", 450000),
            ("Giá bán: 450k. Giá vốn: 190k", 450000),
            ("Giá bán : 450,000 đ", 450000),
            ("Giá bán: 450.000", 450000),
            ("Giá bán: 450000", 450000),
            ("Giá bán: 1.250.000đ", 1250000),
            ("Gia ban: 250000", 250000),
            ("Giá bán - 350.000", 350000),
            ("Giá bán = 500.000 vnđ", 500000),
            ("", None),
            ("Chưa có ghi chú", None)
        ]
        for note, expected in cases:
            with self.subTest(note=note):
                self.assertEqual(extract_selling_price_from_note(note), expected)

if __name__ == "__main__":
    unittest.main()
