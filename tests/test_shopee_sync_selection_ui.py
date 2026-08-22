import threading
import unittest
from pathlib import Path

from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server

import web_app


EDGE_PATH = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")


@unittest.skipUnless(EDGE_PATH.exists(), "Microsoft Edge is required for this Windows UI regression test")
class ShopeeSyncSelectionUiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server("127.0.0.1", 0, web_app.app, threaded=True)
        cls.port = cls.server.server_port
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server_thread.join(timeout=5)

    def test_sync_now_sends_selected_product_page_id(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, executable_path=str(EDGE_PATH))
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{self.port}/", wait_until="domcontentloaded", timeout=10_000)
            page.evaluate(
                """
                const select = document.getElementById("shopeePendingProducts");
                select.replaceChildren(
                    new Option("Clinoper", "clinoper-page"),
                    new Option("Aldocont", "aldocont-page")
                );
                select.value = "clinoper-page";
                document.getElementById("productPageId").value = "clinoper-page";
                document.getElementById("shopeeSyncDriveUrl").value = "G:\\\\My Drive\\\\Hình ảnh Shopee\\\\Clinoper";
                window.__syncPayload = null;
                api = async (url, payload) => {
                    if (url === "/api/shopee/sync/run") {
                        window.__syncPayload = payload;
                        return {message: "ok"};
                    }
                    return {};
                };
                startPoll = () => {};
                """
            )

            page.evaluate("runShopeeSync()")
            page.wait_for_function("window.__syncPayload !== null")
            payload = page.evaluate("window.__syncPayload")

            self.assertEqual(payload["page_id"], "clinoper-page")
            self.assertIn("Clinoper", payload["drive_url"])
            browser.close()

    def test_sync_image_links_sends_selected_product_page_id(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, executable_path=str(EDGE_PATH))
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{self.port}/", wait_until="domcontentloaded", timeout=10_000)
            page.evaluate(
                """
                document.getElementById("productPageId").value = "aldocont-page";
                document.getElementById("shopeeSyncDriveUrl").value = "https://drive.google.com/drive/folders/aldocont";
                window.__linkPayload = null;
                api = async (url, payload) => {
                    if (url === "/api/shopee/sync/links") {
                        window.__linkPayload = payload;
                        return {message: "ok"};
                    }
                    return {};
                };
                startPoll = () => {};
                """
            )

            page.evaluate("syncNotionImageLinks()")
            page.wait_for_function("window.__linkPayload !== null")
            payload = page.evaluate("window.__linkPayload")

            self.assertEqual(payload["page_id"], "aldocont-page")
            browser.close()

    def test_fast_product_switch_keeps_latest_product_and_folder(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, executable_path=str(EDGE_PATH))
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{self.port}/", wait_until="domcontentloaded", timeout=10_000)
            page.evaluate(
                """
                const select = document.getElementById("shopeePendingProducts");
                select.replaceChildren(
                    new Option("Clinoper", "clinoper-page"),
                    new Option("Aldocont", "aldocont-page")
                );
                const realApi = api;
                api = async (url, payload) => {
                    if (!String(url).includes("/api/shopee/product/details")) return realApi(url, payload);
                    const isClinoper = String(url).includes("clinoper-page");
                    await new Promise(resolve => setTimeout(resolve, isClinoper ? 300 : 20));
                    return {
                        id: isClinoper ? "clinoper-page" : "aldocont-page",
                        title: isClinoper ? "Clinoper" : "Aldocont",
                        selected_folder_path: isClinoper ? "G:\\\\Clinoper" : "G:\\\\Aldocont"
                    };
                };
                select.value = "clinoper-page";
                onSelectPendingProduct("clinoper-page");
                select.value = "aldocont-page";
                onSelectPendingProduct("aldocont-page");
                """
            )
            page.wait_for_timeout(450)

            self.assertEqual(page.locator("#productPageId").input_value(), "aldocont-page")
            self.assertEqual(page.locator("#productNameInput").input_value(), "Aldocont")
            self.assertIn("Aldocont", page.locator("#shopeeSyncDriveUrl").input_value())
            browser.close()


if __name__ == "__main__":
    unittest.main()
