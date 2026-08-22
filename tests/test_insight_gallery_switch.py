import threading
import unittest
from pathlib import Path

from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server

import web_app


EDGE_PATH = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")


@unittest.skipUnless(EDGE_PATH.exists(), "Microsoft Edge is required for this Windows UI regression test")
class InsightGallerySwitchTest(unittest.TestCase):
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

    def test_switching_insight_refreshes_gallery_and_ignores_stale_response(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True,
                executable_path=str(EDGE_PATH),
            )
            page = browser.new_page()
            page.goto(
                f"http://127.0.0.1:{self.port}/",
                wait_until="domcontentloaded",
                timeout=10_000,
            )
            page.evaluate("showPosterDashboard()")
            page.locator("#posterExportDir").fill(r"D:\San pham")
            page.evaluate("""
                state.scannedInsights = [
                    {folder_name: "Insight 1"},
                    {folder_name: "Insight 2"}
                ];
                const select = document.getElementById("insightFolderSelect");
                select.replaceChildren(
                    new Option("Insight 1", "0"),
                    new Option("Insight 2", "1")
                );
                const realFetch = window.fetch.bind(window);
                window.fetch = (url, options) => {
                    const urlText = String(url);
                    if (!urlText.includes("/api/automation/images/list")) {
                        return realFetch(url, options);
                    }
                    const isInsight1 = decodeURIComponent(urlText).includes("Insight 1");
                    const name = isInsight1 ? "slow-insight1.png" : "fast-insight2.png";
                    const delay = isInsight1 ? 500 : 20;
                    return new Promise(resolve => setTimeout(() => resolve({
                        json: async () => [{
                            name,
                            url: "/missing.png",
                            file_path: "D:/" + name,
                            time: "now"
                        }]
                    }), delay));
                };
            """)

            page.locator("#insightFolderSelect").select_option("0")
            page.wait_for_timeout(50)
            page.locator("#insightFolderSelect").select_option("1")
            page.wait_for_timeout(700)

            gallery_text = page.locator("#downloadedImagesList").inner_text()
            self.assertIn("fast-insight2.png", gallery_text)
            self.assertNotIn("slow-insight1.png", gallery_text)
            browser.close()


if __name__ == "__main__":
    unittest.main()
