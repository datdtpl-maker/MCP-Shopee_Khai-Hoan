"""Unit and integration tests for ChatGPT image capture & completion guard in MCP Shopee.

Covers all required test conditions specified in GEMINI_CHATGPT_IMAGE_CAPTURE_HANDOFF.md.
"""

from __future__ import annotations

import base64
import struct
import tempfile
import unittest
import zlib
from pathlib import Path
from playwright.sync_api import sync_playwright

from shopee_sync.src.chatgpt_capture import (
    normalize_text,
    find_chatgpt_editor,
    fill_chatgpt_prompt,
    init_chatgpt_image_tracker,
    poll_chatgpt_image,
    save_chatgpt_image_atomic,
)


def make_png_bytes(w: int = 256, h: int = 256, color: tuple[int, int, int, int] = (255, 0, 0, 255)) -> bytes:
    """Generates a minimal valid RGBA PNG binary."""
    raw = bytearray()
    row = bytes([0]) + bytes(color) * w
    raw = row * h
    compressed = zlib.compress(raw)
    png = bytearray(b"\x89PNG\r\n\x1a\n")
    ihdr_data = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)
    png += struct.pack(">I", len(ihdr_data)) + b"IHDR" + ihdr_data + struct.pack(">I", zlib.crc32(b"IHDR" + ihdr_data))
    png += struct.pack(">I", len(compressed)) + b"IDAT" + compressed + struct.pack(">I", zlib.crc32(b"IDAT" + compressed))
    png += struct.pack(">I", 0) + b"IEND" + struct.pack(">I", zlib.crc32(b"IEND"))
    return bytes(png)


def make_png_data_url(w: int = 256, h: int = 256, color: tuple[int, int, int, int] = (255, 0, 0, 255)) -> str:
    """Returns a data URL for a valid RGBA PNG."""
    raw = make_png_bytes(w, h, color)
    return "data:image/png;base64," + base64.b64encode(raw).decode("ascii")


class TestChatGPTCapture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.page = self.browser.new_page()

    def tearDown(self):
        self.page.close()

    def test_normalize_text(self):
        self.assertEqual(normalize_text("  chào   bạn \n thế giới  "), "chào bạn thế giới")
        self.assertEqual(normalize_text(None), "")
        self.assertEqual(normalize_text(""), "")

    def test_save_chatgpt_image_atomic_success(self):
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / "1.png"
            data_url = make_png_data_url(300, 300, (0, 255, 0, 255))
            result = save_chatgpt_image_atomic(data_url, dest)
            self.assertEqual(result, str(dest))
            self.assertTrue(dest.exists())
            self.assertGreater(dest.stat().st_size, 0)
            # Ensure no leftover .part file
            self.assertFalse(dest.with_name("1.png.part").exists())

    def test_save_chatgpt_image_atomic_reject_small(self):
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / "1.png"
            small_data_url = make_png_data_url(100, 100)
            with self.assertRaises(ValueError) as ctx:
                save_chatgpt_image_atomic(small_data_url, dest)
            self.assertIn("quá nhỏ", str(ctx.exception).lower())
            self.assertFalse(dest.exists())

    def test_save_chatgpt_image_atomic_reject_invalid_header(self):
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / "1.png"
            fake_url = "data:image/png;base64," + base64.b64encode(b"NOT_A_VALID_PNG").decode("ascii")
            with self.assertRaises(ValueError) as ctx:
                save_chatgpt_image_atomic(fake_url, dest)
            self.assertIn("png hợp lệ", str(ctx.exception).lower())
            self.assertFalse(dest.exists())

    def test_poll_blocks_canvas_and_loading_text(self):
        """Creating image 31% + canvas: Must wait, never accept canvas, never save early."""
        prompt = "Vẽ ảnh sản phẩm Oximin"
        html = f"""
        <html>
        <body>
          <main>
            <div data-testid="conversation-turn-2">
              <h4>You said:</h4>
              <div data-user-message-bubble="true">{prompt}</div>
            </div>
            <div data-testid="conversation-turn-3">
              <h4>ChatGPT said:</h4>
              <div>
                <canvas width="512" height="512" style="width: 512px; height: 512px;"></canvas>
                <div>Creating image 31%</div>
                <button data-testid="stop-button">Stop</button>
              </div>
            </div>
          </main>
        </body>
        </html>
        """
        self.page.set_content(html)
        tracker = init_chatgpt_image_tracker(self.page, prompt)
        # We need tracker to record baseline BEFORE the request turn, so let's simulate tracker initialized prior
        tracker["previousMatchingPrompts"] = 0

        res = poll_chatgpt_image(self.page, tracker, prompt)
        self.assertNotEqual(res.get("phase"), "image-ready")
        self.assertEqual(res.get("phase"), "awaiting-image")
        self.assertTrue(res.get("busy"))

    def test_poll_rejects_canvas_even_with_edit_and_share_buttons(self):
        """A canvas element with Edit and Share buttons MUST still be rejected (canvas is never a result)."""
        prompt = "Tạo logo thương hiệu"
        html = f"""
        <html>
        <body>
          <main>
            <div>
              <h4>You said:</h4>
              <div data-user-message-bubble="true">{prompt}</div>
            </div>
            <div>
              <h4>ChatGPT said:</h4>
              <div data-testid="generated-image-gallery">
                <div>
                  <canvas width="512" height="512"></canvas>
                  <button aria-label="Edit generated image">Edit</button>
                  <button aria-label="Download generated image">Download</button>
                </div>
              </div>
            </div>
          </main>
        </body>
        </html>
        """
        self.page.set_content(html)
        tracker = {"documentId": "doc_test", "baselineSources": [], "previousMatchingPrompts": 0}
        self.page.evaluate("() => { window.__mcpImageTurnIdentity = { documentId: 'doc_test' }; }")

        res = poll_chatgpt_image(self.page, tracker, prompt)
        self.assertNotEqual(res.get("phase"), "image-ready")
        self.assertEqual(res.get("phase"), "awaiting-image")

    def test_poll_blocks_when_stop_button_active(self):
        """IMG preview loaded, but stop button is still visible -> Must wait, never save early."""
        prompt = "Thiết kế bao bì dược phẩm"
        png_url = make_png_data_url(300, 300)
        html = f"""
        <html>
        <body>
          <main>
            <div>
              <h4>You said:</h4>
              <div data-user-message-bubble="true">{prompt}</div>
            </div>
            <div>
              <h4>ChatGPT said:</h4>
              <div data-testid="generated-image-gallery">
                <div>
                  <img src="{png_url}" width="300" height="300" alt="Generated image" />
                  <button aria-label="Edit generated image">Edit</button>
                  <button aria-label="Download generated image">Download</button>
                </div>
              </div>
              <button data-testid="stop-button">Dừng tạo</button>
            </div>
          </main>
        </body>
        </html>
        """
        self.page.set_content(html)
        tracker = {"documentId": "doc_test", "baselineSources": [], "previousMatchingPrompts": 0}
        self.page.evaluate("() => { window.__mcpImageTurnIdentity = { documentId: 'doc_test' }; }")

        res = poll_chatgpt_image(self.page, tracker, prompt)
        self.assertNotEqual(res.get("phase"), "image-ready")
        self.assertTrue(res.get("busy"))

    def test_poll_blocks_when_first_stop_hidden_and_second_stop_visible(self):
        """When an older stop button is hidden (display: none) but a newer stop button is visible -> must wait."""
        prompt = "Vẽ mẫu banner"
        png_url = make_png_data_url(300, 300)
        html = f"""
        <html>
        <body>
          <main>
            <div>
              <h4>You said:</h4>
              <div data-user-message-bubble="true">{prompt}</div>
            </div>
            <div>
              <h4>ChatGPT said:</h4>
              <button data-testid="stop-button" style="display: none;">Stop</button>
              <div data-testid="generated-image-gallery">
                <div>
                  <img src="{png_url}" width="300" height="300" alt="Generated image" />
                  <button aria-label="Edit generated image">Edit</button>
                  <button aria-label="Download generated image">Download</button>
                </div>
              </div>
              <button data-testid="stop-button">Stop streaming</button>
            </div>
          </main>
        </body>
        </html>
        """
        self.page.set_content(html)
        tracker = {"documentId": "doc_test", "baselineSources": [], "previousMatchingPrompts": 0}
        self.page.evaluate("() => { window.__mcpImageTurnIdentity = { documentId: 'doc_test' }; }")

        res = poll_chatgpt_image(self.page, tracker, prompt)
        self.assertNotEqual(res.get("phase"), "image-ready")
        self.assertTrue(res.get("busy"))

    def test_poll_blocks_when_card_missing_completion_proof(self):
        """IMG >= 256x256 exists, but card lacks Edit and/or Share button -> Must wait."""
        prompt = "Tạo ảnh sản phẩm Oximin"
        png_url = make_png_data_url(300, 300)
        # Missing Download / Share button
        html = f"""
        <html>
        <body>
          <main>
            <div>
              <h4>You said:</h4>
              <div data-user-message-bubble="true">{prompt}</div>
            </div>
            <div>
              <h4>ChatGPT said:</h4>
              <div data-testid="generated-image-gallery">
                <div>
                  <img src="{png_url}" width="300" height="300" alt="Generated image" />
                  <button aria-label="Edit generated image">Edit</button>
                </div>
              </div>
            </div>
          </main>
        </body>
        </html>
        """
        self.page.set_content(html)
        tracker = {"documentId": "doc_test", "baselineSources": [], "previousMatchingPrompts": 0}
        self.page.evaluate("() => { window.__mcpImageTurnIdentity = { documentId: 'doc_test' }; }")

        res = poll_chatgpt_image(self.page, tracker, prompt)
        self.assertNotEqual(res.get("phase"), "image-ready")
        self.assertEqual(res.get("phase"), "awaiting-image")

    def test_poll_succeeds_with_search_turn_layout_and_display_contents(self):
        """Layout with data-content-search-turn-key, display: contents, h4, Edit + Download."""
        prompt = "Vẽ ảnh sản phẩm thực tế Oximin hộp 30 viên"
        png_url = make_png_data_url(400, 400, (10, 200, 50, 255))
        html = f"""
        <html>
        <body>
          <main>
            <div data-content-search-turn-key="turn-abc">
              <div style="display: contents;">
                <h4>You said:</h4>
                <div data-chatgpt-search-unit-key="turn-abc:0:user" data-chatgpt-search-message-ids="msg-user-1">
                  <div data-user-message-bubble="true">{prompt}</div>
                </div>
              </div>
              <div style="display: contents;">
                <h4 data-conversation-role="assistant">ChatGPT said:</h4>
                <div data-chatgpt-search-message-ids="msg-assistant-1">
                  <div data-testid="generated-image-gallery">
                    <div>
                      <button data-testid="generated-image-preview">
                        <img src="{png_url}" width="400" height="400" alt="Generated image 1" />
                      </button>
                      <button aria-label="Edit generated image 1">Chỉnh sửa</button>
                      <button aria-label="Download generated image 1">Tải xuống</button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </main>
        </body>
        </html>
        """
        self.page.set_content(html)
        tracker = {"documentId": "doc_test", "baselineSources": [], "previousMatchingPrompts": 0}
        self.page.evaluate("() => { window.__mcpImageTurnIdentity = { documentId: 'doc_test' }; }")

        res = poll_chatgpt_image(self.page, tracker, prompt)
        self.assertEqual(res.get("phase"), "image-ready")
        self.assertTrue(res.get("dataUrl", "").startswith("data:image/png;base64,"))
        self.assertEqual(res.get("width"), 400)
        self.assertEqual(res.get("height"), 400)

    def test_poll_rejects_fully_transparent_image(self):
        """IMG 256x256 but with all alpha = 0 (transparent blank) -> rejected."""
        prompt = "Ảnh trong suốt"
        transparent_url = make_png_data_url(256, 256, (0, 0, 0, 0))
        html = f"""
        <html>
        <body>
          <main>
            <div>
              <h4>You said:</h4>
              <div data-user-message-bubble="true">{prompt}</div>
            </div>
            <div>
              <h4>ChatGPT said:</h4>
              <div data-testid="generated-image-gallery">
                <div>
                  <img src="{transparent_url}" width="256" height="256" alt="Generated image" />
                  <button aria-label="Edit">Edit</button>
                  <button aria-label="Download">Download</button>
                </div>
              </div>
            </div>
          </main>
        </body>
        </html>
        """
        self.page.set_content(html)
        tracker = {"documentId": "doc_test", "baselineSources": [], "previousMatchingPrompts": 0}
        self.page.evaluate("() => { window.__mcpImageTurnIdentity = { documentId: 'doc_test' }; }")

        res = poll_chatgpt_image(self.page, tracker, prompt)
        self.assertNotEqual(res.get("phase"), "image-ready")

    def test_caller_lifecycle_simulation(self):
        """Simulates MCP Shopee's actual polling loop:
        1. Loading/busy phase: Multiple polls confirm no file written, no success.
        2. Completed phase: Transition to completed DOM -> file saved, atomic file created, valid PNG.
        """
        prompt = "Mô phỏng caller vòng đời thực tế"
        with tempfile.TemporaryDirectory() as td:
            export_path = Path(td) / "1.png"

            # Phase 1: Creating image
            html_loading = f"""
            <html>
            <body>
              <main>
                <div>
                  <h4>You said:</h4>
                  <div data-user-message-bubble="true">{prompt}</div>
                </div>
                <div>
                  <h4>ChatGPT said:</h4>
                  <div>
                    <canvas width="512" height="512"></canvas>
                    <div>Creating image 45%</div>
                    <button data-testid="stop-button">Stop</button>
                  </div>
                </div>
              </main>
            </body>
            </html>
            """
            self.page.set_content(html_loading)
            tracker = {"documentId": "doc_life", "baselineSources": [], "previousMatchingPrompts": 0}
            self.page.evaluate("() => { window.__mcpImageTurnIdentity = { documentId: 'doc_life' }; }")

            # Poll 3 times during loading
            for _ in range(3):
                poll_res = poll_chatgpt_image(self.page, tracker, prompt)
                self.assertNotEqual(poll_res.get("phase"), "image-ready")
                self.assertFalse(export_path.exists(), "File must NOT be written during loading phase")

            # Phase 2: Completion
            final_png_url = make_png_data_url(512, 512, (20, 150, 220, 255))
            html_completed = f"""
            <html>
            <body>
              <main>
                <div>
                  <h4>You said:</h4>
                  <div data-user-message-bubble="true">{prompt}</div>
                </div>
                <div>
                  <h4>ChatGPT said:</h4>
                  <div data-testid="generated-image-gallery">
                    <div>
                      <button data-testid="generated-image-preview">
                        <img src="{final_png_url}" width="512" height="512" alt="Generated image" />
                      </button>
                      <button aria-label="Edit generated image">Edit</button>
                      <button aria-label="Download generated image">Download</button>
                    </div>
                  </div>
                </div>
              </main>
            </body>
            </html>
            """
            self.page.set_content(html_completed)
            self.page.evaluate("() => { window.__mcpImageTurnIdentity = { documentId: 'doc_life' }; }")

            # Final poll after completion
            poll_res = poll_chatgpt_image(self.page, tracker, prompt)
            self.assertEqual(poll_res.get("phase"), "image-ready")
            data_url = poll_res.get("dataUrl")
            self.assertIsNotNone(data_url)

            # Atomic save exactly as web_app.py does
            saved_file = save_chatgpt_image_atomic(data_url, export_path)
            self.assertTrue(export_path.exists(), "File MUST exist after image-ready")
            self.assertEqual(saved_file, str(export_path))
            self.assertGreater(export_path.stat().st_size, 500)

    def test_fill_chatgpt_prompt_variants(self):
        """Tests that fill_chatgpt_prompt successfully types into various ChatGPT editor layouts:
        1. ProseMirror without prompt-textarea id
        2. Classic div#prompt-textarea
        3. Standard textarea
        """
        # Case 1: ProseMirror container without #prompt-textarea
        self.page.set_content("""
            <form>
                <div data-testid="composer-text-input" contenteditable="true" role="textbox">
                    <p data-placeholder="Ask ChatGPT"><br></p>
                </div>
            </form>
        """)
        ed1 = fill_chatgpt_prompt(self.page, "Prompt test 1: ProseMirror")
        val1 = ed1.evaluate("e => e.innerText || e.textContent")
        self.assertIn("Prompt test 1: ProseMirror", val1)

        # Case 2: Classic #prompt-textarea div
        self.page.set_content("""
            <div id="prompt-textarea" contenteditable="true" role="textbox"></div>
        """)
        ed2 = fill_chatgpt_prompt(self.page, "Prompt test 2: Classic div")
        val2 = ed2.evaluate("e => e.innerText || e.textContent")
        self.assertIn("Prompt test 2: Classic div", val2)

        # Case 3: Textarea
        self.page.set_content("""
            <textarea id="prompt-textarea" placeholder="Ask ChatGPT"></textarea>
        """)
        ed3 = fill_chatgpt_prompt(self.page, "Prompt test 3: Textarea")
        val3 = ed3.evaluate("e => e.value")
        self.assertIn("Prompt test 3: Textarea", val3)

    def test_poll_succeeds_when_edit_on_card_and_share_in_turn_controls(self):
        """Realistic ChatGPT UI: Thẻ ảnh chỉ có nút Edit (cây bút chì), nút Share nằm ở turn action controls."""
        prompt = "Thiết kế ảnh feedback thực tế Oximin Gel 25g"
        png_url = make_png_data_url(512, 512, (20, 150, 220, 255))
        html = f"""
        <html>
        <body>
          <main>
            <div data-testid="conversation-turn-2">
              <h4>You said:</h4>
              <div data-user-message-bubble="true">{prompt}</div>
            </div>
            <div data-testid="conversation-turn-3">
              <h4>ChatGPT said:</h4>
              <div>
                <div class="image-card">
                  <img src="{png_url}" width="512" height="512" alt="Generated image" />
                  <button aria-label="Edit image">Chỉnh sửa</button>
                </div>
              </div>
              <div class="turn-actions">
                <button aria-label="Good response">Like</button>
                <button aria-label="Bad response">Dislike</button>
                <button aria-label="Copy">Copy</button>
                <button aria-label="Share this response">Chia sẻ</button>
              </div>
            </div>
          </main>
        </body>
        </html>
        """
        self.page.set_content(html)
        tracker = {"documentId": "doc_real", "baselineSources": [], "previousMatchingPrompts": 0}
        self.page.evaluate("() => { window.__mcpImageTurnIdentity = { documentId: 'doc_real' }; }")

        res = poll_chatgpt_image(self.page, tracker, prompt)
        self.assertEqual(res.get("phase"), "image-ready")
        self.assertEqual(res.get("width"), 512)
        self.assertEqual(res.get("height"), 512)

    def test_save_chatgpt_image_atomic_converts_webp_and_jpeg_to_png(self):
        """Ensures that WebP and JPEG images are safely opened and converted to genuine valid PNG files."""
        import io
        from PIL import Image

        # Create a sample image in memory
        img = Image.new("RGBA", (300, 300), color=(100, 150, 200, 255))
        webp_buf = io.BytesIO()
        img.save(webp_buf, format="WEBP")
        webp_base64 = "data:image/webp;base64," + base64.b64encode(webp_buf.getvalue()).decode("ascii")

        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / "5.png"
            saved_file = save_chatgpt_image_atomic(webp_base64, dest)
            self.assertTrue(dest.exists())
            self.assertEqual(saved_file, str(dest))
            # Verify the saved file is genuinely a PNG
            header = dest.read_bytes()[:8]
            self.assertEqual(header, b"\x89PNG\r\n\x1a\n")


if __name__ == "__main__":
    unittest.main()

