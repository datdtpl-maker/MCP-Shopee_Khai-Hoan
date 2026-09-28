"""ChatGPT Image Capture & Completion Guard for MCP Shopee.

Based on Notion Product Creator v1.2.23 (commit 1ec0d713438782f0ad9935d17406fff7c0418d5f).
Applies the verified completion guard and search-turn layout support while strictly
preserving MCP Shopee's existing workflows and business contracts.
"""

from __future__ import annotations

import base64
import os
import re
import time
import unicodedata
from pathlib import Path
from typing import Any


def normalize_text(text: str | None) -> str:
    """Normalizes Unicode text to NFC and collapses whitespace."""
    if not text:
        return ""
    normalized = unicodedata.normalize("NFC", str(text))
    return re.sub(r"\s+", " ", normalized).strip()


EDITOR_SELECTORS = [
    '#prompt-textarea[contenteditable="true"]',
    '#prompt-textarea',
    'textarea#prompt-textarea',
    '[data-testid="composer-text-input"][contenteditable="true"]',
    '[data-testid="composer-text-input"]',
    'form [contenteditable="true"][role="textbox"]',
    'form .ProseMirror[contenteditable="true"]',
    'div[contenteditable="true"][role="textbox"]',
    '.ProseMirror[contenteditable="true"]',
    'div[contenteditable="true"]',
    'textarea[name="prompt-textarea"]',
    'textarea',
    '[role="textbox"]',
]


def find_chatgpt_editor(page: Any) -> Any | None:
    """Finds a visible and editable ChatGPT composer in the given page."""
    try:
        title = (page.title() or "").lower()
        if any(k in title for k in ["just a moment", "verify", "verification", "xác minh"]):
            raise RuntimeError("ChatGPT đang chờ xác minh bảo mật. Hoàn tất xác minh trong cửa sổ Chrome Debug rồi bấm sinh ảnh lại.")
        if page.query_selector('iframe[src*="challenges.cloudflare.com"]'):
            raise RuntimeError("ChatGPT đang chờ xác minh bảo mật Cloudflare. Vui lòng xác minh trên trình duyệt rồi thử lại.")
    except Exception as e:
        if "xác minh" in str(e):
            raise

    try:
        url = page.url or ""
        if any(p in url for p in ["/auth", "/login", "/signup"]):
            raise RuntimeError("ChatGPT trong Chrome Debug đang yêu cầu đăng nhập. Phiên đăng nhập ở Chrome thông thường không dùng chung với Chrome Debug.")
        login_btn = page.query_selector('[data-testid="login-button"]')
        if login_btn and login_btn.is_visible():
            raise RuntimeError("ChatGPT trong Chrome Debug đang yêu cầu đăng nhập.")
    except Exception as e:
        if "đăng nhập" in str(e):
            raise

    for sel in EDITOR_SELECTORS:
        try:
            candidates = page.query_selector_all(sel)
            for el in candidates:
                if el.is_visible():
                    tag = el.evaluate("e => e.tagName").upper()
                    is_ce = el.evaluate("e => e.isContentEditable || e.getAttribute('contenteditable') === 'true'")
                    if is_ce or tag in ("TEXTAREA", "INPUT") or el.is_editable():
                        return el
        except Exception:
            continue
    return None


def fill_chatgpt_prompt(page: Any, prompt_text: str) -> Any:
    """Finds editor, types prompt reliably using multiple fallbacks, and verifies content."""
    expected = normalize_text(prompt_text)
    if not expected:
        raise ValueError("Nội dung prompt đang trống.")

    # Re-find editor right now (in case DOM re-rendered after file upload)
    editor = find_chatgpt_editor(page)
    if not editor:
        # Wait up to 5 seconds for editor to reappear after file upload
        start = time.time()
        while time.time() - start < 5:
            time.sleep(0.5)
            editor = find_chatgpt_editor(page)
            if editor:
                break
    if not editor:
        raise RuntimeError("Không tìm thấy ô nhập liệu của ChatGPT (sau khi tải ảnh).")

    # Method 1: Try Playwright's native editor.fill()
    filled_ok = False
    try:
        editor.click(timeout=3000)
        editor.focus(timeout=3000)
        editor.fill(prompt_text, timeout=5000)
        val = editor.evaluate("e => (e.tagName === 'TEXTAREA' || e.tagName === 'INPUT') ? e.value : (e.innerText || e.textContent)")
        if normalize_text(val) == expected:
            filled_ok = True
    except Exception:
        pass

    # Method 2: Focus + insertText (ProseMirror / React native typing)
    if not filled_ok:
        try:
            editor.click(timeout=3000)
            editor.focus(timeout=3000)
            page.keyboard.press("ControlOrMeta+A")
            page.keyboard.press("Backspace")
            time.sleep(0.2)
            page.keyboard.insert_text(prompt_text)
            time.sleep(0.5)
            val = editor.evaluate("e => (e.tagName === 'TEXTAREA' || e.tagName === 'INPUT') ? e.value : (e.innerText || e.textContent)")
            if normalize_text(val) == expected:
                filled_ok = True
        except Exception:
            pass

    # Method 3: DOM evaluate with innerHTML / dispatchEvent
    if not filled_ok:
        try:
            editor.evaluate("""(el, text) => {
                el.focus();
                if (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT') {
                    el.value = text;
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                } else {
                    el.innerHTML = `<p>${text}</p>`;
                    el.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: text }));
                }
            }""", prompt_text)
            time.sleep(0.3)
            page.keyboard.press("Space")
            page.keyboard.press("Backspace")
            time.sleep(0.3)
            val = editor.evaluate("e => (e.tagName === 'TEXTAREA' || e.tagName === 'INPUT') ? e.value : (e.innerText || e.textContent)")
            if normalize_text(val) == expected:
                filled_ok = True
        except Exception:
            pass

    # Final check: does editor have content?
    val = editor.evaluate("e => (e.tagName === 'TEXTAREA' || e.tagName === 'INPUT') ? e.value : (e.innerText || e.textContent)")
    if not normalize_text(val):
        raise RuntimeError("Không thể điền nội dung prompt vào ô chat ChatGPT.")

    return editor


def init_chatgpt_image_tracker(page: Any, prompt_text: str) -> dict[str, Any]:
    """Captures baseline state (documentId, baseline sources, previous matching prompts)."""
    expected = normalize_text(prompt_text)
    js_code = """(expected) => {
        const normalize = text => (text || '').normalize('NFC').replace(/\\s+/gu, ' ').trim();
        const docId = 'doc_' + Math.random().toString(36).slice(2) + '_' + Date.now().toString(36);
        window.__mcpImageTurnIdentity = {
            ids: new WeakMap(),
            next: 0,
            documentId: docId
        };
        
        // Collect existing image sources
        const imgs = Array.from(document.querySelectorAll('img'));
        const sources = imgs.map(img => img.currentSrc || img.src || '').filter(s => s && !s.startsWith('data:image/svg'));
        
        // Collect existing user messages matching expected prompt
        const textOf = el => normalize(el.innerText || el.textContent);
        const userNodes = Array.from(document.querySelectorAll('[data-user-message-bubble="true"], [data-testid="user-message"], [data-chatgpt-search-unit-key*=":user"], [data-turn="user"]'));
        let matchingCount = 0;
        userNodes.forEach(node => {
            if (textOf(node).includes(expected)) {
                matchingCount++;
            }
        });
        
        // Fallback matching if no explicit role tags
        if (matchingCount === 0 && expected) {
            const allP = Array.from(document.querySelectorAll('p, div, span'));
            allP.forEach(el => {
                if (el.closest('form, [contenteditable="true"], nav, aside, header, footer')) return;
                if (textOf(el) === expected) {
                    matchingCount++;
                }
            });
        }
        
        return {
            documentId: docId,
            initialUrl: location.href,
            baselineSources: sources,
            previousMatchingPrompts: matchingCount
        };
    }"""
    try:
        return page.evaluate(js_code, expected)
    except Exception as exc:
        # Fallback if evaluation fails
        return {
            "documentId": "fallback_" + str(int(time.time())),
            "initialUrl": page.url,
            "baselineSources": [],
            "previousMatchingPrompts": 0,
        }


POLL_CHATGPT_IMAGE_JS = """(args) => {
    const { promptText, documentId, baselineSources, previousMatchingPrompts } = args;
    const normalize = text => (text || '').normalize('NFC').replace(/\\s+/gu, ' ').trim();
    const expected = normalize(promptText);

    // 1. Verify document identity (detect reload)
    const currentDocId = window.__mcpImageTurnIdentity ? window.__mcpImageTurnIdentity.documentId : null;
    if (currentDocId && currentDocId !== documentId) {
        return { phase: "error", error: "Trang ChatGPT đã tải lại trong lúc tạo ảnh." };
    }

    // 2. Visible helper supporting display: contents
    const visible = (element) => {
        if (!element || element.nodeType !== 1) return false;
        const style = window.getComputedStyle(element);
        if (style.visibility === 'hidden' || style.display === 'none') return false;
        return Boolean(element.getClientRects().length)
            || (style.display === 'contents' && Array.from(element.children).some(visible));
    };

    // 3. Excluded elements
    const excluded = (element) => Boolean(
        element.closest('form, [contenteditable="true"], nav, aside, header, footer, [role="dialog"]')
    );

    // 4. Generation active / stop button check
    const stopButtons = Array.from(document.querySelectorAll('button, [role="button"]')).filter(btn => {
        if (!visible(btn)) return false;
        const testId = btn.getAttribute('data-testid');
        if (testId === 'stop-button') return true;
        const label = normalize(btn.getAttribute('aria-label') || btn.getAttribute('title') || btn.textContent);
        return /^(?:stop|dừng)(?:$|[\\s.,])/i.test(label);
    });
    const generationActive = stopButtons.length > 0;

    // Busy check on elements
    const busySelector = '[aria-busy="true"], [role="progressbar"], [data-testid="stop-button"]';
    const isBusy = (element) => {
        if (element.matches && element.matches(busySelector) && visible(element)) return true;
        if (element.querySelectorAll && Array.from(element.querySelectorAll(busySelector)).some(visible)) return true;
        const statusNodes = Array.from(element.querySelectorAll('div, span, p'));
        return statusNodes.some(st => 
            visible(st) && /^(?:(?:creating|generating|rendering|processing) (?:an? )?image|đang (?:tạo|xử lý|tải) (?:hình )?ảnh)(?:\\s*\\d{1,3}%|[.\\s…])*$/i.test(normalize(st.textContent))
        );
    };

    // 5. Card completion proof check (Edit AND Share/Download must exist on card)
    const checkCardCompletion = (element) => {
        for (let card = element.parentElement, depth = 0; card && depth < 6; card = card.parentElement, depth++) {
            if (card.matches && card.matches('main, body, [data-message-author-role="user"], [data-turn="user"], [data-user-message-bubble]')) break;
            const buttons = Array.from(card.querySelectorAll('button, [role="button"], a[download]'));
            const labels = buttons.flatMap(b => [b.getAttribute('aria-label'), b.getAttribute('title'), b.textContent].filter(Boolean).map(l => l.trim()));
            const hasEdit = labels.some(l => /^(edit|chỉnh sửa)(\\s+((generated )?(hình\\s+)?ảnh|image)(\\s+\\d+)?)?$/i.test(l));
            const hasShareOrDownload = labels.some(l => /download|tải xuống|tải về|share|chia sẻ/i.test(l));
            if (hasEdit && hasShareOrDownload) return true;
            if ((card.matches && card.matches('article, [data-message-author-role], [data-turn]')) || card.querySelector('h4, h5, h6')) break;
        }
        return false;
    };

    // 6. Turn identification
    const root = document.querySelector('main, [role="main"]') || document.body;
    const textOf = element => normalize(element.innerText || element.textContent);
    const labelRole = label => {
        const norm = normalize(label);
        if (/^(?:you said|bạn (?:đã )?nói)\\s*:?$/i.test(norm)) return 'user';
        if (/^(?:chatgpt (?:said|(?:đã )?nói))\\s*:?$/i.test(norm)) return 'assistant';
        return null;
    };
    const ownRole = element => {
        const role = element.getAttribute('data-message-author-role') || element.getAttribute('data-turn')
            || element.getAttribute('data-conversation-role') || element.getAttribute('data-chatgpt-search-unit-key')?.match(/:(user|assistant)$/)?.[1]
            || (element.hasAttribute('data-user-message-bubble') ? 'user' : null);
        return ['user', 'assistant'].includes(role) ? role : labelRole(element.getAttribute('aria-label'));
    };
    const hasAssistantControls = element => {
        if (element.querySelector('[data-testid="good-response-turn-action-button"], [data-testid="bad-response-turn-action-button"]')) return true;
        return Array.from(element.querySelectorAll('button, [role="button"]')).some(b => 
            /^(good response|bad response|(?:like|dislike) this image|câu trả lời (?:hay|không hay)|thích|không thích)$/i.test(normalize(b.getAttribute('aria-label') || b.getAttribute('title')))
        );
    };

    const selector = '[data-testid^="conversation-turn"], article, [data-message-author-role], [data-turn="user"], [data-turn="assistant"], [data-message-id], [data-turn-id], [data-chatgpt-search-unit-key], [data-user-message-bubble], [aria-label^="You said"], [aria-label^="ChatGPT said"], [aria-label^="Bạn đã nói"], [aria-label^="ChatGPT đã nói"]';
    const headingBlocks = Array.from(root.querySelectorAll('h4, h5, h6'))
        .filter(heading => ownRole(heading) || labelRole(heading.textContent)).map(h => h.parentElement).filter(Boolean);
    const rawCandidates = Array.from(new Set([...root.querySelectorAll(selector), ...headingBlocks]))
        .filter(el => el !== root && !excluded(el) && visible(el));

    const candidates = rawCandidates.map(el => {
        const subRoles = new Set([
            ownRole(el),
            ...Array.from(el.querySelectorAll('[data-message-author-role], [data-turn], [data-conversation-role], [data-chatgpt-search-unit-key], [data-user-message-bubble], h4, h5, h6'))
                .map(child => ownRole(child) || labelRole(child.textContent))
        ].filter(Boolean));
        if (subRoles.size > 1) return null; // Wrapper with both roles is not a single turn
        return { element: el, role: Array.from(subRoles)[0] || null };
    }).filter(Boolean);

    let turns = candidates.filter(candidate => !candidates.some(parent => parent !== candidate
        && parent.element.contains(candidate.element) && (parent.role === candidate.role || (parent.role && !candidate.role))));

    // Fallback if no role attributes
    if (expected) {
        const matches = Array.from(root.querySelectorAll('p, div, span')).filter(el => !excluded(el) && visible(el)
            && textOf(el).includes(expected)
            && !Array.from(el.children).some(child => textOf(child).includes(expected)));
        for (const anchor of matches) {
            const existing = turns.find(t => t.element.contains(anchor));
            if (existing) {
                if (!existing.role && !hasAssistantControls(existing.element)) existing.role = 'user';
                continue;
            }
            let user = anchor;
            for (let b = anchor; b.parentElement && b.parentElement !== root; b = b.parentElement) {
                if (b.nextElementSibling && !excluded(b.nextElementSibling) && hasAssistantControls(b.nextElementSibling)) {
                    user = b; break;
                }
            }
            if (user.contains(document.querySelector('#prompt-textarea')) || user === root) user = anchor;
            turns.push({ element: user, role: 'user', fallback: true });
            const reply = user.nextElementSibling;
            if (reply && !excluded(reply) && visible(reply)) {
                if (!turns.some(t => t.element === reply)) {
                    turns.push({ element: reply, role: 'assistant', fallback: true });
                }
            }
        }
    }

    turns.sort((a, b) => (a.element.compareDocumentPosition(b.element) & Node.DOCUMENT_POSITION_FOLLOWING) ? -1 : 1);

    // 7. Find matching user turns
    const matchingUserTurns = turns.filter(t => t.role === 'user' && textOf(t.element).includes(expected));
    if (matchingUserTurns.length <= previousMatchingPrompts) {
        return { phase: "awaiting-request", reason: "Chưa thấy tin nhắn prompt mới trong DOM", busy: generationActive };
    }
    if (matchingUserTurns.length > previousMatchingPrompts + 1) {
        return { phase: "error", error: "Prompt được gửi nhiều lần trong khi tool đang chờ." };
    }

    const currentRequest = matchingUserTurns[matchingUserTurns.length - 1];
    const reqIndex = turns.indexOf(currentRequest);
    if (reqIndex < 0) {
        return { phase: "awaiting-request", reason: "Chưa định vị được vị trí tin nhắn request", busy: generationActive };
    }

    // Turns after request
    const afterTurns = turns.slice(reqIndex + 1);
    if (afterTurns.some(t => t.role === 'user')) {
        return { phase: "error", error: "Có prompt khác xen vào sau prompt hiện tại." };
    }

    // 8. Find assistant turns after request
    const assistantTurns = afterTurns.filter(t => t.role === 'assistant' || hasAssistantControls(t.element) || t.fallback);
    if (assistantTurns.length === 0) {
        return { phase: "awaiting-assistant", reason: "Đang chờ ChatGPT phản hồi...", busy: generationActive };
    }

    // 9. Inspect candidate images in assistant turns
    for (const aTurn of assistantTurns) {
        const turnBusy = generationActive || isBusy(aTurn.element);

        // Find all media elements in this turn
        const mediaElements = Array.from(aTurn.element.querySelectorAll('img, canvas, [style*="background"], [role="img"]'));
        for (const el of mediaElements) {
            // NEVER accept canvas on page
            if (el.tagName === 'CANVAS') {
                continue;
            }
            if (el.tagName !== 'IMG') {
                continue;
            }

            const src = el.currentSrc || el.src || '';
            if (!src || src.startsWith('data:image/svg')) continue;
            if (baselineSources && baselineSources.includes(src)) continue;

            if (el.closest('.attachment, [data-testid="user-attachment"], [data-user-message-bubble]')) {
                continue;
            }

            const w = el.naturalWidth || el.width || 0;
            const h = el.naturalHeight || el.height || 0;
            const complete = el.complete;
            if (!complete || w < 256 || h < 256) {
                continue;
            }

            // Check completion proof on card
            const completedCard = checkCardCompletion(el);
            if (!completedCard) {
                continue;
            }

            // If turn or document is still busy / generating, wait!
            if (turnBusy) {
                return { phase: "awaiting-image", reason: "Ảnh đã hiện nhưng tiến trình tạo ảnh vẫn đang chạy...", busy: true };
            }

            if (!visible(el)) continue;

            // Extract image to new memory canvas
            try {
                const canvas = document.createElement('canvas');
                canvas.width = w;
                canvas.height = h;
                const ctx = canvas.getContext('2d');
                ctx.drawImage(el, 0, 0);

                // Pixel transparency check
                const imgData = ctx.getImageData(0, 0, w, h);
                const pixels = imgData.data;
                let hasPixels = false;
                for (let i = 3; i < pixels.length; i += 4) {
                    if (pixels[i] > 0) {
                        hasPixels = true;
                        break;
                    }
                }
                if (!hasPixels) {
                    continue; // Transparent image, not ready
                }

                const dataUrl = canvas.toDataURL('image/png');
                return {
                    phase: "image-ready",
                    dataUrl: dataUrl,
                    src: src,
                    width: w,
                    height: h
                };
            } catch (err) {
                return { phase: "error", error: "Không đọc được dữ liệu canvas: " + err.message };
            }
        }

        if (turnBusy) {
            return { phase: "awaiting-image", reason: "Đang tạo ảnh...", busy: true };
        }
    }

    return { phase: "awaiting-image", reason: "Chưa thấy ảnh hoàn chỉnh trong phản hồi của assistant", busy: generationActive };
}"""


def poll_chatgpt_image(page: Any, tracker: dict[str, Any], prompt_text: str) -> dict[str, Any]:
    """Polls the ChatGPT page for completed image output."""
    args = {
        "promptText": prompt_text,
        "documentId": tracker.get("documentId"),
        "baselineSources": tracker.get("baselineSources", []),
        "previousMatchingPrompts": tracker.get("previousMatchingPrompts", 0),
    }
    return page.evaluate(POLL_CHATGPT_IMAGE_JS, args)


def save_chatgpt_image_atomic(data_url: str, dest_path: Path) -> str:
    """Decodes data URL, verifies PNG headers and dimensions, and writes atomically."""
    if not data_url or not data_url.startswith("data:image/"):
        raise ValueError("Dữ liệu ảnh trả về không hợp lệ.")

    try:
        header, encoded = data_url.split(",", 1)
        raw_bytes = base64.b64decode(encoded)
    except Exception as e:
        raise ValueError(f"Không giải mã được base64: {e}")

    # Verify PNG header
    if len(raw_bytes) < 24 or not raw_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Ảnh kết quả không có dữ liệu PNG hợp lệ.")

    # Read dimensions from IHDR (bytes 16..24)
    width = int.from_bytes(raw_bytes[16:20], "big")
    height = int.from_bytes(raw_bytes[20:24], "big")
    if width < 256 or height < 256:
        raise ValueError(f"Kích thước ảnh quá nhỏ ({width}x{height}), không đạt chuẩn hoàn chỉnh.")

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = dest_path.with_name(f"{dest_path.name}.part")

    try:
        temp_path.write_bytes(raw_bytes)
        # Atomic rename
        temp_path.replace(dest_path)
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass

    return str(dest_path)
