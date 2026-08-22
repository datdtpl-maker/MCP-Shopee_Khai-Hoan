import unittest
import tempfile
import os
from pathlib import Path
from unittest.mock import patch

from shopee_sync.src import notion_sync
import web_app


def make_page(page_id, title, insight_count=5, media_url=""):
    rich_text = []
    for index in range(1, insight_count + 1):
        rich_text.extend(
            [
                {"type": "text", "text": {"content": f"{index}. Insight {index}:"}},
                {
                    "type": "mention",
                    "mention": {"type": "page", "page": {"id": f"{page_id}-insight-{index}"}},
                    "plain_text": f"Bài {index}",
                },
            ]
        )
    return {
        "id": page_id,
        "properties": {
            "Tên sản phẩm": {"title": [{"plain_text": title}]},
            "Bài viết": {"checkbox": False},
            "Content xong": {"checkbox": True},
            "Trạng thái xử lý": {"select": {"name": "Chờ đăng"}},
            "Insight Library": {"type": "rich_text", "rich_text": rich_text},
            "Media sản phẩm": {"type": "url", "url": media_url},
        },
    }


class ShopeeSyncProductTargetTest(unittest.TestCase):
    def test_sync_endpoint_uses_selected_local_product_folder_not_stale_export_dir(self):
        selected_folder = r"G:\My Drive\Hình ảnh Shopee\Clinoper – Clindamycin + Benzoyl Peroxide"
        stale_folder = r"G:\My Drive\Hình ảnh Shopee\Aldocont B Gel 15g"
        captured = {}

        class ImmediateThread:
            def __init__(self, target, args=(), **_kwargs):
                self.target = target
                self.args = args

            def start(self):
                self.target(*self.args)

        def fake_sync(**_kwargs):
            captured["export_dir"] = os.environ.get("BIGSELLER_EXPORT_DIR")
            return str(Path(selected_folder) / "bigseller_sync_test.xlsx"), ["Clinoper"]

        config = {
            "paths": {"drive_root_dir": r"G:\My Drive\Hình ảnh Shopee"},
            "openai": {"export_dir": stale_folder},
        }
        with (
            patch.object(web_app, "shopee_sync_active", False),
            patch.object(web_app, "load_config", return_value=config),
            patch.object(web_app.threading, "Thread", ImmediateThread),
            patch.object(notion_sync, "sync_notion_to_bigseller_excel", side_effect=fake_sync),
            patch.dict(os.environ, {}, clear=False),
        ):
            response = web_app.app.test_client().post(
                "/api/shopee/sync/run",
                json={"drive_url": selected_folder, "page_id": "clinoper-page"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured["export_dir"], selected_folder)

    def test_insight_folders_are_mapped_by_their_number(self):
        insights = [
            {"insight_name": f"Góc nội dung {index}", "page_id": f"page-{index}"}
            for index in range(1, 6)
        ]
        subfolders = {f"insight{index}": f"folder-{index}" for index in range(1, 6)}

        mapping = notion_sync.map_insights_to_drive_folders(insights, subfolders)

        self.assertEqual([item["folder_id"] for item in mapping], [f"folder-{index}" for index in range(1, 6)])

    def test_image_link_endpoint_targets_one_product_and_enables_replacement(self):
        with patch.object(web_app, "shopee_sync_active", False), patch.object(web_app.threading, "Thread") as thread:
            missing = web_app.app.test_client().post("/api/shopee/sync/links", json={"drive_url": ""})
            accepted = web_app.app.test_client().post(
                "/api/shopee/sync/links",
                json={"drive_url": "https://drive.google.com/drive/folders/aldocont", "page_id": "aldocont-page"},
            )

        self.assertEqual(missing.status_code, 400)
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(thread.call_args.kwargs["args"], (
            "https://drive.google.com/drive/folders/aldocont",
            "aldocont-page",
        ))

    def test_sync_endpoint_requires_and_forwards_selected_page_id(self):
        with patch.object(web_app, "shopee_sync_active", False), patch.object(web_app.threading, "Thread") as thread:
            missing = web_app.app.test_client().post("/api/shopee/sync/run", json={"drive_url": ""})
            accepted = web_app.app.test_client().post(
                "/api/shopee/sync/run",
                json={"drive_url": r"G:\My Drive\Hình ảnh Shopee\Clinoper", "page_id": "clinoper-page"},
            )

        self.assertEqual(missing.status_code, 400)
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(thread.call_args.kwargs["args"][1], "clinoper-page")

    def test_local_folder_match_accepts_product_folder_with_shorter_suffix(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            expected = root / "Aldocont B Gel 15g"
            expected.mkdir()
            (root / "Sản phẩm khác").mkdir()

            actual = notion_sync.find_local_product_folder(
                root,
                "Aldocont B Gel 15g – Adapalene 0.1% + Benzoyl Peroxide 2.5%",
            )

            self.assertEqual(actual, expected)

    def test_selected_page_id_excludes_other_eligible_products(self):
        clinoper = make_page("clinoper-page", "Clinoper")
        aldocont = make_page("aldocont-page", "Aldocont")

        selected = notion_sync.select_products_for_export(
            [clinoper, aldocont],
            target_page_id="clinoper-page",
            override_drive_url="",
        )

        self.assertEqual([page["id"] for page in selected], ["clinoper-page"])

    def test_selected_page_does_not_reuse_another_products_drive_url(self):
        clinoper = make_page("clinoper-page", "Clinoper")
        aldocont = make_page(
            "aldocont-page",
            "Aldocont",
            media_url="https://drive.google.com/drive/folders/aldocont-folder",
        )

        selected = notion_sync.select_products_for_export(
            [clinoper, aldocont],
            target_page_id="clinoper-page",
            override_drive_url="https://drive.google.com/drive/folders/clinoper-folder",
        )

        self.assertEqual([page["id"] for page in selected], ["clinoper-page"])

    def test_selected_product_must_have_exactly_five_insights(self):
        incomplete = make_page("clinoper-page", "Clinoper", insight_count=4)

        with self.assertRaisesRegex(ValueError, "đúng 5 Insight"):
            notion_sync.select_products_for_export(
                [incomplete],
                target_page_id="clinoper-page",
                override_drive_url="",
            )


if __name__ == "__main__":
    unittest.main()
