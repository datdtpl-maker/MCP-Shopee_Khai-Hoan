import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import web_app


class ScanInsightsTest(unittest.TestCase):
    def test_notion_fallback_populates_folder_label_content_and_keywords(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            product_dir = Path(temp_dir) / "Aldocont B Gel 15g"
            for order_num in range(1, 6):
                (product_dir / f"Insight {order_num}").mkdir(parents=True)

            notion_insights = [
                {
                    "page_id": f"page-{order_num}",
                    "order_num": order_num,
                    "display_name": f"Tên bài Insight {order_num}",
                    "post_title": f"Tên bài Insight {order_num}",
                    "angle": f"Góc viết {order_num}",
                    "notion_description": f"Nội dung Insight {order_num}",
                    "keywords": f"từ khóa {order_num}",
                }
                for order_num in range(1, 6)
            ]

            with patch.object(web_app, "load_notion_insights_for_product", return_value=notion_insights):
                response = web_app.app.test_client().post(
                    "/api/automation/scan-insights",
                    json={"export_dir": str(product_dir)},
                )

            self.assertEqual(response.status_code, 200)
            insights = response.get_json()["insights"]
            self.assertEqual(len(insights), 5)
            self.assertEqual(insights[0]["display_name"], "Tên bài Insight 1")
            self.assertEqual(insights[0]["notion_description"], "Nội dung Insight 1")
            self.assertEqual(insights[0]["keywords"], "từ khóa 1")
            self.assertEqual(insights[0]["data_source"], "notion")

    def test_local_json_remains_available_when_notion_is_offline(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            product_dir = Path(temp_dir) / "Sản phẩm Offline"
            (product_dir / "Insight 1").mkdir(parents=True)
            (product_dir / "insights_data.json").write_text(
                json.dumps(
                    {
                        "productDescription": "Mô tả sản phẩm dự phòng",
                        "insights": [
                            {
                                "angle": "Góc viết local",
                                "postTitle": "Tên bài local",
                                "insightContent": "Nội dung Insight local",
                                "keywords": "từ khóa local",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with patch.object(web_app, "load_notion_insights_for_product", return_value=[]):
                response = web_app.app.test_client().post(
                    "/api/automation/scan-insights",
                    json={"export_dir": str(product_dir)},
                )

            insight = response.get_json()["insights"][0]
            self.assertEqual(insight["display_name"], "Tên bài local")
            self.assertEqual(insight["notion_description"], "Nội dung Insight local")
            self.assertEqual(insight["keywords"], "từ khóa local")
            self.assertEqual(insight["data_source"], "local")


if __name__ == "__main__":
    unittest.main()
