from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any
import sys

if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='backslashreplace')
    except Exception:
        pass
if sys.stderr is not None:
    try:
        sys.stderr.reconfigure(encoding='utf-8', errors='backslashreplace')
    except Exception:
        pass

from flask import Flask, jsonify, render_template_string, request

import base64
import requests
from concurrent.futures import ThreadPoolExecutor

import photo_pipeline as pipeline


if getattr(sys, 'frozen', False):
    ROOT = Path(sys.executable).resolve().parent
    BUNDLE_DIR = Path(sys._MEIPASS)
else:
    ROOT = Path(__file__).resolve().parent
    BUNDLE_DIR = ROOT

CONFIG_PATH = ROOT / "config.json"
CURRENT_VERSION = "v2.2.59"


# Tu dong khoi tao cac file config va data tu bundle neu chua ton tai o ngoai
if not CONFIG_PATH.exists():
    example_config = BUNDLE_DIR / "config.example.json"
    if example_config.exists():
        try:
            shutil.copy(example_config, CONFIG_PATH)
            print(f"Da tu dong tao config.json tu config.example.json tai: {CONFIG_PATH}")
        except Exception as e:
            print(f"Loi khi sao chep file config.example.json: {e}")

prompts_path = ROOT / "content_prompts.json"
if not prompts_path.exists():
    example_prompts = BUNDLE_DIR / "content_prompts.json"
    if example_prompts.exists():
        try:
            shutil.copy(example_prompts, prompts_path)
            print(f"Da tu dong khoi tao content_prompts.json tai: {prompts_path}")
        except Exception as e:
            print(f"Loi khi sao chep file content_prompts.json: {e}")

chrome_bat_path = ROOT / "run_debug_chrome.bat"
if not chrome_bat_path.exists():
    try:
        example_bat = BUNDLE_DIR / "run_debug_chrome.bat"
        if example_bat.exists():
            shutil.copy(example_bat, chrome_bat_path)
            print(f"Da tu dong khoi tao run_debug_chrome.bat tai: {chrome_bat_path}")
        else:
            bat_content = """@echo off
title Khoi dong Chrome Debug Port 9222
echo Dang tim kiem duong dan Google Chrome...

set "CHROME_PATH="
if exist "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" (
    set "CHROME_PATH=C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
) else if exist "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe" (
    set "CHROME_PATH=C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe"
) else if exist "%%LocalAppData%%\\Google\\Chrome\\Application\\chrome.exe" (
    set "CHROME_PATH=%%LocalAppData%%\\Google\\Chrome\\Application\\chrome.exe"
)

if "%CHROME_PATH%"=="" (
    echo Khong tim thay Google Chrome tren cac thu muc mac dinh!
    echo Vui long mo Chrome bang tay voi cac tham sau:
    echo chrome.exe --remote-debugging-port=9222 --user-data-dir="%%%%LOCALAPPDATA%%%%\\Google\\Chrome\\User Data Debug"
    pause
    exit /b
)

echo Da tim thay Chrome tai: %%CHROME_PATH%%
echo Dang khoi dong Chrome o che do Cua so Doc lap (App Mode) voi debug port 9222...
echo (Dieu nay giup an thanh URL, tao trai nghiem gop chung sang trong giong Widget ung dung)

start "" "%%CHROME_PATH%%" --app="https://chatgpt.com" --remote-debugging-port=9222 --user-data-dir="%%LOCALAPPDATA%%\\Google\\Chrome\\User Data Debug"
echo Chrome Debug App da duoc khoi dong!
exit
"""
            chrome_bat_path.write_text(bat_content, encoding="utf-8")
            print(f"Da tu dong tao moi run_debug_chrome.bat tai: {chrome_bat_path}")
    except Exception as e:
        print(f"Loi khi khoi tao run_debug_chrome.bat: {e}")

gemini_bat_path = ROOT / "run_debug_chrome_gemini.bat"
if not gemini_bat_path.exists():
    try:
        example_bat = BUNDLE_DIR / "run_debug_chrome_gemini.bat"
        if example_bat.exists():
            shutil.copy(example_bat, gemini_bat_path)
            print(f"Da tu dong khoi tao run_debug_chrome_gemini.bat tai: {gemini_bat_path}")
        else:
            bat_content = """@echo off
title Khoi dong Chrome Debug Port 9223
echo Dang tim kiem duong dan Google Chrome cho Gemini...

set "CHROME_PATH="
if exist "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" (
    set "CHROME_PATH=C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
) else if exist "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe" (
    set "CHROME_PATH=C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe"
) else if exist "%%LocalAppData%%\\Google\\Chrome\\Application\\chrome.exe" (
    set "CHROME_PATH=%%LocalAppData%%\\Google\\Chrome\\Application\\chrome.exe"
)

if "%CHROME_PATH%"=="" (
    echo Khong tim thay Google Chrome tren cac thu muc mac dinh!
    echo Vui long mo Chrome bang tay voi cac tham sau:
    echo chrome.exe --remote-debugging-port=9223 --user-data-dir="%%%%LOCALAPPDATA%%%%\\Google\\Chrome\\User Data Debug Gemini"
    pause
    exit /b
)

echo Da tim thay Chrome tai: %%CHROME_PATH%%
echo Dang khoi dong Chrome Gemini o che do Cua so Doc lap (App Mode) voi debug port 9223...

start "" "%%CHROME_PATH%%" --app="https://gemini.google.com" --remote-debugging-port=9223 --user-data-dir="%%LOCALAPPDATA%%\\Google\\Chrome\\User Data Debug Gemini"
echo Chrome Gemini Debug App da duoc khoi dong!
exit
"""
            gemini_bat_path.write_text(bat_content, encoding="utf-8")
            print(f"Da tu dong tao moi run_debug_chrome_gemini.bat tai: {gemini_bat_path}")
    except Exception as e:
        print(f"Loi khi khoi tao run_debug_chrome_gemini.bat: {e}")

DEFAULT_DRIVE_ROOT = r"G:\My Drive\Hình ảnh Shopee"
EVENT_LOCK = threading.Lock()
EVENTS: list[dict[str, Any]] = []
EVENT_COUNTER = 0
OPERATION_LOCK = threading.Lock()
CONFIG_LOCK = threading.RLock()

app = Flask(__name__)


HTML = r"""
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="icon" type="image/x-icon" href="/favicon.ico?v=2.2.0">
  <link rel="shortcut icon" type="image/x-icon" href="/favicon.ico?v=2.2.0">
  <title>MCP Shopee - Khải Hoàn</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Plus+Jakarta+Sans:wght@500;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {
      color-scheme: dark;
      /* SEO GSC Auditor Style - Dark Navy theme */
      --bg: #0b0f19;
      --surface: #111827;
      --surface-container-low: #0d1321;
      --surface-container-high: #1f2937;
      --panel: #111827;
      --panel-border: rgba(255, 255, 255, 0.05);
      --soft: rgba(255, 255, 255, 0.02);
      --line: rgba(255, 255, 255, 0.04);

      --text: #f3f4f6;
      --text-muted: #9ca3af;
      --muted: #9ca3af;

      /* Elegant Cyan brand accent like GSC Auditor */
      --brand: #2dd4bf;
      --brand-hover: #14b8a6;
      --brand-gradient: linear-gradient(135deg, #0d9488 0%, #2dd4bf 100%);
      --brand-glow: rgba(45, 212, 191, 0.15);

      --primary: #38bdf8;
      --primary-container: #0c4a6e;
      --on-primary-container: #e0f2fe;

      --ok: #34d399;
      --okbg: rgba(52, 211, 153, 0.06);
      --warn: #fbbf24;
      --warnbg: rgba(251, 191, 36, 0.06);
      --danger: #f87171;
      --danger-hover: #fca5a5;
      --danger-gradient: linear-gradient(135deg, #f87171 0%, #b91c1c 100%);
      --shadow: 0 12px 24px rgba(0, 0, 0, 0.4);
      --z-content: 1;
      --z-sticky-panel: 100;
      --z-topbar: 9000;
      --z-header-popover: 9100;
      --z-modal: 20000;

      --font-title: 'Inter', system-ui, sans-serif;
      --font-body: 'Inter', system-ui, sans-serif;
      font-family: var(--font-body);
    }

    body.theme-light {
      color-scheme: light;
      --bg: #f3f4f6;
      --panel: #ffffff;
      --panel-border: rgba(0, 0, 0, 0.08);
      --soft: rgba(0, 0, 0, 0.015);
      --line: rgba(0, 0, 0, 0.03);
      --text: #1f2937;
      --muted: #6b7280;

      --brand: #0d9488;
      --brand-hover: #0f766e;
      --brand-glow: rgba(13, 148, 136, 0.12);

      --primary: #0284c7;
      --primary-container: #e0f2fe;
      --on-primary-container: #0369a1;

      --ok: #059669;
      --okbg: rgba(5, 150, 105, 0.08);
      --warn: #d97706;
      --warnbg: rgba(217, 119, 6, 0.08);
      --danger: #dc2626;
      --danger-hover: #b91c1c;
      --shadow: 0 10px 20px rgba(0, 0, 0, 0.05);
    }

    /* Light Mode Form Overrides */
    body.theme-light .panel input,
    body.theme-light .panel select,
    body.theme-light .panel textarea {
      background-color: #ffffff !important;
      border: 1px solid #cbd5e1 !important;
      color: #111827 !important;
    }
    body.theme-light .panel input[readonly],
    body.theme-light .panel input:disabled,
    body.theme-light .panel textarea[readonly],
    body.theme-light .panel textarea:disabled {
      background-color: #f9fafb !important;
      color: #6b7280 !important;
      border: 1px solid #e5e7eb !important;
    }
    body.theme-light .panel label,
    body.theme-light .panel h4,
    body.theme-light .panel h3,
    body.theme-light .panel-head h3,
    body.theme-light .panel-head h4 {
      color: #111827 !important;
    }
    body.theme-light #contentImgDropzone,
    body.theme-light #sampleImgDropzone,
    body.theme-light #image-upload-zone {
      background-color: #ffffff !important;
      border: 2px dashed #cbd5e1 !important;
    }
    body.theme-light #contentImgDropzone span,
    body.theme-light #sampleImgDropzone span,
    body.theme-light #image-upload-zone span,
    body.theme-light #contentImgDropzone svg,
    body.theme-light #sampleImgDropzone svg,
    body.theme-light #image-upload-zone svg {
      color: #4b5563 !important;
    }
    body.theme-light #automationLogBox,
    body.theme-light #shopeeSyncLogBox {
      background-color: #f9fafb !important;
      border: 1px solid #e5e7eb !important;
      color: #111827 !important;
      box-shadow: none !important;
    }

    @keyframes pulseWarn {
      0% { box-shadow: 0 0 0 0 rgba(245, 158, 11, 0.4); }
      70% { box-shadow: 0 0 0 10px rgba(245, 158, 11, 0); }
      100% { box-shadow: 0 0 0 0 rgba(245, 158, 11, 0); }
    }
    .pulse-warn {
      animation: pulseWarn 2s infinite;
      border-color: var(--warn) !important;
      color: var(--warn) !important;
    }

    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: radial-gradient(circle at top left, rgba(45, 212, 191, 0.05), transparent 45%),
                  radial-gradient(circle at bottom right, rgba(139, 92, 246, 0.03), transparent 45%),
                  var(--bg);
      color: var(--text);
      min-height: 100vh;
      transition: background 0.3s, color 0.3s;
    }

    /* Font va input/textarea dong bo */
    button, input, select, textarea {
      font-family: var(--font-body) !important;
      font-size: 13.5px !important;
    }

    button {
      min-height: 40px;
      border: 0;
      border-radius: 8px;
      padding: 10px 16px;
      background: var(--brand-gradient);
      color: #fff;
      font-weight: 700;
      font-family: var(--font-title);
      cursor: pointer;
      white-space: nowrap;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
      box-shadow: 0 4px 12px var(--brand-glow);
    }
    button:hover {
      background: var(--brand-hover);
      transform: translateY(-1px);
      box-shadow: 0 6px 18px var(--brand-glow);
    }
    button:active {
      transform: translateY(0);
    }
    button:disabled {
      opacity: 0.5;
      cursor: not-allowed;
      transform: none !important;
      box-shadow: none !important;
    }
    button.secondary {
      background: rgba(255, 255, 255, 0.04);
      color: var(--text);
      border: 1px solid rgba(255, 255, 255, 0.06);
      box-shadow: none;
      transition: background 0.3s, color 0.3s, border-color 0.3s;
    }
    body.theme-light button.secondary {
      background: rgba(0, 0, 0, 0.02);
      color: var(--text);
      border: 1px solid rgba(0, 0, 0, 0.06);
    }
    button.secondary:hover {
      background: rgba(255, 255, 255, 0.08);
      border-color: rgba(255, 255, 255, 0.1);
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
    }
    body.theme-light button.secondary:hover {
      background: rgba(0, 0, 0, 0.04);
      border-color: rgba(0, 0, 0, 0.08);
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.03);
    }
    button.ghost {
      background: transparent;
      color: var(--muted);
      border: 1px solid rgba(255, 255, 255, 0.04);
      box-shadow: none;
    }
    body.theme-light button.ghost {
      border-color: rgba(0, 0, 0, 0.04);
    }
    button.ghost:hover {
      background: rgba(255, 255, 255, 0.04);
      color: var(--text);
      border-color: rgba(255, 255, 255, 0.08);
    }
    body.theme-light button.ghost:hover {
      background: rgba(0, 0, 0, 0.02);
      color: var(--text);
      border-color: rgba(0, 0, 0, 0.06);
    }
    button.danger {
      background: var(--danger-gradient);
      box-shadow: 0 4px 12px rgba(239, 68, 68, 0.15);
    }
    button.danger:hover {
      background: var(--danger-hover);
      box-shadow: 0 6px 18px rgba(239, 68, 68, 0.2);
    }
    button.btn-capture {
      background: linear-gradient(135deg, #0891b2 0%, #06b6d4 100%);
      box-shadow: 0 4px 14px rgba(6, 182, 212, 0.2);
    }
    button.btn-capture:hover {
      background: linear-gradient(135deg, #0e7490 0%, #0891b2 100%);
      box-shadow: 0 6px 20px rgba(6, 182, 212, 0.3);
    }
    button.btn-record {
      background: linear-gradient(135deg, #e11d48 0%, #be123c 100%);
      box-shadow: 0 4px 14px rgba(225, 29, 72, 0.2);
    }
    button.btn-record:hover {
      background: linear-gradient(135deg, #be123c 0%, #9f1239 100%);
      box-shadow: 0 6px 20px rgba(225, 29, 72, 0.3);
    }
    button.btn-stop {
      background: linear-gradient(135deg, #4b5563 0%, #374151 100%);
      box-shadow: 0 4px 14px rgba(75, 85, 99, 0.15);
    }
    button.btn-stop:hover {
      background: linear-gradient(135deg, #374151 0%, #1f2937 100%);
      box-shadow: 0 6px 20px rgba(75, 85, 99, 0.25);
    }

    /* Button color classes */
    .md3-btn-primary {
      background: var(--brand-gradient) !important;
      color: #fff !important;
      box-shadow: 0 4px 12px var(--brand-glow) !important;
    }
    .md3-btn-primary:hover {
      background: var(--brand-hover) !important;
    }
    .md3-btn-secondary {
      background: rgba(255, 255, 255, 0.04) !important;
      color: var(--text) !important;
      border: 1px solid rgba(255, 255, 255, 0.06) !important;
      box-shadow: none !important;
    }
    body.theme-light .md3-btn-secondary {
      background: rgba(0, 0, 0, 0.02) !important;
      color: #0f172a !important;
      border: 1px solid rgba(0, 0, 0, 0.06) !important;
    }
    .md3-btn-secondary:hover {
      background: rgba(255, 255, 255, 0.08) !important;
    }
    body.theme-light .md3-btn-secondary:hover {
      background: rgba(0, 0, 0, 0.04) !important;
    }
    .md3-btn-success {
      background: linear-gradient(135deg, #059669 0%, #34d399 100%) !important;
      color: #fff !important;
      box-shadow: 0 4px 12px rgba(52, 211, 153, 0.2) !important;
    }
    .md3-btn-success:hover {
      background: #059669 !important;
    }

    input, select, textarea, .md3-input {
      width: 100%;
      min-height: 40px;
      border: 1px solid rgba(255, 255, 255, 0.08) !important;
      border-radius: 8px !important;
      background: rgba(13, 17, 28, 0.4) !important;
      padding: 10px 14px !important;
      color: var(--text) !important;
      outline: none;
      transition: all 0.2s;
    }
    body.theme-light input,
    body.theme-light select,
    body.theme-light textarea,
    body.theme-light .md3-input {
      background: #fff !important;
      border-color: #cbd5e1 !important;
      color: var(--text) !important;
    }
    input:focus, select:focus, textarea:focus, .md3-input:focus {
      border-color: var(--brand) !important;
      box-shadow: 0 0 0 3px var(--brand-glow) !important;
    }
    label, .md3-label {
      display: block;
      margin-bottom: 6px;
      font-weight: 700;
      font-size: 11.5px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      color: var(--text-muted);
      font-family: var(--font-title);
    }
    body.theme-light label, body.theme-light .md3-label {
      color: #4b5563;
    }
    .shell {
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }
    .sidebar { display: none; }
    .main {
      flex: 1;
      display: flex;
      flex-direction: column;
      min-width: 0;
    }
    .topbar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 20px;
      padding: 10px 32px;
      background: #0b0f19;
      border-bottom: 1px solid var(--panel-border);
      position: sticky;
      top: 0;
      z-index: var(--z-topbar);
      isolation: isolate;
      backdrop-filter: blur(16px);
      -webkit-backdrop-filter: blur(16px);
      box-shadow: 0 8px 24px rgba(0, 0, 0, 0.18);
      transition: background 0.3s, border-color 0.3s;
    }
    body.theme-light .topbar {
      background: #ffffff;
      box-shadow: 0 8px 18px rgba(15, 23, 42, 0.08);
    }
    .topbar h2 {
      margin: 0;
      font-size: 15px;
      font-weight: 800;
      font-family: var(--font-title);
      color: var(--text);
      transition: all 0.3s;
    }
    .actions {
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      align-items: center;
    }
    .action-group {
      display: inline-flex;
      align-items: center;
      background: rgba(255, 255, 255, 0.02);
      border: 1px solid var(--panel-border);
      border-radius: 8px;
      padding: 3px;
      gap: 3px;
    }
    body.theme-light .action-group {
      background: rgba(0, 0, 0, 0.01);
    }
    .action-group-label {
      font-size: 10px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--muted);
      padding: 0 8px 0 4px;
      user-select: none;
      border-right: 1px solid var(--panel-border);
      margin-right: 2px;
      height: 18px;
      display: inline-flex;
      align-items: center;
    }
    .action-group button.group-btn {
      min-height: 32px;
      padding: 6px 10px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 600;
      box-shadow: none !important;
    }
    .action-group button.group-btn:hover {
      transform: translateY(-0.5px);
    }
    .content {
      padding: 24px 32px;
      flex: 1;
      max-width: 1600px;
      width: 100%;
      margin: 0 auto;
      position: relative;
      z-index: var(--z-content);
    }
    #posterDashboard .content,
    #shopeeSyncDashboard .content {
      max-width: 1840px;
      width: 98%;
    }
    .workspace {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 400px;
      gap: 24px;
      align-items: start;
    }
    .work-main {
      display: grid;
      gap: 24px;
      min-width: 0;
    }
    .work-log {
      position: sticky;
      top: 100px;
      z-index: var(--z-sticky-panel);
      min-width: 0;
    }
    .metrics {
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 16px;
    }
    .metric {
      background: var(--panel);
      border: 1px solid var(--panel-border);
      border-radius: 12px;
      box-shadow: var(--shadow);
      padding: 16px;
      min-height: 84px;
      transition: all 0.25s ease;
    }
    .metric:hover {
      transform: translateY(-1px);
      border-color: rgba(45, 212, 191, 0.2);
    }
    .metric small {
      display: block;
      color: var(--muted);
      font-size: 10px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.8px;
      margin-bottom: 6px;
    }
    .metric strong {
      display: block;
      font-size: 14px;
      font-weight: 700;
      color: #fff;
      overflow-wrap: anywhere;
    }
    body.theme-light .metric strong {
      color: #111827;
    }

    /* Nav Tabs Bar GSC style */
    .nav-tabs {
      display: flex;
      gap: 24px;
      align-items: center;
      min-width: 0;
      overflow-x: auto;
      scrollbar-width: none;
    }
    .nav-tabs::-webkit-scrollbar {
      display: none;
    }
    .nav-tab {
      font-family: var(--font-title);
      font-size: 13px;
      font-weight: 700;
      color: var(--text-muted);
      cursor: pointer;
      padding: 16px 2px;
      position: relative;
      transition: all 0.2s ease;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      white-space: nowrap;
    }
    .nav-tab:hover {
      color: var(--text);
    }
    .nav-tab.active {
      color: var(--brand);
    }
    .nav-tab.active::after {
      content: '';
      position: absolute;
      bottom: -15px; /* De no an sat vao vien duoi */
      left: 0;
      width: 100%;
      height: 2px;
      background: var(--brand);
      border-radius: 99px;
      box-shadow: 0 0 8px var(--brand-glow);
    }

    .badge {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border-radius: 6px;
      padding: 3px 8px;
      font-size: 11px;
      font-weight: 700;
      gap: 4px;
      line-height: 1.2;
    }
    .badge.ok {
      background: var(--okbg);
      color: var(--ok);
      border: 1px solid rgba(52, 211, 153, 0.15);
    }
    .badge.ok::before {
      content: '';
      display: inline-block;
      width: 5px;
      height: 5px;
      background: var(--ok);
      border-radius: 50%;
      box-shadow: 0 0 6px var(--ok);
      animation: pulse 1.8s infinite;
    }
    .badge.warn {
      background: var(--warnbg);
      color: var(--warn);
      border: 1px solid rgba(251, 191, 36, 0.15);
    }
    .badge.warn::before {
      content: '';
      display: inline-block;
      width: 5px;
      height: 5px;
      background: var(--warn);
      border-radius: 50%;
      box-shadow: 0 0 6px var(--warn);
      animation: pulse 1.8s infinite;
    }
    .badge.danger {
      background: rgba(239, 68, 68, 0.1);
      color: #f87171;
      border: 1px solid rgba(239, 68, 68, 0.15);
    }
    .badge.danger::before {
      content: '';
      display: inline-block;
      width: 5px;
      height: 5px;
      background: #f87171;
      border-radius: 50%;
      box-shadow: 0 0 6px #f87171;
    }
    @keyframes pulse {
      0% { transform: scale(0.9); opacity: 0.6; }
      50% { transform: scale(1.1); opacity: 1; box-shadow: 0 0 8px currentColor; }
      100% { transform: scale(0.9); opacity: 0.6; }
    }
    .panel {
      background: var(--panel);
      border: 1px solid var(--panel-border);
      border-radius: 12px;
      box-shadow: var(--shadow);
      overflow: hidden;
      position: relative;
      z-index: var(--z-content);
      transition: background 0.3s, border-color 0.3s, box-shadow 0.3s;
    }
    .panel-head {
      padding: 16px 20px;
      border-bottom: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.005);
    }
    .panel-head h3, .panel-head h4 {
      margin: 0;
      font-size: 15px;
      font-weight: 700;
      font-family: var(--font-title);
      color: #fff;
    }
    body.theme-light .panel-head h3, body.theme-light .panel-head h4 {
      color: #111827;
    }
    .panel-head p {
      margin: 4px 0 0;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.4;
    }
    .panel-body {
      padding: 20px;
      display: grid;
      gap: 16px;
    }
    .layout {
      display: grid;
      grid-template-columns: minmax(0, 1.35fr) minmax(320px, 0.65fr);
      gap: 20px;
      align-items: start;
    }
    .two {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }
    .field-action {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 10px;
      align-items: end;
    }
    .hint {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.4;
      display: flex;
      align-items: flex-start;
      gap: 4px;
    }
    .hint::before {
      content: 'ℹ';
      color: var(--brand);
      font-weight: bold;
    }
    .steps {
      display: grid;
      gap: 10px;
    }
    .step {
      display: grid;
      grid-template-columns: 28px 1fr;
      gap: 10px;
      padding: 12px;
      background: rgba(255, 255, 255, 0.015);
      border: 1px solid rgba(255, 255, 255, 0.03);
      border-radius: 10px;
      transition: all 0.2s;
    }
    body.theme-light .step {
      background: rgba(0, 0, 0, 0.01);
      border-color: rgba(0, 0, 0, 0.03);
    }
    .step:hover {
      background: rgba(255, 255, 255, 0.03);
      border-color: rgba(255, 255, 255, 0.06);
      transform: translateX(2px);
    }
    body.theme-light .step:hover {
      background: rgba(0, 0, 0, 0.02);
      border-color: rgba(0, 0, 0, 0.05);
    }
    .step span {
      display: grid;
      place-items: center;
      width: 28px;
      height: 28px;
      border-radius: 50%;
      background: rgba(45, 212, 191, 0.15);
      color: var(--brand);
      font-weight: 800;
      font-family: var(--font-title);
    }
    body.theme-light .step span {
      background: rgba(13, 148, 136, 0.08);
      color: var(--brand);
    }
    .step b {
      display: block;
      margin-bottom: 2px;
      font-size: 13px;
      color: #fff;
    }
    body.theme-light .step b {
      color: #111827;
    }
    .step small {
      display: block;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.35;
    }
    .control-grid {
      display: grid;
      grid-template-columns: minmax(200px, 300px) minmax(0, 1fr);
      gap: 16px;
      align-items: end;
    }
    .control-note {
      padding: 12px;
      border: 1px solid rgba(255, 255, 255, 0.03);
      background: rgba(255, 255, 255, 0.01);
      border-radius: 10px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.45;
    }
    body.theme-light .control-note {
      background: rgba(0, 0, 0, 0.01);
      border-color: rgba(0, 0, 0, 0.04);
    }
    .logbox {
      background: #040811;
      border-radius: 10px;
      border: 1px solid rgba(255, 255, 255, 0.05);
      overflow: hidden;
      box-shadow: inset 0 4px 12px rgba(0, 0, 0, 0.4);
    }
    body.theme-light .logbox {
      background: #f9fafb;
      border-color: #e5e7eb;
      box-shadow: inset 0 1px 3px rgba(0, 0, 0, 0.01);
    }
    .loghead {
      display: flex;
      justify-content: space-between;
      padding: 10px 14px;
      color: var(--text);
      background: rgba(255, 255, 255, 0.015);
      border-bottom: 1px solid rgba(255, 255, 255, 0.05);
      font-size: 12px;
      font-weight: 700;
      font-family: var(--font-title);
    }
    body.theme-light .loghead {
      background: #f3f4f6;
      border-bottom-color: #e5e7eb;
      color: #374151;
    }
    .log {
      min-height: 520px;
      max-height: calc(100vh - 250px);
      overflow: auto;
      padding: 14px;
      font: 12px/1.5 Consolas, "Cascadia Mono", monospace;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .log-item {
      border-left: 3px solid var(--brand);
      padding: 6px 10px;
      border-radius: 0 4px 4px 0;
      background: rgba(255, 255, 255, 0.01);
      animation: fadeIn 0.3s ease-out;
    }
    body.theme-light .log-item {
      background: #fff;
      border: 1px solid #e5e7eb;
      border-left-width: 3px;
      box-shadow: 0 1px 2px rgba(0, 0, 0, 0.01);
    }
    .log-item.log-error {
      border-left-color: var(--danger);
      background: rgba(239, 68, 68, 0.03);
    }
    body.theme-light .log-item.log-error {
      border-left-color: var(--danger);
      background: rgba(239, 68, 68, 0.01);
    }
    .log-item.log-success {
      border-left-color: var(--ok);
      background: rgba(52, 211, 153, 0.03);
    }
    body.theme-light .log-item.log-success {
      border-left-color: var(--ok);
      background: rgba(52, 211, 153, 0.01);
    }
    .log-item.log-warning {
      border-left-color: var(--warn);
      background: rgba(251, 191, 36, 0.03);
    }
    body.theme-light .log-item.log-warning {
      border-left-color: var(--warn);
      background: rgba(251, 191, 36, 0.01);
    }
    .log-time {
      color: #4b5563;
      font-size: 10px;
      font-weight: 600;
      display: block;
      margin-bottom: 2px;
    }
    .log-text {
      margin: 0;
      white-space: pre-wrap;
      word-break: break-all;
      color: #d1d5db;
    }
    body.theme-light .log-text {
      color: #1f2937;
    }
    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(2px); }
      to { opacity: 1; transform: translateY(0); }
    }
    .buttons {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
    }

    /* Shopee Sync work grid and form layout */
    .work-grid {
      display: grid;
      grid-template-columns: 1.25fr 1fr;
      gap: 20px;
      align-items: start;
    }
    .form-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }
    .field-span-2 {
      grid-column: span 2;
    }

    @media(max-width: 1280px) {
      .workspace { grid-template-columns: 1fr !important; }
      .work-grid { grid-template-columns: 1fr !important; }
      .work-log { position: static; }
      .log { min-height: 280px; max-height: 400px; }
    }
    @media(max-width: 960px) {
      .metrics { grid-template-columns: repeat(3, 1fr); }
      .layout, .control-grid { grid-template-columns: 1fr; }
      .topbar { flex-direction: column; align-items: stretch; padding: 14px 20px; }
      .actions { margin-top: 8px; }
      .nav-tabs { margin-top: 8px; justify-content: center; }
    }
    @media(max-width: 640px) {
      .metrics { grid-template-columns: 1fr; }
      .two, .field-action { grid-template-columns: 1fr; }
      .content { padding: 12px; }
      .action-group { width: 100%; flex-direction: column; align-items: stretch; gap: 6px; padding: 8px; }
      .action-group-label { border-right: none; border-bottom: 1px solid var(--panel-border); padding: 0 0 6px; margin-right: 0; margin-bottom: 2px; height: auto; justify-content: center; }
      .buttons button, .actions button { width: 100%; }
    }

    /* Table wrap GSC style */
    .table-wrap {
      background: var(--panel);
      border: 1px solid var(--panel-border);
      border-radius: 12px;
      overflow-x: auto;
      width: 100%;
      box-shadow: var(--shadow);
    }
    .table-wrap table {
      width: 100%;
      border-collapse: collapse;
      text-align: left;
      font-size: 13px;
    }
    .table-wrap th,
    .table-wrap td {
      padding: 12px 16px;
      border-bottom: 1px solid var(--line);
    }
    .table-wrap th {
      background: rgba(255, 255, 255, 0.01);
      color: var(--text-muted);
      font-weight: 700;
      text-transform: uppercase;
      font-size: 11px;
      letter-spacing: 0.5px;
    }
    body.theme-light .table-wrap th {
      background: #f9fafb;
    }
    .table-wrap tbody tr:hover {
      background: rgba(255, 255, 255, 0.01);
    }
    body.theme-light .table-wrap tbody tr:hover {
      background: rgba(0, 0, 0, 0.015);
    }

    /* Poster Editor Spinner & Thumbnail */
    .spinner {
      border: 3px solid var(--soft);
      border-top-color: var(--brand);
      border-radius: 50%;
      width: 36px;
      height: 36px;
      animation: spin 1s linear infinite;
    }
    @keyframes spin {
      0% { transform: rotate(0deg); }
      100% { transform: rotate(360deg); }
    }
    .thumbnail-wrapper {
      position: relative;
      width: 100%;
      aspect-ratio: 1;
      border-radius: 6px;
      overflow: hidden;
      border: 1px solid var(--panel-border);
      background: var(--soft);
    }
    .thumbnail-wrapper img {
      width: 100%;
      height: 100%;
      object-fit: cover;
    }
    .thumbnail-wrapper .remove-btn {
      position: absolute;
      top: 4px;
      right: 4px;
      width: 18px;
      height: 18px;
      border-radius: 50%;
      background: var(--danger);
      color: #fff;
      display: grid;
      place-items: center;
      font-size: 10px;
      font-weight: bold;
      cursor: pointer;
      border: none;
      padding: 0;
      min-height: auto;
      box-shadow: 0 1px 4px rgba(0,0,0,0.3);
    }

    /* Dropdown Menu Styles */
    .dropdown {
      position: relative;
      display: inline-block;
    }
    .dropdown-content {
      display: none;
      position: absolute;
      right: 0;
      top: 100%;
      margin-top: 6px;
      background: var(--panel);
      min-width: 220px;
      box-shadow: var(--shadow);
      border: 1px solid var(--panel-border);
      border-radius: 12px;
      backdrop-filter: blur(20px);
      -webkit-backdrop-filter: blur(20px);
      z-index: var(--z-header-popover);
      padding: 6px;
      animation: dropdownFade 0.2s cubic-bezier(0.4, 0, 0.2, 1);
    }
    .dropdown-content::before {
      content: '';
      position: absolute;
      top: -8px;
      left: 0;
      right: 0;
      height: 8px;
      background: transparent;
    }
    .dropdown:hover .dropdown-content {
      display: block;
    }
    .dropdown-content button, .dropdown-content a {
      width: 100%;
      text-align: left;
      justify-content: flex-start;
      background: transparent !important;
      border: none !important;
      box-shadow: none !important;
      padding: 10px 14px !important;
      border-radius: 8px;
      font-size: 13px !important;
      color: var(--text) !important;
      min-height: auto !important;
      display: flex;
      align-items: center;
      gap: 10px;
      transition: background 0.2s, color 0.2s;
    }
    .dropdown-content button:hover {
      background: var(--soft) !important;
      transform: none !important;
      box-shadow: none !important;
      color: var(--brand) !important;
    }
    .dropdown-content button svg {
      opacity: 0.8;
    }
    @keyframes dropdownFade {
      from { opacity: 0; transform: translateY(-4px); }
      to { opacity: 1; transform: translateY(0); }
    }

    /* Topbar padding update for larger logo */
    .topbar {
      padding: 12px 32px !important;
    }
    #posterDashboard > .content,
    #shopeeSyncDashboard > .content {
      padding-top: 18px !important;
    }
    .prompt-library-card {
      z-index: var(--z-content) !important;
    }
    .modal-overlay {
      z-index: var(--z-modal) !important;
    }
    @media(max-width: 1500px) {
      .topbar {
        gap: 14px;
      }
      #posterDashboard > .content {
        grid-template-columns: 300px minmax(0, 1fr) !important;
      }
      #posterDashboard > .content > aside.panel:last-child {
        grid-column: 1 / -1;
        height: auto !important;
        min-height: 520px;
      }
      #shopeeSyncDashboard > .workspace {
        flex-wrap: wrap;
        padding: 0 18px 18px;
      }
    }
    @media(max-width: 1180px) {
      #posterDashboard > .content {
        grid-template-columns: 1fr !important;
        padding-left: 16px !important;
        padding-right: 16px !important;
      }
      #posterDashboard > .content > aside.panel,
      #posterDashboard > .content > main.panel,
      #shopeeSyncDashboard .panel {
        height: auto !important;
        min-height: unset !important;
        max-width: none !important;
      }
      #shopeeSyncDashboard > .workspace {
        flex-direction: column;
        padding: 0 16px 16px;
      }
      #shopeeSyncDashboard > .workspace > * {
        width: 100% !important;
        max-width: none !important;
      }
    }
    @media(max-width: 720px) {
      .topbar {
        padding: 12px 16px !important;
      }
      .topbar > div:first-child h2 {
        font-size: 15px !important;
      }
      .topbar .actions {
        width: 100%;
        justify-content: stretch;
      }
      .topbar .actions > div {
        flex: 1 1 100%;
      }
      #posterDashboard > .content,
      #shopeeSyncDashboard > .workspace {
        gap: 12px !important;
      }
    }

    /* Styles to fit result images nicely in the column container */
    .poster-card {
      position: relative;
      border-radius: 8px;
      overflow: hidden;
      border: 1px solid var(--panel-border);
      background: #000;
      transition: transform 0.2s, border-color 0.2s;
      width: 100%;
      display: flex;
      flex-direction: column;
    }
    .poster-card:hover {
      transform: translateY(-2px);
      border-color: var(--brand);
    }
    .poster-card img {
      width: 100%;
      height: 200px;
      object-fit: contain;
      background: #000;
      display: block;
    }

    /* Focus styles for forms with brand highlight */
    input:focus, select:focus, textarea:focus, .md3-input:focus {
      border-color: var(--brand) !important;
      box-shadow: 0 0 0 3px var(--brand-glow) !important;
      transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
    }
    
    /* Tactile button active click animation */
    button:active, .md3-btn-primary:active, .md3-btn-secondary:active, .ghost:active, .secondary:active {
      transform: scale(0.97) !important;
      transition: transform 0.05s ease;
    }
    
    /* Elegant scrollbar styling */
    ::-webkit-scrollbar {
      width: 6px;
      height: 6px;
    }
    ::-webkit-scrollbar-track {
      background: rgba(255, 255, 255, 0.01);
    }
    ::-webkit-scrollbar-thumb {
      background: rgba(255, 255, 255, 0.1);
      border-radius: 4px;
    }
    ::-webkit-scrollbar-thumb:hover {
      background: rgba(255, 255, 255, 0.25);
    }

    .poster-card .card-actions {
      position: absolute;
      bottom: 0;
      left: 0;
      right: 0;
      background: linear-gradient(to top, rgba(0,0,0,0.95) 0%, rgba(0,0,0,0.4) 75%, transparent 100%);
      padding: 10px;
      display: flex;
      flex-direction: column;
      gap: 6px;
      opacity: 0;
      transform: translateY(8px);
      transition: opacity 0.2s ease, transform 0.2s ease;
      pointer-events: none;
      z-index: 2;
    }
    .poster-card:hover .card-actions {
      opacity: 1;
      transform: translateY(0);
      pointer-events: auto;
    }

    .post-prompt-fields {
      display: grid;
      grid-template-columns: minmax(220px, 0.8fr) minmax(260px, 1.2fr);
      gap: 12px;
    }

    #save-form[hidden] {
      display: none !important;
    }

    @media (max-width: 760px) {
      .post-prompt-fields {
        grid-template-columns: 1fr;
      }
    }

</style>
</head>
<body>
<div class="shell">
  <aside class="sidebar">
    <div class="brand"><h1>MCP Shopee - Khải Hoàn</h1><p>Giải pháp đồng bộ sản phẩm Notion & Telegram thông minh.</p></div>
    <div class="nav">
      <div class="active"><span>Bảng điều khiển</span><span>Live</span></div>
      <div><span>Thư mục sản phẩm</span><span id="navFolders">0</span></div>
      <div><span>Google Drive</span><span id="navDrive">...</span></div>
      <div><span>Pixel ADB</span><span id="navAdb">...</span></div>
    </div>
  </aside>
  <main class="main" style="display: flex; flex-direction: column;">
    <div id="captureDashboard" style="display: block; width: 100%;">
      <header class="topbar">
        <div style="display: flex; align-items: center; gap: 12px; cursor: pointer;" onclick="showCaptureDashboard()">
          <img src="/favicon.ico" style="width: 44px; height: 44px; border-radius: 50%; border: 1.5px solid var(--brand); box-shadow: 0 0 10px var(--brand-glow); background: #fff;" />
          <div>
            <h2 style="font-size: 19px; font-weight: 800; font-family: var(--font-title); display: flex; align-items: center; gap: 6px; margin: 0; text-transform: uppercase; letter-spacing: 0.5px;">MCP Shopee Khải Hoàn</h2>
          </div>
        </div>
        <div class="nav-tabs">
          <span class="nav-tab nav-tab-capture active" onclick="showCaptureDashboard()"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 4px;"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"></path><circle cx="12" cy="13" r="4"></circle></svg>Chụp &amp; Quay</span>
          <span class="nav-tab nav-tab-shopee" onclick="showShopeeSyncDashboard()"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 4px;"><path d="M6 2L3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z"></path><line x1="3" y1="6" x2="21" y2="6"></line><path d="M16 10a4 4 0 0 1-8 0"></path></svg>Đồng bộ Shopee</span>
          <span class="nav-tab nav-tab-poster" onclick="showPosterDashboard()"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 4px;"><path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z"/></svg>AI Edit/Video</span>
        </div>
        <div class="actions" style="display: flex; align-items: center; gap: 10px;">
          <!-- Dropdown 1: Thiết bị & Hệ thống -->
          <div class="dropdown">
            <button class="secondary" style="font-size: 12px; font-weight: 600; min-height: 34px; display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px; border-radius: 6px;">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>
              Hệ thống
              <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" style="opacity: 0.7; margin-left: 2px;"><polyline points="6 9 12 15 18 9"/></svg>
            </button>
            <div class="dropdown-content">
              <button id="updateAppBtn" onclick="checkAppUpdate(false)" style="">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/></svg>
                Cập nhật: <span id="updateAppText">v1.1.0</span>
              </button>
              <button id="themeToggleBtn" onclick="toggleTheme()">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"></circle><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>
                Giao diện Sáng/Tối
              </button>
              <button onclick="refresh()">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/></svg>
                Làm mới trang
              </button>
              <hr style="border: 0; border-top: 1px solid var(--line); margin: 4px 0;" />
              <button onclick="togglePixelScreen()">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M18.36 6.64a9 9 0 1 1-12.73 0"></path><line x1="12" y1="2" x2="12" y2="12"></line></svg>
                Bật/Tắt màn hình Pixel
              </button>
              <button id="previewBtn" onclick="togglePreview()">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="3" width="20" height="14" rx="2" ry="2"></rect><line x1="8" y1="21" x2="16" y2="21"></line><line x1="12" y1="17" x2="12" y2="21"></line></svg>
                <span id="previewBtnText">Xem Pixel</span>
              </button>
            </div>
          </div>

          <div style="width: 1px; height: 16px; background: var(--line); margin: 0 4px;"></div>

          <!-- Các nút tác vụ chính -->
          <button class="btn-capture" onclick="capture()" style="min-height: 34px; padding: 4px 12px; border-radius: 6px; font-size: 12.5px;" title="Chụp ảnh sản phẩm">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"></path><circle cx="12" cy="13" r="4"></circle></svg>
            Chụp ảnh
          </button>
          <button class="btn-record" onclick="record()" style="min-height: 34px; padding: 4px 12px; border-radius: 6px; font-size: 12.5px;" title="Quay video sản phẩm">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="23 7 16 12 23 17 23 7"></polygon><rect x="1" y="5" width="15" height="14" rx="2" ry="2"></rect></svg>
            Quay video
          </button>
          <button id="btnStop" class="btn-stop" onclick="stopOperation()" style="min-height: 34px; padding: 4px 12px; border-radius: 6px; font-size: 12.5px;" title="Dừng tác vụ hiện tại">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="4" width="16" height="16" rx="2" ry="2"></rect></svg>
            Dừng
          </button>
        </div>
      </header>
      <div class="content">
        <div class="workspace">
        <div class="work-main">
        <section class="metrics">
          <div class="metric"><small>Pixel ADB</small><strong id="adbMetric"><span class="badge warn">Đang kiểm tra</span></strong></div>
          <div class="metric"><small>Thư mục Drive</small><strong id="driveMetric"><span class="badge warn">Đang kiểm tra</span></strong></div>
          <div class="metric"><small>Thư mục đang chọn</small><strong id="selectedMetric">Chưa chọn</strong></div>
          <div class="metric"><small>Số thư mục sản phẩm</small><strong id="folderMetric">0</strong></div>
          <div class="metric"><small>Trạng thái tác vụ</small><strong id="busyMetric"><span class="badge ok">Sẵn sàng</span></strong></div>
        </section>

        <section class="layout">
          <div class="panel">
            <div class="panel-head"><h3>Thư mục Google Drive</h3><p>App ghi file trực tiếp vào thư mục Google Drive for desktop đang đồng bộ trên máy tính.</p></div>
            <div class="panel-body">
              <div class="field-action">
                <div><label for="driveRoot">Đường dẫn thư mục chính</label><input id="driveRoot" value="G:\My Drive\Hình ảnh Shopee"></div>
                <button onclick="saveDriveRoot()">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"></path><polyline points="17 21 17 13 7 13 7 21"></polyline><polyline points="7 3 7 8 15 8"></polyline></svg>
                  Lưu & quét lại
                </button>
              </div>
              <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin: 12px 0 10px;">
                <!-- Cột 1: Shop Shopee & Nguồn Notion -->
                <div style="display: flex; flex-direction: column; justify-content: space-between; gap: 10px; background: rgba(255,255,255,0.02); padding: 12px 14px; border-radius: 8px; border: 1px solid var(--panel-border);">
                  <div>
                    <label for="shopSelect" style="font-weight: 700; font-size: 12.5px; margin-bottom: 6px; display: block;">Shop Shopee</label>
                    <select id="shopSelect" onchange="changeShop()" style="width: 100%; min-height: 38px; font-weight: 600;">
                      <option value="nhathuockh.pharma">nhathuockh.pharma</option>
                      <option value="khaihoanpharmacy">khaihoanpharmacy</option>
                    </select>
                  </div>
                  <button class="md3-btn-primary" onclick="openNotionInsightModal()" style="width: 100%; min-height: 38px; padding: 0 16px; font-weight: 700; font-size: 12.5px; display: inline-flex; align-items: center; justify-content: center; gap: 6px; white-space: nowrap; background: linear-gradient(135deg, #059669, #10b981); color: #fff; border: none; border-radius: 8px; cursor: pointer; box-shadow: 0 2px 8px rgba(16, 185, 129, 0.25);" title="Quét bài viết từ Notion và tự tạo cấu trúc thư mục Insight trên Drive">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon></svg>
                    Quét Notion &amp; Tạo Thư Mục
                  </button>
                </div>

                <!-- Cột 2: Thư mục sản phẩm & Thao tác -->
                <div style="display: flex; flex-direction: column; justify-content: space-between; gap: 10px; background: rgba(255,255,255,0.02); padding: 12px 14px; border-radius: 8px; border: 1px solid var(--panel-border);">
                  <div>
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                      <label for="folderSelect" style="margin: 0; font-weight: 700; font-size: 12.5px;">Thư mục sản phẩm</label>
                      <button class="ghost" id="btnCopyFolderPath" onclick="copyCurrentFolderPath()" style="min-height: auto; padding: 3px 8px; font-size: 11px; display: inline-flex; align-items: center; gap: 4px; background: rgba(45, 212, 191, 0.08); border: 1px solid rgba(45, 212, 191, 0.2); color: var(--brand); font-weight: 700; cursor: pointer; border-radius: 4px;" title="Sao chép đường dẫn thư mục sản phẩm (bao gồm shop)">
                        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"></path><rect x="8" y="2" width="8" height="4" rx="1" ry="1"></rect></svg>
                        Copy đường dẫn
                      </button>
                    </div>
                    <select id="folderSelect" onchange="selectFolder()" style="width: 100%; min-height: 38px; font-weight: 600;"><option value="">-- Chưa chọn thư mục --</option></select>
                  </div>
                  <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
                    <button class="secondary" onclick="scanFolders()" style="min-height: 38px; padding: 0 10px; font-size: 12px; font-weight: 600; display: inline-flex; align-items: center; justify-content: center; gap: 6px; border-radius: 8px; cursor: pointer;">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
                      Quét lại
                    </button>
                    <button class="danger" onclick="deleteFolder()" style="min-height: 38px; padding: 0 10px; font-size: 12px; font-weight: 600; display: inline-flex; align-items: center; justify-content: center; gap: 6px; border-radius: 8px; cursor: pointer;">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg>
                      Xóa thư mục
                    </button>
                  </div>
                </div>
              </div>
              <div class="hint">Bắt buộc chọn đúng thư mục sản phẩm trước khi chụp hoặc quay. App không tự phân loại và không tự tạo album Google Photos.</div>
            </div>
          </div>
          <aside class="panel">
            <div class="panel-head"><h3>Quy trình vận hành</h3><p>Luồng đơn giản, phù hợp xử lý số lượng lớn.</p></div>
            <div class="panel-body steps">
              <div class="step"><span>1</span><div><b>Tạo hoặc chọn thư mục</b><small>Chọn đúng tên sản phẩm trong Drive.</small></div></div>
              <div class="step"><span>2</span><div><b>Điều chỉnh góc máy</b><small>Mở xem màn hình Pixel trước khi thao tác.</small></div></div>
              <div class="step"><span>3</span><div><b>Chụp hoặc quay</b><small>File được chép vào Drive, kiểm tra và xóa khỏi Pixel.</small></div></div>
            </div>
          </aside>
        </section>

        <section class="panel">
          <div class="panel-head"><h3>Cấu hình hệ thống & kết nối</h3><p>Thiết lập thời lượng quay video và phương thức kết nối điều khiển Pixel.</p></div>
          <div class="panel-body">
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 24px;">
              <div>
                <label for="duration">Thời lượng video (giây)</label>
                <input id="duration" type="number" min="1" max="300" value="10">
                <div class="hint" style="margin-top: 6px;">Giới hạn từ 1 đến 300 giây cho mỗi lần quay.</div>
              </div>
              <div>
                <label for="connMode">Kiểu kết nối Pixel</label>
                <select id="connMode" onchange="changeConnMode()">
                  <option value="usb">🔌 Cắm cáp USB vật lý</option>
                  <option value="wifi">📶 Kết nối Wi-Fi không dây</option>
                </select>

                <div id="wifiIpGroup" style="margin-top: 12px; display: none;">
                  <label for="wifiIp">Địa chỉ IP của Pixel (Wi-Fi)</label>
                  <div class="field-action">
                    <input id="wifiIp" placeholder="Ví dụ: 192.168.1.18">
                    <button class="secondary" onclick="detectPixelIp()" title="Dò tìm IP tự động khi đang cắm cáp USB">
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
                      Quét IP (USB)
                    </button>
                    <button onclick="saveConnSettings()">Kết nối Wifi</button>
                  </div>
                  <div class="hint" style="margin-top: 6px;">Cắm cáp USB rồi bấm "Quét IP (USB)" để tự động dò IP, sau đó bấm "Kết nối Wifi" và rút cáp ra.</div>
                </div>
              </div>
              <div>
                <label for="adbPathInput">Đường dẫn thư mục ADB (platform-tools)</label>
                <div class="field-action" style="margin-bottom: 12px;">
                  <input id="adbPathInput" placeholder="Ví dụ: E:\platform-tools" style="width: 100%;">
                </div>

                <label for="scrcpyPathInput" style="display: block;">Đường dẫn thư mục Scrcpy</label>
                <div class="field-action">
                  <input id="scrcpyPathInput" placeholder="Ví dụ: E:\scrcpy-win64-v4.0" style="width: 100%;">
                  <button onclick="saveToolPaths()">Lưu</button>
                </div>
                <div class="hint" style="margin-top: 6px;">Điền thư mục chứa file adb.exe và scrcpy.exe rồi bấm "Lưu".</div>
              </div>
            </div>
          </div>
        </section>
        </div>

        <aside class="panel work-log">
          <div class="panel-head"><h3>Nhật ký xử lý</h3><p>Theo dõi từng bước: chụp/quay, kéo file, chép vào Drive và xóa khỏi Pixel.</p></div>
          <div class="panel-body">
            <div class="buttons"><button class="ghost" onclick="clearLog()"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>Xóa log</button></div>
            <div class="logbox">
              <div class="loghead"><span>Event stream</span><span id="logCount">0 events</span></div>
              <div id="log" class="log"></div>
            </div>
          </div>
        </aside>
        </div>
      </div>
    </div>

    <!-- AI Poster Generator Tab (Content Helper Tool) -->
    <div id="posterDashboard" style="display: none; flex-direction: column; width: 100%;">
      <header class="topbar">
        <div style="display: flex; align-items: center; gap: 12px; cursor: pointer;" onclick="showCaptureDashboard()">
          <img src="/favicon.ico" style="width: 44px; height: 44px; border-radius: 50%; border: 1.5px solid var(--brand); box-shadow: 0 0 10px var(--brand-glow); background: #fff;" />
          <div>
            <h2 style="font-size: 19px; font-weight: 800; font-family: var(--font-title); display: flex; align-items: center; gap: 6px; margin: 0; text-transform: uppercase; letter-spacing: 0.5px;">MCP Shopee Khải Hoàn</h2>
          </div>
        </div>
        <div class="nav-tabs">
          <span class="nav-tab nav-tab-capture" onclick="showCaptureDashboard()"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 4px;"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"></path><circle cx="12" cy="13" r="4"></circle></svg>Chụp &amp; Quay</span>
          <span class="nav-tab nav-tab-shopee" onclick="showShopeeSyncDashboard()"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 4px;"><path d="M6 2L3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z"></path><line x1="3" y1="6" x2="21" y2="6"></line><path d="M16 10a4 4 0 0 1-8 0"></path></svg>Đồng bộ Shopee</span>
          <span class="nav-tab nav-tab-poster active" onclick="showPosterDashboard()"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 4px;"><path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z"/></svg>AI Edit/Video</span>
        </div>
        <div class="actions" style="display: flex; gap: 12px; align-items: center; flex-wrap: wrap;">
          <!-- ChatGPT Chrome Debug Status -->
          <div style="display: flex; align-items: center; gap: 6px;">
            <div id="chromeStatusBadge" class="badge danger" style="padding: 6px 12px; font-weight: 700; font-size: 11px; display: flex; align-items: center; gap: 4px; border-radius: 6px;">
              <span id="chromeStatusText">ChatGPT Chrome: Offline</span>
            </div>
            <button type="button" class="btn-capture" onclick="startChromeDebug()" style="min-height: 32px; padding: 4px 10px; font-size: 11px; background: var(--brand); border-radius: 6px; font-weight: 700;">
              Mở ChatGPT
            </button>
          </div>
          <!-- Gemini Chrome Debug Status -->
          <div style="display: flex; align-items: center; gap: 6px;">
            <div id="geminiStatusBadge" class="badge danger" style="padding: 6px 12px; font-weight: 700; font-size: 11px; display: flex; align-items: center; gap: 4px; border-radius: 6px;">
              <span id="geminiStatusText">Gemini Chrome: Offline</span>
            </div>
            <button type="button" class="btn-capture" onclick="startChromeGemini()" style="min-height: 32px; padding: 4px 10px; font-size: 11px; background: linear-gradient(135deg, #a855f7 0%, #7c3aed 100%); border-radius: 6px; font-weight: 700; border: none; box-shadow: 0 2px 8px rgba(124, 58, 237, 0.2);">
              Mở Gemini
            </button>
          </div>
        </div>
      </header>

      <div class="content" style="padding: 0; display: grid; grid-template-columns: 320px 1fr 450px; gap: 20px; width: 100%; align-items: start; max-width: 1840px;">
        <!-- Cột 1: Thư viện Prompt (Prompts Library) -->
        <aside class="panel" style="display: flex; flex-direction: column; gap: 16px; padding: 20px; height: 1040px;">
          <div style="display: flex; flex-direction: column; gap: 12px; border-bottom: 1px solid var(--panel-border); padding-bottom: 12px; width: 100%;">
            <h4 style="margin: 0; font-family: var(--font-title); font-weight: 800; font-size: 16px; text-align: center; width: 100%;">Thư viện Prompt</h4>
            <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; width: 100%;">
              <button class="ghost" onclick="triggerImportPrompt()" style="padding: 6px 4px; font-size: 11px; color: var(--ok); font-weight: 700; background: rgba(16, 185, 129, 0.05); border: 1px solid rgba(16, 185, 129, 0.15); cursor: pointer; min-height: 36px; border-radius: 6px; text-align: center; display: inline-block; width: 100%; box-shadow: none;" title="Nhập danh sách prompt tạo ảnh từ file .txt"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="display:inline-block; vertical-align:middle; margin-right:4px;"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>Nhập file</button>
              <button class="ghost" onclick="exportPrompts()" style="padding: 6px 4px; font-size: 11px; color: var(--primary); font-weight: 700; background: rgba(59, 130, 246, 0.05); border: 1px solid rgba(59, 130, 246, 0.15); cursor: pointer; min-height: 36px; border-radius: 6px; text-align: center; display: inline-block; width: 100%; box-shadow: none;" title="Xuất toàn bộ 5 prompt tạo ảnh ra file .txt"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="display:inline-block; vertical-align:middle; margin-right:4px;"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="17 8 12 3 7 8"></polyline><line x1="12" y1="3" x2="12" y2="15"></line></svg>Xuất file</button>
              <button class="ghost" onclick="openPromptModal()" style="padding: 6px 4px; font-size: 11px;  background: rgba(238, 77, 45, 0.05); border: 1px solid rgba(238, 77, 45, 0.15); cursor: pointer; min-height: auto; border-radius: 6px; text-align: center; display: inline-block; width: 100%; box-shadow: none;"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="display:inline-block; vertical-align:middle; margin-right:4px;"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>Thêm</button>
            </div>
          </div>
          <input type="file" id="promptImportInput" accept=".txt" onchange="handlePromptImport(event)" style="display: none;">

          <!-- Lọc danh mục -->
          <div style="display: flex; gap: 8px; align-items: center; width: 100%;">
            <select id="promptCategoryFilter" onchange="filterPromptsList()" style="font-size: 12px; min-height: 34px; flex: 1;">
              <option value="all">Tất cả danh mục</option>
            </select>
            <button class="ghost" onclick="openCategoryModal()" style="padding: 6px; min-height: 34px; display: flex; align-items: center; justify-content: center; cursor: pointer; border: 1px solid var(--panel-border); border-radius: 8px; background: none;" title="Quản lý danh mục">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="color: var(--muted);"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>
            </button>
          </div>

          <!-- Danh sách prompts -->
          <div id="promptsLibraryContainer" style="display: flex; flex-direction: column; gap: 8px; flex: 1; overflow-y: auto; padding-right: 4px;">
            <!-- Load động từ API -->
          </div>
        </aside>

        <!-- Cột 2: Bảng điều khiển và Soạn thảo (Control Panel) -->
        <main class="panel" style="display: flex; flex-direction: column; gap: 16px; padding: 20px; min-height: 1040px; height: 1040px; box-sizing: border-box;">
          <div style="border-bottom: 1px solid var(--panel-border); padding-bottom: 12px; margin-bottom: 4px;">
            <h4 style="margin: 0; font-family: var(--font-title); font-weight: 700; font-size: 15px;">Bảng Điều Khiển Gửi</h4>
          </div>

          <div style="display: grid; grid-template-columns: 1fr 1.25fr; gap: 20px; flex: 1; min-height: 0;">
            <!-- Cột con 2.1: Cấu hình và File -->
            <div style="display: flex; flex-direction: column; gap: 16px; min-width: 0;">
              <!-- Đường dẫn lưu ảnh kết quả -->
              <div>
                <label style="margin-bottom: 6px; display: block; font-weight: 600; font-size: 13px; color: var(--text);">Thư mục lưu ảnh kết quả</label>
                <div style="display: flex; gap: 8px;">
                  <input type="text" id="posterExportDir" placeholder="Mặc định: Downloads" onchange="onExportDirChange()" style="flex: 1; min-height: 36px; padding: 6px 12px; font-size: 13px; border-radius: 8px;">
                  <button type="button" class="secondary" onclick="browseExportDirectory()" style="min-height: 36px; padding: 0 14px; font-size: 12px; border-radius: 8px; font-weight: 600; cursor: pointer;">Chọn...</button>
                </div>
                <div style="display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 8px; margin-top: 10px;">
                  <select id="insightFolderSelect" onchange="selectInsightFolder()" style="font-size: 12px; min-height: 36px; border-radius: 8px; background: rgba(13, 17, 28, 0.4); border: 1px solid rgba(255, 255, 255, 0.08); color: var(--text); padding: 0 10px;">
                    <option value="">-- Quét để chọn Insight --</option>
                  </select>
                  <button type="button" class="secondary" onclick="scanInsightFolders()" style="min-height: 36px; padding: 0 12px; font-size: 12.5px; display: inline-flex; align-items: center; gap: 6px; font-weight: 700; border-radius: 8px; cursor: pointer;">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
                    Quét Insight
                  </button>
                </div>
                <div id="selectedInsightLabel" hidden style="margin-top: 7px; color: var(--muted); font-size: 11.5px; line-height: 1.45; overflow-wrap: anywhere;"></div>
              </div>

              <!-- File sản phẩm được chọn (Dropzone cao 140px) -->
              <div style="display: flex; flex-direction: column; gap: 6px;">
                <label style="margin-bottom: 6px; display: block; font-weight: 600; font-size: 13px; color: var(--text);">File sản phẩm thô (Ảnh/Video)</label>
                <div style="position: relative; width: 100%;">
                  <!-- Dropzone kéo thả/chọn file -->
                  <div id="contentImgDropzone" onclick="document.getElementById('contentImgFile').click()" style="border: 2px dashed var(--panel-border); border-radius: 12px; height: 140px; display: flex; flex-direction: column; align-items: center; justify-content: center; cursor: pointer; transition: all 0.3s; background: var(--soft); width: 100%;">
                    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color: var(--brand); margin-bottom: 8px;"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="17 8 12 3 7 8"></polyline><line x1="12" y1="3" x2="12" y2="15"></line></svg>
                    <span id="contentImgLabel" style="font-size: 13px; color: var(--text); text-align: center; padding: 0 15px; font-weight: 600;">Bấm hoặc Kéo thả ảnh/video sản phẩm</span>
                    <span style="font-size: 11px; color: var(--muted); margin-top: 4px;">Hỗ trợ ảnh JPG, PNG hoặc video</span>
                    <input type="file" id="contentImgFile" accept="image/*,video/*" style="display: none;" onchange="handleContentImageSelect(this.files)">
                  </div>
                  <!-- Preview Container -->
                  <div id="contentImgPreviewContainer" style="width: 100%; height: 140px; border-radius: 12px; border: 1px solid var(--panel-border); display: none; overflow: hidden; position: relative; background: var(--soft);">
                    <img id="contentImgPreview" src="" style="width: 100%; height: 100%; object-fit: contain; display: none;">
                    <video id="contentVideoPreview" src="" style="width: 100%; height: 100%; object-fit: contain; display: none;" autoplay loop muted playsinline></video>
                    <button type="button" onclick="clearContentImage()" style="position: absolute; top: 8px; right: 8px; background: rgba(0,0,0,0.7); border: none; border-radius: 50%; width: 24px; height: 24px; display: grid; place-items: center; color: #fff; cursor: pointer; font-size: 14px; z-index: 10; font-weight: bold;">×</button>
                  </div>
                </div>
                <!-- Nút lấy file Pixel mới nhất -->
                <button type="button" class="secondary" onclick="useLatestPixelPhoto()" style="width: 100%; min-height: 34px; font-size: 11px; margin-top: 4px; display: flex; align-items: center; justify-content: center; gap: 6px; font-weight: 700; border-radius: 8px;">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path><polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline><line x1="12" y1="22.08" x2="12" y2="12"></line></svg>
                  Lấy ảnh/video Pixel vừa chụp mới nhất
                </button>
              </div>

              <!-- File ảnh mẫu tham khảo (Dropzone cao 140px) -->
              <div style="display: flex; flex-direction: column; gap: 6px;">
                <label style="margin-bottom: 6px; display: block; font-weight: 600; font-size: 13px; color: var(--text);">Ảnh mẫu tham khảo phong cách (Tùy chọn)</label>
                <div style="display: flex; flex-direction: column; gap: 8px; width: 100%;">
                  <!-- Vùng hiển thị ảnh Preview (khi đã chọn/dán thành công) -->
                  <div id="sampleImgPreviewContainer" style="width: 100%; height: 140px; border-radius: 12px; border: 1px solid var(--panel-border); display: none; overflow: hidden; position: relative; background: var(--soft);">
                    <img id="sampleImgPreview" src="" style="width: 100%; height: 100%; object-fit: contain;">
                    <button type="button" onclick="clearSampleImage()" style="position: absolute; top: 8px; right: 8px; background: rgba(0,0,0,0.7); border: none; border-radius: 50%; width: 24px; height: 24px; display: grid; place-items: center; color: #fff; cursor: pointer; font-size: 14px; z-index: 10; font-weight: bold;">×</button>
                  </div>

                  <!-- Vùng chọn ảnh (chỉ hiển thị khi chưa có ảnh) -->
                  <div id="sampleImgSelectorContainer" style="display: flex; flex-direction: column; gap: 8px; width: 100%;">
                    <!-- Dropzone kéo thả/chọn file -->
                    <div id="sampleImgDropzone" onclick="document.getElementById('sampleImgFile').click()" style="border: 2px dashed var(--panel-border); border-radius: 12px; height: 140px; display: flex; flex-direction: column; align-items: center; justify-content: center; cursor: pointer; transition: all 0.3s; background: var(--soft); width: 100%;">
                      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color: var(--brand); margin-bottom: 8px;"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="17 8 12 3 7 8"></polyline><line x1="12" y1="3" x2="12" y2="15"></line></svg>
                      <span id="sampleImgLabel" style="font-size: 13px; color: var(--text); text-align: center; font-weight: 600;">Bấm hoặc Kéo thả ảnh mẫu tham khảo</span>
                      <input type="file" id="sampleImgFile" accept="image/*" style="display: none;" onchange="handleSampleImageSelect(this.files)">
                    </div>

                    <!-- Ô dán URL riêng biệt -->
                    <input type="text" id="sampleImgUrlInput" placeholder="Hoặc dán link URL ảnh mẫu vào đây..." oninput="handleSampleImageUrlChange(this.value)" style="width: 100%; height: 36px; font-size: 12px; border-radius: 8px; border: 1px solid rgba(255, 255, 255, 0.12); padding: 0 12px; outline: none; transition: border-color 0.2s;">
                  </div>
                </div>
              </div>
            </div>

            <!-- Cột con 2.2: Soạn thảo và Gửi -->
            <div style="display: flex; flex-direction: column; gap: 16px; min-width: 0;">
              <!-- Thông tin sản phẩm từ Notion (Cao 140px) -->
              <div style="display: flex; flex-direction: column; gap: 6px;">
                <label for="notionContentInput" style="font-weight: 600; font-size: 13px; color: var(--text);">Thông tin sản phẩm từ Notion</label>
                <textarea id="notionContentInput" placeholder="Dán nội dung thuộc tính từ Notion..." style="width: 100%; height: 140px; min-height: 140px; resize: none; font-size: 12.5px; line-height: 1.45; border-radius: 8px; padding: 10px;"></textarea>
              </div>

              <!-- Từ khóa chính của insight -->
              <div style="display: flex; flex-direction: column; gap: 6px;">
                <label for="keywordsInput" style="font-weight: 600; font-size: 13px; color: var(--text);">Từ khóa chính của insight</label>
                <input type="text" id="keywordsInput" placeholder="Ví dụ: trẻ trung, sang trọng, năng động..." style="width: 100%; min-height: 36px; padding: 6px 12px; font-size: 12.5px; border-radius: 8px;">
              </div>

              <!-- Nội dung Prompt soạn thảo (Cao 310px) -->
              <div style="display: flex; flex-direction: column; gap: 6px; flex: 1; min-height: 0;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 2px;">
                  <label for="contentEditorPrompt" style="font-weight: 600; font-size: 13px; color: var(--text); margin: 0;">Nội dung Prompt</label>
                  <button class="ghost" onclick="exportCurrentPrompt()" style="padding: 2px 8px; font-size: 11px;  background: none; border: none; cursor: pointer; min-height: auto;" title="Tải nội dung prompt đang soạn thảo về file .txt">💾 Xuất file</button>
                </div>
                <textarea id="contentEditorPrompt" placeholder="Nhập yêu cầu bối cảnh ở đây hoặc click chọn từ thư viện bên trái..." style="width: 100%; height: 310px; min-height: 310px; resize: none; font-size: 13px; line-height: 1.5; border-radius: 8px; padding: 12px; flex: 1;"></textarea>
              </div>

              <!-- Khung gửi tin nhắn -->
              <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 4px;">
                <button class="btn-capture" id="btnSendToChatGPT" onclick="sendToChatGPT()" style="font-size: 13.5px; padding: 10px 16px; border-radius: 8px; font-weight: 700; display: flex; align-items: center; justify-content: center; gap: 8px; min-height: 40px;">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>
                  Gửi Lên ChatGPT
                </button>
                <button class="btn-capture" id="btnSendToGemini" onclick="sendToGemini()" style="font-size: 13.5px; padding: 10px 16px; border-radius: 8px; font-weight: 700; display: flex; align-items: center; justify-content: center; gap: 8px; background: linear-gradient(135deg, #a855f7 0%, #7c3aed 100%); box-shadow: 0 4px 12px rgba(124, 58, 237, 0.3); border: none; min-height: 40px;">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>
                  Gửi Lên Gemini
                </button>
              </div>

              <!-- Nút lấy ảnh thủ công từ tab ChatGPT khi cần -->
              <button class="secondary" id="btnCaptureCurrentChatGPT" onclick="captureCurrentChatGPTImage()" style="margin-top: 6px; width: 100%; font-size: 12.5px; padding: 8px 14px; border-radius: 8px; font-weight: 700; display: flex; align-items: center; justify-content: center; gap: 8px; background: rgba(56, 189, 248, 0.12); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.4); cursor: pointer;" title="Lấy ngay ảnh DALL-E đang hiển thị trên tab ChatGPT lưu vào đúng thư mục máy tính">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"></path><circle cx="12" cy="13" r="4"></circle></svg>
                📸 Lấy ảnh từ tab ChatGPT về máy (Lưu file)
              </button>
            </div>
          </div>
        </main>

        <!-- Cột 3: Danh sách ảnh kết quả tải về (Results Panel & Log) -->
        <aside class="panel" style="display: flex; flex-direction: column; gap: 16px; padding: 20px; height: 1040px;">
          <div style="border-bottom: 1px solid var(--panel-border); padding-bottom: 12px; display: flex; justify-content: space-between; align-items: center;">
            <h4 style="margin: 0; font-family: var(--font-title); font-weight: 700; font-size: 15px;">Ảnh kết quả</h4>
            <div style="display: flex; gap: 8px;">
              <button class="ghost" onclick="clearToolCache()" style="padding: 4px 8px; font-size: 12px; color: var(--danger); background: none; border: none; cursor: pointer; font-weight: 700; min-height: auto;" title="Xóa toàn bộ ảnh tạm và ảnh kết quả cũ">Xóa cache</button>
              <button class="ghost" onclick="loadDownloadedImages()" style="padding: 4px 8px; font-size: 12px; color: var(--brand); background: none; border: none; cursor: pointer; font-weight: 700; min-height: auto;">Làm mới</button>
            </div>
          </div>

          <!-- Khung danh sách ảnh kết quả (nửa trên) -->
          <div id="downloadedImagesList" style="height: 600px; overflow-y: auto; display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; align-content: start; padding-right: 4px;">
            <!-- Load động từ API -->
          </div>

          <!-- Khung Realtime Log (nửa dưới) -->
          <div style="display: flex; flex-direction: column; height: 320px; border-top: 1px solid var(--panel-border); padding-top: 16px;">
            <label style="margin-bottom: 8px; font-size: 13px; font-weight: 600; color: var(--text); text-transform: uppercase;">Nhật ký tiến trình (Realtime Log)</label>
            <div id="automationLogBox" style="flex: 1; background: #030712; border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px; padding: 12px; font-family: 'Cascadia Mono', Consolas, monospace; font-size: 11px; overflow-y: auto; color: #f3f4f6; line-height: 1.5; height: 260px; box-shadow: inset 0 4px 12px rgba(0, 0, 0, 0.5);">
              Chưa có hoạt động nào. Hãy kết nối Chrome và gửi ảnh để bắt đầu.
            </div>
          </div>
        </aside>
      </div>
    </div>

    <!-- Shopee Notion to BigSeller Auto Sync Tab -->
    <div id="shopeeSyncDashboard" style="display: none; flex-direction: column; width: 100%;">
      <header class="topbar">
        <div style="display: flex; align-items: center; gap: 12px; cursor: pointer;" onclick="showCaptureDashboard()">
          <img src="/favicon.ico" style="width: 44px; height: 44px; border-radius: 50%; border: 1.5px solid var(--brand); box-shadow: 0 0 10px var(--brand-glow); background: #fff;" />
          <div>
            <h2 style="font-size: 19px; font-weight: 800; font-family: var(--font-title); display: flex; align-items: center; gap: 6px; margin: 0; text-transform: uppercase; letter-spacing: 0.5px;">MCP Shopee Khải Hoàn</h2>
          </div>
        </div>
        <div class="nav-tabs">
          <span class="nav-tab nav-tab-capture" onclick="showCaptureDashboard()"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 4px;"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"></path><circle cx="12" cy="13" r="4"></circle></svg>Chụp &amp; Quay</span>
          <span class="nav-tab nav-tab-shopee active" onclick="showShopeeSyncDashboard()"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 4px;"><path d="M6 2L3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z"></path><line x1="3" y1="6" x2="21" y2="6"></line><path d="M16 10a4 4 0 0 1-8 0"></path></svg>Đồng bộ Shopee</span>
          <span class="nav-tab nav-tab-poster" onclick="showPosterDashboard()"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 4px;"><path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z"/></svg>AI Edit/Video</span>
        </div>
        <div class="actions" style="display: flex; gap: 12px; align-items: center;">
          <div id="shopeeBotStatusBadge" class="badge danger" style="padding: 6px 12px; font-weight: 700; font-size: 11px; display: flex; align-items: center; gap: 4px; border-radius: 6px;">
            <span id="shopeeBotStatusText">Bot Telegram: OFFLINE</span>
          </div>
          <button type="button" id="btnToggleShopeeBot" class="md3-btn-primary" onclick="toggleShopeeBot()" style="padding: 6px 12px; font-size: 11px; min-height: 32px; border-radius: 6px;">
            Khởi động Bot
          </button>
          <button type="button" id="btnToggleConfig" class="md3-btn-secondary" onclick="toggleConfigColumn()" style="padding: 6px 12px; font-size: 11px; min-height: 32px; border-radius: 6px;" title="Ẩn/Hiện cấu hình">
            Cấu hình
          </button>
        </div>
      </header>

      <div class="workspace" style="display: flex; gap: 20px; width: 100%; max-width: 1840px; margin: 0 auto; align-items: start;">

        <!-- Cột 1: Danh sách sản phẩm từ Shopee Insight Library -->
        <aside class="panel" style="display: flex; flex-direction: column; gap: 12px; padding: 16px; min-width: 320px; max-width: 320px; min-height: 650px; max-height: calc(100vh - 100px); position: sticky; top: 16px; box-sizing: border-box;">
          <div style="display: flex; flex-direction: column; gap: 8px; border-bottom: 1px solid var(--panel-border); padding-bottom: 10px; width: 100%;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <h4 style="margin: 0; font-family: var(--font-title); font-weight: 800; font-size: 15px;">Sản phẩm Notion</h4>
              <button class="ghost" onclick="loadPendingProducts()" style="padding: 4px 10px; font-size: 11px; background: var(--soft); border: 1px solid var(--panel-border); cursor: pointer; border-radius: 6px;" title="Tải lại danh sách từ Notion">🔄 Quét lại</button>
            </div>
            <div style="display: flex; gap: 6px; align-items: center; flex-direction: column;">
              <select id="shopeeShopFilter" onchange="filterShopeeProductsByShop(this.value)" style="width: 100%; padding: 6px 10px; font-size: 12px; border-radius: 6px; background: var(--soft); border: 1px solid var(--panel-border); color: var(--text);">
                <option value="">-- Tất cả Shop --</option>
                <option value="nhathuockh.pharma">nhathuockh.pharma</option>
                <option value="khaihoanpharmacy">khaihoanpharmacy</option>
              </select>
              <select id="shopeeStatusFilter" onchange="filterShopeeProductsByStatus(this.value)" style="width: 100%; padding: 6px 10px; font-size: 12px; border-radius: 6px; background: var(--soft); border: 1px solid var(--panel-border); color: var(--text); font-weight: 600;">
                <option value="">-- Tất cả trạng thái --</option>
                <option value="Chờ đăng">⏳ Chờ đăng (Ưu tiên duyệt)</option>
                <option value="Đã đăng">✅ Đã đăng</option>
                <option value="Lên đơn">📝 Lên đơn</option>
                <option value="Chưa đặt">⚪ Chưa đặt</option>
              </select>
            </div>
            <input type="text" id="shopeeProductSearchInput" oninput="filterShopeeProductsBySearch(this.value)" placeholder="🔍 Tìm kiếm sản phẩm..." style="width: 100%; padding: 6px 10px; font-size: 12px; border-radius: 6px; background: var(--soft); border: 1px solid var(--panel-border); color: var(--text); box-sizing: border-box;">
          </div>

          <!-- Select ẩn phục vụ logic JS hiện tại -->
          <select id="shopeePendingProducts" style="display: none;" onchange="onSelectPendingProduct(this.value)">
            <option value="">-- Chọn sản phẩm --</option>
          </select>

          <!-- Danh sách items trực quan -->
          <div id="shopeePendingProductsList" style="display: flex; flex-direction: column; gap: 8px; flex: 1; overflow-y: auto; padding-right: 4px;">
            <div style="padding: 12px; color: var(--muted); font-size:12.5px; text-align:center;">Đang tải danh sách...</div>
          </div>
        </aside>

        <!-- Cột chính (Giữa và Phải) -->
        <div style="flex: 1; display: flex; flex-direction: column; gap: 20px; min-width: 0;">

          <!-- Cấu hình kết nối Notion / Telegram / API (Cột ẩn/hiện, mặc định ẩn) -->
          <div id="configSectionWrapper" style="display: none; flex-direction: column; gap: 16px; width: 100%; transition: all 0.3s ease;">
            <section class="panel">
              <div class="panel-head" style="padding: 14px 20px; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px;">
                <div>
                  <h4 style="margin: 0; font-family: var(--font-title); font-weight: 700; font-size: 14px;">Cấu hình Notion & Telegram</h4>
                  <p style="margin: 4px 0 0; font-size: 12px; color: var(--muted);">Nhập thông tin kết nối hoặc nạp nhanh từ file <code>đồng bộ shopee.txt</code> / <code>.env</code></p>
                </div>
                <div style="display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
                  <input type="file" id="configFileInput" accept=".txt,.env,.json" style="display: none;" onchange="handleConfigFileUpload(this.files)">
                  <button type="button" class="secondary" onclick="document.getElementById('configFileInput').click()" style="min-height: 34px; padding: 0 12px; font-size: 12px; border-radius: 8px; font-weight: 600; display: inline-flex; align-items: center; gap: 6px; cursor: pointer;">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="17 8 12 3 7 8"></polyline><line x1="12" y1="3" x2="12" y2="15"></line></svg>
                    📂 Nhập file .txt
                  </button>
                  <button type="button" class="secondary" onclick="openPasteConfigModal()" style="min-height: 34px; padding: 0 12px; font-size: 12px; border-radius: 8px; font-weight: 600; display: inline-flex; align-items: center; gap: 6px; cursor: pointer;">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"></path><rect x="8" y="2" width="8" height="4" rx="1" ry="1"></rect></svg>
                    📋 Dán nội dung
                  </button>
                  <button type="button" class="secondary" onclick="exportConfigFile()" style="min-height: 34px; padding: 0 12px; font-size: 12px; border-radius: 8px; font-weight: 600; display: inline-flex; align-items: center; gap: 6px; cursor: pointer;" title="Xuất file mẫu cấu hình .txt">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
                    📥 Xuất file .txt
                  </button>
                </div>
              </div>
              <div class="panel-body" style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 14px; padding: 16px;">
                <div>
                  <label for="shopeeNotionToken" class="md3-label">Notion Integration Token (NOTION_TOKEN)</label>
                  <input id="shopeeNotionToken" class="md3-input" type="password" placeholder="ntn_...">
                </div>
                <div>
                  <label for="shopeeNotionDbId" class="md3-label">Notion Database ID (NOTION_DATABASE_ID)</label>
                  <input id="shopeeNotionDbId" class="md3-input" type="text" placeholder="Ví dụ: ca055a7742824b9598abde7a7686d144">
                </div>
                <div>
                  <label for="shopeeTelegramToken" class="md3-label">Telegram Bot Token (TELEGRAM_BOT_TOKEN)</label>
                  <input id="shopeeTelegramToken" class="md3-input" type="password" placeholder="Mã token của Bot Telegram...">
                </div>
                <div>
                  <label for="shopeeManagerChatId" class="md3-label">Manager Chat ID (MANAGER_CHAT_ID)</label>
                  <input id="shopeeManagerChatId" class="md3-input" type="text" placeholder="ID người quản lý nhận thông báo...">
                </div>
                <div class="field-span-2">
                  <label for="shopeeDriveRootId" class="md3-label">Google Drive Root ID (DRIVE_ROOT_FOLDER_ID)</label>
                  <input id="shopeeDriveRootId" class="md3-input" type="text" placeholder="Ví dụ: 1XrOmOCqdZ3xfkeVaBc0Vr77Q7yRW0PxZ">
                </div>
                <div class="field-span-2">
                  <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                    <label for="shopeeGeminiApiKey" class="md3-label" style="margin: 0;">Gemini API Key (Mặc định Gemini 3.7 Flash)</label>
                    <span id="geminiKeyStatus" style="font-size: 12px; font-weight: 600;"></span>
                  </div>
                  <div class="field-action" style="display: flex; gap: 8px; align-items: center;">
                    <input id="shopeeGeminiApiKey" class="md3-input" type="password" placeholder="Nhập API Key Gemini (AIzaSy...) hoặc OpenAI (sk-...)" style="flex: 1;">
                    <button type="button" id="btnTestGemini" onclick="testGeminiApiKey()" class="secondary" style="min-height: 40px; padding: 0 14px; font-size: 12.5px; font-weight: 600; white-space: nowrap; display: inline-flex; align-items: center; gap: 6px; cursor: pointer;">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>
                      Kiểm tra Key
                    </button>
                    <button onclick="saveShopeeConfig()" class="md3-btn-primary" style="min-height: 40px; padding: 0 18px; white-space: nowrap;">Lưu cấu hình</button>
                  </div>
                </div>
              </div>
            </section>
          </div>

          <!-- Hidden elements for complete JS backward compatibility -->
          <div style="display: none;">
            <select id="unifiedInsightTargetSelect"></select>
            <span id="unifiedProductShopBadge"></span>
            <span id="unifiedProductTitle"></span>
            <span id="unifiedInsightCountBadge"></span>
            <span id="unifiedProductMeta"></span>
            <span id="unifiedAdbBadge"></span>
            <span id="analyze-status"></span>
            <span id="prompt-status"></span>
            <input type="file" id="image">
            <input type="text" id="imageUrl">
            <input type="text" id="keywords">
            <textarea id="useCases"></textarea>
            <textarea id="insightPrompt"></textarea>
          </div>

          <!-- Bảng review insight (Full-width, trọng tâm chỉ để view bài và duyệt bài) -->
          <section class="panel result-panel" style="padding: 20px; margin-bottom: 0;">
            <div class="panel-head result-head" style="border-bottom: 1px solid var(--panel-border); padding-bottom: 12px; margin-bottom: 14px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px;">
              <div>
                <h4 style="margin: 0; font-family: var(--font-title); font-weight: 800; font-size: 16px;">Bảng xem bài viết &amp; Insight</h4>
                <p id="product-name" style="margin: 4px 0 0; font-size: 12.5px; color: var(--muted);">👈 Chọn sản phẩm từ danh sách bên trái</p>
              </div>
              <div style="display: flex; gap: 10px; align-items: center; flex-wrap: wrap;">
                <button type="button" id="btnPreviewPosts" class="secondary" onclick="openFullPostsEditorModal()" style="min-height: 36px; padding: 0 16px; font-weight: 700; font-size: 12.5px; display: inline-flex; align-items: center; gap: 8px; cursor: pointer; border-radius: 6px; background: rgba(56, 189, 248, 0.12); border: 1px solid rgba(56, 189, 248, 0.3); color: #38bdf8;">
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>
                  <span>Xem chi tiết bài viết</span>
                </button>
                <button type="button" class="ghost" onclick="refreshCurrentProductImages()" style="min-height: 36px; padding: 0 10px; font-size: 12px; border-radius: 6px; font-weight: 600; border: 1px solid var(--panel-border);" title="Quét lại ảnh trong các thư mục Insight">
                  🔄 Quét lại ảnh
                </button>
              </div>
            </div>

            <div id="empty-state" class="empty-state" style="padding: 30px; text-align: center; color: var(--muted); font-size: 13.5px; font-weight: 500;">
              👈 Chọn sản phẩm ở cột bên trái để xem nội dung bài viết và hình ảnh các Insight đã chuẩn bị sẵn từ Notion.
            </div>

            <form id="save-form" class="stack" onsubmit="saveInsightsToNotion(event)" hidden style="display: flex; flex-direction: column; gap: 16px;">
              <input type="hidden" id="productPageId" value="">
              <input type="hidden" id="productNameInput" value="">
              <input type="hidden" id="productPrice" value="">
              <input type="hidden" id="productClassification" value="">
              <input type="hidden" id="productVariants" value="">
              <div id="save-product-summary" class="summary-strip" style="display: flex; gap: 10px; flex-wrap: wrap; align-items: center;"></div>

              <div class="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th style="width: 44px; text-align: center;">#</th>
                      <th style="width: 140px;">Góc viết</th>
                      <th style="width: 220px;">Tiêu đề post</th>
                      <th style="min-width: 380px;">Nội dung bài viết</th>
                      <th style="width: 160px;">Từ khóa</th>
                      <th style="width: 190px;">Hình ảnh &amp; Thư mục</th>
                      <th style="width: 110px; text-align: center;">Chi tiết</th>
                    </tr>
                  </thead>
                  <tbody id="insight-table-body"></tbody>
                </table>
              </div>

              <div class="actions save-actions" style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; margin-top: 10px;">
                <div style="display: flex; align-items: center; gap: 8px;">
                  <span style="font-size: 12px; font-weight: 700; color: var(--muted);">Trạng thái Notion:</span>
                  <select id="quickNotionStatusSelect" onchange="changeCurrentProductNotionStatus(this.value)" style="padding: 6px 12px; border-radius: 6px; font-size: 12px; font-weight: 700; background: var(--soft); border: 1px solid var(--panel-border); color: var(--text);">
                    <option value="Chờ đăng">⏳ Chờ đăng</option>
                    <option value="Đã đăng">✅ Đã đăng</option>
                    <option value="Lên đơn">📝 Lên đơn</option>
                    <option value="Nội dung">✍️ Nội dung</option>
                    <option value="Hủy">❌ Hủy</option>
                  </select>
                  <span id="quickStatusSaveFeedback" style="font-size: 11.5px; font-weight: 600; color: #34d399;"></span>
                </div>
                <button id="save-button" class="md3-btn-primary" type="submit" style="min-height: 40px; padding: 0 24px; font-weight: 700; display: inline-flex; align-items: center; gap: 8px;">
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"></path><polyline points="17 21 17 13 7 13 7 21"></polyline><polyline points="7 3 7 8 15 8"></polyline></svg>
                  <span>Lưu bài viết vào Notion</span>
                </button>
              </div>
            </form>
          </section>

          <!-- Sync log + Excel list (2-col grid) -->
          <div style="display: grid; grid-template-columns: 1fr 340px; gap: 20px; align-items: start;">
            <!-- Sync Log Section -->
            <section class="panel" style="display: flex; flex-direction: column; padding: 20px; box-sizing: border-box;">
              <div class="panel-head" style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--panel-border); padding-bottom: 12px; margin-bottom: 16px;">
                <div>
                  <h4 style="margin: 0; font-family: var(--font-title); font-weight: 700; font-size: 15px;">Đồng bộ Notion sang BigSeller</h4>
                  <p style="margin: 4px 0 0; font-size: 12px; color: var(--muted); margin-bottom: 8px;">Khởi chạy tiến trình đồng bộ và xuất Excel thủ công.</p>
                  <div style="display: flex; flex-direction: column; gap: 4px; margin-bottom: 8px; max-width: 480px; width: 100%;">
                    <label class="md3-label" style="font-size: 11px; font-weight: 600; color: var(--text);">Link Google Drive thư mục sản phẩm (Cha) (Tùy chọn)</label>
                    <input type="text" id="shopeeSyncDriveUrl" placeholder="Ví dụ: https://drive.google.com/drive/folders/1aBcDeFg..." style="width: 100%; min-height: 32px; font-size: 11.5px; padding: 4px 10px; border-radius: 6px; border: 1px solid var(--panel-border); background: var(--bg-input); color: var(--text);" oninput="localStorage.setItem('shopee_sync_drive_url', this.value)">
                  </div>
                </div>
                <div style="display: flex; gap: 8px; align-self: flex-end;">
                  <button class="md3-btn-success" onclick="runShopeeSync()" style="padding: 9px 20px; font-size: 12.5px; white-space: nowrap; font-weight: 700; display: inline-flex; align-items: center; gap: 8px; background: linear-gradient(135deg, #059669, #10b981); box-shadow: 0 2px 8px rgba(16, 185, 129, 0.35); border-radius: 8px; cursor: pointer;" title="Xuất file Excel chuẩn BigSeller để đăng sàn">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="12" y1="18" x2="12" y2="12"></line><line x1="9" y1="15" x2="15" y2="15"></line></svg>
                    Xuất file Excel BigSeller
                  </button>
                </div>
              </div>
              <div style="flex: 1; display: flex; flex-direction: column; gap: 8px;">
                <div style="display: flex; justify-content: space-between; align-items: center; gap: 10px;">
                  <span class="md3-label" style="margin: 0;">Nhật ký Realtime</span>
                  <div style="display: flex; align-items: center; gap: 10px;">
                    <input type="text" id="shopeeSyncLogFilter" class="md3-input" oninput="filterShopeeSyncLogs()" placeholder="Lọc log..." style="width: 120px; padding: 4px 10px; font-size: 11px; min-height: unset; height: 26px;" />
                    <label style="display: inline-flex; align-items: center; gap: 4px; font-size: 11px; color: var(--muted); cursor: pointer; font-weight: 600; white-space: nowrap;">
                      <input type="checkbox" id="shopeeSyncLogAutoScroll" checked style="cursor: pointer; accent-color: var(--brand);" /> Tự cuộn
                    </label>
                    <span style="color: var(--panel-border); font-size: 11px;">|</span>
                    <button class="md3-btn-secondary" onclick="clearShopeeSyncLogs()" style="padding: 4px 12px; font-size: 11px; color: var(--danger); border-color: rgba(229, 115, 115, 0.2);" title="Xoá màn hình log">
                      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 2px;"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
                      Xoá log
                    </button>
                  </div>
                </div>
                <div id="shopeeSyncLogBox" style="height: 280px; background: #030712; border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 12px; padding: 14px; font-family: 'Cascadia Mono', Consolas, 'Courier New', monospace; font-size: 11px; line-height: 1.6; overflow-y: auto; color: #f3f4f6; box-shadow: inset 0 4px 12px rgba(0, 0, 0, 0.5);">
                  <!-- Log hiển thị thời gian thực -->
                </div>
              </div>
            </section>

            <!-- Excel List Section -->
            <aside class="panel" style="display: flex; flex-direction: column; gap: 12px; padding: 20px; box-sizing: border-box; height: 100%;">
              <div style="border-bottom: 1px solid var(--panel-border); padding-bottom: 12px; display: flex; justify-content: space-between; align-items: center;">
                <h4 style="margin: 0; font-family: var(--font-title); font-weight: 700; font-size: 15px;">Excel BigSeller đã tạo</h4>
                <div style="display: flex; gap: 6px; align-items: center;">
                  <button class="md3-btn-secondary" onclick="loadShopeeExcelList()" style="padding: 4px 12px; font-size: 11px;">Làm mới</button>
                  <span style="color: var(--panel-border); font-size: 11px;">|</span>
                  <button class="md3-btn-secondary" onclick="deleteShopeeExcelAll()" style="padding: 4px 12px; font-size: 11px; color: var(--danger); border-color: rgba(229, 115, 115, 0.2);">Xoá tất cả</button>
                </div>
              </div>
              <div id="shopeeExcelList" style="flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 10px; max-height: 280px;">
                <!-- Load động từ API -->
              </div>
            </aside>
          </div><!-- end sync-bottom-grid -->
        </div><!-- end col-2 main content -->
      </div><!-- end workspace -->
    </div>

  <!-- Modal Loading khi chọn sản phẩm từ Notion -->
  <div id="productLoadingModal" style="display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.65); backdrop-filter: blur(8px); z-index: 10000; align-items: center; justify-content: center; padding: 20px;">
    <div style="background: #0f172a; border: 1px solid rgba(56, 189, 248, 0.25); border-radius: 16px; padding: 28px 36px; display: flex; flex-direction: column; align-items: center; gap: 18px; box-shadow: 0 25px 60px rgba(0,0,0,0.85); max-width: 440px; width: 100%; text-align: center; animation: fadeInModal 0.25s ease;">
      <div style="position: relative; width: 52px; height: 52px; display: flex; align-items: center; justify-content: center;">
        <div style="width: 52px; height: 52px; border: 3.5px solid rgba(56,189,248,0.15); border-top-color: #38bdf8; border-radius: 50%; animation: spinProductLoading 0.75s linear infinite;"></div>
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#38bdf8" stroke-width="2.5" style="position: absolute;"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
      </div>
      <div>
        <h4 style="margin: 0; font-size: 16.5px; font-weight: 800; color: #ffffff; font-family: var(--font-title); letter-spacing: 0.2px;">Đang nạp dữ liệu từ Notion...</h4>
        <p id="productLoadingText" style="margin: 8px 0 0; font-size: 13px; color: #94a3b8; line-height: 1.5;">Đang tải toàn bộ bài viết, hashtag, các góc Insight và ảnh sản phẩm từ Google Drive. Vui lòng chờ...</p>
      </div>
      <div style="width: 100%; height: 3px; background: rgba(255,255,255,0.08); border-radius: 999px; overflow: hidden;">
        <div style="width: 100%; height: 100%; background: linear-gradient(90deg, #38bdf8, #818cf8); animation: shimmerProgress 1.4s infinite ease-in-out;"></div>
      </div>
    </div>
  </div>
  <style>
    @keyframes spinProductLoading {
      to { transform: rotate(360deg); }
    }
    @keyframes shimmerProgress {
      0% { transform: translateX(-100%); }
      100% { transform: translateX(100%); }
    }
    @keyframes fadeInModal {
      from { opacity: 0; transform: scale(0.96); }
      to { opacity: 1; transform: scale(1); }
    }
  </style>

  <!-- Modal Quét Notion Shopee Insight Library & Tạo Thư Mục -->
  <div id="notionInsightModal" style="display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.75); backdrop-filter: blur(8px); z-index: 9999; align-items: center; justify-content: center; padding: 20px;">
    <div style="background: #0f172a; border: 1px solid rgba(255,255,255,0.12); border-radius: 14px; max-width: 960px; width: 100%; max-height: 88vh; display: flex; flex-direction: column; box-shadow: 0 25px 60px rgba(0,0,0,0.8); overflow: hidden;">
      <!-- Modal Header -->
      <div style="padding: 16px 20px; border-bottom: 1px solid rgba(255,255,255,0.08); display: flex; align-items: center; justify-content: space-between; background: rgba(255,255,255,0.02);">
        <div style="display: flex; align-items: center; gap: 10px;">
          <div style="width: 32px; height: 32px; border-radius: 8px; background: rgba(16, 185, 129, 0.2); display: flex; align-items: center; justify-content: center; color: #10b981;">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon></svg>
          </div>
          <div>
            <h3 style="margin: 0; font-size: 16px; font-weight: 800; font-family: var(--font-title); color: #ffffff;">Quét Notion - Shopee Insight Library</h3>
            <p style="margin: 2px 0 0; font-size: 12px; color: #94a3b8;">Tự động quét số lượng Insight thực tế và tạo thư mục Drive chuẩn phân cấp theo Shop.</p>
          </div>
        </div>
        <button onclick="closeNotionInsightModal()" class="ghost" style="min-height: auto; padding: 6px 10px; font-size: 16px; cursor: pointer; border-radius: 6px; color: #94a3b8;">✕</button>
      </div>

      <!-- Modal Toolbar -->
      <div style="padding: 12px 20px; background: rgba(255,255,255,0.02); border-bottom: 1px solid rgba(255,255,255,0.08); display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px;">
        <div style="display: flex; align-items: center; gap: 10px;">
          <label style="font-size: 12.5px; font-weight: 700; margin: 0; white-space: nowrap; color: #f3f4f6;">Shop lưu ảnh trên Drive:</label>
          <select id="modalShopSelect" onchange="loadNotionInsightProducts()" style="padding: 6px 12px; border-radius: 6px; font-size: 12.5px; background: #1e293b; border: 1px solid rgba(255,255,255,0.15); color: #ffffff;">
            <option value="nhathuockh.pharma">nhathuockh.pharma</option>
            <option value="khaihoanpharmacy">khaihoanpharmacy</option>
          </select>
        </div>
        <div style="display: flex; gap: 8px;">
          <button class="secondary" onclick="loadNotionInsightProducts()" style="padding: 6px 14px; font-size: 12px; font-weight: 600; border-radius: 6px; cursor: pointer; display: inline-flex; align-items: center; gap: 6px; color: #f3f4f6;">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="23 4 23 10 17 10"></polyline><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path></svg>
            Quét lại Notion
          </button>
        </div>
      </div>

      <!-- Modal Body (Table) -->
      <div style="padding: 0; overflow-y: auto; flex: 1; background: #0b1120;">
        <table style="width: 100%; border-collapse: collapse; text-align: left; font-size: 13px;">
          <thead>
            <tr style="border-bottom: 1px solid rgba(255,255,255,0.1); background: #1e293b; color: #f1f5f9; font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;">
              <th style="padding: 12px 16px;">Tên sản phẩm & Chi tiết Insight</th>
              <th style="padding: 12px 16px; text-align: center; width: 95px;">Số Insight</th>
              <th style="padding: 12px 16px; text-align: center; width: 140px;">Trạng thái</th>
              <th style="padding: 12px 16px; text-align: center; width: 120px;">Thư mục / Drive</th>
              <th style="padding: 12px 16px; text-align: right; width: 170px;">Thao tác</th>
            </tr>
          </thead>
          <tbody id="notionInsightTableBody">
            <!-- Render dynamic rows here -->
          </tbody>
        </table>
      </div>

      <!-- Modal Footer -->
      <div style="padding: 12px 20px; border-top: 1px solid var(--panel-border); display: flex; justify-content: space-between; align-items: center; background: rgba(255,255,255,0.01);">
        <span style="font-size: 12px; color: var(--muted);">* Tạo thư mục sẽ tự tạo thư mục cha & các thư mục con theo tên Insight trên Notion, đồng thời cập nhật link Drive lên Notion.</span>
        <button class="secondary" onclick="closeNotionInsightModal()" style="padding: 6px 18px; font-size: 12.5px; border-radius: 6px; cursor: pointer;">Đóng</button>
      </div>
    </div>
  </div>

<script>
  const logBox=document.getElementById("log"); let eventCount=0,lastId=0,poller=null,busy=false,lastAutomationId=0,automationPoller=null;

  function initTheme() {
    const theme = localStorage.getItem('theme') || 'dark';
    if (theme === 'light') {
      document.body.classList.add('theme-light');
    }
    updateThemeButton();
  }

  function toggleTheme() {
    const isLight = document.body.classList.toggle('theme-light');
    localStorage.setItem('theme', isLight ? 'light' : 'dark');
    updateThemeButton();
  }

  function updateThemeButton() {
    const isLight = document.body.classList.contains('theme-light');
    const btn = document.getElementById('themeToggleBtn');
    if (isLight) {
      btn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path></svg> Giao diện tối`;
    } else {
      btn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"></circle><line x1="12" y1="1" x2="12" y2="3"></line><line x1="12" y1="21" x2="12" y2="23"></line><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line><line x1="1" y1="12" x2="3" y2="12"></line><line x1="21" y1="12" x2="23" y2="12"></line><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line></svg> Giao diện sáng`;
    }
  }

  function changeConnMode() {
    const mode = document.getElementById("connMode").value;
    const ipGroup = document.getElementById("wifiIpGroup");
    if (mode === "wifi") {
      ipGroup.style.display = "block";
    } else {
      ipGroup.style.display = "none";
    }
  }

  async function detectPixelIp() {
    try {
      log({status: "Đang quét thiết bị Pixel cắm cáp USB để tự động lấy địa chỉ IP..."});
      const d = await api("/api/pixel/detect-ip", {});
      log(d);
      if (d.ip) {
        document.getElementById("wifiIp").value = d.ip;
        log({status: `Đã tự động dò tìm IP wlan0: ${d.ip}. Tiến hành lưu cấu hình...`});
        await saveConnSettings();
      }
    } catch(e) {
      log(e);
    }
  }

  async function saveConnSettings() {
    try {
      const mode = document.getElementById("connMode").value;
      const ip = document.getElementById("wifiIp").value.trim();

      if (mode === "wifi" && !ip) {
        log({error: "Vui lòng nhập địa chỉ IP của Pixel để kết nối Wi-Fi."});
        return;
      }

      log({status: `Đang lưu cấu hình kết nối qua ${mode.toUpperCase()}...`});
      const d = await api("/api/pixel/connection", {
        connection_mode: mode,
        wifi_ip: ip
      });
      log(d);
      await refresh();
    } catch(e) {
      log(e);
    }
  }

  function log(v) {
    eventCount++;
    document.getElementById("logCount").textContent = `${eventCount} events`;

    let isError = false;
    let isSuccess = false;
    let isWarning = false;
    let text = "";

    if (typeof v === "string") {
      text = v;
      if (v.toLowerCase().includes("lỗi") || v.toLowerCase().includes("error") || v.toLowerCase().includes("failed")) isError = true;
    } else {
      text = JSON.stringify(v, null, 2);
      const step = v.step || "";
      if (step === "error" || v.error) isError = true;
      if (step === "done" || step === "drive_saved" || step === "pulled" || step === "capture" || step === "record" || step === "wifi_connected" || step === "usb_mode" || step === "ip_detected" || step === "chatgpt_done" || step === "gemini_done") isSuccess = true;
      if (step === "cleanup" && v.cleanup_warning) isWarning = true;

      // Tích hợp Realtime Log cho Content Helper Tool
      if (step === "chatgpt_automation" || step === "chatgpt_done" || step === "gemini_automation" || step === "gemini_done" || step === "error") {
        if (step === "chatgpt_done" || step === "gemini_done") {
          loadDownloadedImages();
        }
      }

      // Tích hợp log cho Shopee Sync
      if (step === "shopee_sync") {
        const timeStr = new Date().toLocaleTimeString();
        const rawMsg = v.message || text || "";
        let color = "var(--text-muted)";
        if (rawMsg.toLowerCase().includes("thành công") || rawMsg.toLowerCase().includes("thanh cong") || rawMsg.toLowerCase().includes("hoàn thành") || rawMsg.toLowerCase().includes("success")) color = "#22c55e";
        else if (rawMsg.toLowerCase().includes("lỗi") || rawMsg.toLowerCase().includes("error") || rawMsg.toLowerCase().includes("failed") || rawMsg.toLowerCase().includes("hỏng")) color = "#ef4444";
        else if (rawMsg.toLowerCase().includes("cảnh báo") || rawMsg.toLowerCase().includes("warning")) color = "#eab308";

        state.shopeeLogs.push({
          time: timeStr,
          message: rawMsg,
          color: color
        });

        renderShopeeSyncLogs();

        if (rawMsg && (rawMsg.includes("thành công") || rawMsg.includes("thanh cong") || rawMsg.includes("Sync completed") || rawMsg.includes("thực tế"))) {
          loadShopeeExcelList();
        }
      }
      if (step === "done") {
        refresh();
      }
    }

    let colorClass = "log-info";
    if (isError) colorClass = "log-error";
    else if (isSuccess) colorClass = "log-success";
    else if (isWarning) colorClass = "log-warning";

    const timeStr = new Date().toLocaleTimeString();
    const escText = escapeHtml(text);
    const logItem = `<div class="log-item ${colorClass}">
      <span class="log-time">[${timeStr}]</span>
      <pre class="log-text">${escText}</pre>
    </div>`;

    logBox.innerHTML = logItem + logBox.innerHTML;
  }
  async function clearLog(){try{await fetch("/api/events/clear",{method:"POST"});eventCount=0;lastId=0;logBox.innerHTML="";document.getElementById("logCount").textContent="0 events"}catch(e){console.error(e)}}
  async function api(path,body){const r=await fetch(path,{method:body?"POST":"GET",headers:body?{"Content-Type":"application/json"}:{},body:body?JSON.stringify(body):undefined});const d=await r.json();if(!r.ok)throw d;return d}
  async function pull(){const d=await api(`/api/events?after=${lastId}`);for(const e of d.events||[]){lastId=Math.max(lastId,e.id||0);log(e.payload)}}
  function startPoll(){if(!poller){pull().catch(()=>{});poller=setInterval(()=>pull().catch(()=>{}),700)}}
  async function stopPoll(){if(poller){clearInterval(poller);poller=null}await pull().catch(()=>{})}

  async function pullAutomation() {
    const d = await api(`/api/events?after=${lastAutomationId}`);
    for (const e of d.events || []) {
      lastAutomationId = Math.max(lastAutomationId, e.id || 0);

      const step = e.payload ? e.payload.step : null;
      const msgText = e.payload ? (e.payload.message || e.payload.text || "") : "";

      if (step === "chatgpt_automation" || step === "chatgpt_done" || step === "gemini_automation" || step === "gemini_done" || step === "error") {
        const autoLogBox = document.getElementById("automationLogBox");
        if (autoLogBox) {
          const timeStr = new Date().toLocaleTimeString();
          let color = "#1e293b";
          let icon = "⚙️";
          const isLight = document.body.classList.contains("theme-light");
          if (!isLight) color = "#f8fafc";

          if (step === "error" || msgText.toLowerCase().includes("lỗi") || msgText.toLowerCase().includes("error") || msgText.toLowerCase().includes("failed")) {
            color = "#ef4444";
            icon = "❌";
          } else if (step === "chatgpt_done" || step === "gemini_done" || msgText.toLowerCase().includes("thành công") || msgText.toLowerCase().includes("hoàn thành") || msgText.toLowerCase().includes("success")) {
            color = isLight ? "#15803d" : "#22c55e";
            icon = "✅";
          } else if (msgText.toLowerCase().includes("cảnh báo") || msgText.toLowerCase().includes("warning")) {
            color = isLight ? "#b45309" : "#eab308";
            icon = "⚠️";
          }

          const borderCol = isLight ? "#e2e8f0" : "#334155";
          const timeCol = isLight ? "#64748b" : "#94a3b8";

          autoLogBox.innerHTML += `<div style="margin-bottom: 6px; border-bottom: 1px dashed ${borderCol}; padding-bottom: 6px; display: flex; align-items: start; gap: 8px; font-family: 'Consolas', 'Courier New', monospace;">` +
            `<span style="color: ${timeCol}; font-weight: 600; white-space: nowrap;">[${timeStr}]</span>` +
            `<span style="margin-right: 4px;">${icon}</span>` +
            `<span style="color: ${color}; font-weight: 500; flex: 1; word-break: break-word;">${escapeHtml(msgText)}</span>` +
            `</div>`;
          autoLogBox.scrollTop = autoLogBox.scrollHeight;
        }

        if (step === "chatgpt_done" || step === "gemini_done") {
          loadDownloadedImages();
          stopAutomationPoll();
        }
      }

      // Vẫn ghi vào main stream log của hệ thống
      log(e.payload);
    }
  }
  function startAutomationPoll() {
    if (!automationPoller) {
      pullAutomation().catch(()=>{});
      automationPoller = setInterval(() => pullAutomation().catch(()=>{}), 700);
    }
  }
  async function stopAutomationPoll() {
    if (automationPoller) {
      clearInterval(automationPoller);
      automationPoller = null;
    }
    await pullAutomation().catch(()=>{});
  }

  function selected(){return document.getElementById("folderSelect").value}
  function requireFolder(){if(!selected()){log({error:"Hãy chọn hoặc tạo thư mục sản phẩm trước khi chụp/quay."});return false}return true}
  function setBusy(v){busy=v;document.querySelectorAll("button").forEach(b=>{if(b.id!=="btnStop"&&!b.classList.contains("btn-stop"))b.disabled=v});document.getElementById("themeToggleBtn").disabled=false;if(document.querySelector("#wifiIpGroup button")) document.querySelectorAll("#wifiIpGroup button").forEach(b=>b.disabled=v);}
  async function stopOperation(){try{log({status:"Đang dừng tất cả tiến trình..."});const d=await api("/api/operation/stop",{});log(d);setBusy(false);await refresh()}catch(e){log(e);setBusy(false);await refresh()}}
  function escapeHtml(s){return String(s||"").replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[m]))}
  function render(d){
    document.getElementById("adbMetric").innerHTML=d.adb_device?`<span class="badge ok">${d.adb_device}</span>`:`<span class="badge warn">Chưa thấy Pixel</span>`;
    document.getElementById("driveMetric").innerHTML=d.drive_ready?`<span class="badge ok">Đã kết nối</span>`:`<span class="badge warn">Không tìm thấy</span>`;
    document.getElementById("selectedMetric").textContent=d.selected_folder||"Chưa chọn";
    document.getElementById("folderMetric").textContent=(d.folders||[]).length;
    document.getElementById("busyMetric").innerHTML=d.operation_busy?`<span class="badge warn">Đang xử lý</span>`:`<span class="badge ok">Sẵn sàng</span>`;
    document.getElementById("navFolders").textContent=(d.folders||[]).length;
    document.getElementById("navDrive").textContent=d.drive_ready?"OK":"Lỗi";
    document.getElementById("navAdb").textContent=d.adb_device?"OK":"Offline";
    const uAdb = document.getElementById("unifiedAdbBadge");
    if (uAdb) {
      uAdb.className = d.adb_device ? "badge ok" : "badge warn";
      uAdb.textContent = d.adb_device ? `Pixel ADB: ${d.adb_device}` : "Pixel ADB: Chưa kết nối";
    }
    document.getElementById("driveRoot").value=d.drive_root;
    document.getElementById("connMode").value=d.connection_mode||"usb";
    document.getElementById("wifiIp").value=d.wifi_ip||"";
    document.getElementById("adbPathInput").value=d.adb_path||"";
    document.getElementById("scrcpyPathInput").value=d.scrcpy_path||"";
    changeConnMode();

    if (d.shops && d.shops.length > 0) {
      const shopSel = document.getElementById("shopSelect");
      if (shopSel) {
        const curShop = d.selected_shop || shopSel.value;
        shopSel.innerHTML = d.shops.map(s => `<option value="${escapeHtml(s)}">${escapeHtml(s)}</option>`).join("");
        shopSel.value = curShop;
      }
      const modalShop = document.getElementById("modalShopSelect");
      if (modalShop) {
        const curMShop = d.selected_shop || modalShop.value;
        modalShop.innerHTML = d.shops.map(s => `<option value="${escapeHtml(s)}">${escapeHtml(s)}</option>`).join("");
        modalShop.value = curMShop;
      }
    }

    const s=document.getElementById("folderSelect"),current=d.selected_folder||s.value;
    s.innerHTML='<option value="">-- Chưa chọn thư mục --</option>'+d.folders.map(f=>`<option value="${escapeHtml(f)}">${escapeHtml(f)}</option>`).join("");
    s.value=current;

    const pb=document.getElementById("previewBtn"),pt=document.getElementById("previewBtnText");
    if(pb&&pt){
      if(d.scrcpy_running){pb.classList.add("pulse-warn");pt.textContent="Đóng xem Pixel"}
      else{pb.classList.remove("pulse-warn");pt.textContent="Xem Pixel"}
    }
  }

  async function changeShop(){
    const shopSel = document.getElementById("shopSelect");
    if (!shopSel) return;
    try {
      const res = await api("/api/select-shop", { shop: shopSel.value });
      log(res);
      await refresh();
    } catch(e) { log(e); }
  }

  let notionInsightProducts = [];

  async function openNotionInsightModal() {
    const modal = document.getElementById("notionInsightModal");
    if (modal) modal.style.display = "flex";
    const shopVal = (document.getElementById("shopSelect") || {}).value || "nhathuockh.pharma";
    const modalShop = document.getElementById("modalShopSelect");
    if (modalShop) modalShop.value = shopVal;
    await loadNotionInsightProducts();
  }

  function closeNotionInsightModal() {
    const modal = document.getElementById("notionInsightModal");
    if (modal) modal.style.display = "none";
  }

  async function loadNotionInsightProducts() {
    const tableBody = document.getElementById("notionInsightTableBody");
    if (tableBody) {
      tableBody.innerHTML = '<tr><td colspan="5" style="text-align: center; padding: 24px; color: var(--muted);"><div class="spinner" style="margin: 0 auto 10px;"></div>Đang quét dữ liệu từ Shopee Insight Library trên Notion...</td></tr>';
    }
    const shop = (document.getElementById("modalShopSelect") || document.getElementById("shopSelect") || {}).value || "nhathuockh.pharma";
    try {
      const res = await fetch("/api/notion/insight-products?shop=" + encodeURIComponent(shop));
      const data = await res.json();
      if (!res.ok || data.error) throw new Error(data.error || "Lỗi tải dữ liệu");
      notionInsightProducts = data.products || [];
      renderNotionInsightTable();
    } catch (e) {
      if (tableBody) {
        tableBody.innerHTML = `<tr><td colspan="5" style="text-align: center; padding: 20px; color: #ef4444;">Lỗi: ${escapeHtml(e.message)}</td></tr>`;
      }
    }
  }

  function renderNotionInsightTable() {
    const tableBody = document.getElementById("notionInsightTableBody");
    if (!tableBody) return;
    if (notionInsightProducts.length === 0) {
      tableBody.innerHTML = '<tr><td colspan="5" style="text-align: center; padding: 24px; color: #94a3b8; font-size: 13px;">Không tìm thấy sản phẩm nào trong Notion.</td></tr>';
      return;
    }

    tableBody.innerHTML = notionInsightProducts.map((p, idx) => {
      let statusBadge = "";
      if (!p.insight_count || p.insight_count === 0) {
        statusBadge = '<span class="badge" style="background: rgba(239, 68, 68, 0.15); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.35); font-weight: 700; font-size: 11.5px; padding: 4px 10px; border-radius: 6px;">Chưa có insight</span>';
      } else if (p.status === "Hoàn thành") {
        statusBadge = '<span class="badge ok" style="background: rgba(52, 211, 153, 0.15); color: #34d399; border: 1px solid rgba(52, 211, 153, 0.35); font-weight: 700; font-size: 11.5px; padding: 4px 10px; border-radius: 6px;">✓ Đã tạo thư mục</span>';
      } else {
        statusBadge = '<span class="badge" style="background: rgba(251, 191, 36, 0.15); color: #fbbf24; border: 1px solid rgba(251, 191, 36, 0.35); font-weight: 700; font-size: 11.5px; padding: 4px 10px; border-radius: 6px;">Chưa tạo thư mục</span>';
      }

      const insightNames = (p.insights || []).map(i => `<div style="font-size: 11.5px; color: #93c5fd; margin-top: 3px; font-weight: 500;">🔹 ${escapeHtml(i.title)}</div>`).join("");

      let driveLinkHtml = '<span style="color: #64748b; font-size: 11.5px;">Chưa tạo</span>';
      if (p.drive_url) {
        driveLinkHtml = `<a href="${escapeHtml(p.drive_url)}" target="_blank" style="color: #38bdf8; font-size: 12px; text-decoration: underline; font-weight: 700; display: inline-flex; align-items: center; gap: 4px;">Mở Drive ↗</a>`;
      } else if (p.existing_shop) {
        driveLinkHtml = `<span style="color: #38bdf8; font-size: 12px; font-weight: 600;">📁 ${escapeHtml(p.existing_shop)}</span>`;
      }

      let btnHtml = "";
      if (!p.insight_count || p.insight_count === 0) {
        btnHtml = `<button disabled style="opacity: 0.45; cursor: not-allowed; padding: 6px 14px; font-size: 11.5px; font-weight: 600; border-radius: 6px; background: rgba(255,255,255,0.05); color: #94a3b8; border: 1px solid rgba(255,255,255,0.1);">Chưa có insight</button>`;
      } else if (p.status === "Hoàn thành") {
        btnHtml = `<button class="secondary" onclick="createFoldersForProduct('${escapeHtml(p.page_id)}', ${idx})" id="btnCreateProd_${idx}" style="padding: 6px 14px; font-size: 11.5px; font-weight: 700; border-radius: 6px; cursor: pointer; white-space: nowrap; color: #38bdf8; border: 1px solid rgba(56,189,248,0.4); background: rgba(56,189,248,0.08);">Tạo lại / Cập nhật</button>`;
      } else {
        btnHtml = `<button class="md3-btn-primary" onclick="createFoldersForProduct('${escapeHtml(p.page_id)}', ${idx})" id="btnCreateProd_${idx}" style="padding: 6px 16px; font-size: 11.5px; font-weight: 700; border-radius: 6px; cursor: pointer; white-space: nowrap; background: linear-gradient(135deg, #0d9488, #2dd4bf); color: #fff; box-shadow: 0 2px 8px rgba(45,212,191,0.25);">Tạo thư mục Drive</button>`;
      }

      return `
        <tr style="border-bottom: 1px solid rgba(255,255,255,0.08); background: rgba(255,255,255,0.01);">
          <td style="padding: 12px 14px;">
            <div style="font-weight: 700; font-size: 13.5px; color: #ffffff; line-height: 1.4;">${escapeHtml(p.title)}</div>
            ${insightNames}
          </td>
          <td style="padding: 12px 14px; text-align: center;">
            ${p.insight_count > 0 
              ? `<span style="font-size: 13px; font-weight: 800; color: #2dd4bf; background: rgba(45, 212, 191, 0.15); padding: 3px 10px; border-radius: 6px; border: 1px solid rgba(45, 212, 191, 0.3);">${p.insight_count}</span>` 
              : `<span style="font-size: 12.5px; font-weight: 700; color: #94a3b8;">0</span>`}
          </td>
          <td style="padding: 12px 14px; text-align: center;">
            ${statusBadge}
          </td>
          <td style="padding: 12px 14px; text-align: center;">
            ${driveLinkHtml}
          </td>
          <td style="padding: 12px 14px; text-align: right;">
            ${btnHtml}
          </td>
        </tr>
      `;
    }).join("");
  }

  async function createFoldersForProduct(pageId, btnIdx) {
    const btn = document.getElementById(`btnCreateProd_${btnIdx}`);
    const origText = btn ? btn.innerHTML : "";
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = "Đang tạo...";
    }

    const shop = (document.getElementById("modalShopSelect") || document.getElementById("shopSelect") || {}).value || "nhathuockh.pharma";

    try {
      const res = await fetch("/api/notion/create-product-folders", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ page_id: pageId, shop })
      });
      const data = await res.json();
      if (!res.ok || data.error) throw new Error(data.error || "Lỗi tạo thư mục");

      alert(`Thành công! ${data.status}`);
      await refresh();
      await loadNotionInsightProducts();
      if (typeof loadPendingProducts === "function") {
        await loadPendingProducts();
      }

      const posterDirInput = document.getElementById("posterExportDir");
      if (posterDirInput && data.product_dir) {
        posterDirInput.value = data.product_dir;
        if (typeof onExportDirChange === 'function') onExportDirChange();
        if (typeof scanInsightFolders === 'function') scanInsightFolders();
      }
    } catch (e) {
      alert("Lỗi: " + e.message);
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = origText;
      }
    }
  }
  async function refresh(){try{render(await api("/api/status"))}catch(e){log(e)}}
  async function scanFolders(){try{render(await api("/api/status"));log({status:"Đã quét lại danh sách thư mục."})}catch(e){log(e)}}
  async function togglePreview(){try{const txt=document.getElementById("previewBtnText").textContent;if(txt==="Đóng xem Pixel"){log(await api("/api/close-preview",{}))}else{log(await api("/api/open-preview",{}))}refresh()}catch(e){log(e)}}
  async function saveDriveRoot(){try{log(await api("/api/drive-root",{drive_root:document.getElementById("driveRoot").value}));await refresh()}catch(e){log(e)}}
  async function saveToolPaths(){try{const adb=document.getElementById("adbPathInput").value.trim();const scrcpy=document.getElementById("scrcpyPathInput").value.trim();log(await api("/api/pixel/paths",{adb_path:adb,scrcpy_path:scrcpy}));await refresh()}catch(e){log(e)}}
  async function createFolder(){try{const el=document.getElementById("newFolder");if(!el)return;const d=await api("/api/folders",{name:el.value});el.value="";log(d);await refresh()}catch(e){log(e)}}
  async function deleteFolder(){const name=selected();if(!name){log({error:"Hãy chọn thư mục cần xóa."});return}if(!confirm(`Xóa thư mục rỗng "${name}"?`))return;try{log(await api("/api/folders/delete",{name}));await refresh()}catch(e){log(e)}}
  async function selectFolder(){try{const d=await api("/api/select-folder",{name:selected()});log(d);await refresh()}catch(e){log(e)}}
  async function openPreview(){try{log(await api("/api/open-preview",{}))}catch(e){log(e)}}
  async function togglePixelScreen(){try{log(await api("/api/toggle-screen",{}));await refresh()}catch(e){log(e)}}
  async function run(path,body){if(!requireFolder()||busy)return;setBusy(true);try{log(await api(path,body));await refresh()}catch(e){log(e)}finally{setBusy(false)}}
  function capture(){run("/api/capture",{folder:selected()})}
  function record(){run("/api/record",{folder:selected(),duration:Number(document.getElementById("duration").value||10)})}
  // Poster Creator JS
  let posterImages = []; // Mảng chứa base64 của ảnh upload

  function showPosterDashboard() {
    updateNavTabs("poster");
    document.getElementById("captureDashboard").style.display = "none";
    document.getElementById("shopeeSyncDashboard").style.display = "none";
    document.getElementById("posterDashboard").style.display = "flex";
    // Tải cấu hình OpenAI từ backend lên UI
    loadOpenAIConfig();
  }

  // 0. Thay đổi thư mục lưu ảnh kết quả thủ công (khi tự dán link)
  async function onExportDirChange() {
    await saveOpenAIConfig();
    if (typeof loadDownloadedImages === 'function') {
      loadDownloadedImages();
    }
  }

  // 1. Sao chép nhanh đường dẫn thư mục sản phẩm ở tab Chụp & Quay (đầy đủ thư mục Shop)
  function copyCurrentFolderPath() {
    const rootInput = document.getElementById("driveRoot");
    const root = (rootInput ? rootInput.value : "").trim();
    const shopSelect = document.getElementById("shopSelect");
    const shop = (shopSelect ? shopSelect.value : "").trim();
    const folderSelect = document.getElementById("folderSelect");
    const folder = (folderSelect ? folderSelect.value : "").trim();

    if (!folder) {
      alert("Vui lòng chọn thư mục sản phẩm trước.");
      return;
    }

    let fullPath = root;
    if (fullPath && !fullPath.endsWith("\\") && !fullPath.endsWith("/")) {
      fullPath += "\\";
    }

    if (shop && !folder.toLowerCase().startsWith(shop.toLowerCase() + "\\") && !folder.toLowerCase().startsWith(shop.toLowerCase() + "/")) {
      fullPath += shop + "\\";
    }

    fullPath += folder.replace(/^[/\\]+/, "");

    navigator.clipboard.writeText(fullPath).then(() => {
      const btn = document.getElementById("btnCopyFolderPath");
      const originalHTML = btn.innerHTML;
      btn.innerHTML = `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg> Đã copy!`;
      setTimeout(() => {
        btn.innerHTML = originalHTML;
      }, 1500);
    }).catch(err => {
      alert("Không thể copy đường dẫn: " + err);
    });
  }

  // 2. Quét các thư mục Insight trong thư mục lưu ảnh kết quả
  async function scanInsightFolders() {
    const exportDir = document.getElementById("posterExportDir").value.trim();
    if (!exportDir) {
      alert("Vui lòng nhập hoặc chọn thư mục lưu ảnh kết quả trước.");
      return;
    }

    const select = document.getElementById("insightFolderSelect");
    select.innerHTML = '<option value="">-- Đang quét Insight... --</option>';
    const selectedLabel = document.getElementById("selectedInsightLabel");
    selectedLabel.hidden = true;
    selectedLabel.textContent = "";

    try {
      const response = await fetch("/api/automation/scan-insights", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ export_dir: exportDir })
      });
      const data = await response.json();
      if (!response.ok || data.error) {
        throw new Error(data.error || "Lỗi quét Insight.");
      }

      const insLen = (data.insights && data.insights.length) || 0;
      select.innerHTML = `<option value="">-- Chọn Insight (${insLen}) --</option>`;
      state.scannedInsights = data.insights || [];

      if (state.scannedInsights.length === 0) {
        select.innerHTML = '<option value="">Không tìm thấy thư mục Insight nào</option>';
        return;
      }

      state.scannedInsights.forEach((insight, idx) => {
        const option = document.createElement("option");
        option.value = idx;
        const insightName = insight.display_name || insight.post_title || insight.angle || "Chưa có tên Insight";
        option.textContent = `${insight.folder_name} - ${insightName}`;
        option.title = option.textContent;
        select.appendChild(option);
      });
      
      alert(`Đã quét xong! Tìm thấy ${state.scannedInsights.length} thư mục Insight.`);
    } catch(e) {
      select.innerHTML = '<option value="">Quét thất bại</option>';
      alert("Lỗi quét Insight: " + e.message);
    }
  }

  // 3. Tự động điền dữ liệu và chọn file khi chọn Insight
  function selectInsightFolder() {
    const select = document.getElementById("insightFolderSelect");
    const val = select.value;
    if (val === "") {
      const selectedLabel = document.getElementById("selectedInsightLabel");
      selectedLabel.hidden = true;
      selectedLabel.textContent = "";
      refreshDownloadedImagesForInsightChange();
      return;
    }

    const idx = parseInt(val, 10);
    const insight = state.scannedInsights[idx];
    if (!insight) return;

    const insightName = insight.display_name || insight.post_title || insight.angle || insight.folder_name;
    const fullLabel = `${insight.folder_name} - ${insightName}`;
    select.title = fullLabel;
    const selectedLabel = document.getElementById("selectedInsightLabel");
    selectedLabel.textContent = `Đang chọn: ${fullLabel}`;
    selectedLabel.hidden = false;

    // Đổi Insight phải xóa ngay gallery cũ và chỉ tải ảnh của Insight vừa chọn.
    refreshDownloadedImagesForInsightChange();

    // Tự động điền thông tin mô tả sản phẩm và từ khóa
    document.getElementById("notionContentInput").value = insight.notion_description || "";
    document.getElementById("keywordsInput").value = insight.keywords || "";

    // Tự động nạp file ảnh/video thô (nếu có file)
    if (insight.media_file && insight.media_base64) {
      contentSelectedImageBase64 = insight.media_base64;
      contentSelectedMediaType = insight.media_type;
      
      const imgPreview = document.getElementById("contentImgPreview");
      const videoPreview = document.getElementById("contentVideoPreview");
      const zone = document.getElementById("contentImgDropzone");
      const previewContainer = document.getElementById("contentImgPreviewContainer");

      if (insight.media_type === "video") {
        videoPreview.src = insight.media_url;
        videoPreview.style.display = "block";
        imgPreview.style.display = "none";
        imgPreview.src = "";
      } else {
        imgPreview.src = insight.media_url;
        imgPreview.style.display = "block";
        videoPreview.style.display = "none";
        videoPreview.src = "";
      }

      zone.style.display = "none";
      previewContainer.style.display = "block";
      
      console.log(`Tự động chọn file thô: ${insight.media_file} (Loại: ${insight.media_type})`);
    } else {
      // Nếu không có file media trong folder, reset preview để người dùng tự chọn
      clearContentImage();
    }
  }

  function updateNavTabs(activeTabName) {
    document.querySelectorAll(".nav-tab").forEach(tab => {
      tab.classList.remove("active");
    });
    document.querySelectorAll(".nav-tab-" + activeTabName).forEach(tab => {
      tab.classList.add("active");
    });
  }

  function showCaptureDashboard() {
    updateNavTabs("capture");
    document.getElementById("posterDashboard").style.display = "none";
    document.getElementById("shopeeSyncDashboard").style.display = "none";
    document.getElementById("captureDashboard").style.display = "block";
  }

  let shopeeSyncInitialized = false;
  function showShopeeSyncDashboard() {
    updateNavTabs("shopee");
    document.getElementById("captureDashboard").style.display = "none";
    document.getElementById("posterDashboard").style.display = "none";
    document.getElementById("shopeeSyncDashboard").style.display = "flex";
    loadShopeeConfig();
    loadShopeeExcelList();
    checkShopeeBotStatus();
    loadPendingProducts();
    initInsightPromptEditor();

    if (!shopeeSyncInitialized) {
      shopeeSyncInitialized = true;
      initShopeeDragDrop();
    }
  }

  function initShopeeDragDrop() {
    const pZone = document.getElementById("paste-zone");
    if (pZone) {
      pZone.addEventListener("dragover", (e) => {
        e.preventDefault();
        pZone.style.borderColor = "var(--ok)";
        pZone.style.background = "var(--okbg)";
      });
      pZone.addEventListener("dragleave", (e) => {
        e.preventDefault();
        pZone.style.borderColor = "var(--panel-border)";
        pZone.style.background = "rgba(0,0,0,0.05)";
      });
      pZone.addEventListener("drop", (e) => {
        e.preventDefault();
        pZone.style.borderColor = "var(--panel-border)";
        pZone.style.background = "rgba(0,0,0,0.05)";
        const files = e.dataTransfer?.files;
        if (files && files.length) {
          const file = files[0];
          if (file.type.startsWith("image/")) {
            state.pastedFile = file;
            document.getElementById("image").value = "";
            document.getElementById("imageUrl").value = "";
            renderPreview();
          }
        }
      });
    }
  }

  function toggleConfigColumn() {
    const wrapper = document.getElementById("configSectionWrapper");
    const btn = document.getElementById("btnToggleConfig");
    if (!wrapper || !btn) return;
    if (wrapper.style.display === "none") {
      wrapper.style.display = "flex";
      btn.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg> Ẩn cấu hình`;
    } else {
      wrapper.style.display = "none";
      btn.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg> Hiện cấu hình`;
    }
  }

  async function loadShopeeConfig() {
    try {
      const d = await api("/api/shopee/config");
      document.getElementById("shopeeNotionToken").value = d.NOTION_TOKEN || "";
      document.getElementById("shopeeNotionDbId").value = d.NOTION_DATABASE_ID || "";
      document.getElementById("shopeeTelegramToken").value = d.TELEGRAM_BOT_TOKEN || "";
      document.getElementById("shopeeManagerChatId").value = d.MANAGER_CHAT_ID || "";
      document.getElementById("shopeeGeminiApiKey").value = d.GEMINI_API_KEY || "";
      document.getElementById("shopeeDriveRootId").value = d.DRIVE_ROOT_FOLDER_ID || "";
    } catch(e) {
      console.error("Lỗi tải cấu hình Shopee Sync:", e);
    }
  }

  async function saveShopeeConfig() {
    try {
      const notionToken = document.getElementById("shopeeNotionToken").value.trim();
      const notionDbId = document.getElementById("shopeeNotionDbId").value.trim();
      const telegramToken = document.getElementById("shopeeTelegramToken").value.trim();
      const managerChatId = document.getElementById("shopeeManagerChatId").value.trim();
      const geminiApiKey = document.getElementById("shopeeGeminiApiKey").value.trim();
      const driveRootId = document.getElementById("shopeeDriveRootId").value.trim();

      const payload = {
        NOTION_TOKEN: notionToken,
        NOTION_DATABASE_ID: notionDbId,
        TELEGRAM_BOT_TOKEN: telegramToken,
        MANAGER_CHAT_ID: managerChatId,
        GEMINI_API_KEY: geminiApiKey,
        DRIVE_ROOT_FOLDER_ID: driveRootId,
        PARTNER_ID: "0",
        PARTNER_KEY: "",
        SHOP_ID: "0",
        MOCK_MODE: "True"
      };

      const d = await api("/api/shopee/config/save", payload);
      alert("Đã lưu cấu hình thành công!");
      log({step: "shopee_sync", message: "Đã lưu cấu hình kết nối Notion & Telegram thành công!"});
    } catch(e) {
      alert("Lỗi lưu cấu hình: " + (e.error || e.message || JSON.stringify(e)));
    }
  }

  function parseConfigFileText(text) {
    const result = {};
    if (!text) return result;
    
    const rawLines = text.split(/\r?\n/);
    const cleanLines = rawLines.map(l => l.trim()).filter(l => l && !l.startsWith("---") && !l.startsWith("===") && !l.startsWith("###"));

    // 1. Quét định dạng KEY=VALUE chuẩn của .env
    for (const line of cleanLines) {
      if (line.includes("=") && !line.startsWith("#")) {
        const idx = line.indexOf("=");
        const k = line.substring(0, idx).trim().toUpperCase();
        const v = line.substring(idx + 1).trim();
        if (k.includes("NOTION_TOKEN")) result.NOTION_TOKEN = v;
        else if (k.includes("NOTION_DATABASE_ID") || k.includes("NOTION_DB_ID")) result.NOTION_DATABASE_ID = v;
        else if (k.includes("TELEGRAM_BOT_TOKEN") || k.includes("TELEGRAM_TOKEN")) result.TELEGRAM_BOT_TOKEN = v;
        else if (k.includes("MANAGER_CHAT_ID") || k.includes("CHAT_ID")) result.MANAGER_CHAT_ID = v;
        else if (k.includes("GEMINI_API_KEY") || k.includes("OPENAI_API_KEY") || k.includes("API_KEY")) result.GEMINI_API_KEY = v;
        else if (k.includes("DRIVE_ROOT_FOLDER_ID") || k.includes("DRIVE_ROOT_ID") || k.includes("DRIVE_FOLDER_ID")) result.DRIVE_ROOT_FOLDER_ID = v;
      }
    }

    // 2. Quét định dạng phân cách khối theo dòng (như trong file đồng bộ shopee.txt)
    for (let i = 0; i < cleanLines.length; i++) {
      const line = cleanLines[i];
      const upper = line.toUpperCase();

      const getVal = (idx, currLine) => {
        const colon = currLine.indexOf(":");
        if (colon !== -1) {
          const inlineV = currLine.substring(colon + 1).trim();
          if (inlineV) return inlineV;
        }
        if (idx + 1 < cleanLines.length) {
          return cleanLines[idx + 1];
        }
        return "";
      };

      if (upper.includes("NOTION") && (upper.includes("TOKEN") || upper.includes("INTEGRATION"))) {
        const val = getVal(i, line);
        if (val) result.NOTION_TOKEN = val;
      } else if (upper.includes("NOTION") && (upper.includes("DATABASE") || upper.includes("DB_ID"))) {
        const val = getVal(i, line);
        if (val) result.NOTION_DATABASE_ID = val;
      } else if (upper.includes("TELEGRAM") && (upper.includes("BOT_TOKEN") || upper.includes("TOKEN"))) {
        const val = getVal(i, line);
        if (val) result.TELEGRAM_BOT_TOKEN = val;
      } else if (upper.includes("MANAGER") && upper.includes("CHAT")) {
        const val = getVal(i, line);
        if (val) result.MANAGER_CHAT_ID = val;
      } else if (upper.includes("GEMINI") || upper.includes("OPENAI") || upper.includes("API_KEY") || upper.includes("API KEY")) {
        const val = getVal(i, line);
        if (val) result.GEMINI_API_KEY = val;
      } else if (upper.includes("DRIVE") || upper.includes("ROOT_FOLDER_ID") || upper.includes("GOOGLE DRIVE")) {
        const val = getVal(i, line);
        if (val) result.DRIVE_ROOT_FOLDER_ID = val;
      }
    }

    return result;
  }

  function applyParsedConfig(configObj, autoSave = true) {
    let count = 0;
    if (configObj.NOTION_TOKEN) { document.getElementById("shopeeNotionToken").value = configObj.NOTION_TOKEN; count++; }
    if (configObj.NOTION_DATABASE_ID) { document.getElementById("shopeeNotionDbId").value = configObj.NOTION_DATABASE_ID; count++; }
    if (configObj.TELEGRAM_BOT_TOKEN) { document.getElementById("shopeeTelegramToken").value = configObj.TELEGRAM_BOT_TOKEN; count++; }
    if (configObj.MANAGER_CHAT_ID) { document.getElementById("shopeeManagerChatId").value = configObj.MANAGER_CHAT_ID; count++; }
    if (configObj.GEMINI_API_KEY) { document.getElementById("shopeeGeminiApiKey").value = configObj.GEMINI_API_KEY; count++; }
    if (configObj.DRIVE_ROOT_FOLDER_ID) { document.getElementById("shopeeDriveRootId").value = configObj.DRIVE_ROOT_FOLDER_ID; count++; }

    if (count === 0) {
      alert("Không tìm thấy thông tin cấu hình hợp lệ trong file!");
      return;
    }

    if (autoSave) {
      saveShopeeConfig();
    } else {
      alert(`Đã nạp thành công ${count} thông số cấu hình. Vui lòng bấm "Lưu cấu hình" để lưu lại.`);
    }

    if (configObj.GEMINI_API_KEY) {
      testGeminiApiKey(true);
    }
  }

  async function testGeminiApiKey(silent = false) {
    const statusEl = document.getElementById("geminiKeyStatus");
    const keyInput = document.getElementById("shopeeGeminiApiKey");
    const keyVal = keyInput ? keyInput.value.trim() : "";
    const btn = document.getElementById("btnTestGemini");

    if (!keyVal) {
      if (!silent) alert("Vui lòng nhập API Key trước khi kiểm tra!");
      if (statusEl) {
        statusEl.innerHTML = '<span style="color: var(--danger);">Chưa có API Key</span>';
      }
      return false;
    }

    if (statusEl) {
      statusEl.innerHTML = '<span style="color: var(--brand);">Đang kiểm tra API...</span>';
    }
    if (btn) btn.disabled = true;

    try {
      const res = await api("/api/shopee/config/test-gemini", { api_key: keyVal });
      if (statusEl) {
        statusEl.innerHTML = `<span style="color: var(--success);">✔ ${res.model || "Hợp lệ"}</span>`;
      }
      if (!silent) {
        alert(res.message || "API Key hoạt động rất tốt!");
      }
      return true;
    } catch (err) {
      const errMsg = err.error || err.message || JSON.stringify(err);
      if (statusEl) {
        statusEl.innerHTML = '<span style="color: var(--danger);">✖ Lỗi Key API</span>';
      }
      if (!silent) {
        alert("Kiểm tra API Key thất bại: " + errMsg);
      }
      return false;
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  function handleConfigFileUpload(files) {
    if (!files || files.length === 0) return;
    const file = files[0];
    const reader = new FileReader();
    reader.onload = function(e) {
      const text = e.target.result;
      const parsed = parseConfigFileText(text);
      applyParsedConfig(parsed, true);
      document.getElementById("configFileInput").value = "";
    };
    reader.readAsText(file, "UTF-8");
  }

  function openPasteConfigModal() {
    const modal = document.getElementById("pasteConfigModal");
    if (modal) {
      document.getElementById("pasteConfigTextarea").value = "";
      modal.style.display = "flex";
    }
  }

  function closePasteConfigModal() {
    const modal = document.getElementById("pasteConfigModal");
    if (modal) modal.style.display = "none";
  }

  function applyPastedConfig() {
    const text = document.getElementById("pasteConfigTextarea").value.trim();
    if (!text) {
      alert("Vui lòng dán nội dung cấu hình!");
      return;
    }
    const parsed = parseConfigFileText(text);
    applyParsedConfig(parsed, true);
    closePasteConfigModal();
  }

  function exportConfigFile() {
    const notionToken = document.getElementById("shopeeNotionToken").value.trim();
    const notionDbId = document.getElementById("shopeeNotionDbId").value.trim();
    const telegramToken = document.getElementById("shopeeTelegramToken").value.trim();
    const managerChatId = document.getElementById("shopeeManagerChatId").value.trim();
    const geminiApiKey = document.getElementById("shopeeGeminiApiKey").value.trim();
    const driveRootId = document.getElementById("shopeeDriveRootId").value.trim();

    const lines = [
      "NOTION INTEGRATION TOKEN (NOTION_TOKEN) :",
      notionToken,
      "------------------------------------------------",
      "NOTION DATABASE ID (NOTION_DATABASE_ID) :",
      notionDbId,
      "------------------------------------------------",
      "TELEGRAM BOT TOKEN (TELEGRAM_BOT_TOKEN) :",
      telegramToken,
      "------------------------------------------------",
      "MANAGER CHAT ID (MANAGER_CHAT_ID) :",
      managerChatId,
      "------------------------------------------------",
      "GEMINI/OPENAI API KEY (GEMINI_API_KEY) :",
      geminiApiKey,
      "------------------------------------------------",
      "DRIVE_ROOT_FOLDER_ID :",
      driveRootId
    ];

    const content = lines.join("\\r\\n");
    const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "dong_bo_shopee.txt";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  let cachedShopeePendingProducts = [];
  let selectedShopeeShopFilter = "";

  async function loadPendingProducts() {
    const select = document.getElementById("shopeePendingProducts");
    const listContainer = document.getElementById("shopeePendingProductsList");

    if (select) select.innerHTML = '<option value="">Đang quét danh sách trên Notion...</option>';
    if (listContainer) {
      listContainer.innerHTML = '<div style="padding: 16px; color: var(--muted); font-size:12.5px; text-align:center;">⏳ Đang quét danh sách Notion...</div>';
    }

    try {
      const products = await api("/api/shopee/products/pending");
      cachedShopeePendingProducts = Array.isArray(products) ? products : [];
      renderShopeeProductsList(selectedShopeeShopFilter);
    } catch(e) {
      console.error("Lỗi load sản phẩm pending:", e);
      if (select) select.innerHTML = '<option value="">Lỗi quét sản phẩm từ Notion</option>';
      if (listContainer) {
        listContainer.innerHTML = '<div style="padding: 12px; color: var(--danger); font-size:12.5px; text-align:center;">❌ Lỗi quét sản phẩm từ Notion</div>';
      }
    }
  }

  let shopeeSearchKeyword = "";
  let selectedShopeeStatusFilter = "";

  function filterShopeeProductsBySearch(kw) {
    shopeeSearchKeyword = (kw || "").trim().toLowerCase();
    renderShopeeProductsList(selectedShopeeShopFilter);
  }

  function filterShopeeProductsByShop(shop) {
    selectedShopeeShopFilter = (shop || "").trim();
    renderShopeeProductsList(selectedShopeeShopFilter);
  }

  function filterShopeeProductsByStatus(st) {
    selectedShopeeStatusFilter = (st || "").trim();
    renderShopeeProductsList(selectedShopeeShopFilter);
  }

  function renderShopeeProductsList(filterShop = "") {
    const select = document.getElementById("shopeePendingProducts");
    const listContainer = document.getElementById("shopeePendingProductsList");
    if (!listContainer) return;

    if (select) select.innerHTML = '<option value="">-- Chọn sản phẩm --</option>';
    listContainer.innerHTML = "";

    const filtered = cachedShopeePendingProducts.filter(p => {
      if (filterShop && (p.shop || "").toLowerCase() !== filterShop.toLowerCase()) {
        return false;
      }
      if (selectedShopeeStatusFilter && (p.notion_status || "").toLowerCase() !== selectedShopeeStatusFilter.toLowerCase()) {
        return false;
      }
      if (shopeeSearchKeyword && !(p.title || "").toLowerCase().includes(shopeeSearchKeyword)) {
        return false;
      }
      return true;
    });

    if (filtered.length === 0) {
      if (select) select.innerHTML = '<option value="">Không có sản phẩm phù hợp</option>';
      listContainer.innerHTML = '<div style="padding: 16px; color: var(--muted); font-size:12.5px; text-align:center;">Không có sản phẩm nào phù hợp bộ lọc</div>';
      return;
    }

    const currentSelectedId = document.getElementById("productPageId")?.value || "";

    filtered.forEach(p => {
      if (select) {
        const opt = document.createElement("option");
        opt.value = p.id;
        opt.textContent = `[${p.notion_status || "Chưa đặt"}] ${p.title}`;
        if (p.id === currentSelectedId) opt.selected = true;
        select.appendChild(opt);
      }

      const item = document.createElement("div");
      item.className = "prompt-item";
      const isSelected = p.id === currentSelectedId;
      item.style = `padding: 10px 12px; border: 1px solid ${isSelected ? "var(--brand)" : "var(--panel-border)"}; border-radius: 8px; background: ${isSelected ? "rgba(45, 212, 191, 0.08)" : "var(--soft)"}; cursor: pointer; transition: all 0.2s; display: flex; flex-direction: column; gap: 6px;`;

      const titleEl = document.createElement("div");
      titleEl.style = `font-size: 13px; font-weight: 600; color: ${isSelected ? "var(--brand)" : "var(--text)"}; line-height: 1.4; word-break: break-word;`;
      titleEl.textContent = p.title;
      item.appendChild(titleEl);

      const metaRow = document.createElement("div");
      metaRow.style = "display: flex; gap: 5px; align-items: center; flex-wrap: wrap;";

      // 1. Badge Trạng thái Notion (Chờ đăng, Đã đăng...)
      const nStatus = p.notion_status || "Chưa đặt";
      const nStatusBadge = document.createElement("span");
      if (nStatus === "Chờ đăng") {
        nStatusBadge.style = "font-size: 10.5px; padding: 2px 7px; border-radius: 4px; background: rgba(245, 158, 11, 0.18); color: #f59e0b; font-weight: 700; border: 1px solid rgba(245, 158, 11, 0.35);";
        nStatusBadge.textContent = "⏳ Chờ đăng";
      } else if (nStatus === "Đã đăng") {
        nStatusBadge.style = "font-size: 10.5px; padding: 2px 6px; border-radius: 4px; background: rgba(52, 211, 153, 0.15); color: #34d399; font-weight: 600;";
        nStatusBadge.textContent = "✅ Đã đăng";
      } else if (nStatus === "Lên đơn") {
        nStatusBadge.style = "font-size: 10.5px; padding: 2px 6px; border-radius: 4px; background: rgba(59, 130, 246, 0.15); color: #60a5fa; font-weight: 600;";
        nStatusBadge.textContent = "📝 Lên đơn";
      } else {
        nStatusBadge.style = "font-size: 10.5px; padding: 2px 6px; border-radius: 4px; background: rgba(156, 163, 175, 0.12); color: var(--muted); font-weight: 600;";
        nStatusBadge.textContent = nStatus;
      }
      metaRow.appendChild(nStatusBadge);

      // 2. Badge Shop
      if (p.shop) {
        const shopBadge = document.createElement("span");
        shopBadge.style = "font-size: 10.5px; padding: 2px 6px; border-radius: 4px; background: rgba(56, 189, 248, 0.12); color: #38bdf8; font-weight: 600;";
        shopBadge.textContent = p.shop;
        metaRow.appendChild(shopBadge);
      }

      // 3. Badge số Insight
      const countBadge = document.createElement("span");
      countBadge.style = "font-size: 10.5px; padding: 2px 6px; border-radius: 4px; background: rgba(45, 212, 191, 0.12); color: #2dd4bf; font-weight: 600;";
      countBadge.textContent = `${p.insight_count || 0} Insight`;
      metaRow.appendChild(countBadge);

      // 4. Badge Tình trạng Hình ảnh & Bài viết
      let statusBg = "rgba(156, 163, 175, 0.12)";
      let statusColor = "var(--muted)";
      if (p.status === "Đủ bài & hình") {
        statusBg = "rgba(52, 211, 153, 0.15)";
        statusColor = "#34d399";
      } else if (p.status.includes("Thiếu hình")) {
        statusBg = "rgba(251, 191, 36, 0.15)";
        statusColor = "#fbbf24";
      } else if (p.status === "Chưa có insight") {
        statusBg = "rgba(239, 68, 68, 0.15)";
        statusColor = "#f87171";
      }
      const readyBadge = document.createElement("span");
      readyBadge.style = `font-size: 10px; padding: 2px 6px; border-radius: 4px; background: ${statusBg}; color: ${statusColor}; font-weight: 600;`;
      readyBadge.textContent = p.status;
      metaRow.appendChild(readyBadge);

      // 5. Giá nếu có
      if (p.price) {
        const priceBadge = document.createElement("span");
        priceBadge.style = "font-size: 10px; color: #34d399; font-weight: 700; margin-left: auto;";
        priceBadge.textContent = p.price;
        metaRow.appendChild(priceBadge);
      }

      item.appendChild(metaRow);

      item.onclick = () => {
        listContainer.querySelectorAll(".prompt-item").forEach(el => {
          el.style.borderColor = "var(--panel-border)";
          el.style.background = "var(--soft)";
          const t = el.querySelector("div");
          if (t) t.style.color = "var(--text)";
        });
        item.style.borderColor = "var(--brand)";
        item.style.background = "rgba(45, 212, 191, 0.08)";
        titleEl.style.color = "var(--brand)";

        if (select) select.value = p.id;
        onSelectPendingProduct(p.id);
      };

      listContainer.appendChild(item);
    });
  }
  // --- New AI Insight Shopee JS Logic ---
  const defaultInsightPrompt = [
    "Bạn là người viết insight bán hàng Shopee cho shop dược phẩm/sản phẩm chăm sóc sức khỏe.",
    "Hãy viết thực tế, dễ dùng cho tiêu đề post, caption, video ngắn và lưu Notion.",
    "Ưu tiên góc bán hàng rõ: vấn đề khách đang gặp, công dụng chính, thành phần/hoạt chất, đối tượng dùng, lý do nên chọn sản phẩm.",
    "Không dùng văn phong hoa mỹ, không nói quá công dụng, không thêm cảnh báo y tế thừa.",
    "Mỗi insight phải khác góc nhau và có keyword đủ mạnh để người bán dùng lại."
  ].join(String.fromCharCode(10));

  const defaultPasteText = "Copy ảnh rồi nhấn Ctrl+V tại đây để hiện preview.";
  const insightPromptStorageKey = "insightShopeeInsightPrompt";

  const state = {
    productName: "",
    product: {},
    insights: [],
    visionContext: {},
    imagePreviewUrl: "",
    pastedFile: null,
    currentRewriteRowIndex: null, // Lưu dòng đang sửa để đồng bộ từ Gemini
    shopeeLogs: [],
    lastPostPrompt: null
  };

  let postPromptsList = [];
  let activePostPromptId = "";
  const postPromptStorageKey = "shopeeSelectedPostPromptId";

  function setPostPromptStatus(message, type = "muted") {
    const el = document.getElementById("postPromptStatus");
    if (!el) return;
    el.textContent = message;
    el.style.color = type === "error" ? "var(--danger)" : (type === "success" ? "var(--success)" : "var(--muted)");
  }

  async function loadPostPromptsLibrary(preferredId = "") {
    try {
      const response = await fetch("/api/shopee/post-prompts");
      const data = await response.json();
      if (!response.ok) throw data;
      postPromptsList = Array.isArray(data) ? data : [];

      const select = document.getElementById("postPromptSelect");
      if (!select) return;
      select.innerHTML = "";
      postPromptsList.forEach(item => {
        const option = document.createElement("option");
        option.value = item.id;
        option.textContent = item.is_default ? `${item.title} (mặc định)` : item.title;
        select.appendChild(option);
      });

      const storedId = localStorage.getItem(postPromptStorageKey) || "";
      const targetId = preferredId || storedId || (postPromptsList[0] && postPromptsList[0].id) || "";
      selectPostPromptTemplate(postPromptsList.some(item => item.id === targetId) ? targetId : (postPromptsList[0] && postPromptsList[0].id));
      setPostPromptStatus(`Đã tải ${postPromptsList.length} mẫu prompt.`, "success");
    } catch (error) {
      setPostPromptStatus("Không tải được thư viện prompt: " + (error.error || error.message || "Lỗi không xác định"), "error");
    }
  }

  function selectPostPromptTemplate(promptId) {
    const item = postPromptsList.find(prompt => prompt.id === promptId);
    if (!item) return;
    activePostPromptId = item.id;
    document.getElementById("postPromptSelect").value = item.id;
    document.getElementById("postPromptTitle").value = item.title || "";
    document.getElementById("postPromptContent").value = item.content || "";
    localStorage.setItem(postPromptStorageKey, item.id);
    state.lastPostPrompt = null;
    setPostPromptStatus(`Đang dùng mẫu: ${item.title}`);
  }

  function newPostPromptTemplate() {
    activePostPromptId = "";
    const select = document.getElementById("postPromptSelect");
    if (select) select.selectedIndex = -1;
    document.getElementById("postPromptTitle").value = "";
    document.getElementById("postPromptContent").value = "";
    document.getElementById("postPromptTitle").focus();
    state.lastPostPrompt = null;
    setPostPromptStatus("Đang tạo mẫu mới. Nhập tên, nội dung rồi bấm Lưu sửa.");
  }

  function markPostPromptChanged() {
    state.lastPostPrompt = null;
    setPostPromptStatus("Nội dung đã thay đổi, chưa lưu mẫu. Prompt hiện tại vẫn được dùng khi tạo bài.");
  }

  function getCurrentPostWritingPrompt() {
    const field = document.getElementById("postPromptContent");
    return field ? field.value.trim() : "";
  }

  async function savePostPromptTemplate() {
    const title = document.getElementById("postPromptTitle").value.trim();
    const content = getCurrentPostWritingPrompt();
    if (!title || !content) {
      setPostPromptStatus("Cần nhập đủ tên mẫu và nội dung prompt.", "error");
      return;
    }
    setPostPromptStatus("Đang lưu prompt...");
    try {
      const response = await fetch("/api/shopee/post-prompts", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({id: activePostPromptId, title, content})
      });
      const data = await response.json();
      if (!response.ok) throw data;
      activePostPromptId = data.prompt.id;
      await loadPostPromptsLibrary(activePostPromptId);
      setPostPromptStatus(`Đã lưu mẫu: ${data.prompt.title}`, "success");
    } catch (error) {
      setPostPromptStatus("Lỗi lưu prompt: " + (error.error || error.message || "Lỗi không xác định"), "error");
    }
  }

  async function deletePostPromptTemplate() {
    if (!activePostPromptId) {
      setPostPromptStatus("Chưa chọn mẫu cần xóa.", "error");
      return;
    }
    const item = postPromptsList.find(prompt => prompt.id === activePostPromptId);
    if (!item || !confirm(`Xóa mẫu prompt “${item.title}”?`)) return;
    try {
      const response = await fetch(`/api/shopee/post-prompts/${encodeURIComponent(activePostPromptId)}`, {method: "DELETE"});
      const data = await response.json();
      if (!response.ok) throw data;
      localStorage.removeItem(postPromptStorageKey);
      await loadPostPromptsLibrary();
      setPostPromptStatus("Đã xóa mẫu prompt.", "success");
    } catch (error) {
      setPostPromptStatus("Không thể xóa: " + (error.error || error.message || "Lỗi không xác định"), "error");
    }
  }

  async function importPostPromptTemplates(event) {
    const file = event.target.files && event.target.files[0];
    if (!file) return;
    const formData = new FormData();
    formData.append("file", file);
    setPostPromptStatus("Đang nhập prompt từ file...");
    try {
      const response = await fetch("/api/shopee/post-prompts/import", {method: "POST", body: formData});
      const data = await response.json();
      if (!response.ok) throw data;
      await loadPostPromptsLibrary();
      setPostPromptStatus(`Đã nhập ${data.count} mẫu prompt.`, "success");
    } catch (error) {
      setPostPromptStatus("Lỗi nhập file: " + (error.error || error.message || "Lỗi không xác định"), "error");
    } finally {
      event.target.value = "";
    }
  }

  function exportPostPromptTemplates() {
    setPostPromptStatus("Đang xuất toàn bộ prompt...");
    window.location.href = "/api/shopee/post-prompts/export";
    window.setTimeout(() => setPostPromptStatus("Đã gửi file prompt tới thư mục tải xuống.", "success"), 600);
  }

  function initInsightPromptEditor() {
    const promptInput = document.getElementById("insightPrompt");
    if (promptInput) {
      promptInput.value = localStorage.getItem(insightPromptStorageKey) || defaultInsightPrompt;
    }
  }

  function saveInsightPrompt() {
    const promptInput = document.getElementById("insightPrompt");
    if (promptInput) {
      localStorage.setItem(insightPromptStorageKey, promptInput.value.trim());
      setPromptStatus("Đã lưu prompt tạo insight.", "is-success");
    }
  }

  function resetInsightPrompt() {
    const promptInput = document.getElementById("insightPrompt");
    if (promptInput) {
      promptInput.value = defaultInsightPrompt;
      localStorage.removeItem(insightPromptStorageKey);
      setPromptStatus("Đã khôi phục prompt mặc định.", "is-success");
    }
  }

  function setPromptStatus(msg, tone) {
    const status = document.getElementById("prompt-status");
    if (status) {
      status.textContent = msg;
      status.className = `status ${tone}`;
    }
  }

  function setStatus(elementId, message, tone = "muted") {
    const el = document.getElementById(elementId);
    if (el) {
      el.textContent = message;
      el.className = `status ${tone}`;
    }
  }

  let pendingProductDetailsRequestId = 0;

  async function onSelectPendingProduct(pageId) {
    const requestId = ++pendingProductDetailsRequestId;
    clearImageState();
    if (!pageId) {
      document.getElementById("productPageId").value = "";
      document.getElementById("productNameInput").value = "";
      document.getElementById("productPrice").value = "";
      document.getElementById("productClassification").value = "";
      document.getElementById("productVariants").value = "";
      const driveInput = document.getElementById("shopeeSyncDriveUrl");
      if (driveInput) driveInput.value = "";
      localStorage.removeItem("shopee_sync_drive_url");
      state.insights = [];
      const emptyState = document.getElementById("empty-state");
      const saveForm = document.getElementById("save-form");
      if (emptyState) emptyState.hidden = false;
      if (saveForm) saveForm.hidden = true;
      const btnPreview = document.getElementById("btnPreviewPosts");
      if (btnPreview) {
        btnPreview.innerHTML = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg> <span>Xem chi tiết bài viết</span>';
      }
      return;
    }

    // Ghi nhận lựa chọn ngay khi click để nút Đồng bộ không dùng page_id cũ.
    document.getElementById("productPageId").value = pageId;

    // Hiển thị Pop-up loading chuyên nghiệp
    const loadingModal = document.getElementById("productLoadingModal");
    if (loadingModal) {
      loadingModal.style.display = "flex";
    }

    setStatus("analyze-status", "Đang tải thông tin sản phẩm và nội dung các Insight từ Notion...", "muted");
    try {
      const details = await api(`/api/shopee/product/details?page_id=${pageId}`);
      const selectedPageId = document.getElementById("shopeePendingProducts")?.value || "";
      if (requestId !== pendingProductDetailsRequestId || selectedPageId !== pageId) {
        return;
      }
      document.getElementById("productPageId").value = details.id || "";
      document.getElementById("productNameInput").value = details.master_title || details.title || "";
      document.getElementById("productPrice").value = details.price || "";
      document.getElementById("productClassification").value = details.classification || "";
      document.getElementById("productVariants").value = details.variants || "";
      const driveInput = document.getElementById("shopeeSyncDriveUrl");
      if (driveInput) {
        driveInput.value = details.selected_folder_path || "";
        localStorage.setItem("shopee_sync_drive_url", driveInput.value);
      }

      // Cập nhật state.product
      state.product = {
        productPageId: details.id || "",
        name: details.master_title || details.title || "",
        price: details.price || "",
        classification: details.classification || "",
        variants: details.variants || "",
        shop: details.shop || "",
        folderPath: details.selected_folder_path || "",
        folderName: details.selected_folder || "",
        master: details.master || null,
        notion_status: details.notion_status || "",
        note: details.note || "",
        driveUrl: details.drive_url || ""
      };
      state.productName = details.master_title || details.title || "";

      // Đồng bộ trạng thái Notion vào dropdown chuyển nhanh
      const statusSelect = document.getElementById("quickNotionStatusSelect");
      if (statusSelect && details.notion_status) {
        statusSelect.value = details.notion_status;
      }

      // Nạp danh sách Insight từ Notion page
      state.insights = (details.insights || []).map(ins => ({
        id: ins.id,
        order: ins.order,
        angle: ins.angle || "",
        postTitle: ins.title || "",
        insightContent: ins.description || "",
        keywords: ins.keywords || "",
        folderName: ins.folder_name || "",
        driveUrl: ins.drive_url || "",
        imageCount: ins.image_count || 0,
        images: ins.images || []
      }));

      // Cập nhật giao diện Review Panel
      const emptyState = document.getElementById("empty-state");
      const saveForm = document.getElementById("save-form");
      const prodNameEl = document.getElementById("product-name");

      if (prodNameEl) {
        prodNameEl.innerHTML = `<span style="font-weight: 700; color: var(--text);">${escapeHtml(details.title)}</span>` +
          (details.master_title && details.master_title !== details.title ? ` <span style="font-size: 11.5px; color: var(--muted);">(Master DB: ${escapeHtml(details.master_title)})</span>` : "") +
          ` · <span style="color: var(--brand); font-weight: 600;">${state.insights.length} Insight sẵn sàng</span>`;
      }

      if (emptyState) emptyState.hidden = state.insights.length > 0;
      if (saveForm) saveForm.hidden = state.insights.length === 0;

      renderProductSummary();
      renderInsightsTable();

      // Cập nhật text nút Xem chi tiết bài viết theo đúng số lượng Insight thực tế (chỉ 1 icon)
      const btnPreview = document.getElementById("btnPreviewPosts");
      if (btnPreview) {
        const insCount = state.insights.length;
        btnPreview.innerHTML = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg> <span>Xem chi tiết bài viết (${insCount} Insight)</span>`;
      }

      // Cập nhật thanh Media & Tạo hình thống nhất
      const uTitle = document.getElementById("unifiedProductTitle");
      if (uTitle) uTitle.textContent = details.title || "Chưa có tiêu đề";
      const uShop = document.getElementById("unifiedProductShopBadge");
      if (uShop) uShop.textContent = details.shop || "Chưa xác định Shop";
      const uCountBadge = document.getElementById("unifiedInsightCountBadge");
      if (uCountBadge) {
        uCountBadge.style.display = "inline-flex";
        uCountBadge.textContent = `${state.insights.length} Insight sẵn sàng`;
      }
      const uSelect = document.getElementById("unifiedInsightTargetSelect");
      if (uSelect) {
        uSelect.innerHTML = `<option value="">-- Cả thư mục sản phẩm (${escapeHtml(details.selected_folder || details.title)}) --</option>` +
          (details.insights || []).map(ins => `<option value="${escapeHtml(ins.folder_name)}">${escapeHtml(ins.folder_name)} (${ins.image_count || 0} hình)</option>`).join("");
      }
      const uMeta = document.getElementById("unifiedProductMeta");
      if (uMeta) {
        let metaHtml = "";
        if (details.master_title) {
          metaHtml += `<span>🏷️ Master DB: <b>${escapeHtml(details.master_title)}</b></span>`;
        }
        if (details.price) {
          metaHtml += `<span style="color: #34d399;">💰 Giá: <b>${escapeHtml(details.price)}</b></span>`;
        }
        if (details.classification) {
          metaHtml += `<span>📦 Phân loại: <b>${escapeHtml(details.classification)}</b></span>`;
        }
        if (details.selected_folder_path) {
          metaHtml += `<span style="color: #38bdf8; cursor: pointer; text-decoration: underline; font-weight: 600;" onclick="openCurrentProductFolder()" title="Bấm để mở thư mục trên máy tính">📁 ${escapeHtml(details.selected_folder_path)}</span>`;
        } else {
          metaHtml += `<span style="color: #fbbf24; font-weight: 600;">⚠️ Chưa tạo thư mục local Drive</span>`;
        }
        uMeta.innerHTML = metaHtml;
      }

      setStatus("analyze-status", `✓ Đã tải xong ${state.insights.length} Insight từ Notion!`, "is-success");
    } catch(e) {
      if (requestId !== pendingProductDetailsRequestId) return;
      console.error("Lỗi tải chi tiết sản phẩm:", e);
      setStatus("analyze-status", "Lỗi tải thông tin sản phẩm: " + (e.error || e.message || JSON.stringify(e)), "is-error");
    } finally {
      if (loadingModal) {
        loadingModal.style.display = "none";
      }
    }
  }

  async function changeCurrentProductNotionStatus(newStatus) {
    const pageId = document.getElementById("productPageId")?.value || state.product?.productPageId;
    if (!pageId) {
      alert("Vui lòng chọn một sản phẩm trước khi đổi trạng thái!");
      return;
    }
    const feedback = document.getElementById("quickStatusSaveFeedback");
    if (feedback) {
      feedback.textContent = "Đang lưu...";
      feedback.style.color = "var(--muted)";
    }
    try {
      const res = await api("/api/shopee/product/update-status", { page_id: pageId, status: newStatus });
      if (feedback) {
        feedback.textContent = "✓ Đã cập nhật!";
        feedback.style.color = "#34d399";
        setTimeout(() => { if (feedback) feedback.textContent = ""; }, 3000);
      }
      if (state.product) {
        state.product.notion_status = newStatus;
      }
      // Làm mới danh sách sản phẩm bên trái để cập nhật badge trạng thái
      if (typeof fetchShopeePendingProducts === "function") {
        fetchShopeePendingProducts();
      }
    } catch(e) {
      console.error(e);
      if (feedback) {
        feedback.textContent = "❌ Lỗi!";
        feedback.style.color = "var(--danger)";
      }
      alert("Lỗi cập nhật trạng thái Notion: " + (e.error || e.message || JSON.stringify(e)));
    }
  }

  async function captureForCurrentProduct(specificSubfolder = "") {
    if (busy) {
      alert("Pixel đang bận xử lý tác vụ khác, vui lòng đợi...");
      return;
    }
    const currentProd = state.product;
    if (!currentProd || !currentProd.name) {
      alert("Vui lòng chọn một sản phẩm từ danh sách bên trái trước khi chụp ảnh.");
      return;
    }

    let targetFolder = "";
    const shop = currentProd.shop || document.getElementById("shopeeShopFilter")?.value || "";
    const prodFolder = currentProd.folderName || currentProd.name;

    const sub = specificSubfolder || document.getElementById("unifiedInsightTargetSelect")?.value || "";
    if (sub) {
      targetFolder = (shop ? `${shop}/` : "") + `${prodFolder}/${sub}`;
    } else {
      targetFolder = (shop ? `${shop}/` : "") + `${prodFolder}`;
    }

    setBusy(true);
    try {
      log({ step: "capture", message: `📸 Đang chụp ảnh Pixel vào: ${targetFolder}...` });
      const res = await api("/api/capture", { folder: targetFolder, shop: shop });
      log(res);
      // Tự động quét lại và reload hình ảnh sản phẩm để cập nhật thumbnail ngay trên bảng review
      if (currentProd.productPageId) {
        await onSelectPendingProduct(currentProd.productPageId);
      }
    } catch(e) {
      console.error(e);
      log({ step: "error", message: `Lỗi chụp ảnh: ${e.error || e.message || JSON.stringify(e)}` });
      alert(`Lỗi chụp ảnh Pixel: ${e.error || e.message || JSON.stringify(e)}`);
    } finally {
      setBusy(false);
    }
  }

  async function recordForCurrentProduct() {
    if (busy) return;
    const currentProd = state.product;
    if (!currentProd || !currentProd.name) {
      alert("Vui lòng chọn sản phẩm trước.");
      return;
    }
    const shop = currentProd.shop || "";
    const prodFolder = currentProd.folderName || currentProd.name;
    const sub = document.getElementById("unifiedInsightTargetSelect")?.value || "";
    const targetFolder = (shop ? `${shop}/` : "") + `${prodFolder}` + (sub ? `/${sub}` : "");
    const duration = 10;
    setBusy(true);
    try {
      log({ step: "record", message: `🎥 Đang quay video Pixel (${duration}s) vào: ${targetFolder}...` });
      const res = await api("/api/record", { folder: targetFolder, duration: duration, shop: shop });
      log(res);
      if (currentProd.productPageId) {
        await onSelectPendingProduct(currentProd.productPageId);
      }
    } catch(e) {
      log({ step: "error", message: `Lỗi quay video: ${e.error || e.message}` });
      alert(`Lỗi quay video: ${e.error || e.message}`);
    } finally {
      setBusy(false);
    }
  }

  async function openCurrentProductFolder() {
    const currentProd = state.product;
    const folderPath = currentProd?.folderPath;
    if (!folderPath) {
      alert("Chưa tìm thấy thư mục local của sản phẩm trên máy tính.");
      return;
    }
    try {
      await api("/api/folder/reveal", { folder_path: folderPath });
    } catch(e) {
      alert("Không thể mở thư mục: " + (e.error || e.message));
    }
  }

  async function refreshCurrentProductImages() {
    const currentProd = state.product;
    if (currentProd?.productPageId) {
      await onSelectPendingProduct(currentProd.productPageId);
    }
  }

  function onImageFileChange() {
    const fileInput = document.getElementById("image");
    if (fileInput.files && fileInput.files.length) {
      state.pastedFile = null;
      document.getElementById("imageUrl").value = "";
    }
    renderPreview();
  }

  function onImageUrlInput() {
    const urlInput = document.getElementById("imageUrl");
    if (urlInput.value.trim()) {
      document.getElementById("image").value = "";
      state.pastedFile = null;
    }
    renderPreview();
  }

  function clearImageState() {
    state.pastedFile = null;
    state.imagePreviewUrl = "";
    document.getElementById("image").value = "";
    document.getElementById("imageUrl").value = "";

    // New UI: hide overlay, show placeholder
    const overlay = document.getElementById("image-preview-overlay");
    const placeholder = document.getElementById("upload-placeholder");
    if (overlay) overlay.style.display = "none";
    if (placeholder) placeholder.style.display = "flex";

    const imgPrev = document.getElementById("image-preview");
    if (imgPrev) imgPrev.removeAttribute("src");

    const zone = document.getElementById("image-upload-zone");
    if (zone) zone.classList.remove("is-active");
  }

  function showPreview(src, label) {
    state.imagePreviewUrl = src;

    // New UI: set image src and show overlay
    const imgPrev = document.getElementById("image-preview");
    if (imgPrev) imgPrev.src = src;

    const labelEl = document.getElementById("preview-label");
    if (labelEl) labelEl.textContent = label;

    const overlay = document.getElementById("image-preview-overlay");
    if (overlay) overlay.style.display = "flex";

    const placeholder = document.getElementById("upload-placeholder");
    if (placeholder) placeholder.style.display = "none";

    const zone = document.getElementById("image-upload-zone");
    if (zone) zone.classList.add("is-active");
  }

  function renderPreview() {
    const file = document.getElementById("image").files?.[0] || state.pastedFile;
    const imageUrl = document.getElementById("imageUrl").value.trim();

    if (!file) {
      if (imageUrl) {
        showPreview(imageUrl, "Ảnh từ link đã sẵn sàng");
        return;
      }
      clearImageState();
      return;
    }

    const reader = new FileReader();
    reader.onload = (event) => {
      showPreview(event.target?.result || "", `Ảnh đã chọn: ${file.name || "image.png"}`);
    };
    reader.readAsDataURL(file);
  }

  function onPasteZonePaste(event) {
    const clipboardItems = event.clipboardData?.items || [];
    for (const item of clipboardItems) {
      if (item.type.startsWith("image/")) {
        const file = item.getAsFile();
        if (file) {
          event.preventDefault();
          state.pastedFile = new File([file], file.name || "pasted-image.png", { type: file.type });
          document.getElementById("image").value = "";
          document.getElementById("imageUrl").value = "";
          renderPreview();
          return;
        }
      }
    }

    const text = event.clipboardData?.getData("text")?.trim();
    if (text && (text.startsWith("http://") || text.startsWith("https://"))) {
      event.preventDefault();
      state.pastedFile = null;
      document.getElementById("image").value = "";
      document.getElementById("imageUrl").value = text;
      renderPreview();
    }
  }

  function onDropZone(event) {
    event.preventDefault();
    const zone = document.getElementById("image-upload-zone");
    if (zone) zone.classList.remove("is-active");
    const files = event.dataTransfer?.files;
    if (files && files.length) {
      const file = files[0];
      if (file.type.startsWith("image/")) {
        state.pastedFile = new File([file], file.name || "dropped-image.png", { type: file.type });
        document.getElementById("image").value = "";
        document.getElementById("imageUrl").value = "";
        renderPreview();
      }
    }
  }

  async function openChromeDebugGemini() {
    const btn = document.getElementById("open-chrome-button");
    btn.disabled = true;
    setStatus("analyze-status", "Đang kết nối tới Chrome Debug qua cổng 9223...", "muted");
    try {
      const d = await api("/api/check-gemini-login", { profileDirectory: "__tool_profile__" });
      if (!d.loggedIn) {
        setStatus("analyze-status", d.message || "Gemini chưa sẵn sàng. Hãy đăng nhập Chrome debug.", "is-error");
      } else {
        setStatus("analyze-status", d.message || "Gemini đã sẵn sàng.", "is-success");
      }
    } catch(e) {
      setStatus("analyze-status", "Không kết nối được: " + (e.error || e.message || JSON.stringify(e)), "is-error");
    } finally {
      btn.disabled = false;
    }
  }

  async function resolveImageFileForAnalysis() {
    const selectedFile = document.getElementById("image").files?.[0] || state.pastedFile;
    const imageUrl = document.getElementById("imageUrl").value.trim();

    if (selectedFile) {
      return selectedFile;
    }

    if (!imageUrl) {
      return null;
    }

    setStatus("analyze-status", "Đang tải ảnh từ URL qua server...", "muted");

    try {
      const response = await fetch("/api/shopee/download-image", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: imageUrl })
      });

      const d = await response.json();
      if (!response.ok || !d.success) {
        throw new Error(d.error || "Không tải được ảnh từ link này qua server.");
      }

      // Chuyển base64 tải về thành File object
      const responseBlob = await fetch(d.base64);
      const blob = await responseBlob.blob();
      return new File([blob], "image-url-upload." + (d.mime.split("/")[1] || "png"), { type: d.mime });
    } catch(e) {
      console.error("Lỗi tải ảnh từ URL:", e);
      throw new Error(e.message || "Lỗi không xác định khi tải ảnh qua server.");
    }
  }

  function collectProductInfo() {
    return {
      productPageId: document.getElementById("productPageId").value,
      name: document.getElementById("productNameInput").value.trim(),
      price: document.getElementById("productPrice").value.trim(),
      variants: document.getElementById("productVariants").value.trim(),
      classification: document.getElementById("productClassification").value.trim()
    };
  }

  async function analyzeProduct() {
    const btn = document.getElementById("analyze-button");
    const chromeBtn = document.getElementById("open-chrome-button");
    const status = "analyze-status";

    const product = collectProductInfo();
    if (!product.name) {
      setStatus(status, "Vui lòng nhập tên sản phẩm trước khi phân tích.", "is-error");
      document.getElementById("productNameInput").focus();
      return;
    }

    let imageFile;
    try {
      imageFile = await resolveImageFileForAnalysis();
    } catch(e) {
      setStatus(status, e.message, "is-error");
      return;
    }

    if (!imageFile) {
      setStatus(status, "Hãy chọn hoặc dán ảnh sản phẩm trước khi phân tích.", "is-error");
      return;
    }

    btn.disabled = true;
    chromeBtn.disabled = true;
    setStatus(status, "Đang gửi ảnh và thông tin sản phẩm sang Gemini (Chrome 9223). Vui lòng đợi...", "muted");

    const formData = new FormData();
    formData.append("image", imageFile, imageFile.name || "product-image.png");
    formData.append("productName", product.name);
    formData.append("productPrice", product.price);
    formData.append("productVariants", product.variants);
    formData.append("productClassification", product.classification);
    formData.append("keywords", document.getElementById("keywords").value.trim());
    formData.append("useCases", document.getElementById("useCases").value.trim());

    const promptVal = document.getElementById("insightPrompt") ? document.getElementById("insightPrompt").value.trim() : "";
    formData.append("insightPrompt", promptVal);

    try {
      const response = await fetch("/api/analyze-product", {
        method: "POST",
        body: formData
      });

      const payload = await response.json();
      if (!response.ok || payload.error) {
        throw new Error(payload.error || "Lỗi không xác định khi phân tích ảnh.");
      }

      applyAnalysisResult(payload);
      setStatus(status, `Đã sinh ${state.insights.length} insight bằng Gemini thành công!`, "is-success");
    } catch(e) {
      console.error(e);
      setStatus(status, "Lỗi phân tích: " + e.message, "is-error");
    } finally {
      btn.disabled = false;
      chromeBtn.disabled = false;
    }
  }

  async function syncGeminiResultManual() {
    const btn = document.getElementById("sync-gemini-button");
    const status = "analyze-status";

    btn.disabled = true;
    setStatus(status, "Đang kết nối Chrome và đồng bộ câu trả lời mới nhất từ Gemini...", "muted");

    try {
      const response = await fetch("/api/sync-gemini-result", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        }
      });

      const payload = await response.json();
      if (!response.ok || payload.error) {
        throw new Error(payload.error || "Lỗi đồng bộ dữ liệu từ Gemini.");
      }

      const resultType = payload.type;
      const data = payload.data;

      if (resultType === "analyze") {
        applyAnalysisResult(data);
        setStatus(status, `Đã đồng bộ thành công 5 insight phân tích từ Gemini!`, "is-success");
      } else if (resultType === "rewrite") {
        const rowIndex = state.currentRewriteRowIndex;
        if (rowIndex !== null && rowIndex >= 0 && rowIndex < state.insights.length) {
          const rawInsight = data.insight || {};
          state.insights[rowIndex] = {
            angle: rawInsight.angle || rawInsight.GocViet || rawInsight.gocViet || "",
            postTitle: rawInsight.postTitle || rawInsight.title || rawInsight.tieuDe || "",
            insightContent: rawInsight.insightContent || rawInsight.content || rawInsight.noiDung || "",
            keywords: rawInsight.keywords || rawInsight.keyword || rawInsight.tuKhoa || ""
          };
          renderInsightsTable();
          setStatus(status, `Đã đồng bộ thành công bài viết viết lại #${rowIndex + 1}!`, "is-success");
          state.currentRewriteRowIndex = null; // Reset
        } else {
          alert("Tìm thấy kết quả viết lại single insight từ Gemini. Nếu bạn muốn sửa dòng nào, vui lòng bấm nút 'Viết lại' ở dòng đó trước khi bấm 'Đồng bộ từ Gemini'.");
          setStatus(status, "Đồng bộ viết lại: Thiếu thông tin dòng cần sửa.", "is-error");
        }
      } else {
        throw new Error("Không nhận diện được loại câu trả lời của Gemini.");
      }

    } catch(e) {
      console.error(e);
      setStatus(status, "Lỗi đồng bộ: " + e.message, "is-error");
      alert("Lỗi đồng bộ: " + e.message);
    } finally {
      btn.disabled = false;
    }
  }

  function applyAnalysisResult(payload) {
    console.log("applyAnalysisResult PAYLOAD RECEIVED:", payload);
    const currentProduct = collectProductInfo();
    const resolvedName = payload.productName || currentProduct.name || "";

    // Chuẩn hóa insights với các key fallback để tránh hiển thị trống
    const rawInsights = Array.isArray(payload.insights) ? payload.insights : [];
    console.log("rawInsights:", rawInsights);
    const normalized = rawInsights.map(item => ({
      angle: item.angle || item.GocViet || item.gocViet || "",
      postTitle: item.postTitle || item.title || item.tieuDe || "",
      insightContent: item.insightContent || item.content || item.noiDung || "",
      keywords: item.keywords || item.keyword || item.tuKhoa || ""
    }));

    // Kiểm tra xem có đủ dữ liệu và các thuộc tính bắt buộc không rỗng
    const validInsights = normalized.filter(item => item.angle.trim() && item.postTitle.trim() && item.insightContent.trim());

    if (validInsights.length !== 5) {
      throw new Error(`Dữ liệu trả về không đủ 5 insight hoàn chỉnh (chỉ có ${validInsights.length}/5 insight hợp lệ).`);
    }

    state.product = {
      ...currentProduct,
      name: resolvedName
    };
    state.productName = resolvedName;
    state.insights = validInsights;
    console.log("state.insights normalized & validated:", state.insights);

    state.visionContext = payload.visionContext || {};

    if (resolvedName && !document.getElementById("productNameInput").value.trim()) {
      document.getElementById("productNameInput").value = resolvedName;
    }

    document.getElementById("product-name").textContent = resolvedName || "Tên sản phẩm không rõ";
    document.getElementById("empty-state").hidden = state.insights.length > 0;
    document.getElementById("save-form").hidden = state.insights.length === 0;

    renderProductSummary();
    renderInsightsTable();
  }

  function renderProductSummary() {
    const summary = document.getElementById("save-product-summary");
    if (!summary) return;
    const product = state.product || {};
    summary.innerHTML = "";

    // 1. Badge Master DB status
    const masterChip = document.createElement("div");
    if (product.master && product.master.title) {
      masterChip.style = "padding: 6px 12px; border-radius: 8px; background: rgba(52, 211, 153, 0.12); border: 1px solid rgba(52, 211, 153, 0.3); color: #34d399; font-size: 12px; font-weight: 600; display: inline-flex; align-items: center; gap: 6px;";
      masterChip.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"></polyline></svg> Master DB: ${escapeHtml(product.master.title)} (Giá: ${escapeHtml(product.price || 'Chưa có')} | ${escapeHtml(product.classification || 'Mặc định')})`;
    } else {
      masterChip.style = "padding: 6px 12px; border-radius: 8px; background: rgba(251, 191, 36, 0.1); border: 1px solid rgba(251, 191, 36, 0.25); color: #fbbf24; font-size: 12px; font-weight: 600; display: inline-flex; align-items: center; gap: 6px;";
      masterChip.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg> Chưa tìm thấy trong Master DB (ca055a7742824b9598abde7a7686d144)`;
    }
    summary.appendChild(masterChip);

    // 2. Thư mục local Drive chip
    if (product.folderPath) {
      const folderChip = document.createElement("div");
      folderChip.style = "padding: 6px 12px; border-radius: 8px; background: rgba(56, 189, 248, 0.1); border: 1px solid rgba(56, 189, 248, 0.25); color: #38bdf8; font-size: 12px; font-weight: 500; display: inline-flex; align-items: center; gap: 6px; word-break: break-all;";
      folderChip.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg> Thư mục Drive: ${escapeHtml(product.shop ? product.shop + ' / ' : '')}${escapeHtml(product.folderName || product.folderPath)}`;
      summary.appendChild(folderChip);
    }

    // 3. Link Media sản phẩm Drive chip (nếu có)
    if (product.driveUrl) {
      const mediaChip = document.createElement("a");
      mediaChip.href = product.driveUrl;
      mediaChip.target = "_blank";
      mediaChip.style = "padding: 6px 12px; border-radius: 8px; background: rgba(59, 130, 246, 0.1); border: 1px solid rgba(59, 130, 246, 0.25); color: #60a5fa; font-size: 12px; font-weight: 600; display: inline-flex; align-items: center; gap: 6px; text-decoration: none;";
      mediaChip.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"></path><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"></path></svg> Link Media Drive ↗`;
      summary.appendChild(mediaChip);
    }

    // 4. Ghi chú (Note) nếu có
    if (product.note) {
      const noteChip = document.createElement("div");
      noteChip.style = "padding: 6px 12px; border-radius: 8px; background: rgba(168, 85, 247, 0.1); border: 1px solid rgba(168, 85, 247, 0.25); color: #c084fc; font-size: 12px; font-weight: 500; display: inline-flex; align-items: center; gap: 6px;";
      noteChip.innerHTML = `📝 Ghi chú: ${escapeHtml(product.note)}`;
      summary.appendChild(noteChip);
    }
  }

  function renderInsightsTable() {
    const tbody = document.getElementById("insight-table-body");
    if (!tbody) return;
    tbody.innerHTML = "";

    state.insights.forEach((insight, index) => {
      const row = document.createElement("tr");

      // 1. Cột STT
      const indexCell = document.createElement("td");
      indexCell.style = "text-align: center; font-weight: 700; color: var(--brand); vertical-align: top; padding-top: 14px;";
      indexCell.textContent = String(index + 1);

      // 2. Cột Góc viết
      const angleCell = document.createElement("td");
      angleCell.style = "vertical-align: top; padding-top: 12px;";
      const angleBadge = document.createElement("div");
      angleBadge.style = "display: inline-block; padding: 5px 10px; border-radius: 6px; background: rgba(45, 212, 191, 0.12); color: var(--brand); font-weight: 700; font-size: 12px; line-height: 1.4; border: 1px solid rgba(45, 212, 191, 0.25);";
      angleBadge.textContent = insight.angle || `Góc #${index + 1}`;
      angleCell.appendChild(angleBadge);

      // 3. Cột Tiêu đề post
      const titleCell = document.createElement("td");
      titleCell.style = "vertical-align: top; padding-top: 12px;";
      const titleEl = document.createElement("div");
      titleEl.style = "font-weight: 700; font-size: 13px; color: var(--text); line-height: 1.45;";
      titleEl.textContent = insight.postTitle || "Chưa có tiêu đề";
      titleCell.appendChild(titleEl);

      // 4. Cột Nội dung bài viết (Tóm tắt ngắn gọn + nút xem chi tiết)
      const contentCell = document.createElement("td");
      contentCell.style = "vertical-align: top; padding-top: 12px;";
      const contentPreview = document.createElement("div");
      contentPreview.style = "font-size: 12px; color: var(--muted); line-height: 1.5; max-height: 60px; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; word-break: break-word;";
      const rawText = (insight.insightContent || "").replace(/[*#⭐🍀📍]/g, "").trim();
      contentPreview.textContent = rawText || "Chưa có nội dung bài viết.";
      
      const btnViewInline = document.createElement("button");
      btnViewInline.type = "button";
      btnViewInline.className = "ghost";
      btnViewInline.style = "margin-top: 6px; padding: 3px 8px; font-size: 11px; font-weight: 700; border-radius: 4px; background: rgba(56, 189, 248, 0.1); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.25); cursor: pointer; display: inline-flex; align-items: center; gap: 4px;";
      btnViewInline.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg> Xem chi tiết bài`;
      btnViewInline.onclick = () => openInsightDetailModal(index);
      contentCell.append(contentPreview, btnViewInline);

      // 5. Cột Từ khóa
      const keywordsCell = document.createElement("td");
      keywordsCell.style = "vertical-align: top; padding-top: 12px;";
      const kwWrapper = document.createElement("div");
      kwWrapper.style = "display: flex; flex-wrap: wrap; gap: 4px;";
      const kws = (insight.keywords || "").split(/[,;\n]/).map(k => k.trim()).filter(Boolean);
      if (kws.length > 0) {
        kws.slice(0, 3).forEach(k => {
          const tag = document.createElement("span");
          tag.style = "font-size: 11px; padding: 2px 6px; border-radius: 4px; background: var(--soft); border: 1px solid var(--panel-border); color: var(--muted);";
          tag.textContent = k;
          kwWrapper.appendChild(tag);
        });
        if (kws.length > 3) {
          const more = document.createElement("span");
          more.style = "font-size: 10px; color: var(--muted); align-self: center;";
          more.textContent = `+${kws.length - 3}`;
          kwWrapper.appendChild(more);
        }
      } else {
        kwWrapper.innerHTML = `<span style="font-size: 11px; color: var(--muted);">—</span>`;
      }
      keywordsCell.appendChild(kwWrapper);

      // 6. Cột Hình ảnh & Thư mục
      const mediaCell = document.createElement("td");
      mediaCell.style = "vertical-align: top; padding-top: 12px;";
      mediaCell.appendChild(createInsightMediaCell(insight, index));

      // 7. Cột Thao tác Chi tiết
      const actionCell = document.createElement("td");
      actionCell.style = "vertical-align: top; text-align: center; padding-top: 12px;";
      const btnAction = document.createElement("button");
      btnAction.type = "button";
      btnAction.className = "secondary";
      btnAction.style = "min-height: 32px; padding: 0 10px; font-size: 11.5px; font-weight: 700; border-radius: 6px; cursor: pointer; display: inline-flex; align-items: center; gap: 4px; white-space: nowrap;";
      btnAction.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg> Chi tiết`;
      btnAction.onclick = () => openInsightDetailModal(index);
      actionCell.appendChild(btnAction);

      row.append(indexCell, angleCell, titleCell, contentCell, keywordsCell, mediaCell, actionCell);
      tbody.appendChild(row);
    });
  }

  function createInsightMediaCell(insight, index) {
    const wrapper = document.createElement("div");
    wrapper.style = "display: flex; flex-direction: column; gap: 6px; padding: 4px 0;";

    // Status & Count badge
    const statusRow = document.createElement("div");
    statusRow.style = "display: flex; align-items: center; justify-content: space-between; gap: 6px;";

    const countBadge = document.createElement("span");
    const count = insight.imageCount || (insight.images ? insight.images.length : 0);
    if (count > 0) {
      countBadge.style = "color: #34d399; font-weight: 700; font-size: 11.5px; display: inline-flex; align-items: center; gap: 4px;";
      countBadge.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"></polyline></svg> ${count} hình`;
    } else {
      countBadge.style = "color: #fbbf24; font-weight: 600; font-size: 11.5px; display: inline-flex; align-items: center; gap: 4px;";
      countBadge.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg> Chưa có hình`;
    }
    statusRow.appendChild(countBadge);

    if (insight.driveUrl) {
      const linkA = document.createElement("a");
      linkA.href = insight.driveUrl;
      linkA.target = "_blank";
      linkA.style = "color: #38bdf8; font-size: 11px; text-decoration: underline; font-weight: 600;";
      linkA.textContent = "Mở Drive ↗";
      statusRow.appendChild(linkA);
    }
    wrapper.appendChild(statusRow);

    // Folder name
    if (insight.folderName) {
      const folderDiv = document.createElement("div");
      folderDiv.style = "font-size: 10.5px; color: var(--muted); word-break: break-all; line-height: 1.3;";
      folderDiv.innerHTML = `📁 ${escapeHtml(insight.folderName)}`;
      wrapper.appendChild(folderDiv);
    }

    // Thumbnails
    if (insight.images && insight.images.length > 0) {
      const thumbRow = document.createElement("div");
      thumbRow.style = "display: flex; gap: 4px; flex-wrap: wrap; margin-top: 2px;";
      insight.images.slice(0, 4).forEach(img => {
        const thumb = document.createElement("img");
        thumb.src = img.url;
        thumb.title = img.name;
        thumb.style = "width: 32px; height: 32px; object-fit: cover; border-radius: 4px; border: 1px solid var(--panel-border); cursor: pointer; transition: transform 0.15s;";
        thumb.onmouseenter = () => { thumb.style.transform = "scale(1.15)"; };
        thumb.onmouseleave = () => { thumb.style.transform = "scale(1)"; };
        thumb.onclick = () => window.open(img.url, "_blank");
        thumbRow.appendChild(thumb);
      });
      if (insight.images.length > 4) {
        const moreSpan = document.createElement("span");
        moreSpan.style = "font-size: 10px; color: var(--muted); align-self: center;";
        moreSpan.textContent = `+${insight.images.length - 4}`;
        thumbRow.appendChild(moreSpan);
      }
      wrapper.appendChild(thumbRow);
    }

    return wrapper;
  }

  function createEditableCell(value, field, rowIndex, multiline = false) {
    const el = document.createElement(multiline ? "textarea" : "input");
    if (!multiline) {
      el.type = "text";
    }
    el.value = value;
    el.addEventListener("input", (e) => {
      state.insights[rowIndex][field] = e.target.value;
    });
    return el;
  }

  function createRewriteCell(rowIndex) {
    const wrapper = document.createElement("div");
    wrapper.className = "rewrite-cell";

    const commentInput = document.createElement("textarea");
    commentInput.rows = 3;
    commentInput.placeholder = "Góp ý: thiếu keyword, tiêu đề chưa SEO...";

    const button = document.createElement("button");
    button.type = "button";
    button.className = "rewrite-button btn-capture";
    button.textContent = "Viết lại";

    button.style.padding = "6px 12px";
    button.style.fontSize = "12px";
    button.style.minHeight = "28px";

    button.addEventListener("click", () => rewriteInsightAtRow(rowIndex, commentInput, button));

    wrapper.append(commentInput, button);
    return wrapper;
  }

  async function rewriteInsightAtRow(rowIndex, commentInput, button) {
    const comment = commentInput.value.trim();
    if (!comment) {
      setStatus("analyze-status", "Nhập góp ý cần sửa trước khi viết lại.", "is-error");
      return;
    }

    button.disabled = true;
    setStatus("analyze-status", `Đang gửi yêu cầu viết lại insight #${rowIndex + 1}...`, "muted");
    state.currentRewriteRowIndex = rowIndex; // Lưu lại dòng đang sửa để đồng bộ thủ công nếu cần

    try {
      const response = await fetch("/api/rewrite-insight", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          productName: state.productName,
          visionContext: state.visionContext,
          insight: state.insights[rowIndex],
          comment
        })
      });

      const payload = await response.json();
      if (!response.ok || payload.error) {
        throw new Error(payload.error || "Lỗi viết lại insight.");
      }

      state.insights[rowIndex] = payload.insight;

      // Chuẩn hóa single insight vừa viết lại
      const rawInsight = state.insights[rowIndex] || {};
      state.insights[rowIndex] = {
        angle: rawInsight.angle || rawInsight.GocViet || rawInsight.gocViet || "",
        postTitle: rawInsight.postTitle || rawInsight.title || rawInsight.tieuDe || "",
        insightContent: rawInsight.insightContent || rawInsight.content || rawInsight.noiDung || "",
        keywords: rawInsight.keywords || rawInsight.keyword || rawInsight.tuKhoa || ""
      };

      renderInsightsTable();
      setStatus("analyze-status", `Đã cập nhật lại bài viết #${rowIndex + 1} thành công.`, "is-success");
    } catch (e) {
      setStatus("analyze-status", "Lỗi viết lại: " + e.message, "is-error");
    } finally {
      button.disabled = false;
    }
  }

  let activeModalPostIndex = 0;

  function openInsightDetailModal(targetIndex = 0) {
    if (!state.insights || state.insights.length === 0) {
      alert("Vui lòng chọn một sản phẩm từ danh sách bên trái trước!");
      return;
    }
    const modalTitle = document.getElementById("fullPostsModalTitle");
    if (modalTitle) {
      modalTitle.textContent = `Xem & Chỉnh Sửa Chi Tiết Bài Viết (${state.insights.length} Insight)`;
    }
    activeModalPostIndex = Math.max(0, Math.min(targetIndex, state.insights.length - 1));
    renderFullPostsModalTabs();
    loadPostToModalFields(activeModalPostIndex);
    const modal = document.getElementById("fullPostsModal");
    if (modal) modal.style.display = "flex";
  }

  async function openFullPostsEditorModal() {
    openInsightDetailModal(0);
  }

  function closeFullPostsEditorModal() {
    const modal = document.getElementById("fullPostsModal");
    if (modal) modal.style.display = "none";
  }

  function renderFullPostsModalTabs() {
    const header = document.getElementById("fullPostsTabHeader");
    if (!header) return;
    header.innerHTML = "";

    state.insights.forEach((item, idx) => {
      const isActive = (idx === activeModalPostIndex);
      const tabBtn = document.createElement("div");
      tabBtn.role = "button";
      tabBtn.style.cssText = `
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        padding: 8px 12px;
        border-radius: 8px;
        cursor: pointer;
        transition: all 0.2s ease;
        border: 1px solid ${isActive ? '#38bdf8' : 'var(--panel-border)'};
        background: ${isActive ? 'rgba(56, 189, 248, 0.16)' : 'rgba(255, 255, 255, 0.03)'};
        box-shadow: ${isActive ? '0 2px 8px rgba(56, 189, 248, 0.2)' : 'none'};
      `;

      const titleText = escapeHtml(item.angle || item.postTitle || ('Insight ' + (idx + 1)));
      const activePill = isActive
        ? `<span style="font-size: 11px; font-weight: 700; color: #38bdf8; background: rgba(56, 189, 248, 0.2); padding: 2px 8px; border-radius: 12px; flex-shrink: 0;">Đang xem</span>`
        : `<span style="font-size: 11px; color: var(--muted); background: rgba(255, 255, 255, 0.05); padding: 2px 8px; border-radius: 12px; flex-shrink: 0;">Nhấn chọn</span>`;

      tabBtn.innerHTML = `
        <div style="display: flex; align-items: center; gap: 10px; overflow: hidden; flex: 1;">
          <span style="display: inline-flex; align-items: center; gap: 5px; font-weight: 800; font-size: 13px; color: ${isActive ? '#38bdf8' : 'var(--text)'}; min-width: 66px; flex-shrink: 0;">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"></polyline></svg>
            Bài #${idx + 1}
          </span>
          <span style="font-size: 12px; font-weight: ${isActive ? '600' : '400'}; color: ${isActive ? '#f8fafc' : 'var(--muted)'}; white-space: normal; line-height: 1.4; word-break: break-word;">
            ${titleText}
          </span>
        </div>
        ${activePill}
      `;

      tabBtn.onclick = () => {
        saveModalFieldsToPost(activeModalPostIndex);
        activeModalPostIndex = idx;
        renderFullPostsModalTabs();
        loadPostToModalFields(activeModalPostIndex);
      };

      tabBtn.onmouseover = () => {
        if (idx !== activeModalPostIndex) {
          tabBtn.style.background = 'rgba(255, 255, 255, 0.07)';
          tabBtn.style.borderColor = 'rgba(255, 255, 255, 0.2)';
        }
      };
      tabBtn.onmouseout = () => {
        if (idx !== activeModalPostIndex) {
          tabBtn.style.background = 'rgba(255, 255, 255, 0.03)';
          tabBtn.style.borderColor = 'var(--panel-border)';
        }
      };

      header.appendChild(tabBtn);
    });
  }

  function loadPostToModalFields(idx) {
    const item = state.insights[idx];
    if (!item) return;
    const post = item.full_post || {};

    document.getElementById("modalEditPostTitle").value = item.postTitle || "";
    document.getElementById("modalEditAngle").value = item.angle || "";
    
    // Nạp toàn văn bài viết chi tiết từ Notion hoặc AI sinh
    let desc = "";
    if (typeof post.description === "string" && post.description.trim()) {
      desc = post.description;
    } else if (Array.isArray(post.description) && post.description.length > 0) {
      desc = post.description.join("\n\n");
    } else {
      desc = item.insightContent || "";
    }
    document.getElementById("modalEditDescription").value = desc;

    document.getElementById("modalEditIngredients").value = Array.isArray(post.ingredients) ? post.ingredients.join("\n") : (post.ingredients || "");
    document.getElementById("modalEditBenefits").value = Array.isArray(post.benefits) ? post.benefits.join("\n") : (post.benefits || "");
    document.getElementById("modalEditTargetUsers").value = Array.isArray(post.target_users) ? post.target_users.join("\n") : (post.target_users || "");
    document.getElementById("modalEditUsage").value = Array.isArray(post.usage) ? post.usage.join("\n") : (post.usage || "");
    document.getElementById("modalEditNotes").value = Array.isArray(post.notes) ? post.notes.join("\n") : (post.notes || "");
    document.getElementById("modalEditHashtags").value = Array.isArray(post.hashtags) ? post.hashtags.join(" ") : (post.hashtags || item.keywords || "");
  }

  function saveModalFieldsToPost(idx) {
    if (!state.insights[idx]) return;

    const postTitle = document.getElementById("modalEditPostTitle").value.trim();
    const angle = document.getElementById("modalEditAngle").value.trim();
    const descText = document.getElementById("modalEditDescription").value.trim();

    state.insights[idx].postTitle = postTitle;
    state.insights[idx].angle = angle;
    state.insights[idx].insightContent = descText;

    const ingText = document.getElementById("modalEditIngredients").value.trim();
    const benText = document.getElementById("modalEditBenefits").value.trim();
    const tarText = document.getElementById("modalEditTargetUsers").value.trim();
    const noteText = document.getElementById("modalEditNotes").value.trim();

    state.insights[idx].full_post = {
      description: descText,
      ingredients: ingText ? ingText.split("\n").map(s => s.trim()).filter(Boolean) : [],
      benefits: benText ? benText.split("\n").map(s => s.trim()).filter(Boolean) : [],
      target_users: tarText ? tarText.split("\n").map(s => s.trim()).filter(Boolean) : [],
      usage: document.getElementById("modalEditUsage").value.trim(),
      notes: noteText ? noteText.split("\n").map(s => s.trim()).filter(Boolean) : [],
      hashtags: document.getElementById("modalEditHashtags").value.trim()
    };
  }

  function saveFullPostsFromModal() {
    saveModalFieldsToPost(activeModalPostIndex);
    renderInsightsTable(); // Cập nhật lại tiêu đề, angle và tóm tắt lên bảng review
    closeFullPostsEditorModal();

    const previewBtn = document.getElementById("btnPreviewPosts");
    if (previewBtn) {
      const insCount = state.insights.length;
      previewBtn.innerHTML = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg> <span>Xem chi tiết bài viết (${insCount} Insight - Đã lưu sửa)</span>`;
    }
    alert("Đã lưu nội dung chi tiết bài viết! Bạn có thể bấm 'Lưu bài viết vào Notion' để cập nhật lên hệ thống.");
  }

  async function regenerateCurrentPostWithAI() {
    const idx = activeModalPostIndex;
    const item = state.insights[idx];
    if (!item) return;

    const btn = document.getElementById("btnRegenSinglePost");
    if (btn) btn.disabled = true;

    try {
      const product = collectProductInfo();
      const res = await api("/api/insight/generate-single-post", {
        productName: product.name || state.productName,
        productDescription: product.description || "",
        classification: product.classification || "",
        angle: document.getElementById("modalEditAngle").value.trim() || item.angle,
        postTitle: document.getElementById("modalEditPostTitle").value.trim() || item.postTitle,
        insightContent: item.insightContent || "",
        keywords: item.keywords || "",
        writingPrompt: getCurrentPostWritingPrompt()
      });

      if (res.full_post) {
        state.insights[idx].full_post = res.full_post;
        loadPostToModalFields(idx);
        alert(`Đã tạo lại bài viết #${idx + 1} thành công bằng Gemini AI!`);
      }
    } catch (e) {
      alert("Lỗi viết lại bài bằng AI: " + (e.error || e.message || JSON.stringify(e)));
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  async function saveInsightsToNotion(event) {
    if (event) event.preventDefault();

    const saveBtn = document.getElementById("save-button");
    if (saveBtn) saveBtn.disabled = true;
    setStatus("save-status", "Đang lưu bài viết và insight vào Notion...", "muted");

    try {
      const selectedPageId = document.getElementById("productPageId")?.value.trim() || "";
      const payload = {
        page_id: selectedPageId,
        product_name: document.getElementById("productNameInput")?.value.trim() || "",
        price: document.getElementById("productPrice")?.value.trim() || "",
        classification: document.getElementById("productClassification")?.value.trim() || "",
        variants: document.getElementById("productVariants")?.value.trim() || "",
        insights: state.insights.map(item => ({
          id: item.id,
          title: item.postTitle || "",
          angle: item.angle || "",
          keywords: item.keywords || "",
          content: item.insightContent || ""
        }))
      };

      const res = await api("/api/shopee/insights/save-to-notion", payload);
      setStatus("save-status", `✓ ${res.message || "Đã lưu vào Notion thành công!"}`, "is-success");
      alert(res.message || "Đã lưu thành công các Insight vào Notion!");
    } catch(e) {
      console.error(e);
      setStatus("save-status", "Lỗi lưu Notion: " + (e.error || e.message || JSON.stringify(e)), "is-error");
      alert("Lỗi lưu Notion: " + (e.error || e.message || JSON.stringify(e)));
    } finally {
      if (saveBtn) saveBtn.disabled = false;
    }
  }

  async function generateProductInsights() {
    const select = document.getElementById("shopeePendingProducts");
    const pageId = select.value;
    if (!pageId) {
      alert("Vui lòng chọn một sản phẩm từ danh sách!");
      return;
    }

    const productTitle = select.options[select.selectedIndex].text;
    if (!confirm(`Bạn có chắc chắn muốn AI tự động sinh 5 bài viết Insight cho sản phẩm "${productTitle}" không?`)) {
      return;
    }

    document.getElementById("shopeeSyncLogBox").innerHTML = "";
    log({step: "shopee_sync", message: `Gửi yêu cầu sinh 5 bài viết AI cho sản phẩm: ${productTitle}...`});
    startPoll();

    try {
      const d = await api("/api/shopee/insights/generate", { page_id: pageId });
      log({step: "shopee_sync", message: d.message});
      // Tự động load lại danh sách sản phẩm sau 30 giây (khi tiến trình dự kiến hoàn tất)
      setTimeout(loadPendingProducts, 30000);
    } catch(e) {
      log({step: "shopee_sync", message: "Lỗi sinh bài viết: " + (e.error || e.message || JSON.stringify(e))});
      alert("Lỗi: " + (e.error || e.message || JSON.stringify(e)));
    }
  }

  async function checkShopeeBotStatus() {
    try {
      const d = await api("/api/shopee/bot/status");
      updateShopeeBotUI(d.running);
    } catch(e) {
      console.error("Lỗi kiểm tra trạng thái bot:", e);
    }
  }

  function updateShopeeBotUI(running) {
    const badge = document.getElementById("shopeeBotStatusBadge");
    const text = document.getElementById("shopeeBotStatusText");
    const btn = document.getElementById("btnToggleShopeeBot");

    if (running) {
      badge.className = "badge ok";
      badge.style.background = "rgba(34, 197, 94, 0.15)";
      text.textContent = "Bot Telegram: ONLINE";
      btn.textContent = "Dừng Bot Telegram";
      btn.style.background = "#ef4444";
    } else {
      badge.className = "badge danger";
      badge.style.background = "rgba(239, 68, 68, 0.15)";
      text.textContent = "Bot Telegram: OFFLINE";
      btn.textContent = "Khởi động Telegram Bot";
      btn.style.background = "var(--brand)";
    }
  }

  async function toggleShopeeBot() {
    const btn = document.getElementById("btnToggleShopeeBot");
    const isRunning = btn.textContent.includes("Dừng");

    try {
      if (isRunning) {
        log({step: "shopee_sync", message: "Đang gửi yêu cầu dừng Bot Telegram..."});
        const d = await api("/api/shopee/bot/stop", {});
        log({step: "shopee_sync", message: d.message});
      } else {
        log({step: "shopee_sync", message: "Đang gửi yêu cầu khởi động Bot Telegram..."});
        const d = await api("/api/shopee/bot/start", {});
        log({step: "shopee_sync", message: d.message});
      }
      setTimeout(checkShopeeBotStatus, 1500);
    } catch(e) {
      log({step: "shopee_sync", message: "Lỗi: " + (e.error || e.message || JSON.stringify(e))});
      alert("Lỗi điều khiển bot: " + (e.error || e.message || JSON.stringify(e)));
    }
  }

  async function runShopeeSync() {
    document.getElementById("shopeeSyncLogBox").innerHTML = "";
    log({step: "shopee_sync", message: "Gửi yêu cầu chạy đồng bộ Notion -> BigSeller..."});
    startPoll();

    const driveUrl = document.getElementById("shopeeSyncDriveUrl") ? document.getElementById("shopeeSyncDriveUrl").value.trim() : "";
    const selectedPageId = document.getElementById("productPageId")?.value.trim()
      || document.getElementById("shopeePendingProducts")?.value.trim()
      || "";
    if (!selectedPageId) {
      alert("Vui lòng chọn đúng sản phẩm cần xuất Excel trước khi đồng bộ.");
      return;
    }

    try {
      const d = await api("/api/shopee/sync/run", { drive_url: driveUrl, page_id: selectedPageId });
      log({step: "shopee_sync", message: d.message});
    } catch(e) {
      log({step: "shopee_sync", message: "Lỗi đồng bộ: " + (e.error || e.message || JSON.stringify(e))});
      alert("Lỗi kích hoạt đồng bộ: " + (e.error || e.message || JSON.stringify(e)));
    }
  }

  async function syncNotionImageLinks() {
    document.getElementById("shopeeSyncLogBox").innerHTML = "";
    log({step: "shopee_sync", message: "Bắt đầu tiến trình đồng bộ link hình ảnh Google Drive sang Notion..."});
    startPoll();

    const driveUrl = document.getElementById("shopeeSyncDriveUrl") ? document.getElementById("shopeeSyncDriveUrl").value.trim() : "";
    const selectedPageId = document.getElementById("productPageId")?.value.trim() || "";
    if (!selectedPageId) {
      alert("Vui lòng chọn đúng sản phẩm cần sửa link hình trước khi đồng bộ.");
      return;
    }

    try {
      const d = await api("/api/shopee/sync/links", { drive_url: driveUrl, page_id: selectedPageId });
      log({step: "shopee_sync", message: d.message});
    } catch(e) {
      log({step: "shopee_sync", message: "Lỗi đồng bộ link hình: " + (e.error || e.message || JSON.stringify(e))});
      alert("Lỗi kích hoạt đồng bộ link hình: " + (e.error || e.message || JSON.stringify(e)));
    }
  }

  async function loadShopeeExcelList() {
    try {
      const d = await api("/api/shopee/excel/list");
      const list = document.getElementById("shopeeExcelList");
      if (!list) return;

      if (d.length === 0) {
        list.innerHTML = `<div style="color: var(--muted); text-align: center; padding: 20px; font-size: 13px;">Chưa tạo file Excel nào.</div>`;
        return;
      }

      list.innerHTML = d.map(f => `
        <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--panel-border); border-radius: 8px; padding: 12px; display: flex; flex-direction: column; gap: 8px;">
          <div style="font-weight: 600; font-size: 13px; text-overflow: ellipsis; overflow: hidden; white-space: nowrap; color: var(--text);" title="${escapeHtml(f.name)}">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--brand)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 6px; display: inline-block; vertical-align: middle;"><path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2z"></path></svg>${escapeHtml(f.name)}
          </div>
          <div style="font-size: 11px; color: var(--muted); display: flex; justify-content: space-between; align-items: center;">
            <span>${f.time}</span>
            <div style="display: flex; gap: 8px; align-items: center;">
              <a href="${f.url}" download="${escapeHtml(f.name)}" style="color: var(--brand); text-decoration: none; font-weight: 700;">Tải về</a>
              <span style="color: var(--panel-border);">|</span>
              <a href="#" onclick="deleteShopeeExcel('${escapeHtml(f.name)}', '${escapeHtml((f.file_path || '').replace(/\\/g, '\\\\'))}'); return false;" style="color: #ef4444; text-decoration: none; font-weight: 700;">Xóa</a>
            </div>
          </div>
        </div>
      `).join("");
    } catch(e) {
      console.error("Lỗi tải danh sách file Excel:", e);
    }
  }

  async function deleteShopeeExcel(name, filePath) {
    if (!confirm(`Bạn có chắc chắn muốn xóa file ${name}?`)) return;
    try {
      const res = await fetch("/api/shopee/excel/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, file_path: filePath })
      });
      const d = await res.json();
      if (d.success) {
        loadShopeeExcelList();
      } else {
        alert("Lỗi xóa file: " + (d.error || d.message));
      }
    } catch(e) {
      console.error("Lỗi xóa file Excel:", e);
      alert("Lỗi xóa file Excel: " + e.message);
    }
  }

  async function deleteShopeeExcelAll() {
    if (!confirm("Bạn có chắc chắn muốn xóa TẤT CẢ các file Excel đồng bộ Shopee đã tạo? Hành động này không thể hoàn tác.")) return;
    try {
      const res = await fetch("/api/shopee/excel/delete-all", {
        method: "POST",
        headers: { "Content-Type": "application/json" }
      });
      const d = await res.json();
      if (d.success) {
        loadShopeeExcelList();
        alert(d.message);
      } else {
        alert("Lỗi xóa file: " + (d.error || d.message));
      }
    } catch(e) {
      console.error("Lỗi xóa tất cả file Excel:", e);
      alert("Lỗi xóa tất cả file Excel: " + e.message);
    }
  }

  function clearShopeeSyncLogs() {
    state.shopeeLogs = [];
    renderShopeeSyncLogs();
  }

  function renderShopeeSyncLogs() {
    const shopeeLogBox = document.getElementById("shopeeSyncLogBox");
    if (!shopeeLogBox) return;

    const filterInput = document.getElementById("shopeeSyncLogFilter");
    const filterVal = filterInput ? filterInput.value.trim().toLowerCase() : "";

    const filtered = state.shopeeLogs.filter(log => {
      if (!filterVal) return true;
      return log.message.toLowerCase().includes(filterVal);
    });

    shopeeLogBox.innerHTML = filtered.map(log => {
      return `<div style="color: ${log.color}; margin-bottom: 4px;">[${log.time}] ${escapeHtml(log.message)}</div>`;
    }).join("");

    const autoScrollCb = document.getElementById("shopeeSyncLogAutoScroll");
    const shouldScroll = autoScrollCb ? autoScrollCb.checked : true;
    if (shouldScroll) {
      shopeeLogBox.scrollTop = shopeeLogBox.scrollHeight;
    }
  }

  function filterShopeeSyncLogs() {
    renderShopeeSyncLogs();
  }

  async function useLatestPixelPhotoForShopee() {
    try {
      const response = await fetch("/api/automation/latest-photo");
      const d = await response.json();
      if (!response.ok) throw d;

      const isVideo = d.type === 'video' || d.name.endsWith('.mp4');
      if (isVideo) {
        alert("Hiện tại tính năng Shopee Sync chỉ hỗ trợ các file hình ảnh.");
        return;
      }

      // Chuyển dữ liệu base64 thành đối tượng File để tương thích tốt với luồng upload/paste
      const responseBlob = await fetch(d.base64);
      const blob = await responseBlob.blob();
      state.pastedFile = new File([blob], d.name, { type: blob.type });

      document.getElementById("image").value = "";
      document.getElementById("imageUrl").value = "";
      renderPreview();
    } catch(e) {
      console.error("Lỗi lấy ảnh Pixel mới nhất:", e);
      alert("Lỗi lấy ảnh Pixel mới nhất: " + (e.error || e.message || JSON.stringify(e)));
    }
  }

  function handlePosterFiles(files) {
    const limit = 4;
    const currentCount = posterImages.length;
    const remaining = limit - currentCount;
    const filesToProcess = Array.from(files).slice(0, remaining);

    filesToProcess.forEach(file => {
      const reader = new FileReader();
      reader.onload = function(e) {
        posterImages.push({
          name: file.name,
          base64: e.target.result
        });
        renderThumbnails();
      };
      reader.readAsDataURL(file);
    });
  }

  function renderThumbnails() {
    const container = document.getElementById("uploadedThumbnails");
    container.innerHTML = "";

    posterImages.forEach((img, idx) => {
      const wrapper = document.createElement("div");
      wrapper.className = "thumbnail-wrapper";
      wrapper.innerHTML = `
        <img src="${img.base64}" alt="${escapeHtml(img.name)}">
        <button class="remove-btn" onclick="removeUploadedImage(${idx})">×</button>
      `;
      container.appendChild(wrapper);
    });

    // Cập nhật nhãn đếm ảnh
    const label = document.querySelector("#posterDashboard label");
    label.textContent = `Tải lên hình ảnh (Tối đa 4) - Đã chọn ${posterImages.length}/4`;
  }

  function removeUploadedImage(idx) {
    posterImages.splice(idx, 1);
    renderThumbnails();
  }

  function updatePromptCount() {
    const prompt = document.getElementById("posterPrompt").value;
    document.getElementById("promptCharCount").textContent = `${prompt.length}/1000`;
  }

  function selectQuantity(btn, qty) {
    document.getElementById("posterQuantity").value = qty;
    document.querySelectorAll(".quantity-selector .select-btn").forEach(b => {
      b.classList.add("secondary");
    });
    btn.classList.remove("secondary");
  }

  const promptTemplates = [
    "Vui lòng tạo một poster quảng cáo sang trọng cho sản phẩm này, đặt trên một bệ đá cẩm thạch trắng, xung quanh có các giọt nước tinh khiết lấp lánh, ánh sáng studio studio softbox rực rỡ, nền màu gradient xanh dương mát mẻ, phong cách chuyên nghiệp, ảnh quảng cáo mỹ phẩm thương mại.",
    "Tạo poster quảng cáo thương mại cho sản phẩm, bối cảnh thiên nhiên tự nhiên với các lá trà xanh tươi mát xung quanh, ánh nắng tự nhiên nhẹ nhàng chiếu qua kẽ lá, hậu cảnh bokeh rừng xanh mướt, phong cách organic sạch sẽ, quảng cáo sản phẩm tự nhiên.",
    "Poster quảng cáo sản phẩm phong cách tương lai huyền ảo, đặt sản phẩm trên đĩa bay hologram phát sáng neon màu tím và xanh lam, nền công nghệ cyber hiện đại mờ ảo, khói huyền ảo bay nhẹ, phong cách 3D render cực kỳ sắc nét.",
    "Thiết kế poster quảng cáo phong cách tối giản (minimalism) cho sản phẩm, đặt trên một khối gỗ thô mộc mạc, nền trơn màu be ấm áp, ánh sáng mặt trời tự nhiên tạo bóng đổ dài nghệ thuật, phong cách đơn giản, tinh tế, trang nhã."
  ];
  let currentTemplateIdx = 0;

  function insertPromptTemplate() {
    document.getElementById("posterPrompt").value = promptTemplates[currentTemplateIdx];
    updatePromptCount();
    currentTemplateIdx = (currentTemplateIdx + 1) % promptTemplates.length;
  }

  async function checkAPIKey() {
    const key = document.getElementById("openaiKey").value.trim();
    if (!key) {
      alert("Vui lòng nhập API Key trước khi kiểm tra.");
      return;
    }

    const btn = document.getElementById("btnCheckAPI");
    const originalText = btn.textContent;
    btn.disabled = true;
    btn.textContent = "Đang check...";

    try {
      const r = await fetch("/api/openai/check", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({api_key: key})
      });
      const d = await r.json();

      if (d.valid) {
        // Tự động lưu khi check thành công
        await saveOpenAIConfig();
        let msg = "Kết nối API Key thành công!\n\n";
        msg += `1. GPT-4o / GPT-4o-mini: ${d.has_gpt4o ? "Sẵn sàng ✅" : "Không có quyền ❌"}\n`;
        msg += `2. GPT-image-1.5: ${d.has_dalle3 ? "Sẵn sàng ✅" : "Không có quyền ❌"}\n\n`;
        if (!d.has_dalle3) {
          msg += "⚠️ CẢNH BÁO: Tài khoản của bạn gọi được GPT-4o nhưng mô hình gpt-image-1.5 bị OpenAI báo không tồn tại. Vui lòng kiểm tra xem bạn đã nạp đủ $5 (lên Tier 1) chưa hoặc xem trong mục Settings -> Projects -> Limits/Models trên trang OpenAI xem model gpt-image-1.5 có bị tắt (disabled) không.";
        } else {
          msg += "🎉 Tài khoản của bạn đã đầy đủ quyền và sẵn sàng hoạt động!";
        }
        alert(msg);
      } else {
        alert("Lỗi kết nối API: " + d.message);
      }
    } catch(e) {
      alert("Lỗi kiểm tra API: " + (e.message || JSON.stringify(e)));
    } finally {
      btn.disabled = false;
      btn.textContent = originalText;
    }
  }

  async function loadOpenAIConfig() {
    try {
      const r = await fetch("/api/openai/config");
      const d = await r.json();
      const keyEl = document.getElementById("openaiKey");
      if (keyEl && d.api_key) {
        keyEl.value = d.api_key;
      }
      const dirEl = document.getElementById("posterExportDir");
      if (dirEl && d.export_dir) {
        dirEl.value = d.export_dir;
      }
    } catch(e) {
      console.error(e);
    }
  }

  async function saveOpenAIConfig() {
    const keyEl = document.getElementById("openaiKey");
    const key = keyEl ? keyEl.value.trim() : "";
    const dirEl = document.getElementById("posterExportDir");
    const dir = dirEl ? dirEl.value.trim() : "";
    await fetch("/api/openai/config", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({api_key: key, export_dir: dir})
    });
  }

  async function saveOpenAIConfigBtn() {
    try {
      await saveOpenAIConfig();
      alert("Đã lưu API Key thành công!");
    } catch(e) {
      alert("Lỗi lưu API Key: " + (e.message || JSON.stringify(e)));
    }
  }

  async function browseExportDirectory() {
    try {
      const r = await fetch("/api/utils/select-directory", { method: "POST" });
      const d = await r.json();
      if (d.directory) {
        const dirEl = document.getElementById("posterExportDir");
        if (dirEl) {
          dirEl.value = d.directory;
        }
        await saveOpenAIConfig();
        loadDownloadedImages();
      }
    } catch(e) {
      alert("Không thể mở hộp thoại chọn thư mục: " + (e.error || e.message || JSON.stringify(e)));
    }
  }

  // ==========================================
  // CONTENT IMAGE HELPER TOOL JS
  // ==========================================
  const CURRENT_VERSION = "v2.2.59";
  let promptsList = [];
  function addEvent(evt) {
    if (typeof appendAutomationLog === 'function') {
      appendAutomationLog(evt.message || JSON.stringify(evt));
    } else {
      console.log(evt.message || evt);
    }
  }
  let categoriesList = ["Shopee", "Facebook", "General"];
  let editingCategories = [];
  let contentSelectedImageBase64 = null;
  let sampleSelectedImageBase64 = null;
  let selectedPromptTitle = "";
  let chromeStatusInterval = null;

  async function loadPromptsLibrary() {
    try {
      const response = await fetch("/api/content/prompts");
      promptsList = await response.json();
      renderPromptsLibrary();
    } catch(e) {
      console.error("Lỗi tải thư viện prompts:", e);
    }
  }

  function renderPromptsLibrary() {
    const filter = document.getElementById("promptCategoryFilter").value;
    const container = document.getElementById("promptsLibraryContainer");
    container.innerHTML = "";

    const filtered = promptsList.filter(p => filter === "all" || p.category === filter);

    if (filtered.length === 0) {
      container.innerHTML = `<div style="text-align:center; color:var(--muted); font-size:12px; margin-top:20px;">Thư viện trống.</div>`;
      return;
    }

    filtered.forEach(p => {
      const card = document.createElement("div");
      card.className = "prompt-library-card";
      card.style = "background: rgba(255,255,255,0.03); border: 1px solid var(--panel-border); border-radius: 8px; padding: 12px; cursor: pointer; position: relative; transition: all 0.2s;";
      card.innerHTML = `
        <div style="font-weight: 700; font-size: 13px; color: var(--text); margin-bottom: 4px; display: flex; justify-content: space-between; align-items: center; padding-right: 85px;">
          <span style="text-overflow: ellipsis; overflow: hidden; white-space: nowrap; max-width: 220px; color: var(--text);" title="${escapeHtml(p.title)}">${escapeHtml(p.title)}</span>
        </div>
        <div style="font-size: 12px; color: var(--muted); display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; line-height: 1.4; padding-right: 20px;">
          ${escapeHtml(p.content)}
        </div>
        <div style="position: absolute; top: 10px; right: 10px; display: flex; gap: 6px; z-index: 2;">
          <span onclick="event.stopPropagation(); openPromptModal('${p.id}')" style="color:var(--brand); font-size: 10px; cursor:pointer; font-weight:700; background:rgba(59,130,246,0.15); padding: 2px 6px; border-radius: 4px; transition: background 0.2s;">Sửa</span>
          <span onclick="event.stopPropagation(); deletePromptTemplate('${p.id}')" style="color:#ef4444; font-size: 10px; cursor:pointer; font-weight:700; background:rgba(239,68,68,0.15); padding: 2px 6px; border-radius: 4px; transition: background 0.2s;">Xóa</span>
        </div>
      `;
      card.onclick = () => selectPromptTemplate(p.id);

      card.onmouseenter = () => { card.style.background = "rgba(255,255,255,0.07)"; card.style.borderColor = "var(--brand)"; };
      card.onmouseleave = () => { card.style.background = "rgba(255,255,255,0.03)"; card.style.borderColor = "var(--panel-border)"; };

      container.appendChild(card);
    });
  }

  function escapeHtml(str) {
    if (!str) return "";
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  }

  function selectPromptTemplate(id) {
    const p = promptsList.find(item => item.id === id);
    if (p) {
      document.getElementById("contentEditorPrompt").value = p.content;
      selectedPromptTitle = p.title || "";
    }
  }

  function filterPromptsList() {
    renderPromptsLibrary();
  }

  async function loadCategories() {
    try {
      const response = await fetch("/api/content/categories");
      categoriesList = await response.json();
      updateCategoryDropdowns();
    } catch(e) {
      console.error("Lỗi tải danh mục:", e);
    }
  }

  function updateCategoryDropdowns() {
    const filterSelect = document.getElementById("promptCategoryFilter");
    const currentFilterVal = filterSelect.value;
    filterSelect.innerHTML = `<option value="all">Tất cả danh mục</option>`;
    categoriesList.forEach(cat => {
      filterSelect.innerHTML += `<option value="${escapeHtml(cat)}">${escapeHtml(cat)}</option>`;
    });
    if (categoriesList.includes(currentFilterVal)) {
      filterSelect.value = currentFilterVal;
    } else {
      filterSelect.value = "all";
    }

    const modalSelect = document.getElementById("promptModalCategory");
    modalSelect.innerHTML = "";
    categoriesList.forEach(cat => {
      modalSelect.innerHTML += `<option value="${escapeHtml(cat)}">${escapeHtml(cat)}</option>`;
    });
  }

  window.openCategoryModal = function() {
    editingCategories = [...categoriesList];
    renderCategoriesManageList();
    document.getElementById("categoryModal").style.display = "flex";
  };

  window.closeCategoryModal = function() {
    document.getElementById("categoryModal").style.display = "none";
  };

  function renderCategoriesManageList() {
    const container = document.getElementById("categoriesListContainer");
    container.innerHTML = "";

    if (editingCategories.length === 0) {
      container.innerHTML = `<div style="text-align:center; color:var(--muted); font-size:12px; margin: 10px 0;">Chưa có danh mục nào. Hãy bấm thêm mới ở dưới.</div>`;
      return;
    }

    editingCategories.forEach((cat, index) => {
      const row = document.createElement("div");
      row.style = "display: flex; gap: 8px; align-items: center; width: 100%;";
      row.innerHTML = `
        <input type="text" value="${escapeHtml(cat)}" onchange="updateEditingCategoryValue(${index}, this.value)" style="flex: 1; min-height: 36px; padding: 0 10px; background: rgba(0,0,0,0.12); border: 1px solid var(--panel-border); border-radius: 6px; color: var(--text); font-size: 13px;">
        <button type="button" class="ghost" onclick="deleteCategoryInModal(${index})" style="min-height: 36px; padding: 8px; border: 1px solid rgba(239,68,68,0.2); border-radius: 6px; color: #ef4444; cursor: pointer; display: flex; align-items: center; justify-content: center; background: none;" title="Xóa danh mục">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg>
        </button>
      `;
      container.appendChild(row);
    });
  }

  window.updateEditingCategoryValue = function(index, val) {
    editingCategories[index] = val.trim();
  };

  window.addCategoryRowInModal = function() {
    editingCategories.push("");
    renderCategoriesManageList();
    setTimeout(() => {
      const container = document.getElementById("categoriesListContainer");
      container.scrollTop = container.scrollHeight;
      const inputs = container.querySelectorAll("input");
      if (inputs.length > 0) {
        inputs[inputs.length - 1].focus();
      }
    }, 50);
  };

  window.deleteCategoryInModal = function(index) {
    editingCategories.splice(index, 1);
    renderCategoriesManageList();
  };

  window.saveCategoriesFromModal = async function() {
    const newCategories = editingCategories.map(c => c.trim()).filter(c => c !== "");
    if (newCategories.length === 0) {
      alert("Bạn phải giữ lại ít nhất 1 danh mục.");
      return;
    }

    const rename_map = {};
    const deleted = [];

    const minLen = Math.min(categoriesList.length, newCategories.length);
    for (let i = 0; i < minLen; i++) {
      if (categoriesList[i] !== newCategories[i]) {
        rename_map[categoriesList[i]] = newCategories[i];
      }
    }

    if (categoriesList.length > newCategories.length) {
      for (let i = newCategories.length; i < categoriesList.length; i++) {
        deleted.push(categoriesList[i]);
      }
    }

    try {
      const response = await fetch("/api/content/categories", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          categories: newCategories,
          rename_map: rename_map,
          deleted: deleted
        })
      });
      const d = await response.json();
      if (!response.ok) throw d;

      closeCategoryModal();
      await loadCategories();
      await loadPromptsLibrary();
    } catch(e) {
      alert("Lỗi lưu danh mục: " + (e.error || e.message || JSON.stringify(e)));
    }
  };

  function triggerImportPrompt() {
    document.getElementById('promptImportInput').click();
  }

  function handlePromptImport(event) {
    const file = event.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    addEvent({step: 'prompt_import', message: `Bắt đầu xử lý nhập tệp: ${file.name}...`});

    fetch('/api/content/prompts/import', {
      method: 'POST',
      body: formData
    })
    .then(async res => {
      const data = await res.json();
      if (!res.ok) throw data;
      return data;
    })
    .then(data => {
      addEvent({step: 'prompt_import', message: `Nhập file thành công! Đã thêm ${data.count} prompt mới.`});
      loadCategories().then(() => {
        loadPromptsLibrary();
      });
    })
    .catch(err => {
      console.error(err);
      addEvent({step: 'error', message: `Lỗi nhập file: ${err.message || err.error || 'Lỗi không xác định'}`});
    })
    .finally(() => {
      event.target.value = '';
    });
  }

  function exportPrompts() {
    if (!promptsList || promptsList.length === 0) {
      alert("Thư viện prompt đang trống, không thể xuất.");
      return;
    }
    addEvent({step: 'prompt_export', message: 'Đang chuẩn bị xuất danh sách prompt...'});
    const lines = promptsList.map(p => {
      const category = p.category || "General";
      const title = p.title || "";
      const content = p.content || "";
      return `Danh mục: ${category}\nTiêu đề: ${title}\nNội dung: ${content}`;
    });
    const exportText = lines.join('\n---\n');
    const blob = new Blob([exportText], { type: 'text/plain;charset=utf-8' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = 'prompts_export.txt';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    addEvent({step: 'prompt_export', message: 'Đã xuất file prompts_export.txt thành công.'});
  }

  function exportCurrentPrompt() {
    const promptText = document.getElementById('contentEditorPrompt').value.trim();
    if (!promptText) {
      alert("Nội dung prompt đang trống, không thể xuất.");
      return;
    }
    addEvent({step: 'prompt_export', message: 'Đang tải prompt soạn thảo...'});
    const blob = new Blob([promptText], { type: 'text/plain;charset=utf-8' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = 'prompt_soan_thao.txt';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    addEvent({step: 'prompt_export', message: 'Đã tải tệp prompt_soan_thao.txt thành công.'});
  }

  function openPromptModal(id = "") {
    const modal = document.getElementById("promptModal");
    const title = document.getElementById("promptModalTitle");
    const idInput = document.getElementById("promptModalId");
    const catSelect = document.getElementById("promptModalCategory");
    const titleInput = document.getElementById("promptModalTitleInput");
    const contentInput = document.getElementById("promptModalContentInput");

    if (id) {
      title.innerText = "Sửa Prompt Mẫu";
      const p = promptsList.find(item => item.id === id);
      if (p) {
        idInput.value = p.id;
        catSelect.value = p.category;
        titleInput.value = p.title;
        contentInput.value = p.content;
      }
    } else {
      title.innerText = "Thêm Prompt Mới";
      idInput.value = "";
      catSelect.value = categoriesList.length > 0 ? categoriesList[0] : "";
      titleInput.value = "";
      contentInput.value = "";
    }

    modal.style.display = "flex";
  }

  function closePromptModal() {
    document.getElementById("promptModal").style.display = "none";
  }

  async function savePromptFromModal() {
    const id = document.getElementById("promptModalId").value;
    const category = document.getElementById("promptModalCategory").value;
    const title = document.getElementById("promptModalTitleInput").value.trim();
    const content = document.getElementById("promptModalContentInput").value.trim();

    if (!title || !content) {
      alert("Vui lòng nhập đầy đủ tiêu đề và nội dung.");
      return;
    }

    try {
      const response = await fetch("/api/content/prompts", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({ id, category, title, content })
      });
      const d = await response.json();
      if (!response.ok) throw d;

      closePromptModal();
      await loadPromptsLibrary();
    } catch(e) {
      alert("Lỗi lưu prompt: " + (e.error || e.message || JSON.stringify(e)));
    }
  }

  async function deletePromptTemplate(id) {
    if (!confirm("Bạn có chắc chắn muốn xóa prompt này không?")) return;
    try {
      const response = await fetch(`/api/content/prompts/${id}`, { method: "DELETE" });
      const d = await response.json();
      if (!response.ok) throw d;
      await loadPromptsLibrary();
    } catch(e) {
      alert("Lỗi xóa prompt: " + (e.error || e.message || JSON.stringify(e)));
    }
  }

  async function startChromeDebug() {
    try {
      const response = await fetch("/api/automation/chrome/start", { method: "POST" });
      const d = await response.json();
      if (!response.ok) throw d;
      alert("Đã kích hoạt tệp mở Chrome Debug. Cửa sổ Chrome thật sẽ tự động hiển thị.");
      setTimeout(checkChromeStatus, 1500);
    } catch(e) {
      alert("Không thể chạy lệnh Chrome: " + (e.message || JSON.stringify(e)));
    }
  }

  async function checkChromeStatus() {
    try {
      const response = await fetch("/api/automation/chrome/status");
      const d = await response.json();
      const badge = document.getElementById("chromeStatusBadge");
      const text = document.getElementById("chromeStatusText");

      if (d.online) {
        badge.className = "badge ok";
        text.innerText = "ChatGPT Chrome: Online";
      } else {
        badge.className = "badge danger";
        text.innerText = "ChatGPT Chrome: Offline";
      }
    } catch(e) {
      console.error("Lỗi kiểm tra trạng thái Chrome Debug 9222:", e);
    }

    try {
      const response = await fetch("/api/automation/chrome-gemini/status");
      const d = await response.json();
      const badge = document.getElementById("geminiStatusBadge");
      const text = document.getElementById("geminiStatusText");

      if (d.online) {
        badge.className = "badge ok";
        text.innerText = "Gemini Chrome: Online";
      } else {
        badge.className = "badge danger";
        text.innerText = "Gemini Chrome: Offline";
      }
    } catch(e) {
      console.error("Lỗi kiểm tra trạng thái Chrome Debug 9223:", e);
    }
  }

  let contentSelectedMediaType = 'image'; // 'image' or 'video'

  function handleContentImageSelect(files) {
    if (!files || files.length === 0) return;
    const file = files[0];
    const reader = new FileReader();

    const isVideo = file.type.startsWith('video/');
    contentSelectedMediaType = isVideo ? 'video' : 'image';

    reader.onload = function(e) {
      contentSelectedImageBase64 = e.target.result;

      const imgPreview = document.getElementById("contentImgPreview");
      const videoPreview = document.getElementById("contentVideoPreview");

      if (isVideo) {
        imgPreview.style.display = "none";
        videoPreview.src = contentSelectedImageBase64;
        videoPreview.style.display = "block";
      } else {
        videoPreview.style.display = "none";
        imgPreview.src = contentSelectedImageBase64;
        imgPreview.style.display = "block";
      }

      document.getElementById("contentImgPreviewContainer").style.display = "block";
      document.getElementById("contentImgDropzone").style.display = "none";
    };
    reader.readAsDataURL(file);
  }

  function clearContentImage() {
    contentSelectedImageBase64 = null;
    contentSelectedMediaType = 'image';
    document.getElementById("contentImgPreview").src = "";
    document.getElementById("contentImgPreview").style.display = "none";
    document.getElementById("contentVideoPreview").src = "";
    document.getElementById("contentVideoPreview").style.display = "none";
    document.getElementById("contentImgPreviewContainer").style.display = "none";
    document.getElementById("contentImgDropzone").style.display = "flex";
    document.getElementById("contentImgFile").value = "";
  }

  function handleSampleImageSelect(files) {
    if (!files || files.length === 0) return;
    const file = files[0];
    const reader = new FileReader();

    reader.onload = function(e) {
      sampleSelectedImageBase64 = e.target.result;

      const imgPreview = document.getElementById("sampleImgPreview");
      imgPreview.src = sampleSelectedImageBase64;

      document.getElementById("sampleImgPreviewContainer").style.display = "block";
      document.getElementById("sampleImgSelectorContainer").style.display = "none";
    };
    reader.readAsDataURL(file);
  }

  function handleSampleImageUrlChange(url) {
    if (typeof url !== 'string') {
      const urlInput = document.getElementById("sampleImgUrlInput");
      url = urlInput ? urlInput.value : "";
    }
    url = url.trim();
    if (!url) {
      clearSampleImage();
      return;
    }
    sampleSelectedImageBase64 = url;
    const imgPreview = document.getElementById("sampleImgPreview");
    imgPreview.src = "/api/proxy-image?url=" + encodeURIComponent(url);
    document.getElementById("sampleImgPreviewContainer").style.display = "block";
    document.getElementById("sampleImgSelectorContainer").style.display = "none";
  }

  function clearSampleImage() {
    sampleSelectedImageBase64 = null;
    document.getElementById("sampleImgPreview").src = "";
    document.getElementById("sampleImgPreviewContainer").style.display = "none";
    document.getElementById("sampleImgSelectorContainer").style.display = "flex";
    document.getElementById("sampleImgFile").value = "";
    const urlInput = document.getElementById("sampleImgUrlInput");
    if (urlInput) urlInput.value = "";
  }

  async function useLatestPixelPhoto() {
    try {
      const response = await fetch("/api/automation/latest-photo");
      const d = await response.json();
      if (!response.ok) throw d;

      contentSelectedImageBase64 = d.base64;
      const isVideo = d.type === 'video' || d.name.endsWith('.mp4');
      contentSelectedMediaType = isVideo ? 'video' : 'image';

      const imgPreview = document.getElementById("contentImgPreview");
      const videoPreview = document.getElementById("contentVideoPreview");

      if (isVideo) {
        imgPreview.style.display = "none";
        videoPreview.src = contentSelectedImageBase64;
        videoPreview.style.display = "block";
      } else {
        videoPreview.style.display = "none";
        imgPreview.src = contentSelectedImageBase64;
        imgPreview.style.display = "block";
      }

      document.getElementById("contentImgPreviewContainer").style.display = "block";
      document.getElementById("contentImgDropzone").style.display = "none";

      appendAutomationLog(`Đã tải thành công file mới nhất từ Pixel: ${d.name}`);
    } catch(e) {
      alert("Lỗi lấy ảnh/video Pixel: " + (e.error || e.message || JSON.stringify(e)));
    }
  }

  function appendAutomationLog(msg) {
    const logBox = document.getElementById("automationLogBox");
    if (!logBox) return;
    const now = new Date();
    const timeStr = now.toLocaleTimeString();
    const isLight = document.body.classList.contains("theme-light");
    const borderCol = isLight ? "#e2e8f0" : "#334155";
    const timeCol = isLight ? "#64748b" : "#94a3b8";
    let color = isLight ? "#1e293b" : "#f8fafc";
    let icon = "⚙️";

    if (msg.toLowerCase().includes("lỗi") || msg.toLowerCase().includes("error") || msg.toLowerCase().includes("failed")) {
      color = "#ef4444";
      icon = "❌";
    } else if (msg.toLowerCase().includes("thành công") || msg.toLowerCase().includes("hoàn thành") || msg.toLowerCase().includes("success")) {
      color = isLight ? "#15803d" : "#22c55e";
      icon = "✅";
    } else if (msg.toLowerCase().includes("cảnh báo") || msg.toLowerCase().includes("warning")) {
      color = isLight ? "#b45309" : "#eab308";
      icon = "⚠️";
    }

    logBox.innerHTML += `<div style="margin-bottom: 6px; border-bottom: 1px dashed ${borderCol}; padding-bottom: 6px; display: flex; align-items: start; gap: 8px; font-family: 'Consolas', 'Courier New', monospace;">` +
      `<span style="color: ${timeCol}; font-weight: 600; white-space: nowrap;">[${timeStr}]</span>` +
      `<span style="margin-right: 4px;">${icon}</span>` +
      `<span style="color: ${color}; font-weight: 500; flex: 1; word-break: break-word;">${escapeHtml(msg)}</span>` +
      `</div>`;
    logBox.scrollTop = logBox.scrollHeight;
  }


  async function captureCurrentChatGPTImage() {
    const exportDirInput = document.getElementById("posterExportDir").value.trim();
    const insightSelect = document.getElementById("insightFolderSelect");
    let exportDir = exportDirInput;
    if (insightSelect && insightSelect.value !== "") {
      const idx = parseInt(insightSelect.value, 10);
      const insight = state.scannedInsights[idx];
      if (insight && insight.folder_name) {
        const separator = exportDirInput.endsWith("\\") ? "" : "\\";
        exportDir = exportDirInput + separator + insight.folder_name;
      }
    }
    if (!exportDir) {
      alert("Vui lòng chọn hoặc cấu hình thư mục lưu ảnh trước!");
      return;
    }

    let num = 1;
    if (selectedPromptTitle) {
      const lower = selectedPromptTitle.toLowerCase();
      if (lower.includes("cover") || lower.includes("ảnh bìa") || lower.includes("anh bia")) {
        num = 1;
      } else {
        const match = selectedPromptTitle.match(/(?:số|ảnh|hình|prompt)\s*(\d+)/i) || selectedPromptTitle.match(/(\d+)/);
        if (match) num = parseInt(match[1], 10);
      }
    }

    const btn = document.getElementById("btnCaptureCurrentChatGPT");
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = `<span class="spinner" style="width:14px;height:14px;margin:0 4px 0 0;display:inline-block;vertical-align:middle;"></span> Đang lấy ảnh từ ChatGPT...`;
    }

    appendAutomationLog(`Đang kết nối tới tab ChatGPT để lưu ảnh thành ${num}.png...`);

    try {
      const res = await fetch("/api/automation/chatgpt/capture-current", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ export_dir: exportDir, prompt_number: num, prompt_title: selectedPromptTitle })
      });
      const data = await res.json();
      if (!res.ok || !data.success) {
        throw new Error(data.error || "Không lấy được ảnh");
      }
      appendAutomationLog(`✅ Thành công! ${data.message} (${data.filename})`);
      alert(`Đã lưu ảnh thành công: ${data.filename}\nTại: ${data.file_path}`);
      if (typeof loadDownloadedImages === "function") {
        await loadDownloadedImages();
      }
    } catch (err) {
      appendAutomationLog(`❌ Lỗi: ${err.message}`);
      alert(`Lỗi lấy ảnh từ ChatGPT: ${err.message}`);
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"></path><circle cx="12" cy="13" r="4"></circle></svg> 📸 Lấy ảnh từ tab ChatGPT về máy (Lưu file)`;
      }
    }
  }


  async function sendToChatGPT() {
    const prompt = document.getElementById("contentEditorPrompt").value.trim();
    if (!prompt) {
      alert("Vui lòng nhập nội dung prompt.");
      return;
    }

    const notionContent = document.getElementById("notionContentInput").value.trim();
    const keywords = document.getElementById("keywordsInput").value.trim();

    // Clear log ở cả backend và frontend để nhận log mới tinh từ after=0
    try {
      await fetch("/api/events/clear", { method: "POST" });
    } catch(e) {}
    lastAutomationId = 0;

    document.getElementById("automationLogBox").innerHTML = "";
    appendAutomationLog("Bắt đầu tiến trình gửi yêu cầu lên ChatGPT...");

    startAutomationPoll();

    const exportDirInput = document.getElementById("posterExportDir").value.trim();
    const insightSelect = document.getElementById("insightFolderSelect");
    let exportDir = exportDirInput;
    if (insightSelect && insightSelect.value !== "") {
      const idx = parseInt(insightSelect.value, 10);
      const insight = state.scannedInsights[idx];
      if (insight && insight.folder_name) {
        const separator = exportDirInput.endsWith("\\") ? "" : "\\";
        exportDir = exportDirInput + separator + insight.folder_name;
      }
    }

    try {
      const response = await fetch("/api/automation/chatgpt/send", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          prompt: prompt,
          image: contentSelectedImageBase64,
          sample_image: sampleSelectedImageBase64,
          notion_content: notionContent,
          keywords: keywords,
          prompt_title: selectedPromptTitle,
          export_dir: exportDir
        })
      });
      const d = await response.json();
      if (!response.ok) throw d;

      appendAutomationLog("Backend đã nhận lệnh. Tiến trình Playwright ChatGPT đang chạy ngầm...");
    } catch(e) {
      appendAutomationLog("Lỗi: " + (e.error || e.message || JSON.stringify(e)));
      alert("Lỗi gửi yêu cầu ChatGPT: " + (e.error || e.message || JSON.stringify(e)));
    }
  }

  async function sendToGemini() {
    const prompt = document.getElementById("contentEditorPrompt").value.trim();
    if (!prompt) {
      alert("Vui lòng nhập nội dung prompt.");
      return;
    }

    const notionContent = document.getElementById("notionContentInput").value.trim();
    const keywords = document.getElementById("keywordsInput").value.trim();

    // Clear log ở cả backend và frontend để nhận log mới tinh từ after=0
    try {
      await fetch("/api/events/clear", { method: "POST" });
    } catch(e) {}
    lastAutomationId = 0;

    document.getElementById("automationLogBox").innerHTML = "";
    appendAutomationLog("Bắt đầu tiến trình gửi yêu cầu lên Gemini...");

    startAutomationPoll();

    const exportDirInput = document.getElementById("posterExportDir").value.trim();
    const insightSelect = document.getElementById("insightFolderSelect");
    let exportDir = exportDirInput;
    if (insightSelect && insightSelect.value !== "") {
      const idx = parseInt(insightSelect.value, 10);
      const insight = state.scannedInsights[idx];
      if (insight && insight.folder_name) {
        const separator = exportDirInput.endsWith("\\") ? "" : "\\";
        exportDir = exportDirInput + separator + insight.folder_name;
      }
    }

    try {
      const response = await fetch("/api/automation/gemini/send", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          prompt: prompt,
          media: contentSelectedImageBase64,
          media_type: contentSelectedMediaType,
          sample_image: sampleSelectedImageBase64,
          notion_content: notionContent,
          keywords: keywords,
          prompt_title: selectedPromptTitle,
          export_dir: exportDir
        })
      });
      const d = await response.json();
      if (!response.ok) throw d;

      appendAutomationLog("Backend đã nhận lệnh. Tiến trình Playwright Gemini đang chạy ngầm...");
    } catch(e) {
      appendAutomationLog("Lỗi: " + (e.error || e.message || JSON.stringify(e)));
      alert("Lỗi gửi yêu cầu Gemini: " + (e.error || e.message || JSON.stringify(e)));
    }
  }

  async function startChromeGemini() {
    try {
      const response = await fetch("/api/automation/chrome-gemini/start", { method: "POST" });
      const d = await response.json();
      if (!response.ok) throw d;
      alert("Đã kích hoạt tệp mở Chrome Gemini Debug. Cửa sổ Chrome thật sẽ tự động hiển thị.");
      setTimeout(checkChromeStatus, 1500);
    } catch(e) {
      alert("Không thể chạy lệnh Chrome Gemini: " + (e.message || JSON.stringify(e)));
    }
  }

  async function clearToolCache() {
    if (!confirm("Bạn có chắc chắn muốn xóa toàn bộ ảnh/video tạm trong inbox để giải phóng bộ nhớ không?")) {
      return;
    }
    try {
      const response = await fetch("/api/automation/clear-cache", { method: "POST" });
      const data = await response.json();
      if (response.ok && data.success) {
        clearContentImage();
        // Dọn sạch danh sách hiển thị trên UI mà không xóa file thật trên đĩa
        const container = document.getElementById("downloadedImagesList");
        if (container) {
          container.innerHTML = `<div style="grid-column: span 2; text-align:center; color:var(--muted); font-size:12px; margin-top:40px;">Chưa có ảnh/video nào tải về.</div>`;
        }
        const logBox = document.getElementById("automationLogBox");
        if (logBox) {
          logBox.innerHTML = "Đã xóa sạch cache. Sẵn sàng cho tác vụ mới.";
        }
        alert("Đã xóa sạch bộ nhớ tạm thành công!");
      } else {
        alert("Lỗi xóa cache: " + (data.error || data.message));
      }
    } catch (e) {
      alert("Lỗi kết nối khi xóa cache: " + e.message);
    }
  }

  let downloadedImagesRequestId = 0;

  function getSelectedInsightExportDir() {
    const exportDirInput = document.getElementById("posterExportDir").value.trim();
    const insightSelect = document.getElementById("insightFolderSelect");
    if (insightSelect && insightSelect.value !== "") {
      const idx = parseInt(insightSelect.value, 10);
      const insight = state.scannedInsights[idx];
      if (insight && insight.folder_name) {
        const separator = exportDirInput.endsWith("\\") ? "" : "\\";
        return exportDirInput + separator + insight.folder_name;
      }
    }
    return exportDirInput;
  }

  function showDownloadedImagesMessage(message) {
    const container = document.getElementById("downloadedImagesList");
    if (!container) return;
    container.innerHTML = `<div style="grid-column: span 2; text-align:center; color:var(--muted); font-size:12px; margin-top:40px;">${escapeHtml(message)}</div>`;
  }

  function refreshDownloadedImagesForInsightChange() {
    // Vô hiệu hóa mọi response đang chờ của Insight trước trước khi tạo request mới.
    downloadedImagesRequestId += 1;
    showDownloadedImagesMessage("Đang tải ảnh của Insight đã chọn...");
    void loadDownloadedImages();
  }

  async function loadDownloadedImages() {
    const requestId = ++downloadedImagesRequestId;
    const exportDir = getSelectedInsightExportDir();
    try {
      const response = await fetch("/api/automation/images/list?export_dir=" + encodeURIComponent(exportDir));
      const images = await response.json();
      if (requestId !== downloadedImagesRequestId || exportDir !== getSelectedInsightExportDir()) {
        return;
      }
      renderDownloadedImages(images);
    } catch(e) {
      console.error("Lỗi lấy danh sách kết quả đã tải:", e);
      if (requestId === downloadedImagesRequestId) {
        showDownloadedImagesMessage("Không tải được ảnh của Insight đã chọn.");
      }
    }
  }

  function renderDownloadedImages(images) {
    const container = document.getElementById("downloadedImagesList");
    container.innerHTML = "";

    if (images.length === 0) {
      container.innerHTML = `<div style="grid-column: span 2; text-align:center; color:var(--muted); font-size:12px; margin-top:40px;">Chưa có ảnh/video nào tải về.</div>`;
      return;
    }

    images.forEach(img => {
      const card = document.createElement("div");
      card.className = "poster-card";

      const isVideo = img.name.endsWith('.mp4');
      const mediaElement = isVideo
        ? `<video src="${img.url}" style="width: 100%; height: 200px; display: block; object-fit: contain; background: #000;" autoplay loop muted playsinline></video>`
        : `<img src="${img.url}" alt="${img.name}">`;

      // Tách tên thư mục và tên file từ img.name (ví dụ: "Insight 3/5.png")
      let folderName = "Thư mục chính";
      let fileName = img.name;
      if (img.name.indexOf("/") !== -1) {
        const parts = img.name.split("/");
        folderName = parts[0];
        fileName = parts[1];
      }

      card.innerHTML = `
        ${mediaElement}
        <div class="card-actions">
          <div style="font-size: 11px; color: #fff; font-weight: 700; text-align: center; text-shadow: 0 1px 2px rgba(0,0,0,0.8); margin-bottom: 2px; word-break: break-all;">
            ${fileName}
          </div>
          <button onclick="event.stopPropagation(); revealImageFolder('${img.file_path.replace(/\\/g, '\\\\')}')" style="min-height: 26px; font-size: 10px; padding: 2px 8px; font-weight: 700; border-radius: 6px; background: rgba(45, 212, 191, 0.2); border: 1px solid rgba(45, 212, 191, 0.5); color: var(--brand); cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 4px; text-shadow: 0 1px 1px rgba(0,0,0,0.5); width: 100%; transition: all 0.2s;" title="Mở thư mục chứa file này trên máy tính">
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2z"></path></svg>
            📂 ${folderName}
          </button>
          <a href="/api/images/download?path=${encodeURIComponent(img.file_path)}" download="${fileName}" onclick="event.stopPropagation();" style="min-height: 24px; font-size: 10px; padding: 2px 8px; font-weight: 700; border-radius: 6px; background: rgba(56, 189, 248, 0.2); border: 1px solid rgba(56, 189, 248, 0.5); color: #38bdf8; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 4px; text-decoration: none; width: 100%; margin-top: 4px; transition: all 0.2s;" title="Tải ảnh này về máy tính">
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
            ⬇ Tải về máy
          </a>
        </div>
      `;

      container.appendChild(card);
    });
  }

  async function revealImageFolder(filePath) {
    try {
      const response = await fetch("/api/automation/image/reveal", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({ file_path: filePath })
      });
      const d = await response.json();
      if (!response.ok) throw d;
    } catch(e) {
      alert("Lỗi mở thư mục: " + (e.error || e.message || JSON.stringify(e)));
    }
  }

  async function checkAppUpdate(autoAlert = false) {
    try {
      const response = await fetch('/api/app/check-update');
      const data = await response.json();
      if (!response.ok) throw data;

      const updateBtn = document.getElementById("updateAppBtn");
      const updateText = document.getElementById("updateAppText");

      if (data.has_update) {
        updateBtn.classList.add("pulse-warn");
        updateText.innerText = `Cập nhật (${data.latest_version})`;

        if (!autoAlert) {
          const confirmUpdate = confirm(`Có phiên bản mới: ${data.latest_version}\n\nNội dung: ${data.release_notes || 'Không có ghi chú.'}\n\nBạn có muốn tải về và tự động cài đè cập nhật ngay bây giờ không?\n(Chương trình sẽ tự động đóng và khởi động lại sau khi hoàn thành)`);
          if (confirmUpdate) {
            startAppUpdate(data.download_url);
          }
        }
      } else {
        updateBtn.classList.remove("pulse-warn");
        updateText.innerText = `Phiên bản: ${data.current_version}`;
        if (!autoAlert) {
          alert("Bạn đang sử dụng phiên bản mới nhất!");
        }
      }
    } catch (e) {
      console.error("Lỗi kiểm tra cập nhật:", e);
      if (!autoAlert) {
        alert("Lỗi kiểm tra cập nhật: " + (e.error || e.message || JSON.stringify(e)));
      }
    }
  }

  async function startAppUpdate(downloadUrl) {
    const updateBtn = document.getElementById("updateAppBtn");
    const updateText = document.getElementById("updateAppText");

    if (updateBtn) {
      updateBtn.disabled = true;
      updateBtn.classList.remove("pulse-warn");
    }

    if (typeof appendAutomationLog === 'function') {
      appendAutomationLog("Khởi chạy tiến trình cập nhật ngầm...");
    }

    try {
      const response = await fetch('/api/app/perform-update', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({download_url: downloadUrl})
      });
      const data = await response.json();
      if (!response.ok) throw data;

      let lastMsg = "";
      const pollInterval = setInterval(async () => {
        try {
          const statusRes = await fetch('/api/app/update-status');
          const statusData = await statusRes.json();

          if (statusData.status === "downloading" || statusData.status === "extracting") {
            if (updateText) {
              updateText.innerText = statusData.message;
            }
            if (typeof appendAutomationLog === 'function' && lastMsg !== statusData.message) {
              appendAutomationLog(statusData.message);
              lastMsg = statusData.message;
            }
          } else if (statusData.status === "ready") {
            clearInterval(pollInterval);
            if (typeof appendAutomationLog === 'function') {
              appendAutomationLog("Chuẩn bị xong! Đang kích hoạt updater...");
            }
            alert("Đã chuẩn bị xong! Ứng dụng sẽ tự động đóng và khởi động lại phiên bản mới sau vài giây. Vui lòng chờ.");
            window.close();
          } else if (statusData.status === "error") {
            clearInterval(pollInterval);
            if (updateBtn) updateBtn.disabled = false;
            if (updateText) updateText.innerText = "Cập nhật lỗi";
            alert("Lỗi cập nhật: " + statusData.error);
          }
        } catch (err) {
          console.error("Lỗi poll status update:", err);
        }
      }, 1000);

    } catch (e) {
      if (updateBtn) updateBtn.disabled = false;
      alert("Lỗi cập nhật: " + (e.error || e.message || JSON.stringify(e)));
    }
  }

  Date.prototype.strftime = function(format) {
    const o = {
      "Y+": this.getFullYear(),
      "m+": this.getMonth() + 1,
      "d+": this.getDate(),
      "H+": this.getHours(),
      "M+": this.getMinutes(),
      "S+": this.getSeconds()
    };
    let fmt = format;
    for (let k in o) {
      if (new RegExp("(" + k + ")").test(fmt)) {
        const val = String(o[k]);
        fmt = fmt.replace(RegExp.$1, (RegExp.$1.length === 1) ? val : val.padStart(RegExp.$1.length, "0"));
      }
    }
    return fmt;
  };

  initTheme();
  refresh();

  // Khoi tao Content Helper Tool
  loadOpenAIConfig();
  loadCategories().then(() => {
    loadPromptsLibrary();
  });
  loadPostPromptsLibrary();
  loadDownloadedImages();
  checkChromeStatus();
  chromeStatusInterval = setInterval(checkChromeStatus, 4000);
  checkAppUpdate(true);
  startPoll();

  // Khôi phục link Drive cha cho Shopee Sync từ localStorage
  try {
    const savedShopeeUrl = localStorage.getItem('shopee_sync_drive_url') || '';
    const shopeeInput = document.getElementById("shopeeSyncDriveUrl");
    if (shopeeInput) {
      shopeeInput.value = savedShopeeUrl;
    }
  } catch(e) {}
</script>
<!-- Modal them/sua prompt -->
<div id="promptModal" class="modal-overlay" style="display: none; position: fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.6); backdrop-filter:blur(4px); z-index:9999; justify-content:center; align-items:center;">
  <div class="panel" style="width: 460px; padding: 24px; display: flex; flex-direction: column; gap: 16px; border: 1px solid var(--panel-border); box-shadow: 0 20px 25px -5px rgb(0 0 0 / 0.5); background: var(--bg);">
    <h3 id="promptModalTitle" style="font-family: var(--font-title); font-weight: 700; margin: 0 0 4px 0; font-size: 18px;">Thêm Prompt Mới</h3>
    <input type="hidden" id="promptModalId">

    <div>
      <label for="promptModalCategory" style="margin-bottom: 6px; display: block; font-weight: 600;">Danh mục</label>
      <select id="promptModalCategory" style="font-size: 13px; width: 100%; min-height: 38px;">
        <!-- Load động từ JS -->
      </select>
    </div>

    <div>
      <label for="promptModalTitleInput" style="margin-bottom: 6px; display: block; font-weight: 600;">Tiêu đề</label>
      <input type="text" id="promptModalTitleInput" placeholder="Ví dụ: Bối cảnh biển mùa hè" style="width: 100%; min-height: 38px; padding: 0 10px; background: rgba(0,0,0,0.12); border: 1px solid var(--panel-border); border-radius: 6px; color: var(--text);">
    </div>

    <div>
      <label for="promptModalContentInput" style="margin-bottom: 6px; display: block; font-weight: 600;">Nội dung prompt</label>
      <textarea id="promptModalContentInput" placeholder="Vui lòng nhập prompt..." style="height: 120px; font-size: 13px; line-height: 1.4; resize: none; width: 100%; padding: 10px; background: rgba(0,0,0,0.12); border: 1px solid var(--panel-border); border-radius: 6px; color: var(--text);"></textarea>
    </div>

    <div style="display: flex; justify-content: flex-end; gap: 12px; margin-top: 8px;">
      <button type="button" class="secondary" onclick="closePromptModal()" style="min-height: 36px; padding: 0 16px; font-size: 13px; font-weight: 600;">Hủy</button>
      <button type="button" class="btn-capture" onclick="savePromptFromModal()" style="min-height: 36px; padding: 0 20px; font-size: 13px; font-weight: 700;">Lưu</button>
    </div>
  </div>
</div>

<!-- Modal quan ly danh muc -->
<div id="categoryModal" class="modal-overlay" style="display: none; position: fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.6); backdrop-filter:blur(4px); z-index:9999; justify-content:center; align-items:center;">
  <div class="panel" style="width: 460px; padding: 24px; display: flex; flex-direction: column; gap: 16px; border: 1px solid var(--panel-border); box-shadow: 0 20px 25px -5px rgb(0 0 0 / 0.5); background: var(--bg);">
    <h3 style="font-family: var(--font-title); font-weight: 700; margin: 0 0 4px 0; font-size: 18px;">Quản Lý Danh Mục</h3>

    <div style="font-size: 11px; color: var(--muted); margin-bottom: 2px; line-height: 1.4;">
      * Lưu ý: Khi đổi tên hoặc xóa danh mục, các prompt mẫu thuộc danh mục đó sẽ được tự động đồng bộ hóa tương ứng.
    </div>

    <div id="categoriesListContainer" style="display: flex; flex-direction: column; gap: 10px; max-height: 280px; overflow-y: auto; padding-right: 4px; margin-bottom: 4px;">
      <!-- Danh sach danh muc se duoc render bang JS -->
    </div>

    <button type="button" class="secondary" onclick="addCategoryRowInModal()" style="width: 100%; min-height: 36px; font-weight: 600; font-size: 13px; display: flex; align-items: center; justify-content: center; gap: 6px;">
      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="display:inline-block; vertical-align:middle; margin-right:4px;"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>Thêm danh mục mới
    </button>

    <div style="display: flex; justify-content: flex-end; gap: 12px; margin-top: 8px; border-top: 1px solid var(--panel-border); padding-top: 16px;">
      <button type="button" class="secondary" onclick="closeCategoryModal()" style="min-height: 36px; padding: 0 16px; font-size: 13px; font-weight: 600;">Hủy</button>
      <button type="button" class="btn-capture" onclick="saveCategoriesFromModal()" style="min-height: 36px; padding: 0 20px; font-size: 13px; font-weight: 700;">Lưu thay đổi</button>
    </div>
  </div>
</div>

<!-- Modal dán cấu hình nhanh -->
<div id="pasteConfigModal" class="modal-overlay" style="display: none; position: fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.6); backdrop-filter:blur(4px); z-index:9999; justify-content:center; align-items:center;">
  <div class="panel" style="width: 540px; padding: 24px; display: flex; flex-direction: column; gap: 14px; border: 1px solid var(--panel-border); box-shadow: 0 20px 25px -5px rgb(0 0 0 / 0.5); background: var(--bg);">
    <div style="display: flex; justify-content: space-between; align-items: center;">
      <h3 style="font-family: var(--font-title); font-weight: 700; margin: 0; font-size: 17px;">Dán Nội Dung Cấu Hình</h3>
      <button type="button" onclick="closePasteConfigModal()" style="background:none; border:none; color:var(--muted); font-size:22px; cursor:pointer; padding:0 4px; line-height:1;">&times;</button>
    </div>
    <p style="margin: 0; font-size: 12px; color: var(--muted); line-height: 1.4;">
      Dán nội dung từ file cấu hình <code>đồng bộ shopee.txt</code> hoặc file <code>.env</code> vào ô bên dưới. Hệ thống sẽ tự động phân tích tất cả các khóa và giá trị tương ứng.
    </p>
    <textarea id="pasteConfigTextarea" placeholder="NOTION INTEGRATION TOKEN (NOTION_TOKEN) :&#10;ntn_...&#10;------------------------------------------------&#10;NOTION DATABASE ID (NOTION_DATABASE_ID) :&#10;ca055...&#10;------------------------------------------------&#10;TELEGRAM BOT TOKEN (TELEGRAM_BOT_TOKEN) :&#10;...&#10;------------------------------------------------&#10;MANAGER CHAT ID (MANAGER_CHAT_ID) :&#10;...&#10;------------------------------------------------&#10;GEMINI/OPENAI API KEY (GEMINI_API_KEY) :&#10;...&#10;------------------------------------------------&#10;DRIVE_ROOT_FOLDER_ID :&#10;..." style="width: 100%; height: 220px; font-family: monospace; font-size: 12px; padding: 10px; border-radius: 8px; border: 1px solid var(--panel-border); background: var(--soft); color: var(--text); resize: vertical; box-sizing: border-box;"></textarea>
    <div style="display: flex; justify-content: flex-end; gap: 12px; border-top: 1px solid var(--panel-border); padding-top: 14px;">
      <button type="button" class="secondary" onclick="closePasteConfigModal()" style="min-height: 36px; padding: 0 16px; font-size: 13px; font-weight: 600;">Hủy</button>
      <button type="button" class="md3-btn-primary" onclick="applyPastedConfig()" style="min-height: 36px; padding: 0 20px; font-size: 13px; font-weight: 700;">Áp dụng & Lưu cấu hình</button>
    </div>
  </div>
</div>

<!-- Modal xem và chỉnh sửa bài viết 5 Insight -->
<div id="fullPostsModal" class="modal-overlay" style="display: none; position: fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.7); backdrop-filter:blur(5px); z-index:9999; justify-content:center; align-items:center; padding: 20px;">
  <div class="panel" style="width: 900px; max-width: 95vw; max-height: 90vh; padding: 24px; display: flex; flex-direction: column; gap: 16px; border: 1px solid var(--panel-border); box-shadow: 0 25px 35px -5px rgb(0 0 0 / 0.6); background: var(--bg); border-radius: 14px;">
    <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--panel-border); padding-bottom: 12px;">
      <div>
        <h3 id="fullPostsModalTitle" style="font-family: var(--font-title); font-weight: 700; margin: 0; font-size: 18px; color: var(--text);">Xem & Chỉnh Sửa Chi Tiết Bài Viết</h3>
        <p style="margin: 4px 0 0; font-size: 12px; color: var(--muted);">Kiểm tra và sửa trực tiếp từng mục trước khi ghi nhận lên Notion</p>
      </div>
      <button type="button" onclick="closeFullPostsEditorModal()" style="background:none; border:none; color:var(--muted); font-size:24px; cursor:pointer; padding:0 6px; line-height:1;">&times;</button>
    </div>

    <!-- Danh sách chọn Insight xếp từ trên xuống dưới (1 -> 2 -> ...) -->
    <div style="display: flex; flex-direction: column; gap: 6px;">
      <div style="font-size: 12px; font-weight: 700; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; display: flex; justify-content: space-between; align-items: center;">
        <span>Danh sách Insight bài viết</span>
        <span style="font-size: 11.5px; font-weight: 400; text-transform: none; color: var(--muted);">Nhấp vào bài viết bên dưới để chuyển đổi nội dung xem & sửa</span>
      </div>
      <div id="fullPostsTabHeader" style="display: flex; flex-direction: column; gap: 6px; max-height: 160px; overflow-y: auto; padding: 4px; border: 1px solid var(--panel-border); border-radius: 8px; background: rgba(0, 0, 0, 0.15);">
        <!-- Sẽ được render động bằng JS -->
      </div>
    </div>

    <!-- Form chỉnh sửa nội dung bài viết của tab hiện tại -->
    <div id="fullPostsTabBody" style="flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 14px; padding-right: 6px; max-height: calc(90vh - 220px);">
      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 14px;">
        <div>
          <label class="md3-label">Tiêu đề bài viết Shopee</label>
          <input type="text" id="modalEditPostTitle" class="md3-input" placeholder="Tiêu đề bài viết...">
        </div>
        <div>
          <label class="md3-label">Góc tiếp cận (Angle)</label>
          <input type="text" id="modalEditAngle" class="md3-input" placeholder="Góc bán hàng...">
        </div>
      </div>

      <div>
        <label class="md3-label" style="font-weight: 700; color: var(--brand); font-size: 13px;">Nội dung bài viết chi tiết (Chuẩn Shopee)</label>
        <textarea id="modalEditDescription" class="md3-input" rows="12" style="width: 100%; min-height: 260px; font-size: 13px; line-height: 1.6; resize: vertical; padding: 12px; font-family: inherit;" placeholder="Nội dung bài viết chi tiết..."></textarea>
      </div>

      <details style="margin-top: 4px; font-size: 12px; color: var(--muted); border: 1px solid var(--panel-border); border-radius: 8px; padding: 8px 12px; background: var(--soft);">
        <summary style="cursor: pointer; font-weight: 700; color: var(--text);">➕ Phân rã từng phần cấu trúc (Thành phần, Công dụng, HDSD...)</summary>
        <div style="display: flex; flex-direction: column; gap: 12px; margin-top: 10px;">
          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 14px;">
            <div>
              <label class="md3-label">Thành phần nổi bật (Mỗi thành phần 1 dòng)</label>
              <textarea id="modalEditIngredients" class="md3-input" rows="3" style="height: 80px; resize: vertical;" placeholder="Hoạt chất 1: giải thích...&#10;Hoạt chất 2: giải thích..."></textarea>
            </div>
            <div>
              <label class="md3-label">Công dụng hỗ trợ (Mỗi công dụng 1 dòng)</label>
              <textarea id="modalEditBenefits" class="md3-input" rows="3" style="height: 80px; resize: vertical;" placeholder="Công dụng 1...&#10;Công dụng 2..."></textarea>
            </div>
          </div>

          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 14px;">
            <div>
              <label class="md3-label">Đối tượng sử dụng (Mỗi đối tượng 1 dòng)</label>
              <textarea id="modalEditTargetUsers" class="md3-input" rows="2" style="height: 65px; resize: vertical;" placeholder="Đối tượng 1...&#10;Đối tượng 2..."></textarea>
            </div>
            <div>
              <label class="md3-label">Lưu ý khi sử dụng (Mỗi lưu ý 1 dòng)</label>
              <textarea id="modalEditNotes" class="md3-input" rows="2" style="height: 65px; resize: vertical;" placeholder="Lưu ý 1...&#10;Lưu ý 2..."></textarea>
            </div>
          </div>

          <div>
            <label class="md3-label">Hướng dẫn sử dụng</label>
            <textarea id="modalEditUsage" class="md3-input" rows="2" style="height: 65px; resize: vertical;" placeholder="Hướng dẫn sử dụng từng bước..."></textarea>
          </div>
        </div>
      </details>

      <div>
        <label class="md3-label">Hashtags bài viết</label>
        <input type="text" id="modalEditHashtags" class="md3-input" placeholder="#TenSanPham #khaihoanskincare #khaihoanderma...">
      </div>
    </div>

    <!-- Footer buttons -->
    <div style="display: flex; justify-content: space-between; align-items: center; border-top: 1px solid var(--panel-border); padding-top: 14px; margin-top: 4px;">
      <button type="button" class="secondary" id="btnRegenSinglePost" onclick="regenerateCurrentPostWithAI()" style="min-height: 38px; padding: 0 16px; font-size: 12.5px; font-weight: 600; display: inline-flex; align-items: center; gap: 6px; cursor: pointer;">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/></svg>
        ✨ Viết lại bài này bằng Gemini AI
      </button>
      <div style="display: flex; gap: 10px;">
        <button type="button" class="secondary" onclick="closeFullPostsEditorModal()" style="min-height: 38px; padding: 0 18px; font-size: 13px; font-weight: 600;">Đóng</button>
        <button type="button" class="md3-btn-primary" onclick="saveFullPostsFromModal()" style="min-height: 38px; padding: 0 22px; font-size: 13px; font-weight: 700;">💾 Lưu thay đổi bài viết</button>
      </div>
    </div>
  </div>
</div>
</body>
</html>
"""


def settings() -> pipeline.Settings:
    pipeline.load_dotenv(ROOT)
    cfg = pipeline.load_settings(CONFIG_PATH)
    try:
        cfg.adb_serial = adb_device_serial(cfg)
    except Exception:
        pass
    return cfg


_cached_config = None
_cached_config_mtime = 0.0

def load_config() -> dict[str, Any]:
    global _cached_config, _cached_config_mtime
    with CONFIG_LOCK:
        try:
            mtime = os.path.getmtime(CONFIG_PATH)
            if _cached_config is not None and mtime == _cached_config_mtime:
                return _cached_config.copy()
            content = CONFIG_PATH.read_text(encoding="utf-8")
            config = json.loads(content)
            _cached_config = config
            _cached_config_mtime = mtime
            return config.copy()
        except Exception:
            if _cached_config is not None:
                return _cached_config.copy()
            return {}


def save_config(config: dict[str, Any]) -> None:
    global _cached_config, _cached_config_mtime
    with CONFIG_LOCK:
        temp_path = CONFIG_PATH.with_suffix(".json.tmp")
        temp_path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(temp_path, CONFIG_PATH)
        _cached_config = config.copy()
        _cached_config_mtime = os.path.getmtime(CONFIG_PATH)


def drive_root() -> Path:
    config = load_config()
    value = config.get("paths", {}).get("drive_root_dir", DEFAULT_DRIVE_ROOT)
    return Path(value).expanduser()


def selected_folder_name() -> str:
    return str(load_config().get("paths", {}).get("selected_drive_folder", "")).strip()


def save_path_setting(key: str, value: str) -> None:
    with CONFIG_LOCK:
        config = load_config()
        config.setdefault("paths", {})[key] = value
        save_config(config)


def validate_drive_root(path: Path) -> Path:
    if not path.exists() or not path.is_dir():
        raise ValueError(f"Không tìm thấy thư mục Drive: {path}")
    return path.resolve()


_NOTION_DS_CACHE = {
    "insight": {
        "nhathuockh.pharma": "6d20cd08-5a5a-41b9-b7f9-966b708a8241",
        "khaihoanpharmacy": "2672b9c4-69e7-4477-bd83-3ca15f015434",
    },
    "master": {
        "nhathuockh.pharma": "839708fb-4e87-4df8-9fe8-6a66c9f5bddd",
        "khaihoanpharmacy": "15893870-8887-4252-9d62-201001ffa6fb",
    }
}


def clean_shop_name(s: str) -> str:
    if not s:
        return ""
    import unicodedata
    s = s.lower().strip()
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode('utf-8')
    return re.sub(r'[^a-z0-9]', '', s)


def list_shop_names() -> list[str]:
    try:
        root = validate_drive_root(drive_root())
        shops = set()
        if root and root.is_dir():
            for path in root.iterdir():
                if path.is_dir() and not path.name.startswith("."):
                    shops.add(path.name)
        for s in _NOTION_DS_CACHE.get("insight", {}).keys():
            shops.add(s)
        preferred = ["nhathuockh.pharma", "khaihoanpharmacy"]
        return sorted(list(shops), key=lambda s: (preferred.index(s) if s in preferred else 99, s.lower()))
    except Exception:
        return ["nhathuockh.pharma", "khaihoanpharmacy"]


def selected_shop_name() -> str:
    config = load_config()
    shop = str(config.get("paths", {}).get("selected_shop", "")).strip()
    shops = list_shop_names()
    if shop in shops:
        return shop
    if "nhathuockh.pharma" in shops:
        return "nhathuockh.pharma"
    return shops[0] if shops else "nhathuockh.pharma"


def list_drive_folders(shop: str | None = None) -> list[str]:
    root = validate_drive_root(drive_root())
    active_shop = (shop or selected_shop_name()).strip()
    if active_shop:
        shop_dir = root / active_shop
        if shop_dir.is_dir():
            return sorted((path.name for path in shop_dir.iterdir() if path.is_dir() and not path.name.startswith(".")), key=str.casefold)

    folders = []
    for sub in root.iterdir():
        if sub.is_dir() and not sub.name.startswith("."):
            if sub.name in ["nhathuockh.pharma", "khaihoanpharmacy"]:
                for p in sub.iterdir():
                    if p.is_dir() and not p.name.startswith("."):
                        folders.append(f"{sub.name}/{p.name}")
            else:
                folders.append(sub.name)
    return sorted(folders, key=str.casefold)


def validate_folder_name(name: str) -> str:
    cleaned = name.strip().rstrip(". ")
    if not cleaned:
        raise ValueError("Tên thư mục sản phẩm không được để trống.")
    cleaned = re.sub(r'[\\/*?:"<>|]', '-', cleaned).strip()
    cleaned = re.sub(r'-+', '-', cleaned).strip()
    if cleaned in {".", ".."}:
        raise ValueError("Tên thư mục không hợp lệ.")
    return cleaned


def selected_drive_folder(requested: str | None = None, shop: str | None = None) -> Path:
    root = validate_drive_root(drive_root())
    raw_name = (requested or selected_folder_name()).strip()
    if not raw_name:
        raise ValueError("Chưa chọn thư mục sản phẩm.")

    active_shop = (shop or selected_shop_name()).strip()

    # 1. Trực tiếp nếu là relative path có chứa separator
    if "/" in raw_name or "\\" in raw_name:
        target = (root / raw_name).resolve()
        if target.is_relative_to(root) and target.is_dir():
            return target

    clean_name = validate_folder_name(raw_name)

    # 2. Tìm trong shop đang chọn
    if active_shop:
        target = (root / active_shop / clean_name).resolve()
        if target.is_relative_to(root) and target.is_dir():
            return target

    # 3. Tìm trực tiếp tại root
    target = (root / clean_name).resolve()
    if target.is_relative_to(root) and target.is_dir():
        return target

    # 4. Tìm trong tất cả các shop con
    for sub in root.iterdir():
        if sub.is_dir() and not sub.name.startswith("."):
            candidate = (sub / clean_name).resolve()
            if candidate.is_dir():
                return candidate

    # 5. Fallback đường dẫn theo active_shop
    parent = (root / active_shop) if active_shop and (root / active_shop).is_dir() else root
    return (parent / clean_name).resolve()


def unique_target(folder: Path, filename: str) -> Path:
    candidate = folder / filename
    if not candidate.exists():
        return candidate
    stem, suffix = Path(filename).stem, Path(filename).suffix
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    for index in range(1, 1000):
        candidate = folder / f"{stem}_{stamp}_{index:03d}{suffix}"
        if not candidate.exists():
            return candidate
    raise RuntimeError("Không thể tạo tên file duy nhất trong thư mục Drive.")


def copy_media_to_drive(source: Path, folder: Path) -> Path:
    if not source.exists() or not source.is_file():
        raise FileNotFoundError(f"Không tìm thấy file vừa kéo từ Pixel: {source}")
    target = unique_target(folder, source.name)
    temp = target.with_name(f".{target.name}.part")
    target_created = False
    try:
        shutil.copy2(source, temp)
        if temp.stat().st_size != source.stat().st_size:
            raise RuntimeError("File chép vào Drive không đủ dung lượng. App giữ nguyên file trên Pixel.")
        os.replace(temp, target)
        target_created = True
        if target.stat().st_size != source.stat().st_size:
            raise RuntimeError("Không xác minh được file đích trong Drive. App giữ nguyên file trên Pixel.")
    except Exception:
        temp.unlink(missing_ok=True)
        if target_created:
            target.unlink(missing_ok=True)
        raise
    return target


def finalize_pixel_media(cfg: pipeline.Settings, local_path: Path) -> dict[str, str]:
    try:
        remote = pipeline.delete_pixel_media(cfg, local_path)
        local_path.unlink(missing_ok=True)
        return {"pixel_file": remote, "cleanup": "Đã xóa file khỏi Pixel sau khi chép Drive thành công."}
    except Exception as exc:
        return {"cleanup_warning": f"File đã có trong Drive nhưng chưa xóa được khỏi Pixel: {exc}"}


def add_event(payload: dict[str, Any]) -> None:
    global EVENT_COUNTER
    with EVENT_LOCK:
        EVENT_COUNTER += 1
        EVENTS.append({"id": EVENT_COUNTER, "payload": payload})
        del EVENTS[:-200]


def error_response(exc: Exception, status: int = 500):
    return jsonify({"error": str(exc)}), status


def adb_device_serial(cfg: pipeline.Settings) -> str:
    config = load_config()
    pixel_cfg = config.get("pixel", {})
    connection_mode = pixel_cfg.get("connection_mode", "usb")
    wifi_ip = pixel_cfg.get("wifi_ip", "").strip()

    # Quét danh sách thiết bị hiện có
    output = pipeline.adb_command(cfg, "devices", check=False).stdout.splitlines()
    devices = []
    for line in output:
        if "\tdevice" in line:
            devices.append(line.split()[0])

    if connection_mode == "wifi":
        if not wifi_ip:
            raise ValueError("Chưa cấu hình địa chỉ IP của Pixel để kết nối không dây.")
        if ":" in wifi_ip:
            target_serial = wifi_ip
        else:
            target_serial = f"{wifi_ip}:5555"

        # Nếu có các kết nối mạng khác đang tồn tại không khớp với IP mục tiêu, ngắt kết nối chúng
        network_devices = [d for d in devices if ":" in d and d != target_serial]
        if network_devices:
            for nd in network_devices:
                pipeline.adb_command(cfg, "disconnect", nd, check=False)
            # Quét lại danh sách sau khi dọn dẹp
            output = pipeline.adb_command(cfg, "devices", check=False).stdout.splitlines()
            devices = [line.split()[0] for line in output if "\tdevice" in line]

        # Nếu chưa kết nối wifi, thử adb connect
        if target_serial not in devices:
            pipeline.adb_command(cfg, "connect", target_serial, check=False)
            # Quét lại danh sách thiết bị
            output = pipeline.adb_command(cfg, "devices", check=False).stdout.splitlines()
            devices = [line.split()[0] for line in output if "\tdevice" in line]

        if target_serial not in devices:
            raise RuntimeError(f"Không thể kết nối đến Pixel qua Wifi tại {target_serial}. Hãy kiểm tra IP điện thoại và đảm bảo bắt chung Wifi.")
        return target_serial
    else:
        # Chế độ USB: Lọc các thiết bị không chứa dấu hai chấm ':' (tức là không phải IP mạng)
        usb_devices = [d for d in devices if ":" not in d]
        if not usb_devices:
            # Nếu không tìm thấy qua USB nhưng có cấu hình adb_serial trong config.json
            if cfg.adb_serial and cfg.adb_serial in devices:
                return cfg.adb_serial
            raise RuntimeError("Chưa thấy Pixel cắm cáp USB. Hãy kiểm tra cáp và USB debugging.")
        if len(usb_devices) > 1:
            if cfg.adb_serial and cfg.adb_serial in usb_devices:
                return cfg.adb_serial
            raise RuntimeError("Có nhiều thiết bị USB. Điền adb_serial trong config.json để chọn thiết bị.")
        return usb_devices[0]


def find_scrcpy_exe() -> Path:
    config = load_config()
    configured_scrcpy = config.get("pixel", {}).get("scrcpy_path", "").strip()

    candidates = []
    if configured_scrcpy:
        path = Path(configured_scrcpy)
        if path.is_dir():
            exe_file = path / "scrcpy.exe" if os.name == "nt" else path / "scrcpy"
            candidates.append(exe_file)
        else:
            candidates.append(path)

    configured_env = os.environ.get("SCRCPY_PATH", "").strip()
    if configured_env:
        candidates.append(Path(configured_env))
    candidates.append(Path(r"C:\FastbootFirmwareFlasher\ExtraTools\scrcpy\scrcpy.exe"))

    found = shutil.which("scrcpy")
    if found:
        candidates.append(Path(found))
    for candidate in candidates:
        if candidate and candidate.exists():
            return candidate
    raise FileNotFoundError("Không tìm thấy scrcpy.exe. Vui lòng cấu hình đường dẫn scrcpy trên giao diện cài đặt.")


def open_camera(cfg: pipeline.Settings) -> None:
    pipeline.adb_command(cfg, "shell", "am", "start", "-a", "android.media.action.STILL_IMAGE_CAMERA", check=False)


def sleep_pixel(cfg: pipeline.Settings) -> None:
    pipeline.adb_command(cfg, "shell", "input", "keyevent", "223", check=False)


def wake_pixel(cfg: pipeline.Settings) -> None:
    pipeline.adb_command(cfg, "shell", "input", "keyevent", "224", check=False)


def pixel_screen_is_on(cfg: pipeline.Settings) -> bool:
    result = pipeline.adb_command(cfg, "shell", "dumpsys", "power", check=False)
    output = f"{result.stdout}\n{result.stderr}"
    lowered = output.lower()
    compact = lowered.replace(" ", "")
    if "display power: state=on" in lowered or "mholdingdisplaywakelockssuspendblocker=true" in lowered:
        return True
    if "display power: state=off" in lowered or "mholdingdisplaywakelockssuspendblocker=false" in lowered:
        return False
    if "mwakefulness=awake" in compact or "misinteractive:true" in compact or "misinteractive=true" in compact:
        return True
    if "mwakefulness=asleep" in compact or "misinteractive:false" in compact or "misinteractive=false" in compact:
        return False
    wakefulness_lines = [line.lower() for line in output.splitlines() if "wakefulness=" in line.lower()]
    if any("awake" in line or "dreaming" in line for line in wakefulness_lines):
        return True
    if any("asleep" in line for line in wakefulness_lines):
        return False
    raise RuntimeError("Không đọc được trạng thái màn hình Pixel từ dumpsys power.")


def ensure_pixel_awake_and_unlocked(cfg: pipeline.Settings) -> None:
    try:
        # 1. Kiểm tra màn hình, nếu tắt thì đánh thức
        if not pixel_screen_is_on(cfg):
            add_event({"step": "wake_pixel", "message": "Màn hình Pixel đang tắt. Đang tự động đánh thức..."})
            pipeline.adb_command(cfg, "shell", "input", "keyevent", "224", check=False)
            time.sleep(0.5)

        # 2. Gửi lệnh mở khóa (Menu keyevent 82 và vuốt màn hình lên)
        pipeline.adb_command(cfg, "shell", "input", "keyevent", "82", check=False)
        time.sleep(0.3)
        pipeline.adb_command(cfg, "shell", "input", "swipe", "500", "1500", "500", "500", "250", check=False)
        time.sleep(0.5)
    except Exception as exc:
        add_event({"step": "warning", "message": f"Không thể tự động mở khóa màn hình: {exc}"})


def stop_existing_scrcpy() -> None:
    if os.name == "nt":
        creationflags = 0x08000000
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        subprocess.run(["taskkill", "/IM", "scrcpy.exe", "/F"], text=True, capture_output=True, check=False, startupinfo=startupinfo, creationflags=creationflags)


def running_scrcpy_processes() -> list[str]:
    if os.name != "nt":
        return []
    command = "Get-Process scrcpy -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id"
    creationflags = 0x08000000
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0
    output = subprocess.run(["powershell", "-NoProfile", "-Command", command], text=True, capture_output=True, check=False, startupinfo=startupinfo, creationflags=creationflags).stdout
    return [line.strip() for line in output.splitlines() if line.strip()]


@app.get("/")
def index():
    # Thay thế động phiên bản vào HTML trước khi trả về để đồng bộ hiển thị và tránh dùng Jinja trên CSS
    rendered_html = re.sub(r'const CURRENT_VERSION = "v[^"]*";', f'const CURRENT_VERSION = "{CURRENT_VERSION}";', HTML)
    rendered_html = re.sub(r'<span id="updateAppText">v[^<]*</span>', f'<span id="updateAppText">{CURRENT_VERSION}</span>', rendered_html)
    return rendered_html


@app.get("/favicon.ico")
def favicon():
    from flask import send_from_directory
    return send_from_directory(str(BUNDLE_DIR), "favicon.ico", mimetype="image/vnd.microsoft.icon")


@app.get("/api/events")
def api_events():
    after = int(request.args.get("after") or 0)
    with EVENT_LOCK:
        return jsonify({"events": [event for event in EVENTS if int(event["id"]) > after]})


@app.post("/api/events/clear")
def api_clear_events():
    global EVENT_COUNTER
    with EVENT_LOCK:
        EVENTS.clear()
        EVENT_COUNTER = 0
    return jsonify({"status": "Đã xóa log."})


@app.get("/api/status")
def api_status():
    cfg = settings()
    config = load_config()
    pixel_cfg = config.get("pixel", {})
    connection_mode = pixel_cfg.get("connection_mode", "usb")
    wifi_ip = pixel_cfg.get("wifi_ip", "")

    adb = pipeline.adb_command(cfg, "devices", check=False).stdout.splitlines()
    devices = [line.split()[0] for line in adb if "\tdevice" in line]
    try:
        folders, ready = list_drive_folders(), True
    except Exception:
        folders, ready = [], False

    current_device = cfg.adb_serial if cfg.adb_serial else (devices[0] if devices else "")

    # Kiểm tra xem scrcpy có đang chạy không
    scrcpy_running = len(running_scrcpy_processes()) > 0

    return jsonify({
        "adb_device": current_device,
        "drive_root": str(drive_root()),
        "drive_ready": ready,
        "shops": list_shop_names(),
        "selected_shop": selected_shop_name(),
        "selected_folder": selected_folder_name(),
        "folders": folders,
        "operation_busy": OPERATION_LOCK.locked(),
        "connection_mode": connection_mode,
        "wifi_ip": wifi_ip,
        "scrcpy_running": scrcpy_running,
        "adb_path": pixel_cfg.get("adb_path", ""),
        "scrcpy_path": pixel_cfg.get("scrcpy_path", "")
    })


@app.get("/api/shops")
def api_get_shops():
    try:
        return jsonify({
            "shops": list_shop_names(),
            "selected_shop": selected_shop_name()
        })
    except Exception as exc:
        return error_response(exc, 400)


@app.post("/api/select-shop")
def api_select_shop():
    try:
        shop = str((request.json or {}).get("shop", "")).strip()
        shops = list_shop_names()
        if shop not in shops:
            raise ValueError(f"Shop '{shop}' không tồn tại trên Drive.")
        save_path_setting("selected_shop", shop)
        save_path_setting("selected_drive_folder", "")
        folders = list_drive_folders(shop)
        return jsonify({
            "status": f"Đã chuyển sang shop {shop}.",
            "selected_shop": shop,
            "folders": folders
        })
    except Exception as exc:
        return error_response(exc, 400)


@app.post("/api/drive-root")
def api_drive_root():
    try:
        value = str((request.json or {}).get("drive_root", "")).strip()
        root = validate_drive_root(Path(value).expanduser())
        save_path_setting("drive_root_dir", str(root))
        save_path_setting("selected_drive_folder", "")
        return jsonify({"status": "Đã lưu thư mục Drive.", "drive_root": str(root), "shops": list_shop_names(), "selected_shop": selected_shop_name(), "folders": list_drive_folders()})
    except Exception as exc:
        return error_response(exc, 400)


@app.post("/api/folders")
def api_create_folder():
    try:
        data = request.json or {}
        raw_name = str(data.get("name", "")).strip()
        shop_name = str(data.get("shop", "")).strip() or selected_shop_name()
        insights_list = data.get("insights", [])

        root = validate_drive_root(drive_root())
        shop_dir = root / shop_name if shop_name else root
        shop_dir.mkdir(parents=True, exist_ok=True)

        name = validate_folder_name(raw_name)
        target = shop_dir / name
        created = not target.exists()
        target.mkdir(parents=True, exist_ok=True)
        if not target.is_dir():
            raise ValueError("Đường dẫn đã tồn tại nhưng không phải thư mục.")

        # Tạo insight con nếu có danh sách chỉ định
        if insights_list and isinstance(insights_list, list):
            for ins in insights_list:
                ins_title = ins if isinstance(ins, str) else (ins.get("folder_name") or ins.get("title") or "")
                if ins_title:
                    clean_ins = validate_folder_name(ins_title)
                    (target / clean_ins).mkdir(parents=True, exist_ok=True)
        elif data.get("auto_insights", False):
            for i in range(1, 6):
                insight_folder = target / f"Insight {i}"
                insight_folder.mkdir(exist_ok=True)

        save_path_setting("selected_shop", shop_name)
        save_path_setting("selected_drive_folder", name)
        return jsonify({
            "status": "Đã tạo thư mục sản phẩm thành công." if created else "Thư mục đã tồn tại, app đã chọn lại.",
            "folder": name,
            "shop": shop_name,
            "path": str(target)
        })
    except Exception as exc:
        return error_response(exc, 400)


def get_notion_insight_ds_for_shop(notion_client, shop_name: str) -> str:
    """
    Tìm Data Source ID của Shopee Insight Library cho shop chỉ định.
    Tự động hỗ trợ nhathuockh.pharma, khaihoanpharmacy và mọi shop mới trong tương lai.
    """
    clean_target = clean_shop_name(shop_name)
    for s_name, ds_id in _NOTION_DS_CACHE.get("insight", {}).items():
        if clean_shop_name(s_name) == clean_target:
            return ds_id

    try:
        from shopee_sync.src.notion_sync import call_notion_with_retry
        search_res = call_notion_with_retry(notion_client.search, filter={"value": "data_source", "property": "object"})
        for ds in search_res.get("results", []):
            title = "".join([t.get("plain_text", "") for t in ds.get("title", [])]).strip()
            clean_title = clean_shop_name(title)
            ds_id = ds.get("id")
            if "insight" in clean_title:
                if clean_target and clean_target in clean_title:
                    _NOTION_DS_CACHE["insight"][shop_name] = ds_id
                    return ds_id
                if "|" in title:
                    shop_part = title.split("|")[-1].strip()
                    _NOTION_DS_CACHE["insight"][shop_part] = ds_id
                elif "shopee insight library" in title.lower():
                    _NOTION_DS_CACHE["insight"]["nhathuockh.pharma"] = ds_id
    except Exception as exc:
        print(f"[Notion DS Resolver] Lỗi tìm kiếm data source: {exc}")

    if clean_target in ["khaihoanpharmacy", "khaihoan"]:
        return "2672b9c4-69e7-4477-bd83-3ca15f015434"
    return "6d20cd08-5a5a-41b9-b7f9-966b708a8241"


def get_notion_master_ds_for_shop(notion_client, shop_name: str) -> str:
    """
    Tìm Data Source ID của Master DB (Shopee - Xử lý sản phẩm đăng) cho shop chỉ định.
    """
    clean_target = clean_shop_name(shop_name)
    for s_name, ds_id in _NOTION_DS_CACHE.get("master", {}).items():
        if clean_shop_name(s_name) == clean_target:
            return ds_id

    try:
        from shopee_sync.src.notion_sync import call_notion_with_retry
        search_res = call_notion_with_retry(notion_client.search, filter={"value": "data_source", "property": "object"})
        for ds in search_res.get("results", []):
            title = "".join([t.get("plain_text", "") for t in ds.get("title", [])]).strip()
            clean_title = clean_shop_name(title)
            ds_id = ds.get("id")
            if "xử lý sản phẩm đăng" in title.lower() or "xu ly san pham dang" in clean_title:
                if clean_target and clean_target in clean_title:
                    _NOTION_DS_CACHE["master"][shop_name] = ds_id
                    return ds_id
                if "|" in title:
                    shop_part = title.split("|")[-1].strip()
                    _NOTION_DS_CACHE["master"][shop_part] = ds_id
                else:
                    _NOTION_DS_CACHE["master"]["nhathuockh.pharma"] = ds_id
    except Exception as exc:
        print(f"[Notion Master DS Resolver] Lỗi tìm kiếm data source: {exc}")

    if clean_target in ["khaihoanpharmacy", "khaihoan"]:
        return "15893870-8887-4252-9d62-201001ffa6fb"
    return "839708fb-4e87-4df8-9fe8-6a66c9f5bddd"


@app.get("/api/notion/insight-products")
def api_get_notion_insight_products():
    try:
        from notion_client import Client
        try:
            from shopee_sync.src.notion_sync import call_notion_with_retry, find_local_product_folder
        except ImportError:
            from src.notion_sync import call_notion_with_retry, find_local_product_folder
        from dotenv import load_dotenv
        load_dotenv(SHOPEE_SYNC_ROOT / ".env")
        token = os.getenv("NOTION_TOKEN")
        if not token:
            raise ValueError("Chưa cấu hình NOTION_TOKEN trong file .env")

        notion = Client(auth=token)
        target_shop = request.args.get("shop", "").strip() or selected_shop_name()
        ds_id = get_notion_insight_ds_for_shop(notion, target_shop)
        res = call_notion_with_retry(notion.data_sources.query, data_source_id=ds_id, page_size=100)

        # Lấy danh sách subfolder đã có trên local Drive
        root = validate_drive_root(drive_root())
        local_folders_by_shop = {}
        for s in list_shop_names():
            s_dir = root / s
            if s_dir.is_dir():
                local_folders_by_shop[s] = [f.name.lower() for f in s_dir.iterdir() if f.is_dir()]

        products = []
        for page in res.get("results", []):
            props = page.get("properties", {})
            loai_sel = props.get("Loại bản ghi", {}).get("select") or {}
            loai_name = loai_sel.get("name", "")

            title_list = props.get("Tên post Shopee", {}).get("title", [])
            title = title_list[0].get("plain_text", "").strip() if title_list else ""
            if not title:
                for p_val in props.values():
                    if p_val.get("type") == "title":
                        tl = p_val.get("title", [])
                        if tl:
                            title = tl[0].get("plain_text", "").strip()
                        break

            if not title or not title.strip():
                continue

            if loai_name == "Nhóm Insight" or title.startswith("Insight "):
                num_prop = props.get("Số Insight", {}).get("rollup", {})
                insight_count = int(num_prop.get("number") or 0)

                drive_url = ""
                for url_key in ["URL", "Link Drive bộ ảnh", "Link Drive", "Media sản phẩm"]:
                    if url_key in props and props[url_key].get("url"):
                        drive_url = props[url_key]["url"]
                        break
                if not drive_url:
                    cw_rel = props.get("Công việc Shopee", {}).get("relation", [])
                    if cw_rel:
                        try:
                            cw_page = call_notion_with_retry(notion.pages.retrieve, page_id=cw_rel[0]["id"])
                            cw_props = cw_page.get("properties", {})
                            drive_url = cw_props.get("Media sản phẩm", {}).get("url") or cw_props.get("URL", {}).get("url") or ""
                        except Exception:
                            pass

                rel_insights = props.get("Danh sách Insight", {}).get("relation", [])
                if not insight_count:
                    insight_count = len(rel_insights)

                child_insights = []
                for rel in rel_insights:
                    child_id = rel.get("id")
                    try:
                        c_page = call_notion_with_retry(notion.pages.retrieve, page_id=child_id)
                        c_props = c_page.get("properties", {})
                        c_title = ""
                        for cp_val in c_props.values():
                            if cp_val.get("type") == "title":
                                ctl = cp_val.get("title", [])
                                if ctl:
                                    c_title = ctl[0].get("plain_text", "").strip()
                                break
                        clean_child = re.sub(r'[\\/*?:"<>|]', '-', c_title).strip()
                        clean_child = re.sub(r'-+', '-', clean_child).strip()
                        order_val = c_props.get("Thứ tự", {}).get("number")
                        c_drive_url = c_props.get("Link Drive bộ ảnh", {}).get("url") or c_props.get("URL", {}).get("url") or ""
                        child_insights.append({
                            "id": child_id,
                            "title": c_title,
                            "folder_name": clean_child,
                            "order": order_val or (len(child_insights) + 1),
                            "drive_url": c_drive_url
                        })
                    except Exception as e:
                        print(f"Lỗi đọc insight con {child_id}: {e}")

                child_insights.sort(key=lambda x: x["order"])

                existing_shop = None
                if root and root.is_dir():
                    if target_shop:
                        target_shop_dir = root / target_shop
                        matched = find_local_product_folder(target_shop_dir, title) if target_shop_dir.is_dir() else None
                        if matched and matched.is_dir():
                            existing_shop = target_shop
                    else:
                        matched = find_local_product_folder(root, title)
                        if matched and matched.is_dir():
                            try:
                                rel = matched.relative_to(root)
                                if len(rel.parts) > 1:
                                    existing_shop = rel.parts[0]
                                else:
                                    existing_shop = matched.name
                            except Exception:
                                existing_shop = "Drive"

                # Logic trạng thái chuẩn xác tuyệt đối:
                # 1. Nếu số insight = 0: Luôn luôn là "Chưa có insight", dù trước đó đã tạo thư mục hay có link Drive
                if insight_count == 0:
                    status_name = "Chưa có insight"
                elif existing_shop is not None:
                    status_name = "Hoàn thành"
                else:
                    status_name = "Có insight"

                products.append({
                    "page_id": page.get("id"),
                    "title": title,
                    "clean_folder_name": re.sub(r'[\\/*?:"<>|]', '-', title).strip(),
                    "insight_count": insight_count,
                    "status": status_name,
                    "drive_url": drive_url,
                    "existing_shop": existing_shop,
                    "insights": child_insights
                })

        order_map = {"Có insight": 0, "Chưa có insight": 1, "Hoàn thành": 2}
        products.sort(key=lambda x: (order_map.get(x["status"], 9), x["title"]))
        return jsonify({"success": True, "products": products, "shop": target_shop, "data_source_id": ds_id})
    except Exception as exc:
        return error_response(exc, 400)


@app.post("/api/notion/create-product-folders")
def api_create_notion_product_folders():
    try:
        data = request.json or {}
        page_id = str(data.get("page_id", "")).strip()
        shop_name = str(data.get("shop", "")).strip() or selected_shop_name()
        if not page_id:
            raise ValueError("Thiếu page_id sản phẩm.")

        from notion_client import Client
        from shopee_sync.src.notion_sync import call_notion_with_retry, update_notion_page_safe
        from shopee_sync.src import convert_zicum
        from dotenv import load_dotenv
        load_dotenv(SHOPEE_SYNC_ROOT / ".env")
        token = os.getenv("NOTION_TOKEN")
        notion = Client(auth=token)

        page = call_notion_with_retry(notion.pages.retrieve, page_id=page_id)
        props = page.get("properties", {})
        title_list = props.get("Tên post Shopee", {}).get("title", [])
        title = title_list[0].get("plain_text", "").strip() if title_list else ""
        if not title:
            for p_val in props.values():
                if p_val.get("type") == "title":
                    tl = p_val.get("title", [])
                    if tl:
                        title = tl[0].get("plain_text", "").strip()
                    break

        if not title:
            raise ValueError("Không tìm thấy tiêu đề sản phẩm trên Notion.")

        root = validate_drive_root(drive_root())
        shop_dir = root / shop_name
        shop_dir.mkdir(parents=True, exist_ok=True)

        clean_prod_name = re.sub(r'[\\/*?:"<>|]', '-', title).strip()
        clean_prod_name = re.sub(r'-+', '-', clean_prod_name).strip()
        product_dir = shop_dir / clean_prod_name
        product_dir.mkdir(parents=True, exist_ok=True)

        rel_insights = props.get("Danh sách Insight", {}).get("relation", [])
        created_insights = []

        for idx, rel in enumerate(rel_insights, 1):
            child_id = rel.get("id")
            try:
                c_page = call_notion_with_retry(notion.pages.retrieve, page_id=child_id)
                c_props = c_page.get("properties", {})
                c_title = ""
                for cp_val in c_props.values():
                    if cp_val.get("type") == "title":
                        ctl = cp_val.get("title", [])
                        if ctl:
                            c_title = ctl[0].get("plain_text", "").strip()
                        break
                if not c_title:
                    c_title = f"Insight {idx}"

                clean_child = re.sub(r'[\\/*?:"<>|]', '-', c_title).strip()
                clean_child = re.sub(r'-+', '-', clean_child).strip()
                child_dir = product_dir / clean_child
                child_dir.mkdir(parents=True, exist_ok=True)
                created_insights.append({
                    "page_id": child_id,
                    "title": c_title,
                    "folder_name": clean_child,
                    "path": str(child_dir),
                    "drive_url": ""
                })
            except Exception as e:
                print(f"Lỗi tạo thư mục insight con {child_id}: {e}")

        # Thử lấy link Drive online từ Google Drive web crawler nếu có
        drive_url = ""
        for url_key in ["URL", "Link Drive bộ ảnh", "Media sản phẩm"]:
            if url_key in props and props[url_key].get("url"):
                drive_url = props[url_key]["url"]
                break

        try:
            root_folder_id = os.getenv("DRIVE_ROOT_FOLDER_ID", "1XrOmOCqdZ3xfkeVaBc0Vr77Q7yRW0PxZ")
            shop_subfolders = convert_zicum.get_subfolders_of_drive_folder(root_folder_id)
            shop_key = convert_zicum.clean_name(shop_name)
            shop_folder_id = shop_subfolders.get(shop_key)
            if not shop_folder_id:
                for k, fid in shop_subfolders.items():
                    if k in shop_key or shop_key in k:
                        shop_folder_id = fid
                        break

            if shop_folder_id:
                prod_subfolders = convert_zicum.get_subfolders_of_drive_folder(shop_folder_id)
                prod_key = convert_zicum.clean_name(clean_prod_name)
                prod_folder_id = prod_subfolders.get(prod_key)
                if not prod_folder_id:
                    for k, fid in prod_subfolders.items():
                        if k in prod_key or prod_key in k:
                            prod_folder_id = fid
                            break
                if prod_folder_id:
                    drive_url = f"https://drive.google.com/drive/folders/{prod_folder_id}"

                    # Cập nhật link Drive cho từng insight con
                    child_subfolders = convert_zicum.get_subfolders_of_drive_folder(prod_folder_id)
                    for ci in created_insights:
                        c_key = convert_zicum.clean_name(ci["folder_name"])
                        c_fid = child_subfolders.get(c_key)
                        if not c_fid:
                            for ck, cfid in child_subfolders.items():
                                if ck in c_key or c_key in ck:
                                    c_fid = cfid
                                    break
                        if c_fid:
                            c_link = f"https://drive.google.com/drive/folders/{c_fid}"
                            ci["drive_url"] = c_link
                            try:
                                c_page_obj = call_notion_with_retry(notion.pages.retrieve, page_id=ci["page_id"])
                                c_props_map = c_page_obj.get("properties", {})
                                c_up = {}
                                if "Link Drive bộ ảnh" in c_props_map:
                                    c_up["Link Drive bộ ảnh"] = {"url": c_link}
                                if "URL" in c_props_map:
                                    c_up["URL"] = {"url": c_link}
                                if "Trạng thái tạo hình" in c_props_map:
                                    c_up["Trạng thái tạo hình"] = {"select": {"name": "Đã tạo hình"}}
                                if c_up:
                                    update_notion_page_safe(notion, page_id=ci["page_id"], properties=c_up)
                            except Exception as c_err:
                                print(f"Lỗi cập nhật insight con Notion {ci['page_id']}: {c_err}")
        except Exception as e:
            print(f"Lỗi quét Drive link: {e}")

        # Cập nhật Notion cho Nhóm Insight: Trạng thái & URL (hỗ trợ cả cột URL và Link Drive bộ ảnh)
        update_props = {}
        if "Trạng thái" in props:
            update_props["Trạng thái"] = {"select": {"name": "Hoàn thành"}}
        if "Trạng thái tạo hình" in props:
            update_props["Trạng thái tạo hình"] = {"select": {"name": "Đã tạo hình"}}
        if drive_url:
            if "URL" in props:
                update_props["URL"] = {"url": drive_url}
            else:
                # Tự động tạo cột URL nếu database chưa có
                try:
                    p_parent = page.get("parent", {})
                    ds_parent_id = p_parent.get("data_source_id")
                    if ds_parent_id:
                        notion.data_sources.update(data_source_id=ds_parent_id, properties={"URL": {"url": {}}})
                        update_props["URL"] = {"url": drive_url}
                except Exception:
                    pass
            if "Link Drive bộ ảnh" in props:
                update_props["Link Drive bộ ảnh"] = {"url": drive_url}

        if update_props:
            try:
                update_notion_page_safe(notion, page_id=page_id, properties=update_props)
            except Exception as e:
                print(f"Lỗi cập nhật Notion page {page_id}: {e}")

        # Cập nhật cả bản ghi liên kết trong Master DB (Công việc Shopee) nếu có
        cw_rel = props.get("Công việc Shopee", {}).get("relation", [])
        for cw in cw_rel:
            cw_id = cw.get("id")
            if cw_id:
                try:
                    cw_page = call_notion_with_retry(notion.pages.retrieve, page_id=cw_id)
                    cw_props = cw_page.get("properties", {})
                    cw_update = {}
                    if drive_url:
                        if "Media sản phẩm" in cw_props:
                            cw_update["Media sản phẩm"] = {"url": drive_url}
                        elif "URL" in cw_props:
                            cw_update["URL"] = {"url": drive_url}
                    if "Trạng thái" in cw_props and cw_props["Trạng thái"].get("select") is None:
                        cw_update["Trạng thái"] = {"select": {"name": "Chờ đăng"}}
                    if cw_update:
                        update_notion_page_safe(notion, page_id=cw_id, properties=cw_update)
                except Exception as cw_err:
                    print(f"Lỗi cập nhật Master DB liên kết {cw_id}: {cw_err}")

        # Ghi nhận trạng thái chọn folder hiện tại
        save_path_setting("selected_shop", shop_name)
        save_path_setting("selected_drive_folder", clean_prod_name)

        return jsonify({
            "success": True,
            "status": f"Đã tạo thư mục sản phẩm '{clean_prod_name}' cùng {len(created_insights)} thư mục Insight tại shop '{shop_name}'.",
            "product_name": clean_prod_name,
            "shop": shop_name,
            "product_dir": str(product_dir),
            "drive_url": drive_url,
            "created_insights": created_insights
        })
    except Exception as exc:
        return error_response(exc, 400)


@app.post("/api/select-folder")
def api_select_folder():
    try:
        name = str((request.json or {}).get("name", "")).strip()
        target = selected_drive_folder(name)
        save_path_setting("selected_drive_folder", target.name)
        return jsonify({"status": "Đã chọn thư mục sản phẩm.", "folder": target.name, "path": str(target)})
    except Exception as exc:
        return error_response(exc, 400)


@app.post("/api/folders/delete")
def api_delete_folder():
    try:
        if OPERATION_LOCK.locked():
            raise RuntimeError("Pixel đang chụp hoặc quay. Hãy đợi tác vụ hiện tại hoàn tất.")
        name = str((request.json or {}).get("name", "")).strip()
        target = selected_drive_folder(name)

        # Xóa cưỡng bức toàn bộ thư mục sản phẩm (bao gồm các thư mục con Insight 1-5 và file ảnh)
        shutil.rmtree(target)

        if selected_folder_name() == target.name:
            save_path_setting("selected_drive_folder", "")
        add_event({"step": "folder_deleted", "message": "Đã xóa thư mục sản phẩm.", "folder": target.name})
        return jsonify({"status": "Đã xóa thư mục sản phẩm cùng toàn bộ nội dung bên trong.", "folder": target.name})
    except Exception as exc:
        return error_response(exc, 400)


@app.post("/api/pixel/connection")
def api_pixel_connection():
    try:
        if OPERATION_LOCK.locked():
            raise RuntimeError("Pixel đang chụp hoặc quay. Hãy đợi tác vụ hiện tại hoàn tất.")

        payload = request.json or {}
        connection_mode = str(payload.get("connection_mode", "usb")).strip().lower()
        wifi_ip = str(payload.get("wifi_ip", "")).strip()

        if connection_mode not in {"usb", "wifi"}:
            raise ValueError("Kiểu kết nối không hợp lệ.")

        with CONFIG_LOCK:
            config = load_config()
            config.setdefault("pixel", {})["connection_mode"] = connection_mode
            config.setdefault("pixel", {})["wifi_ip"] = wifi_ip
            save_config(config)

        cfg = settings()
        status_msg = f"Đã chuyển cấu hình sang kết nối qua {connection_mode.upper()}."

        if connection_mode == "wifi":
            if not wifi_ip:
                raise ValueError("Vui lòng nhập địa chỉ IP của Pixel.")
            if ":" in wifi_ip:
                target = wifi_ip
            else:
                target = f"{wifi_ip}:5555"
            add_event({"step": "wifi_connect_attempt", "message": f"Đang thử kết nối Wi-Fi đến {target}...", "ip": wifi_ip})
            res = pipeline.adb_command(cfg, "connect", target, check=False).stdout
            if "connected" in res.lower() or "already connected" in res.lower():
                status_msg = f"Kết nối Wi-Fi thành công đến {target}."
                add_event({"step": "wifi_connected", "message": status_msg, "ip": wifi_ip})
            else:
                add_event({"step": "wifi_connect_warning", "message": f"Yêu cầu kết nối Wi-Fi đã gửi: {res.strip()}", "ip": wifi_ip})
        else:
            add_event({"step": "usb_mode", "message": "Đã chuyển sang chế độ cắm dây USB."})

        return jsonify({"status": status_msg, "connection_mode": connection_mode, "wifi_ip": wifi_ip})
    except Exception as exc:
        return error_response(exc, 400)


@app.post("/api/pixel/paths")
def api_pixel_paths():
    try:
        data = request.json or {}
        adb_path = str(data.get("adb_path", "")).strip()
        scrcpy_path = str(data.get("scrcpy_path", "")).strip()

        with CONFIG_LOCK:
            config = load_config()
            config.setdefault("pixel", {})["adb_path"] = adb_path
            config.setdefault("pixel", {})["scrcpy_path"] = scrcpy_path
            save_config(config)

        # Cập nhật tạm thời cho session hiện tại trong os.environ
        if adb_path:
            os.environ["ADB_PATH"] = adb_path
            p = Path(adb_path)
            adb_dir = str(p if p.is_dir() else p.parent)
            pipeline.add_to_path_env(adb_dir)
        if scrcpy_path:
            os.environ["SCRCPY_PATH"] = scrcpy_path
            p = Path(scrcpy_path)
            scrcpy_dir = str(p if p.is_dir() else p.parent)
            pipeline.add_to_path_env(scrcpy_dir)

        return jsonify({"status": "Đã lưu cấu hình đường dẫn công cụ thành công."})
    except Exception as exc:
        return error_response(exc, 400)


@app.post("/api/pixel/detect-ip")
def api_pixel_detect_ip():
    try:
        cfg = settings()
        # Quét danh sách thiết bị hiện có
        output = pipeline.adb_command(cfg, "devices", check=False).stdout.splitlines()
        usb_devices = []
        for line in output:
            if "\tdevice" in line:
                serial = line.split()[0]
                if ":" not in serial: # Không phải thiết bị mạng
                    usb_devices.append(serial)

        if not usb_devices:
            raise RuntimeError("Không tìm thấy thiết bị Pixel đang cắm cáp USB. Hãy cắm tạm cáp USB để tự động dò IP.")

        target_usb = usb_devices[0]
        # Lấy IP từ thiết bị wlan0 của thiết bị usb này
        ip_output = pipeline.adb_command(cfg, "-s", target_usb, "shell", "ip addr show wlan0", check=False).stdout

        match = re.search(r"inet\s+(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})", ip_output)
        if not match:
            raise RuntimeError("Thiết bị Pixel đã kết nối USB nhưng không tìm thấy địa chỉ IP Wifi. Hãy kiểm tra xem Pixel đã kết nối vào cùng mạng Wifi chưa.")

        ip = match.group(1)
        # Kích hoạt tcpip 5555 trên thiết bị USB này luôn để người dùng đỡ phải làm thủ công!
        pipeline.adb_command(cfg, "-s", target_usb, "tcpip", "5555", check=False)

        add_event({"step": "ip_detected", "message": f"Đã dò tìm thấy IP của Pixel wlan0: {ip} và tự động kích hoạt chế độ không dây TCP/IP 5555.", "ip": ip})
        return jsonify({"ip": ip, "status": "Dò IP thành công."})
    except Exception as exc:
        return error_response(exc, 400)


@app.post("/api/open-preview")
def api_open_preview():
    try:
        if OPERATION_LOCK.locked():
            raise RuntimeError("Pixel đang chụp hoặc quay. Hãy đợi tác vụ hiện tại hoàn tất.")
        cfg, scrcpy = settings(), find_scrcpy_exe()
        serial = adb_device_serial(cfg)
        stop_existing_scrcpy()
        open_camera(cfg)
        # Giữ màn hình Pixel luôn sáng khi cắm cáp để tránh tự động tắt làm mất zoom (khẩu độ)
        pipeline.adb_command(cfg, "shell", "settings", "put", "global", "stay_on_while_plugged_in", "7", check=False)
        time.sleep(0.8)
        args = [str(scrcpy), "--serial", serial, "--stay-awake", "--no-audio", "--window-title", "Pixel Drive Capture - Camera Preview"]
        env = os.environ.copy()
        adb = os.environ.get("ADB", "").strip() or shutil.which("adb")
        if adb:
            env["ADB"] = adb
        flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        subprocess.Popen(args, cwd=str(scrcpy.parent), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
        time.sleep(2)
        pids = running_scrcpy_processes()
        if os.name == "nt" and not pids:
            raise RuntimeError("scrcpy đã thoát ngay. Hãy kiểm tra ADB/driver.")
        return jsonify({"status": "Đã mở màn hình Pixel.", "adb_serial": serial, "scrcpy_pids": pids})
    except Exception as exc:
        return error_response(exc, 400)


@app.post("/api/close-preview")
def api_close_preview():
    try:
        stop_existing_scrcpy()
        add_event({"step": "pixel_preview_close", "message": "Đã đóng cửa sổ xem Pixel trên máy tính (điện thoại vẫn giữ sáng và mở camera)."})
        return jsonify({"status": "Đã đóng preview."})
    except Exception as exc:
        return error_response(exc, 400)


@app.post("/api/sleep-pixel")
def api_sleep_pixel():
    try:
        if OPERATION_LOCK.locked():
            raise RuntimeError("Pixel đang chụp hoặc quay. Hãy đợi tác vụ hiện tại hoàn tất.")
        cfg = settings()
        serial = adb_device_serial(cfg)
        stop_existing_scrcpy()
        sleep_pixel(cfg)
        add_event({"step": "pixel_sleep", "message": "Đã tắt màn hình Pixel và đóng scrcpy.", "adb_serial": serial})
        return jsonify({"status": "Đã tắt màn hình Pixel.", "adb_serial": serial})
    except Exception as exc:
        return error_response(exc, 400)


@app.post("/api/toggle-screen")
def api_toggle_screen():
    try:
        if OPERATION_LOCK.locked():
            raise RuntimeError("Pixel đang chụp hoặc quay. Hãy đợi tác vụ hiện tại hoàn tất.")
        cfg = settings()
        serial = adb_device_serial(cfg)
        was_on = pixel_screen_is_on(cfg)
        if was_on:
            stop_existing_scrcpy()
            sleep_pixel(cfg)
            action = "off"
            message = "Đã tắt màn hình Pixel và đóng scrcpy."
            status = "Đã tắt màn hình Pixel."
        else:
            wake_pixel(cfg)
            action = "on"
            message = "Đã bật màn hình Pixel."
            status = "Đã bật màn hình Pixel."
        add_event({"step": "pixel_screen_toggle", "action": action, "message": message, "adb_serial": serial})
        return jsonify({"status": status, "screen": action, "adb_serial": serial})
    except Exception as exc:
        return error_response(exc, 400)


def stop_all_processes() -> None:
    if os.name == "nt":
        creationflags = 0x08000000
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        # Kill scrcpy
        subprocess.run(["taskkill", "/IM", "scrcpy.exe", "/F"], text=True, capture_output=True, check=False, startupinfo=startupinfo, creationflags=creationflags)
        # Kill adb.exe
        subprocess.run(["taskkill", "/IM", "adb.exe", "/F"], text=True, capture_output=True, check=False, startupinfo=startupinfo, creationflags=creationflags)


@app.post("/api/operation/stop")
def api_operation_stop():
    try:
        add_event({"step": "stop_operation", "message": "Yêu cầu dừng khẩn cấp tất cả tiến trình đang chạy..."})

        # Kill adb.exe và scrcpy.exe cưỡng bức
        stop_all_processes()

        # Giải phóng khóa tác vụ
        if OPERATION_LOCK.locked():
            try:
                OPERATION_LOCK.release()
            except RuntimeError:
                pass

        add_event({"step": "stop_operation", "message": "Đã dừng tất cả tiến trình và giải phóng trạng thái tác vụ."})
        return jsonify({"status": "Đã dừng tất cả tiến trình và giải phóng thiết bị."})
    except Exception as exc:
        return error_response(exc, 400)


@app.post("/api/capture")
def api_capture():
    if not OPERATION_LOCK.acquire(blocking=False):
        return error_response(RuntimeError("Pixel đang xử lý một tác vụ khác. Hãy đợi hoàn tất rồi thử lại."), 409)
    try:
        cfg = settings()
        ensure_pixel_awake_and_unlocked(cfg)
        folder = selected_drive_folder(str((request.json or {}).get("folder", "")).strip())
        add_event({"step": "capture", "message": "Đang mở camera Pixel và chụp ảnh.", "folder": folder.name})
        media = pipeline.capture_from_pixel(cfg)
        add_event({"step": "pulled", "message": "Đã kéo ảnh mới từ Pixel về máy.", "file": str(media)})
        target = copy_media_to_drive(media, folder)
        add_event({"step": "drive_saved", "message": "Đã chép ảnh vào thư mục Drive.", "file": str(target), "size": target.stat().st_size})
        cleanup = finalize_pixel_media(cfg, media)
        add_event({"step": "cleanup", **cleanup})
        payload = {"status": "Hoàn tất chụp ảnh.", "drive_file": str(target), "folder": folder.name, **cleanup}
        add_event({"step": "done", **payload})
        return jsonify(payload)
    except Exception as exc:
        add_event({"step": "error", "message": str(exc)})
        return error_response(exc)
    finally:
        OPERATION_LOCK.release()


@app.post("/api/record")
def api_record():
    if not OPERATION_LOCK.acquire(blocking=False):
        return error_response(RuntimeError("Pixel đang xử lý một tác vụ khác. Hãy đợi hoàn tất rồi thử lại."), 409)
    try:
        cfg = settings()
        ensure_pixel_awake_and_unlocked(cfg)
        payload = request.json or {}
        folder = selected_drive_folder(str(payload.get("folder", "")).strip())
        duration = max(1, min(int(payload.get("duration") or 10), 300))
        add_event({"step": "record", "message": "Đang quay video trên Pixel.", "folder": folder.name, "duration": duration})
        media = pipeline.capture_video_from_pixel(cfg, duration)
        add_event({"step": "pulled", "message": "Đã kéo video mới từ Pixel về máy.", "file": str(media)})
        target = copy_media_to_drive(media, folder)
        add_event({"step": "drive_saved", "message": "Đã chép video vào thư mục Drive.", "file": str(target), "size": target.stat().st_size})
        cleanup = finalize_pixel_media(cfg, media)
        add_event({"step": "cleanup", **cleanup})
        result = {"status": "Hoàn tất quay video.", "drive_file": str(target), "folder": folder.name, "duration": duration, **cleanup}
        add_event({"step": "done", **result})
        return jsonify(result)
    except Exception as exc:
        add_event({"step": "error", "message": str(exc)})
        return error_response(exc)
    finally:
        OPERATION_LOCK.release()


@app.post("/api/folder/reveal")
def api_reveal_folder():
    try:
        payload = request.json or {}
        folder_path_str = payload.get("folder_path", "").strip()
        if not folder_path_str:
            raise ValueError("Thiếu đường dẫn thư mục.")
        p = Path(folder_path_str)
        if not p.exists():
            raise FileNotFoundError(f"Thư mục không tồn tại: {folder_path_str}")
        import subprocess
        subprocess.Popen(["explorer.exe", str(p)])
        return jsonify({"success": True, "status": "Đã mở thư mục trong Explorer.", "path": str(p)})
    except Exception as exc:
        return error_response(exc, 400)


@app.post("/api/utils/select-directory")
def api_select_directory():
    try:
        import ctypes
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", wintypes.DWORD),
                ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD),
                ("Data4", wintypes.BYTE * 8)
            ]
            def __init__(self, l, w1, w2, b1, b2, b3, b4, b5, b6, b7, b8):
                self.Data1 = l
                self.Data2 = w1
                self.Data3 = w2
                self.Data4 = (wintypes.BYTE * 8)(b1, b2, b3, b4, b5, b6, b7, b8)

        CLSID_FileOpenDialog = GUID(0xDC1C5A9C, 0xE88A, 0x4DDE, 0xA5, 0xA1, 0x60, 0xF8, 0x2A, 0x20, 0xAE, 0xf7)
        IID_IFileOpenDialog = GUID(0x42F85136, 0xDB7E, 0x439C, 0x85, 0xF1, 0xE4, 0x07, 0x5D, 0x13, 0x5F, 0xC8)

        FOS_PICKFOLDERS = 0x20
        FOS_FORCEFILESYSTEM = 0x40

        ole32 = ctypes.windll.ole32
        ole32.CoInitialize(None)

        def get_method(interface_ptr, index, restype, argtypes):
            vtable_ptr = ctypes.cast(interface_ptr, ctypes.POINTER(ctypes.c_void_p))[0]
            func_ptr = ctypes.cast(vtable_ptr, ctypes.POINTER(ctypes.c_void_p))[index]
            return ctypes.WINFUNCTYPE(restype, *argtypes)(func_ptr)

        dialog = ctypes.c_void_p()
        hr = ole32.CoCreateInstance(
            ctypes.byref(CLSID_FileOpenDialog),
            None,
            1, # CLSCTX_INPROC_SERVER
            ctypes.byref(IID_IFileOpenDialog),
            ctypes.byref(dialog)
        )
        if hr < 0:
            ole32.CoUninitialize()
            return jsonify({"directory": ""})

        path = ""
        try:
            # SetOptions is index 9
            set_options = get_method(dialog, 9, ctypes.c_long, [ctypes.c_void_p, ctypes.c_uint])
            set_options(dialog, FOS_PICKFOLDERS | FOS_FORCEFILESYSTEM)

            # SetTitle is index 17
            set_title = get_method(dialog, 17, ctypes.c_long, [ctypes.c_void_p, ctypes.c_wchar_p])
            set_title(dialog, "Chọn thư mục lưu ảnh kết quả")

            user32 = ctypes.windll.user32
            user32.GetForegroundWindow.restype = wintypes.HWND
            user32.SetForegroundWindow.argtypes = [wintypes.HWND]
            user32.AllowSetForegroundWindow.argtypes = [wintypes.DWORD]
            owner_hwnd = user32.GetForegroundWindow()
            try:
                user32.AllowSetForegroundWindow(0xFFFFFFFF)
                if owner_hwnd:
                    user32.SetForegroundWindow(owner_hwnd)
            except Exception:
                pass

            # Show is index 3. Gan owner theo cua so dang focus de folder picker
            # nhay len truoc app thay vi bi an sau Chrome/PowerShell.
            show = get_method(dialog, 3, ctypes.c_long, [ctypes.c_void_p, ctypes.c_void_p])
            hr_show = show(dialog, ctypes.c_void_p(owner_hwnd) if owner_hwnd else None)

            if hr_show == 0:
                # GetResult is index 20
                shell_item = ctypes.c_void_p()
                get_result = get_method(dialog, 20, ctypes.c_long, [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)])
                get_result(dialog, ctypes.byref(shell_item))

                if shell_item:
                    # GetDisplayName is index 5
                    get_display_name = get_method(shell_item, 5, ctypes.c_long, [ctypes.c_void_p, ctypes.c_uint, ctypes.POINTER(ctypes.c_wchar_p)])
                    path_ptr = ctypes.c_wchar_p()
                    # 0x80058000 = SIGDN_FILESYSPATH
                    hr_name = get_display_name(shell_item, 0x80058000, ctypes.byref(path_ptr))
                    if hr_name == 0 and path_ptr.value:
                        path = path_ptr.value
                        ole32.CoTaskMemFree(path_ptr)

                    # Release shell item (index 2)
                    release_item = get_method(shell_item, 2, ctypes.c_ulong, [ctypes.c_void_p])
                    release_item(shell_item)
        finally:
            # Release dialog (index 2)
            release_dialog = get_method(dialog, 2, ctypes.c_ulong, [ctypes.c_void_p])
            release_dialog(dialog)
            ole32.CoUninitialize()

        if path:
            return jsonify({"directory": os.path.normpath(path)})
        return jsonify({"directory": ""})
    except Exception as exc:
        return error_response(exc, 500)



@app.post("/api/openai/check")
def api_openai_check():
    try:
        payload = request.json or {}
        api_key = str(payload.get("api_key", "")).strip()
        if not api_key:
            raise ValueError("Vui lòng cung cấp API Key để kiểm tra.")

        from openai import OpenAI
        client = OpenAI(api_key=api_key)

        has_gpt4o = False
        try:
            models_data = client.models.list()
            model_ids = [m.id for m in models_data.data]
            has_gpt4o = "gpt-4o" in model_ids or "gpt-4o-mini" in model_ids
        except Exception as e:
            return jsonify({
                "valid": False,
                "message": f"API Key không hợp lệ hoặc tài khoản hết tiền: {e}"
            })

        has_dalle3 = False
        dalle3_error_msg = ""
        try:
            client.images.generate(
                model="gpt-image-1.5",
                prompt="",
                n=1,
                size="1024x1024"
            )
        except Exception as e:
            err_str = str(e)
            if "does not exist" in err_str:
                has_dalle3 = False
                dalle3_error_msg = "Mô hình gpt-image-1.5 bị khóa hoặc chưa được cấp quyền (tài khoản Tier 0 hoặc bị tắt trong Project)."
            else:
                has_dalle3 = True

        return jsonify({
            "valid": True,
            "has_gpt4o": has_gpt4o,
            "has_dalle3": has_dalle3,
            "dalle3_msg": dalle3_error_msg or "Sẵn sàng hoạt động ✅"
        })
    except Exception as exc:
        return jsonify({
            "valid": False,
            "message": str(exc)
        })


@app.get("/api/openai/config")
def api_openai_config_get():
    config = load_config()
    openai_cfg = config.get("openai", {})
    return jsonify({
        "api_key": openai_cfg.get("api_key", ""),
        "export_dir": openai_cfg.get("export_dir", "")
    })


@app.post("/api/openai/config")
def api_openai_config_post():
    try:
        payload = request.json or {}
        api_key = str(payload.get("api_key", "")).strip()
        export_dir = str(payload.get("export_dir", "")).strip()

        with CONFIG_LOCK:
            config = load_config()
            openai_cfg = config.setdefault("openai", {})
            openai_cfg["api_key"] = api_key
            openai_cfg["export_dir"] = export_dir
            save_config(config)

        return jsonify({"status": "Đã lưu cấu hình OpenAI."})
    except Exception as exc:
        return error_response(exc, 400)


def process_hybrid_composition(bg_url_or_base64: str, product_base64_data: str, size_str: str) -> str:
    import io
    import base64
    import requests
    from PIL import Image, ImageFilter, ImageDraw
    import rembg

    # 1. Load ảnh nền (AI sinh)
    if bg_url_or_base64.startswith("data:image/"):
        header, encoded = bg_url_or_base64.split(",", 1)
        bg_data = base64.b64decode(encoded)
        bg_img = Image.open(io.BytesIO(bg_data)).convert("RGBA")
    else:
        # Tải từ URL
        resp = requests.get(bg_url_or_base64, timeout=30)
        resp.raise_for_status()
        bg_img = Image.open(io.BytesIO(resp.content)).convert("RGBA")

    bg_w, bg_h = bg_img.size

    # 2. Load ảnh sản phẩm (người dùng tải lên)
    if "," in product_base64_data:
        header, encoded = product_base64_data.split(",", 1)
    else:
        encoded = product_base64_data
    prod_data = base64.b64decode(encoded)
    prod_raw = Image.open(io.BytesIO(prod_data)).convert("RGBA")

    # 3. Tách nền bằng rembg
    prod_rgba = rembg.remove(prod_raw)

    # 4. Tự động crop sát biên sản phẩm (autocrop)
    bbox = prod_rgba.getbbox()
    if bbox:
        prod_cropped = prod_rgba.crop(bbox)
    else:
        prod_cropped = prod_rgba

    p_w, p_h = prod_cropped.size

    # 5. Tính toán kích thước resize sản phẩm
    # Chiều cao sản phẩm chiếm khoảng 52% chiều cao ảnh nền
    target_h = int(bg_h * 0.52)
    target_w = int(p_w * (target_h / p_h))

    # Nếu chiều rộng sản phẩm vượt quá 70% chiều rộng ảnh nền, resize theo chiều rộng
    if target_w > int(bg_w * 0.7):
        target_w = int(bg_w * 0.7)
        target_h = int(p_h * (target_w / p_w))

    prod_resized = prod_cropped.resize((target_w, target_h), Image.Resampling.LANCZOS)

    # 6. Tạo bóng đổ mềm (soft shadow) ở chân sản phẩm
    shadow_mask = Image.new("RGBA", (bg_w, bg_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(shadow_mask)

    # Vị trí đặt sản phẩm
    # Căn giữa theo chiều ngang
    paste_x = (bg_w - target_w) // 2
    # Chân sản phẩm cách đáy 22% chiều cao ảnh nền
    offset_y = int(bg_h * 0.22)
    paste_y = bg_h - target_h - offset_y

    if paste_y < 10:
        paste_y = 10

    # Kích thước bóng đổ: hình elip dẹt dưới chân sản phẩm
    shadow_w = int(target_w * 0.9)
    shadow_h_ell = int(shadow_w * 0.12)

    shadow_x0 = paste_x + (target_w - shadow_w) // 2
    shadow_y0 = paste_y + target_h - (shadow_h_ell // 2)
    shadow_x1 = shadow_x0 + shadow_w
    shadow_y1 = shadow_y0 + shadow_h_ell

    # Vẽ bóng đổ màu đen mờ (alpha = 110 trong 255)
    draw.ellipse([shadow_x0, shadow_y0, shadow_x1, shadow_y1], fill=(0, 0, 0, 110))

    # Blur bóng đổ
    blur_radius = max(5, int(shadow_w * 0.08))
    shadow_blurred = shadow_mask.filter(ImageFilter.GaussianBlur(blur_radius))

    # 7. Ghép bóng đổ và sản phẩm lên nền
    bg_img.alpha_composite(shadow_blurred)
    bg_img.alpha_composite(prod_resized, (paste_x, paste_y))

    # 8. Chuyển ảnh kết quả về base64
    buffered = io.BytesIO()
    final_rgb = bg_img.convert("RGB")
    final_rgb.save(buffered, format="JPEG", quality=95)
    img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")

    return f"data:image/jpeg;base64,{img_str}"


@app.post("/api/poster/generate")
def api_poster_generate():
    try:
        payload = request.json or {}
        user_prompt = str(payload.get("prompt", "")).strip()
        quantity = max(1, min(int(payload.get("quantity") or 4), 9))
        size = str(payload.get("size", "1024x1024")).strip()
        images = payload.get("images", []) # Mảng chứa base64
        keep_original = bool(payload.get("keep_original", False))

        config = load_config()
        api_key = config.get("openai", {}).get("api_key", "").strip()
        if not api_key:
            raise ValueError("Chưa cấu hình OpenAI API Key.")

        from openai import OpenAI
        client = OpenAI(api_key=api_key)

        # 1. Nếu có ảnh tải lên, dùng GPT-4o Vision để phân tích và sinh prompt chi tiết cho ảnh nền hoặc ảnh poster
        final_prompt = user_prompt
        if images:
            message_content = []
            if keep_original:
                # Chế độ Hybrid: Chỉ sinh bối cảnh nền trống (không vẽ lại sản phẩm)
                message_content.append({
                    "type": "text",
                    "text": (
                        "You are an expert product advertising poster designer. "
                        "We will remove the background of the user's product image and place it directly onto the new generated background. "
                        "Your job is to analyze the product style (colors, mood, aesthetics) and design a matching background scene for it. "
                        "The user's scene requirement is: \"" + user_prompt + "\". "
                        "Write a highly descriptive, professional English prompt for gpt-image-1-mini to generate this background scene. "
                        "CRITICAL REQUIREMENT: The background must feature a clean, empty stand, platform, podium, shelf, or flat surface in the center to place the product later. "
                        "The podium/surface must be completely empty, with no objects or bottles on it. "
                        "DO NOT include the product itself or any bottles in the prompt. "
                        "Describe premium studio lighting, soft shadows, matching colors, and high-end advertising photography style. "
                        "Output ONLY the final raw descriptive English prompt for gpt-image-1-mini, nothing else."
                    )
                })
            else:
                # Chế độ vẽ lại hoàn toàn bằng AI
                message_content.append({
                    "type": "text",
                    "text": (
                        "You are an expert product advertising poster designer. "
                        "Analyze the raw product image(s) provided (shape, color, label, brand) "
                        "and combine it with the user's background request: \"" + user_prompt + "\". "
                        "Write a highly descriptive, professional English prompt for gpt-image-1-mini "
                        "to generate a stunning, realistic commercial advertising poster featuring this exact product in the requested setting. "
                        "Describe the product in detail so gpt-image-1-mini can recreate it accurately, "
                        "along with premium studio lighting, soft shadows, and commercial photography style. "
                        "Only output the raw English prompt for gpt-image-1-mini, nothing else."
                    )
                })

            for base64_data in images[:4]: # Giới hạn tối đa 4 ảnh
                if "," in base64_data:
                    base64_data = base64_data.split(",", 1)[1]
                message_content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{base64_data}"
                    }
                })

            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": message_content}],
                max_tokens=500
            )
            final_prompt = response.choices[0].message.content.strip()
            # Log prompt đã tối ưu
            add_event({"step": "poster_gpt_prompt", "message": f"GPT-4o Vision đã tạo prompt vẽ nền: {final_prompt}" if keep_original else f"GPT-4o Vision đã tạo prompt vẽ tranh chi tiết: {final_prompt}"})

        # 2. Gọi gpt-image-1-mini để tạo ảnh poster/nền
        def generate_single_image():
            response = client.images.generate(
                model="gpt-image-1-mini",
                prompt=final_prompt,
                size=size,
                quality="medium", # Sử dụng 'medium' để tiết kiệm chi phí theo yêu cầu người dùng
                n=1
            )
            img_obj = response.data[0]
            if hasattr(img_obj, "url") and img_obj.url:
                return img_obj.url
            elif hasattr(img_obj, "b64_json") and img_obj.b64_json:
                return f"data:image/png;base64,{img_obj.b64_json}"
            elif isinstance(img_obj, dict):
                if img_obj.get("url"):
                    return img_obj["url"]
                elif img_obj.get("b64_json"):
                    return f"data:image/png;base64,{img_obj['b64_json']}"
            return None

        msg_type = "ảnh nền AI" if (keep_original and images) else "ảnh poster từ AI"
        add_event({"step": "poster_generating", "message": f"Đang kết nối gpt-image-1-mini để tạo {quantity} {msg_type} với kích thước {size}..."})

        raw_urls = []
        with ThreadPoolExecutor(max_workers=min(quantity, 4)) as executor:
            futures = [executor.submit(generate_single_image) for _ in range(quantity)]
            for fut in futures:
                try:
                    res = fut.result()
                    if res:
                        raw_urls.append(res)
                except Exception as e:
                    add_event({"step": "error", "message": f"Lỗi tạo ảnh đơn lẻ: {e}"})

        if not raw_urls:
            raise RuntimeError("Tất cả các lượt gọi API gpt-image-1-mini đều thất bại. Hãy kiểm tra kết nối API Key và quota tài khoản.")

        # 3. Nếu ở chế độ Hybrid, thực hiện ghép ảnh sản phẩm thật lên nền
        final_images = []
        if keep_original and images:
            add_event({"step": "hybrid_processing", "message": "Đang thực hiện tách nền sản phẩm thật và ghép đè lên nền AI..."})
            product_base64 = images[0]
            for bg_url in raw_urls:
                try:
                    composed_base64 = process_hybrid_composition(bg_url, product_base64, size)
                    final_images.append(composed_base64)
                except Exception as e:
                    add_event({"step": "hybrid_error_warning", "message": f"Lỗi ghép ảnh: {e}. Hệ thống tự động sử dụng ảnh nền gốc."})
                    final_images.append(bg_url)
        else:
            final_images = raw_urls

        add_event({"step": "poster_done", "message": f"Đã tạo thành công {len(final_images)} ảnh poster quảng cáo."})
        return jsonify({"images": final_images})

    except Exception as exc:
        add_event({"step": "error", "message": str(exc)})
        return error_response(exc, 400)


@app.post("/api/poster/save")
def api_poster_save():
    try:
        payload = request.json or {}
        image_url = str(payload.get("image_url", "")).strip()
        filename = str(payload.get("filename", "")).strip()

        if not image_url or not filename:
            raise ValueError("Thiếu URL ảnh hoặc tên file.")

        config = load_config()
        export_dir = config.get("openai", {}).get("export_dir", "").strip()

        target_folder = None
        if export_dir:
            path = Path(export_dir).expanduser()
            if path.exists() and path.is_dir():
                target_folder = path

        if not target_folder:
            # Mặc định lưu vào thư mục Drive hiện tại đang chọn
            try:
                target_folder = selected_drive_folder()
            except Exception:
                # Nếu chưa chọn thư mục, lưu vào drive_root_dir
                target_folder = drive_root()

        if not target_folder.exists():
            target_folder.mkdir(parents=True, exist_ok=True)

        dest_path = target_folder / filename

        if image_url.startswith("data:image/"):
            try:
                if "," in image_url:
                    header, encoded = image_url.split(",", 1)
                else:
                    encoded = image_url
                data = base64.b64decode(encoded)
                dest_path.write_bytes(data)
            except Exception as e:
                raise ValueError(f"Không thể giải mã dữ liệu ảnh Base64: {e}")
        else:
            # Tải ảnh từ OpenAI URL về
            r = requests.get(image_url, timeout=30)
            r.raise_for_status()
            dest_path.write_bytes(r.content)

        add_event({"step": "poster_saved", "message": f"Đã lưu poster thành công vào thư mục: {dest_path}", "file": str(dest_path)})
        return jsonify({"status": "Lưu poster thành công.", "saved_path": str(dest_path)})

    except Exception as exc:
        add_event({"step": "error", "message": str(exc)})
        return error_response(exc, 400)


# ==========================================
# CONTENT IMAGE HELPER TOOL AUTOMATION API
# ==========================================

PROMPTS_FILE = ROOT / "content_prompts.json"
POST_PROMPTS_FILE = ROOT / "post_prompts.json"
POST_PROMPTS_LOCK = threading.RLock()

_cached_prompts = None
_cached_prompts_mtime = 0.0

def load_prompts():
    global _cached_prompts, _cached_prompts_mtime
    if not PROMPTS_FILE.exists():
        return []
    try:
        mtime = os.path.getmtime(PROMPTS_FILE)
        if _cached_prompts is not None and mtime == _cached_prompts_mtime:
            return _cached_prompts.copy()
        with open(PROMPTS_FILE, "r", encoding="utf-8") as f:
            prompts = json.load(f)
        _cached_prompts = prompts
        _cached_prompts_mtime = mtime
        return prompts.copy()
    except Exception:
        if _cached_prompts is not None:
            return _cached_prompts.copy()
        return []

def save_prompts(prompts_list):
    global _cached_prompts, _cached_prompts_mtime
    try:
        with open(PROMPTS_FILE, "w", encoding="utf-8") as f:
            json.dump(prompts_list, f, ensure_ascii=False, indent=2)
        _cached_prompts = prompts_list.copy()
        _cached_prompts_mtime = os.path.getmtime(PROMPTS_FILE)
        return True
    except Exception:
        return False

@app.get("/api/content/prompts")
def api_get_prompts():
    return jsonify(load_prompts())

@app.post("/api/content/prompts")
def api_save_prompt():
    try:
        data = request.json or {}
        p_id = data.get("id")
        category = str(data.get("category", "General")).strip()
        title = str(data.get("title", "")).strip()
        content = str(data.get("content", "")).strip()

        if not title or not content:
            raise ValueError("Tiêu đề và nội dung không được để trống.")

        prompts = load_prompts()

        if p_id:
            # Update
            found = False
            for p in prompts:
                if p["id"] == p_id:
                    p["category"] = category
                    p["title"] = title
                    p["content"] = content
                    found = True
                    break
            if not found:
                prompts.append({"id": p_id, "category": category, "title": title, "content": content})
        else:
            # Create new
            import uuid
            p_id = str(uuid.uuid4())
            prompts.append({"id": p_id, "category": category, "title": title, "content": content})

        if save_prompts(prompts):
            return jsonify({"status": "Lưu thành công.", "prompt": {"id": p_id, "category": category, "title": title, "content": content}})
        else:
            raise RuntimeError("Không thể ghi file dữ liệu.")
    except Exception as exc:
        return error_response(exc, 400)

@app.delete("/api/content/prompts/<prompt_id>")
def api_delete_prompt(prompt_id):
    try:
        prompts = load_prompts()
        updated = [p for p in prompts if p["id"] != prompt_id]
        if len(updated) == len(prompts):
            raise ValueError("Không tìm thấy prompt tương ứng.")
        if save_prompts(updated):
            return jsonify({"status": "Xóa thành công."})
        else:
            raise RuntimeError("Không thể ghi file dữ liệu.")
    except Exception as exc:
        return error_response(exc, 400)


def parse_prompts_txt(text: str) -> list[dict[str, str]]:
    prompts = []
    # Chuẩn hóa xuống dòng
    text = text.replace('\r\n', '\n').replace('\r', '\n')

    current_prompt = {}
    current_field = None
    content_lines = []

    for raw_line in text.split('\n'):
        line = raw_line.strip()

        # Nếu gặp dòng phân cách
        if line.startswith('---') or line.startswith('==='):
            if current_prompt.get('title') and (current_prompt.get('content') is not None or content_lines):
                current_prompt['content'] = '\n'.join(content_lines).strip()
                prompts.append(current_prompt)
            current_prompt = {}
            current_field = None
            content_lines = []
            continue

        # Kiểm tra Danh mục
        match_cat = re.match(r'^(Danh mục|Category)\s*:\s*(.*)$', line, re.IGNORECASE)
        if match_cat:
            if current_prompt.get('title') and (current_prompt.get('content') is not None or content_lines):
                current_prompt['content'] = '\n'.join(content_lines).strip()
                prompts.append(current_prompt)
                current_prompt = {}
                content_lines = []

            current_prompt['category'] = match_cat.group(2).strip()
            current_field = 'category'
            continue

        # Kiểm tra Tiêu đề
        match_title = re.match(r'^(Tiêu đề|Title)\s*:\s*(.*)$', line, re.IGNORECASE)
        if match_title:
            current_prompt['title'] = match_title.group(2).strip()
            current_field = 'title'
            continue

        # Kiểm tra Nội dung
        match_content = re.match(r'^(Nội dung|Content)\s*:\s*(.*)$', line, re.IGNORECASE)
        if match_content:
            current_field = 'content'
            content_lines = [match_content.group(2).strip()]
            current_prompt['content'] = ''
            continue

        # Nội dung nhiều dòng
        if current_field == 'content':
            content_lines.append(raw_line)

    # Lưu prompt cuối cùng
    if current_prompt.get('title') and (current_prompt.get('content') is not None or content_lines):
        current_prompt['content'] = '\n'.join(content_lines).strip()
        prompts.append(current_prompt)

    return prompts


@app.post("/api/content/prompts/import")
def api_import_prompts():
    try:
        if 'file' not in request.files:
            raise ValueError("Không tìm thấy file trong yêu cầu tải lên.")
        file = request.files['file']
        if not file.filename:
            raise ValueError("Tên file không hợp lệ.")

        text = file.read().decode('utf-8', errors='ignore')
        imported_prompts = parse_prompts_txt(text)

        if not imported_prompts:
            raise ValueError("Không tìm thấy prompt hợp lệ nào trong file. Vui lòng kiểm tra lại cấu trúc file.")

        existing_prompts = load_prompts()
        config = load_config()

        # Đảm bảo có content_categories trong config
        if "content_categories" not in config:
            config["content_categories"] = ["Shopee", "Facebook", "General"]

        categories = config["content_categories"]
        categories_modified = False

        count = 0
        import uuid
        for p in imported_prompts:
            cat = p.get('category', 'General').strip()
            if not cat:
                cat = 'General'

            # Nếu danh mục chưa có, tự động thêm vào config.json
            if cat not in categories:
                categories.append(cat)
                categories_modified = True

            title = p.get('title', 'Imported Prompt').strip()
            content = p.get('content', '').strip()

            if not content:
                continue

            # Tạo prompt và lưu
            p_id = str(uuid.uuid4())
            existing_prompts.append({
                "id": p_id,
                "category": cat,
                "title": title,
                "content": content
            })
            count += 1

        if count > 0:
            save_prompts(existing_prompts)
            if categories_modified:
                config["content_categories"] = categories
                save_config(config)

        return jsonify({"success": True, "count": count})

    except Exception as exc:
        return error_response(exc, 400)


@app.get("/api/content/prompts/export")
def api_export_prompts():
    try:
        prompts = load_prompts()
        lines = []
        for p in prompts:
            category = p.get("category", "General")
            title = p.get("title", "")
            content = p.get("content", "")
            prompt_str = f"Danh mục: {category}\nTiêu đề: {title}\nNội dung: {content}"
            lines.append(prompt_str)

        export_text = "\n---\n".join(lines)
        from flask import Response
        return Response(
            export_text,
            mimetype="text/plain",
            headers={"Content-Disposition": "attachment;filename=prompts_export.txt"}
        )
    except Exception as exc:
        return error_response(exc, 400)


def default_post_prompt_record():
    return {
        "id": DEFAULT_POST_PROMPT_ID,
        "title": "Prompt mặc định",
        "content": DEFAULT_POST_PROMPT_CONTENT,
        "is_default": True,
    }


def load_post_prompts():
    with POST_PROMPTS_LOCK:
        prompts = []
        if POST_PROMPTS_FILE.exists():
            try:
                loaded = json.loads(POST_PROMPTS_FILE.read_text(encoding="utf-8"))
                if isinstance(loaded, list):
                    prompts = [item for item in loaded if isinstance(item, dict)]
            except Exception:
                prompts = []

        if not any(item.get("id") == DEFAULT_POST_PROMPT_ID for item in prompts):
            prompts.insert(0, default_post_prompt_record())
        return [dict(item) for item in prompts]


def save_post_prompts(prompts):
    cleaned = []
    for item in prompts:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        content = str(item.get("content", "")).strip()
        if not title or not content:
            continue
        cleaned.append({
            "id": str(item.get("id", "")).strip(),
            "title": title,
            "content": content,
            "is_default": str(item.get("id", "")).strip() == DEFAULT_POST_PROMPT_ID,
        })

    if not any(item["id"] == DEFAULT_POST_PROMPT_ID for item in cleaned):
        cleaned.insert(0, default_post_prompt_record())

    with POST_PROMPTS_LOCK:
        POST_PROMPTS_FILE.write_text(
            json.dumps(cleaned, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return cleaned


@app.get("/api/shopee/post-prompts")
def api_get_post_prompts():
    return jsonify(load_post_prompts())


@app.post("/api/shopee/post-prompts")
def api_save_post_prompt():
    try:
        import uuid

        data = request.json or {}
        prompt_id = str(data.get("id", "")).strip() or str(uuid.uuid4())
        title = str(data.get("title", "")).strip()
        content = str(data.get("content", "")).strip()
        if not title or not content:
            raise ValueError("Tên mẫu và nội dung prompt không được để trống.")

        prompts = load_post_prompts()
        record = {
            "id": prompt_id,
            "title": title,
            "content": content,
            "is_default": prompt_id == DEFAULT_POST_PROMPT_ID,
        }
        for index, item in enumerate(prompts):
            if item.get("id") == prompt_id:
                prompts[index] = record
                break
        else:
            prompts.append(record)

        save_post_prompts(prompts)
        return jsonify({"success": True, "prompt": record})
    except Exception as exc:
        return error_response(exc, 400)


@app.delete("/api/shopee/post-prompts/<prompt_id>")
def api_delete_post_prompt(prompt_id):
    try:
        if prompt_id == DEFAULT_POST_PROMPT_ID:
            raise ValueError("Prompt mặc định được giữ lại để tool luôn có mẫu dự phòng.")
        prompts = load_post_prompts()
        updated = [item for item in prompts if item.get("id") != prompt_id]
        if len(updated) == len(prompts):
            raise ValueError("Không tìm thấy prompt cần xóa.")
        save_post_prompts(updated)
        return jsonify({"success": True})
    except Exception as exc:
        return error_response(exc, 400)


@app.post("/api/shopee/post-prompts/import")
def api_import_post_prompts():
    try:
        import uuid

        uploaded = request.files.get("file")
        if not uploaded or not uploaded.filename:
            raise ValueError("Vui lòng chọn file prompt .txt.")
        parsed = parse_prompts_txt(uploaded.read().decode("utf-8", errors="ignore"))
        prompts = load_post_prompts()
        count = 0
        for item in parsed:
            title = str(item.get("title", "Prompt nhập từ file")).strip()
            content = str(item.get("content", "")).strip()
            if not content:
                continue
            prompts.append({
                "id": str(uuid.uuid4()),
                "title": title,
                "content": content,
                "is_default": False,
            })
            count += 1
        if not count:
            raise ValueError("File không có prompt hợp lệ.")
        save_post_prompts(prompts)
        return jsonify({"success": True, "count": count})
    except Exception as exc:
        return error_response(exc, 400)


@app.get("/api/shopee/post-prompts/export")
def api_export_post_prompts():
    try:
        from flask import Response

        sections = []
        for item in load_post_prompts():
            sections.append(
                f"Tiêu đề: {item.get('title', '')}\nNội dung: {item.get('content', '')}"
            )
        return Response(
            "\n---\n".join(sections),
            mimetype="text/plain; charset=utf-8",
            headers={"Content-Disposition": "attachment;filename=shopee_post_prompts.txt"},
        )
    except Exception as exc:
        return error_response(exc, 400)


def parse_version(v_str):
    if not v_str:
        return (0, 0, 0)
    cleaned = v_str.strip().lower().lstrip('v')
    parts = []
    for p in cleaned.split('.'):
        num_str = ''.join(c for c in p if c.isdigit())
        parts.append(int(num_str) if num_str else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])

UPDATE_STATUS = {
    "status": "idle",
    "progress": 0,
    "message": "",
    "error": None
}
UPDATE_STATUS_LOCK = threading.Lock()

def set_update_status(status, progress=0, message="", error=None):
    global UPDATE_STATUS
    with UPDATE_STATUS_LOCK:
        UPDATE_STATUS = {
            "status": status,
            "progress": progress,
            "message": message,
            "error": error
        }

def run_update_in_background(download_url):
    try:
        import tempfile
        temp_update_dir = Path(tempfile.gettempdir()) / "PixelDriveCaptureUpdate"
        if temp_update_dir.exists():
            shutil.rmtree(temp_update_dir, ignore_errors=True)
        temp_update_dir.mkdir(parents=True, exist_ok=True)

        set_update_status("downloading", 0, "Bắt đầu tải bản cập nhật...")
        add_event({"step": "app_update", "message": "Bắt đầu tải tệp tin cập nhật từ GitHub..."})

        zip_path = temp_update_dir / "update_tmp.zip"
        headers = {"User-Agent": "PixelDriveCapture-Updater"}
        r = requests.get(download_url, headers=headers, stream=True, timeout=60)
        r.raise_for_status()

        total_length = r.headers.get('content-length')
        if total_length is None:
            with open(zip_path, "wb") as f:
                f.write(r.content)
            set_update_status("downloading", 50, "Đã tải xong tệp zip.")
        else:
            dl = 0
            total_length = int(total_length)
            with open(zip_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
                        dl += len(chunk)
                        percent = int(100 * dl / total_length)
                        set_update_status("downloading", percent, f"Đang tải: {percent}%...")
                        if percent % 10 == 0:
                            add_event({"step": "app_update", "message": f"Đang tải bản cập nhật: {percent}%..."})

        set_update_status("extracting", 90, "Đang giải nén dữ liệu cập nhật...")
        add_event({"step": "app_update", "message": "Đang giải nén dữ liệu cập nhật..."})

        import zipfile
        extract_dir = temp_update_dir / "extract"
        extract_dir.mkdir(exist_ok=True)

        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)

        extract_source = extract_dir
        sub_dir = extract_dir / "MCPShopee"
        if sub_dir.exists() and sub_dir.is_dir():
            extract_source = sub_dir

        # Kiểm tra tính hợp lệ của gói cập nhật (bắt buộc phải có MCPShopee.exe)
        target_exe_in_update = extract_source / "MCPShopee.exe"
        if not target_exe_in_update.exists():
            found_exes = list(extract_dir.glob("**/MCPShopee.exe"))
            if found_exes:
                extract_source = found_exes[0].parent
            else:
                set_update_status("failed", 0, "Gói cập nhật không chứa file thực thi MCPShopee.exe!")
                add_event({"step": "app_update", "message": "Lỗi: Không tìm thấy MCPShopee.exe trong gói giải nén. Đã hủy cập nhật để bảo vệ phần mềm."})
                return

        exe_path = ROOT / "MCPShopee.exe"
        bat_path = ROOT / "updater.bat"

        # Định nghĩa các đường dẫn dạng chuỗi không chứa dấu gạch chéo ngược trong f-string
        root_str = str(ROOT).replace('/', '\\')
        root_internal = str(ROOT / "_internal").replace('/', '\\')
        exe_path_str = str(exe_path).replace('/', '\\')
        extract_source_str = str(extract_source).replace('/', '\\')
        temp_update_dir_str = str(temp_update_dir).replace('/', '\\')

        bat_content = f"""@echo off
chcp 65001 > nul
title MCP Shopee - Updater
echo ==================================================
echo   DANG CAP NHAT PHAN MEM - VUI LONG CHO...
echo ==================================================
echo.

:: Kiểm tra quyền Admin
:check_privileges
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Dang yeu cau quyen Administrator de cap nhat...
    powershell -Command "Start-Process -FilePath '%0' -ArgumentList 'am_admin' -Verb RunAs"
    exit /b
)

:: Force kill truoc de day nhanh tien trinh
taskkill /F /IM MCPShopee.exe >nul 2>&1

:wait_close
tasklist /FI "IMAGENAME eq MCPShopee.exe" 2>nul | find /I /N "MCPShopee.exe" >nul
if "%ERRORLEVEL%"=="0" (
    echo Dang cho MCP Shopee tat hoan toan...
    ping 127.0.0.1 -n 2 > nul
    goto wait_close
)

:: Cho them 1 giay de he thong giai phong hoan toan file handle
ping 127.0.0.1 -n 2 > nul

echo Dang don dep phien ban cu...
:: Ap dung co che doi ten de tranh loi lock file tren Windows
if exist "{root_internal}" (
    rd /s /q "{root_internal}.old" >nul 2>&1
    ren "{root_internal}" "_internal.old" >nul 2>&1
    rd /s /q "{root_internal}" >nul 2>&1
)
if exist "{exe_path_str}" (
    del /f /q "{exe_path_str}.old" >nul 2>&1
    ren "{exe_path_str}" "MCPShopee.exe.old" >nul 2>&1
    del /f /q "{exe_path_str}" >nul 2>&1
)

echo Dang sao chep cac tep tin moi...
:: Dung robocopy khong /MOVE de giu lai nguon, loai tru updater.bat dang chay de tranh loi file locked
robocopy "{extract_source_str}" "{root_str}" /E /IS /IT /XF config.json config.example.json updater.bat /R:5 /W:1

if %errorlevel% LSS 8 (
    :: Kiem tra neu MCPShopee.exe khong ton tai sau khi copy, rollback ngay
    if not exist "{exe_path_str}" (
        if exist "{exe_path_str}.old" ren "{exe_path_str}.old" "MCPShopee.exe"
        if exist "{root_internal}.old" ren "{root_internal}.old" "_internal"
        echo LOI: Khong tim thay MCPShopee.exe moi! Da khoi phuc phien ban cu an toan.
        pause
        exit /b 1
    )

    echo Dang don dep cac tep tin tam...
    :: Chi xoa khi copy thanh cong
    if exist "{temp_update_dir_str}" rd /s /q "{temp_update_dir_str}" >nul 2>&1

    :: Xoa file .old neu he thong da giai phong
    del /f /q "{exe_path_str}.old" >nul 2>&1
    rd /s /q "{root_internal}.old" >nul 2>&1

    echo.
    echo ==================================================
    echo   CAP NHAT THANH CONG!
    echo   Dang khoi dong lai MCP Shopee...
    echo ==================================================
    start "" "{exe_path_str}"
) else (
    echo.
    echo ==================================================
    echo   LOI: KHONG THE SAO CHEP CAC TEP TIN MOI!
    echo   Ma loi Robocopy: %errorlevel%
    echo   Vui long dong tat ca cac cua so ung dung va thu lai.
    echo ==================================================
    pause
)

(goto) 2>nul & del "%~f0"
"""
        bat_path.write_text(bat_content, encoding="utf-8")

        set_update_status("ready", 100, "Đang khởi chạy updater...")
        add_event({"step": "app_update", "message": "Đã tải xong bản cập nhật. Đang khởi chạy updater..."})

        subprocess.Popen(f'"{bat_path}"', shell=True, creationflags=subprocess.CREATE_NEW_CONSOLE)

        time.sleep(1.0)
        os._exit(0)

    except Exception as exc:
        set_update_status("error", 0, f"Lỗi cập nhật: {exc}", error=str(exc))
        add_event({"step": "error", "message": f"Lỗi trong quá trình cập nhật: {exc}"})
        print(f"[Update Thread] Error: {exc}")


@app.get("/api/app/check-update")
def api_check_update():
    try:
        url = "https://api.github.com/repos/datdtpl-maker/MCP-Shopee_Khai-Hoan/releases/latest"
        headers = {"User-Agent": "MCPShopee-Updater"}

        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 404:
            return jsonify({
                "has_update": False,
                "current_version": CURRENT_VERSION,
                "latest_version": CURRENT_VERSION,
                "download_url": "",
                "release_notes": "Chưa có bản cập nhật nào được phát hành trên GitHub."
            })

        r.raise_for_status()
        release_data = r.json()

        latest_version = release_data.get("tag_name", "").strip()
        release_notes = release_data.get("body", "").strip()

        download_url = ""
        assets = release_data.get("assets", [])
        for asset in assets:
            name = asset.get("name", "")
            if name.endswith(".zip"):
                download_url = asset.get("browser_download_url", "")
                break

        # Chỉ sử dụng các file nén binary .zip đính kèm trên Release (không dùng zipball_url nguồn thô)
        if not download_url:
            download_url = ""

        has_update = False
        if latest_version:
            if parse_version(latest_version) > parse_version(CURRENT_VERSION):
                has_update = True

        return jsonify({
            "has_update": has_update,
            "current_version": CURRENT_VERSION,
            "latest_version": latest_version,
            "download_url": download_url,
            "release_notes": release_notes
        })
    except Exception as exc:
        return error_response(exc, 400)


@app.post("/api/app/perform-update")
def api_perform_update():
    try:
        data = request.json or {}
        download_url = data.get("download_url", "").strip()
        if not download_url:
            raise ValueError("Thiếu link tải bản cập nhật.")

        threading.Thread(target=run_update_in_background, args=(download_url,)).start()
        return jsonify({"success": True, "message": "Tiến trình cập nhật đã bắt đầu chạy ngầm."})
    except Exception as exc:
        return error_response(exc, 400)


@app.get("/api/app/update-status")
def api_get_update_status():
    global UPDATE_STATUS
    with UPDATE_STATUS_LOCK:
        return jsonify(UPDATE_STATUS)


@app.get("/api/content/categories")
def api_get_categories():
    try:
        config = load_config()
        categories = config.get("content_categories")
        if not categories:
            categories = ["Shopee", "Facebook", "General"]
            with CONFIG_LOCK:
                config = load_config()
                config["content_categories"] = categories
                save_config(config)
        return jsonify(categories)
    except Exception as exc:
        return error_response(exc, 400)


@app.post("/api/content/categories")
def api_save_categories():
    try:
        data = request.json or {}
        categories = data.get("categories")
        rename_map = data.get("rename_map", {})
        deleted_list = data.get("deleted", [])

        if not isinstance(categories, list):
            raise ValueError("Categories phải là một danh sách.")

        cleaned_categories = []
        for cat in categories:
            cat_str = str(cat).strip()
            if cat_str and cat_str not in cleaned_categories:
                cleaned_categories.append(cat_str)

        if not cleaned_categories:
            cleaned_categories = ["Shopee", "Facebook", "General"]

        with CONFIG_LOCK:
            config = load_config()
            config["content_categories"] = cleaned_categories
            save_config(config)

        # Đồng bộ hóa prompt category
        prompts = load_prompts()
        prompts_changed = False

        # Đổi tên danh mục
        if rename_map:
            for p in prompts:
                old_cat = p.get("category")
                if old_cat in rename_map:
                    p["category"] = rename_map[old_cat]
                    prompts_changed = True

        # Xóa danh mục
        default_cat = cleaned_categories[0] if cleaned_categories else "General"
        if deleted_list:
            for p in prompts:
                old_cat = p.get("category")
                if old_cat in deleted_list:
                    if old_cat not in rename_map:
                        p["category"] = default_cat
                        prompts_changed = True

        if prompts_changed:
            save_prompts(prompts)

        return jsonify({"status": "Lưu danh mục thành công.", "categories": cleaned_categories})
    except Exception as exc:
        return error_response(exc, 400)


def get_chrome_path():
    import os
    paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe")
    ]
    for p in paths:
        if os.path.exists(p):
            return p
    return None


def kill_processes_by_commandline(process_name, cmd_pattern):
    import subprocess
    import os
    if os.name == "nt":
        ps_cmd = f"Get-CimInstance Win32_Process -Filter \"Name = '{process_name}' and CommandLine like '%{cmd_pattern}%'\" | Invoke-CimMethod -MethodName Terminate"
        cmd = ["powershell", "-NoProfile", "-Command", ps_cmd]
        try:
            subprocess.run(cmd, capture_output=True, text=True, check=False)
        except Exception as e:
            print(f"[Kill Process] Lỗi dọn dẹp {process_name} ({cmd_pattern}): {e}")


def kill_mcp_shopee_except_current(current_pid):
    import subprocess
    import os
    if os.name == "nt":
        ps_cmd = f"Get-CimInstance Win32_Process -Filter \"Name = 'MCPShopee.exe' and ProcessID <> {current_pid}\" | Invoke-CimMethod -MethodName Terminate"
        cmd = ["powershell", "-NoProfile", "-Command", ps_cmd]
        try:
            subprocess.run(cmd, capture_output=True, text=True, check=False)
        except Exception as e:
            print(f"[Kill Process] Lỗi dọn dẹp MCPShopee.exe cũ: {e}")


@app.post("/api/automation/chrome/start")
def api_chrome_start():
    try:
        chrome_path = get_chrome_path()
        if not chrome_path:
            raise FileNotFoundError("Không tìm thấy trình duyệt Google Chrome cài đặt trên hệ thống!")

        # Dọn dẹp tiến trình Chrome debug cũ ở port 9222 trước khi mở mới
        kill_processes_by_commandline("chrome.exe", "remote-debugging-port=9222")
        import time
        time.sleep(0.3)

        # Khởi chạy trực tiếp chrome.exe GUI độc lập, sử dụng profile cục bộ trong dự án và mở cửa sổ bình thường
        user_data_dir = str(ROOT / "chrome_profile_debug")
        cmd = [
            chrome_path,
            "https://chatgpt.com",
            "--remote-debugging-port=9222",
            f"--user-data-dir={user_data_dir}"
        ]
        subprocess.Popen(cmd)

        add_event({"step": "chrome_automation", "message": "Đã phát lệnh kích hoạt Chrome Debugging Port 9222."})
        return jsonify({"status": "Đã kích hoạt Chrome Debug."})
    except Exception as exc:
        return error_response(exc, 400)


@app.get("/api/automation/chrome/status")
def api_chrome_status():
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.5)
    try:
        s.connect(("127.0.0.1", 9222))
        s.close()
        return jsonify({"online": True, "message": "Chrome Debug Port 9222 đang online."})
    except Exception:
        return jsonify({"online": False, "message": "Chrome Debug Port 9222 chưa hoạt động."})


@app.post("/api/automation/chrome-gemini/start")
def api_chrome_gemini_start():
    try:
        chrome_path = get_chrome_path()
        if not chrome_path:
            raise FileNotFoundError("Không tìm thấy trình duyệt Google Chrome cài đặt trên hệ thống!")

        # Dọn dẹp tiến trình Chrome debug cũ ở port 9223 trước khi mở mới
        kill_processes_by_commandline("chrome.exe", "remote-debugging-port=9223")
        import time
        time.sleep(0.3)

        # Khởi chạy trực tiếp chrome.exe GUI độc lập cho Gemini, sử dụng profile cục bộ trong dự án và mở cửa sổ bình thường
        user_data_dir = str(ROOT / "chrome_profile_debug_gemini")
        cmd = [
            chrome_path,
            "https://gemini.google.com",
            "--remote-debugging-port=9223",
            f"--user-data-dir={user_data_dir}"
        ]
        subprocess.Popen(cmd)

        add_event({"step": "gemini_automation", "message": "Đã phát lệnh kích hoạt Chrome Debugging Port 9223 cho Gemini."})
        return jsonify({"status": "Đã kích hoạt Chrome Gemini Debug."})
    except Exception as exc:
        return error_response(exc, 400)


@app.get("/api/automation/chrome-gemini/status")
def api_chrome_gemini_status():
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.5)
    try:
        s.connect(("127.0.0.1", 9223))
        s.close()
        return jsonify({"online": True, "message": "Chrome Debug Port 9223 đang online."})
    except Exception:
        return jsonify({"online": False, "message": "Chrome Debug Port 9223 chưa hoạt động."})


def get_image_number_from_title(title: str) -> str:
    if not title:
        return "1"
    title_clean = title.strip()
    if title_clean == "Tạo ảnh Cover Shopee":
        return "1"
    import re
    match = re.search(r'(?:Số\s+)?(\d+)', title_clean, re.IGNORECASE)
    if match:
        return match.group(1)
    return "1"


def run_chatgpt_automation_thread(image_path: str | None, prompt_text: str, export_dir: str, sample_path: str | None = None, prompt_title: str | None = None):
    from playwright.sync_api import sync_playwright
    import os
    import base64
    from datetime import datetime
    import time
    from shopee_sync.src.chatgpt_capture import (
        find_chatgpt_editor,
        fill_chatgpt_prompt,
        init_chatgpt_image_tracker,
        poll_chatgpt_image,
        save_chatgpt_image_atomic,
    )

    add_event({"step": "chatgpt_automation", "message": "Bắt đầu tiến trình tự động hóa ChatGPT..."})

    try:
        with sync_playwright() as p:
            add_event({"step": "chatgpt_automation", "message": "Đang kết nối tới Chrome Debug qua cổng 9222..."})
            try:
                browser = p.chromium.connect_over_cdp("http://localhost:9222")
            except Exception as e:
                add_event({"step": "error", "message": f"Không kết nối được Chrome Debug. Vui lòng bấm 'Khởi động Chrome' và đăng nhập ChatGPT. Chi tiết: {e}"})
                return

            context = browser.contexts[0]

            # Tìm tab ChatGPT
            page = None
            for p_page in context.pages:
                if "chatgpt.com" in p_page.url:
                    page = p_page
                    break

            if not page:
                add_event({"step": "chatgpt_automation", "message": "Không tìm thấy tab ChatGPT đang mở. Đang mở tab mới..."})
                page = context.new_page()
                page.goto("https://chatgpt.com")
                # Đợi trang tải
                page.wait_for_load_state("load")

            # Đợi ô nhập text sẵn sàng
            try:
                editor_el = find_chatgpt_editor(page)
                if not editor_el:
                    page.wait_for_selector("#prompt-textarea", timeout=15000)
                    editor_el = find_chatgpt_editor(page)
                if not editor_el:
                    add_event({"step": "error", "message": "Không tìm thấy ô nhập liệu '#prompt-textarea'. Vui lòng kiểm tra lại trang web ChatGPT."})
                    return
            except Exception as e_editor:
                add_event({"step": "error", "message": f"Lỗi ô nhập liệu ChatGPT hoặc trang bị khóa: {e_editor}"})
                return

            # Thiết lập baseline tracker để khóa danh tính phiên và đếm prompt
            tracker = init_chatgpt_image_tracker(page, prompt_text)

            # Các selectors của nút gửi
            send_selectors = [
                'button[data-testid="send-button"]',
                'button[data-testid="fruitjuice-send-button"]',
                'button[aria-label="Send prompt"]',
                'button[aria-label="Gửi phản hồi"]',
                'button.mb-1.mr-1',
                'button:has(svg)',
                'button:has(path[d*="M12"])',
                '#prompt-textarea ~ button',
                'div[contenteditable="true"] ~ button'
            ]

            # Xây dựng danh sách file cần upload
            files_to_upload = []
            if image_path and os.path.exists(image_path):
                files_to_upload.append(image_path)
            if sample_path and os.path.exists(sample_path):
                files_to_upload.append(sample_path)

            # Upload ảnh nếu có
            if files_to_upload:
                desc = "ảnh sản phẩm" if len(files_to_upload) == 1 else "ảnh sản phẩm và ảnh mẫu"
                add_event({"step": "chatgpt_automation", "message": f"Đang upload {desc} lên ChatGPT..."})
                file_input = page.query_selector('input[type="file"]')
                if file_input:
                    file_input.set_input_files(files_to_upload)
                    # Chờ tối đa 60 giây cho tệp tải lên xong (đợi nút Send sẵn sàng/enabled)
                    add_event({"step": "chatgpt_automation", "message": "Đang chờ tải tệp lên hoàn tất (đợi nút Gửi sẵn sàng)..."})
                    upload_success = False
                    for i in range(60):
                        time.sleep(1.0)
                        for sel in send_selectors:
                            try:
                                btn = page.query_selector(sel)
                                if btn and btn.is_enabled():
                                    upload_success = True
                                    break
                            except Exception:
                                pass
                        if upload_success:
                            add_event({"step": "chatgpt_automation", "message": f"Tệp đã tải lên hoàn tất sau {i+1} giây."})
                            break
                    if not upload_success:
                        add_event({"step": "chatgpt_automation", "message": "Cảnh báo: Quá thời gian chờ tải tệp lên, vẫn tiến hành nhập prompt..."})
                else:
                    add_event({"step": "chatgpt_automation", "message": "Cảnh báo: Không tìm thấy input tải file của ChatGPT."})

            # Điền prompt
            add_event({"step": "chatgpt_automation", "message": "Đang nhập prompt..."})
            try:
                editor = fill_chatgpt_prompt(page, prompt_text)
                time.sleep(1.0)
            except Exception as e_fill:
                print(f"[ChatGPT Auto] Lỗi điền prompt: {e_fill}")
                add_event({"step": "error", "message": f"Không thể nhập prompt vào ChatGPT: {e_fill}"})
                return

            print(f"[ChatGPT Auto] Baseline tracker: {len(tracker.get('baselineSources', []))} anh nguon, {tracker.get('previousMatchingPrompts', 0)} prompt cu khop.")

            # Vòng lặp thử gửi tin nhắn (Tối đa 5 lần thử, mỗi lần cách nhau 2 giây)
            sent_successfully = False
            for attempt in range(1, 6):
                if attempt > 1:
                    add_event({"step": "chatgpt_automation", "message": f"Thử gửi lại lần {attempt} do tin nhắn chưa được gửi đi..."})

                # Thử click nút gửi
                clicked = False
                for sel in send_selectors:
                    try:
                        btn = page.query_selector(sel)
                        if btn and btn.is_enabled():
                            btn.click(timeout=1500)
                            clicked = True
                            add_event({"step": "chatgpt_automation", "message": f"[Lần {attempt}] Đã click nút gửi ChatGPT."})
                            break
                    except Exception:
                        continue

                # Nếu không click được bằng nút, thử nhấn Enter trên editor
                if not clicked and editor:
                    try:
                        editor.focus()
                        page.keyboard.press("Enter")
                        add_event({"step": "chatgpt_automation", "message": f"[Lần {attempt}] Đã gửi lệnh phím Enter."})
                        clicked = True
                    except Exception as press_ex:
                        print(f"[ChatGPT Auto] Lỗi phím Enter: {press_ex}")

                # Đợi 2 giây để kiểm tra xem tin nhắn đã gửi đi chưa (ô chat trống)
                time.sleep(2.0)

                # Kiểm tra xem ô chat có trống rỗng không
                try:
                    textarea_val = ""
                    if editor:
                        textarea_val = editor.evaluate("e => ((e.tagName === 'TEXTAREA' || e.tagName === 'INPUT') ? e.value : (e.innerText || e.textContent)).trim()")
                    if not textarea_val:
                        sent_successfully = True
                        add_event({"step": "chatgpt_automation", "message": "Gửi prompt thành công! Ô chat đã trống."})
                        break
                except Exception as e_check:
                    print(f"[ChatGPT Auto] Lỗi kiểm tra ô chat: {e_check}")
                    sent_successfully = True
                    break

            if not sent_successfully:
                add_event({"step": "chatgpt_automation", "message": "Cảnh báo: Đã thử gửi 5 lần nhưng ô nhập liệu vẫn còn nội dung. Tiếp tục chờ sinh ảnh..."})

            time.sleep(1.0)
            add_event({"step": "chatgpt_automation", "message": "Đã gửi prompt thành công. Đang chờ ChatGPT / DALL-E sinh ảnh mới..."})

            # Quét định kỳ để phát hiện ảnh hoàn chỉnh từ ChatGPT
            start_time = time.time()
            found_image = False
            image_data_url = None
            last_reason = ""

            while time.time() - start_time < 240:  # Timeout 240 giây (4 phút)
                time.sleep(2.5)
                try:
                    poll_res = poll_chatgpt_image(page, tracker, prompt_text)
                    phase = poll_res.get("phase")

                    if phase == "error":
                        err_msg = poll_res.get("error", "Lỗi nhận diện giao diện ChatGPT")
                        print(f"[ChatGPT Auto] Polling error: {err_msg}")
                        if "tải lại" in err_msg or "Có prompt khác" in err_msg:
                            add_event({"step": "chatgpt_automation", "message": f"Cảnh báo ChatGPT: {err_msg}"})
                            break
                        continue

                    if phase == "image-ready":
                        image_data_url = poll_res.get("dataUrl")
                        image_src = poll_res.get("src")
                        if not image_data_url and image_src:
                            # Thử fetch blob sang base64 dataUrl trong page context
                            try:
                                fetch_js = """async (src) => {
                                    try {
                                        const resp = await fetch(src, { credentials: 'include' });
                                        if (!resp.ok) return null;
                                        const blob = await resp.blob();
                                        return new Promise((resolve) => {
                                            const reader = new FileReader();
                                            reader.onloadend = () => resolve(reader.result);
                                            reader.onerror = () => resolve(null);
                                            reader.readAsDataURL(blob);
                                        });
                                    } catch (e) {
                                        return null;
                                    }
                                }"""
                                image_data_url = page.evaluate(fetch_js, image_src)
                            except Exception as e_fetch:
                                print(f"[ChatGPT Auto] Fetch blob thất bại: {e_fetch}")

                        if not image_data_url and image_src:
                            # Fallback cuối: Playwright element screenshot
                            try:
                                locator = page.locator(f"img[src='{image_src}']").last
                                if locator.count() > 0:
                                    scr_bytes = locator.screenshot(type="png")
                                    image_data_url = "data:image/png;base64," + base64.b64encode(scr_bytes).decode("ascii")
                            except Exception as e_scr:
                                print(f"[ChatGPT Auto] Screenshot fallback thất bại: {e_scr}")

                        if image_data_url:
                            found_image = True
                            break

                    # Các phase chờ: "awaiting-request", "awaiting-assistant", "awaiting-image"
                    reason = poll_res.get("reason", "")
                    if reason and reason != last_reason and poll_res.get("busy"):
                        last_reason = reason
                        print(f"[ChatGPT Auto] {reason}")
                except Exception as e_poll:
                    print(f"[ChatGPT Auto] Ngoại lệ khi quét ảnh: {e_poll}")
                    continue

            if found_image and image_data_url:
                add_event({"step": "chatgpt_automation", "message": "Đã phát hiện ảnh kết quả mới từ ChatGPT. Đang kiểm tra và lưu an toàn..."})

                num = get_image_number_from_title(prompt_title)
                filename = f"{num}.png"

                out_dir = Path(export_dir)
                dest_path = out_dir / filename

                try:
                    save_chatgpt_image_atomic(image_data_url, dest_path)
                    add_event({
                        "step": "chatgpt_done",
                        "message": f"Tải ảnh thành công! Đã lưu file: {filename}",
                        "file_path": str(dest_path),
                        "filename": filename
                    })
                except Exception as save_err:
                    add_event({"step": "error", "message": f"Lỗi kiểm tra hoặc lưu file ảnh: {save_err}"})
            else:
                add_event({"step": "error", "message": "Quá thời gian chờ hoặc không phát hiện ảnh mới từ ChatGPT."})

    except Exception as exc:
        add_event({"step": "error", "message": f"Lỗi trong quá trình tự động hóa: {exc}"})


@app.post("/api/automation/chatgpt/send")
def api_chatgpt_send():
    try:
        payload = request.json or {}
        prompt_text = str(payload.get("prompt", "")).strip()
        image_base64 = payload.get("image", None)
        sample_base64 = payload.get("sample_image", None)
        notion_content = str(payload.get("notion_content", "")).strip()
        keywords = str(payload.get("keywords", "")).strip()
        prompt_title = payload.get("prompt_title", None)

        if not prompt_text:
            raise ValueError("Nội dung prompt không được trống.")

        config = load_config()
        export_dir = payload.get("export_dir", "").strip()
        if not export_dir:
            export_dir = config.get("openai", {}).get("export_dir", "").strip()
        if not export_dir:
            export_dir = str(Path.home() / "Downloads")

        inbox_path = ROOT / config.get("paths", {}).get("inbox_dir", "inbox")
        inbox_path.mkdir(parents=True, exist_ok=True)

        # 1. Lưu ảnh sản phẩm thô
        temp_img_path = None
        if image_base64:
            if "," in image_base64:
                header, encoded = image_base64.split(",", 1)
            else:
                encoded = image_base64
            img_data = base64.b64decode(encoded)
            temp_img_path = str(inbox_path / "temp_chatgpt_upload.png")
            with open(temp_img_path, "wb") as f:
                f.write(img_data)

        # 2. Lưu ảnh mẫu phong cách (nếu có)
        temp_sample_path = None
        if sample_base64:
            temp_sample_path = str(inbox_path / "temp_chatgpt_sample.png")
            if sample_base64.startswith("http://") or sample_base64.startswith("https://"):
                import requests
                try:
                    response = requests.get(sample_base64, timeout=30)
                    response.raise_for_status()
                    img_data = response.content
                    with open(temp_sample_path, "wb") as f:
                        f.write(img_data)
                except Exception as e:
                    raise ValueError(f"Không thể tải ảnh mẫu từ URL: {e}")
            else:
                if "," in sample_base64:
                    header, encoded = sample_base64.split(",", 1)
                else:
                    encoded = sample_base64
                img_data = base64.b64decode(encoded)
                with open(temp_sample_path, "wb") as f:
                    f.write(img_data)

        # Thay thế động các biến trong prompt
        final_prompt = prompt_text
        if notion_content:
            final_prompt = final_prompt.replace("{{selected_notion_content}}", notion_content)
        else:
            final_prompt = final_prompt.replace("{{selected_notion_content}}", "(Không có thông tin Notion)")

        if keywords:
            final_prompt = final_prompt.replace("{{selected_keywords}}", keywords)
        else:
            final_prompt = final_prompt.replace("{{selected_keywords}}", "(Không có từ khóa insight)")

        if temp_sample_path:
            final_prompt = final_prompt.replace("{{image_sample}}", "ảnh mẫu tham khảo phong cách được đính kèm")
        else:
            final_prompt = final_prompt.replace("{{image_sample}}", "bạn tự design phong cách phù hợp")

        t = threading.Thread(
            target=run_chatgpt_automation_thread,
            args=(temp_img_path, final_prompt, export_dir, temp_sample_path, prompt_title)
        )
        t.daemon = True
        t.start()

        return jsonify({"status": "Tiến trình gửi lên ChatGPT đã được bắt đầu."})
    except Exception as exc:
        return error_response(exc, 400)


@app.post("/api/automation/chatgpt/capture-current")
def api_chatgpt_capture_current():
    """Lấy ảnh DALL-E trực tiếp từ tab ChatGPT đang mở lưu vào thư mục máy tính."""
    try:
        from playwright.sync_api import sync_playwright
        from shopee_sync.src.chatgpt_capture import save_chatgpt_image_atomic
        import base64

        data = request.json or {}
        export_dir = str(data.get("export_dir", "")).strip()
        prompt_title = data.get("prompt_title", "")
        raw_num = data.get("prompt_number")
        if raw_num is not None and str(raw_num).isdigit() and int(raw_num) > 1:
            prompt_number = int(raw_num)
        elif prompt_title:
            prompt_number = int(get_image_number_from_title(prompt_title))
        else:
            prompt_number = 1
        if not export_dir:
            raise ValueError("Thiếu thư mục lưu ảnh (export_dir).")

        with sync_playwright() as p:
            try:
                browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
            except Exception as e:
                return jsonify({"success": False, "error": f"Không thể kết nối Chrome Debug (cổng 9222): {e}"}), 400

            chat_page = None
            for ctx in browser.contexts:
                for pg in ctx.pages:
                    if "chatgpt.com" in pg.url or "chat.openai.com" in pg.url:
                        chat_page = pg
                        break
                if chat_page:
                    break

            if not chat_page:
                return jsonify({"success": False, "error": "Không tìm thấy tab ChatGPT đang mở trong Chrome."}), 404

            extract_js = """() => {
                const imgs = Array.from(document.querySelectorAll('img')).filter(img => {
                    const w = img.naturalWidth || img.width || 0;
                    const h = img.naturalHeight || img.height || 0;
                    const src = img.currentSrc || img.src || '';
                    if (!src || src.startsWith('data:image/svg')) return false;
                    if (img.closest('.attachment, [data-testid="user-attachment"], [data-user-message-bubble]')) return false;
                    return (w >= 256 && h >= 256) || src.includes('files.oaiusercontent.com') || src.includes('oaistatic');
                });
                if (imgs.length === 0) return null;
                const lastImg = imgs[imgs.length - 1];
                return {
                    src: lastImg.currentSrc || lastImg.src,
                    width: lastImg.naturalWidth || lastImg.width,
                    height: lastImg.naturalHeight || lastImg.height
                };
            }"""
            img_info = chat_page.evaluate(extract_js)
            if not img_info:
                return jsonify({"success": False, "error": "Không tìm thấy ảnh DALL-E nào trên tab ChatGPT."}), 404

            src = img_info.get("src")
            image_data_url = None

            # Cách 1: Fetch blob trong page context
            fetch_js = """async (src) => {
                try {
                    const resp = await fetch(src, { credentials: 'include' });
                    if (!resp.ok) return null;
                    const blob = await resp.blob();
                    return new Promise((resolve) => {
                        const reader = new FileReader();
                        reader.onloadend = () => resolve(reader.result);
                        reader.onerror = () => resolve(null);
                        reader.readAsDataURL(blob);
                    });
                } catch (e) {
                    return null;
                }
            }"""
            try:
                image_data_url = chat_page.evaluate(fetch_js, src)
            except Exception:
                pass

            # Cách 2: Screenshot element
            if not image_data_url:
                try:
                    locator = chat_page.locator(f"img[src='{src}']").last
                    if locator.count() > 0:
                        scr_bytes = locator.screenshot(type="png")
                        image_data_url = "data:image/png;base64," + base64.b64encode(scr_bytes).decode("ascii")
                except Exception:
                    pass

            if not image_data_url:
                return jsonify({"success": False, "error": "Không thể trích xuất dữ liệu ảnh từ tab ChatGPT."}), 500

            out_dir = Path(export_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            filename = f"{prompt_number}.png"
            dest_path = out_dir / filename

            saved_path = save_chatgpt_image_atomic(image_data_url, dest_path)

            return jsonify({
                "success": True,
                "filename": filename,
                "file_path": saved_path,
                "message": f"Đã lưu thành công file {filename} vào thư mục!"
            })
    except Exception as exc:
        return error_response(exc, 500)


@app.get("/api/images/download")
def api_download_image():
    """Tải file ảnh trực tiếp về máy tính người dùng qua trình duyệt."""
    try:
        from flask import send_file
        file_path = request.args.get("path", "").strip()
        if not file_path:
            return jsonify({"error": "Thiếu đường dẫn file"}), 400
        p = Path(file_path)
        if not p.is_file():
            return jsonify({"error": f"Không tìm thấy file: {p.name}"}), 404
        return send_file(str(p), as_attachment=True, download_name=p.name)
    except Exception as exc:
        return error_response(exc, 500)


def run_gemini_automation_thread(media_path: str | None, prompt_text: str, export_dir: str, media_type: str, prompt_title: str | None = None):
    from playwright.sync_api import sync_playwright
    import os
    import base64
    from datetime import datetime
    import time

    add_event({"step": "gemini_automation", "message": "Bắt đầu tiến trình tự động hóa Gemini..."})

    try:
        with sync_playwright() as p:
            add_event({"step": "gemini_automation", "message": "Đang kết nối tới Chrome Debug qua cổng 9223..."})
            try:
                browser = p.chromium.connect_over_cdp("http://localhost:9223")
            except Exception as e:
                add_event({"step": "error", "message": f"Không kết nối được Chrome Gemini Debug. Vui lòng bấm 'Mở Chrome Gemini' và đăng nhập. Chi tiết: {e}"})
                return

            context = browser.contexts[0]

            # Tìm tab Gemini
            page = None
            for p_page in context.pages:
                if "gemini.google.com" in p_page.url:
                    page = p_page
                    break

            if not page:
                add_event({"step": "gemini_automation", "message": "Không tìm thấy tab Gemini đang mở. Đang mở tab mới..."})
                page = context.new_page()
                page.goto("https://gemini.google.com")
                page.wait_for_load_state("load")

            # Đợi ô nhập text sẵn sàng
            try:
                page.wait_for_selector('div[contenteditable="true"]', timeout=15000)
            except Exception:
                add_event({"step": "error", "message": "Không tìm thấy ô nhập liệu của Gemini. Vui lòng kiểm tra lại trang web."})
                return

            # Các selectors của nút gửi Gemini
            send_selectors = [
                'button.send-button',
                'button[aria-label="Gửi tin nhắn"]',
                'button[aria-label="Send message"]',
                'div.send-button-container button',
                'button:has(svg path[d*="M2 "])'
            ]

            # Đếm số lượng ảnh lớn và video hiện tại trên toàn trang trước khi thao tác
            initial_imgs = 0
            initial_vids = 0
            try:
                media_info = page.evaluate("""() => {
                    const imgs = Array.from(document.querySelectorAll('img')).filter(img => {
                        const w = img.naturalWidth || img.width;
                        const h = img.naturalHeight || img.height;
                        if (w < 200 || h < 200) return false;
                        if (img.src.startsWith('data:image/svg')) return false;
                        return true;
                    });
                    const vids = Array.from(document.querySelectorAll('video'));
                    return { imgs: imgs.length, vids: vids.length };
                }""")
                initial_imgs = media_info["imgs"]
                initial_vids = media_info["vids"]
                print(f"[Gemini Auto] Media ban dau: Imgs={initial_imgs}, Vids={initial_vids}")
            except Exception as e_count:
                print(f"[Gemini Auto] Loi dem media ban dau: {e_count}")

            # 1. Upload ảnh/video trước nếu có
            if media_path and os.path.exists(media_path):
                add_event({"step": "gemini_automation", "message": f"Đang upload tệp sản phẩm: {os.path.basename(media_path)}..."})

                upload_triggered = False

                # Quét debug DOM xung quanh ô chat và gửi lên log
                try:
                    debug_info = page.evaluate("""() => {
                        const getEditor = () => {
                            const editors = Array.from(document.querySelectorAll('div[contenteditable="true"]')).filter(el => {
                                const rect = el.getBoundingClientRect();
                                return rect.width > 0 && rect.height > 0;
                            });
                            return editors[editors.length - 1] || document.querySelector('div[contenteditable="true"]');
                        };
                        const editor = getEditor();
                        if (!editor) return "Không tìm thấy editor";

                        const editorRect = editor.getBoundingClientRect();
                        let info = [];

                        // Quét tất cả phần tử bên trái editor trong cùng container cha (lên 7 cấp)
                        let parent = editor.parentElement;
                        for (let i = 0; i < 7 && parent; i++) {
                            const elements = parent.querySelectorAll('button, [role="button"], g-icon, svg, div, span');
                            for (const el of elements) {
                                const r = el.getBoundingClientRect();
                                if (r.width > 0 && r.height > 0 && r.left < editorRect.left) {
                                    const yDiff = Math.abs((r.top + r.height/2) - (editorRect.top + editorRect.height/2));
                                    if (yDiff < 120) {
                                        const label = el.getAttribute('aria-label') || el.getAttribute('title') || '';
                                        const txt = (el.textContent || '').trim().substring(0, 15);
                                        const tag = el.tagName.toLowerCase();
                                        const hasOnclick = typeof el.onclick === 'function' || el.getAttribute('onclick');
                                        info.push(`${tag}[lbl='${label}', txt='${txt}', yDiff=${Math.round(yDiff)}, click=${!!hasOnclick}]`);
                                    }
                                }
                            }
                            parent = parent.parentElement;
                        }
                        return info.slice(0, 8).join(' | ');
                    }""")
                    add_event({"step": "gemini_automation", "message": f"Debug DOM bên trái ô chat: {debug_info}"})
                except Exception as e_dbg:
                    print(f"[Gemini Auto] Lỗi quét debug DOM: {e_dbg}")

                # Cố gắng click nút dấu cộng (+) để hiển thị menu đính kèm
                try:
                    attach_btn = page.evaluate_handle("""() => {
                        const getEditor = () => {
                            const editors = Array.from(document.querySelectorAll('div[contenteditable="true"]')).filter(el => {
                                const rect = el.getBoundingClientRect();
                                return rect.width > 0 && rect.height > 0;
                            });
                            return editors[editors.length - 1] || document.querySelector('div[contenteditable="true"]');
                        };
                        const editor = getEditor();
                        if (!editor) return null;

                        const editorRect = editor.getBoundingClientRect();

                        // 1. Selector trực tiếp cực kỳ mạnh mẽ cho nút dấu cộng của Gemini
                        const directSelectors = [
                            'button[aria-label*="tải lên" i]',
                            'button[aria-label*="upload" i]',
                            'button[aria-label*="công cụ" i]',
                            'gem-icon-button[arialabel*="tải lên" i] button',
                            'gem-icon-button[arialabel*="upload" i] button',
                            'button:has(mat-icon[fonticon="plus"])',
                            'button:has(mat-icon[data-mat-icon-name="plus"])'
                        ];
                        for (const sel of directSelectors) {
                            const btn = document.querySelector(sel);
                            if (btn) {
                                const r = btn.getBoundingClientRect();
                                if (r.width > 0 && r.height > 0) return btn;
                            }
                        }

                        let bestBtn = null;
                        let minDistance = 1000;

                        // 2. Quét các phần tử click phổ biến nằm bên trái ô nhập liệu cùng hàng ngang (nới rộng yDiff lên 120px do prompt dài làm editor rất cao)
                        const candidates = document.querySelectorAll('button, [role="button"], g-icon, svg, div.uploader, .attach-button, gem-icon-button');
                        for (const el of candidates) {
                            const rect = el.getBoundingClientRect();
                            if (rect.width > 0 && rect.height > 0 && rect.left < editorRect.left) {
                                const yDiff = Math.abs((rect.top + rect.height/2) - (editorRect.top + editorRect.height/2));
                                if (yDiff < 120) { // Nới rộng Y lên 120px
                                    const distance = editorRect.left - rect.right;
                                    if (distance >= -15 && distance < minDistance) { // Cho phép xê dịch nhẹ
                                        minDistance = distance;
                                        bestBtn = el;
                                    }
                                }
                            }
                        }

                        // 3. Fallback: Quét các thẻ div/span nhỏ bên trái ô nhập liệu trong cùng container cha (nới rộng yDiff lên 120px)
                        if (!bestBtn) {
                            let parent = editor.parentElement;
                            for (let i = 0; i < 4 && parent; i++) {
                                const divs = parent.querySelectorAll('div, span');
                                for (const el of divs) {
                                    const rect = el.getBoundingClientRect();
                                    if (rect.width > 8 && rect.width < 100 && rect.height > 8 && rect.height < 100 && rect.left < editorRect.left) {
                                        const yDiff = Math.abs((rect.top + rect.height/2) - (editorRect.top + editorRect.height/2));
                                        if (yDiff < 120) {
                                            const distance = editorRect.left - rect.right;
                                            if (distance >= -15 && distance < minDistance) {
                                                minDistance = distance;
                                                bestBtn = el;
                                            }
                                        }
                                    }
                                }
                                parent = parent.parentElement;
                            }
                        }

                        // 4. Fallback toàn cục theo nhãn mở rộng rộng rãi
                        if (!bestBtn) {
                            const labels = [
                                "đính kèm", "thêm tệp", "tải tệp", "attach", "add file", "upload file",
                                "upload media", "attach files", "add_circle", "thêm hình ảnh", "thêm ảnh",
                                "tải lên", "công cụ", "upload", "content", "plus"
                            ];
                            for (const el of document.querySelectorAll('button, [role="button"], g-icon, div, span')) {
                                const label = (el.getAttribute('aria-label') || el.getAttribute('title') || el.getAttribute('arialabel') || '').toLowerCase();
                                const txt = (el.textContent || '').trim();
                                if (labels.some(l => label.includes(l)) || txt === '+' || txt === 'add') {
                                    return el.closest('button') || el.closest('[role="button"]') || el;
                                }
                            }
                        }

                        return bestBtn;
                    }""")

                    if attach_btn and attach_btn.as_element():
                        add_event({"step": "gemini_automation", "message": "Đã tìm thấy nút dấu cộng đính kèm (+). Đang mở menu..."})
                        attach_btn.as_element().click()
                        time.sleep(2.5) # Chờ 2.5 giây để menu mở và render

                        # ƯU TIÊN 1: Tìm nút cụ thể trên menu bằng thuật toán quét DOM thông minh và click bằng expect_file_chooser
                        menu_item = page.evaluate_handle("""(mType) => {
                            const isVid = mType === "video";
                            const targets = isVid
                                ? ['video']
                                : ['hình ảnh', 'images', 'tệp', 'file', 'ảnh', 'photos', 'tải tệp', 'tải ảnh'];

                            const elements = Array.from(document.querySelectorAll('*'));
                            let candidates = [];

                            for (const el of elements) {
                                const rect = el.getBoundingClientRect();
                                if (rect.width > 0 && rect.height > 0) {
                                    const text = (el.innerText || el.textContent || '').trim();
                                    const ariaLabel = (el.getAttribute('aria-label') || el.getAttribute('title') || el.getAttribute('arialabel') || '').trim();

                                    const textLower = text.toLowerCase();
                                    const labelLower = ariaLabel.toLowerCase();

                                    let match = false;
                                    if (isVid) {
                                        if (textLower === 'video' || labelLower === 'video' || (text.includes('Video') && text.length < 50)) {
                                            match = true;
                                        }
                                    } else {
                                        if (targets.some(t => textLower === t || labelLower === t || (textLower.includes(t) && text.length < 50))) {
                                            match = true;
                                        }
                                    }

                                    if (match) {
                                        candidates.push({ el, text, ariaLabel });
                                    }
                                }
                            }

                            if (candidates.length === 0) return null;

                            // Ưu tiên text ngắn nhất để chính xác
                            candidates.sort((a, b) => a.text.length - b.text.length);
                            const bestCandidate = candidates[0].el;

                            // Đi ngược lên các cha để tìm element click được
                            let cur = bestCandidate;
                            for (let i = 0; i < 6 && cur; i++) {
                                const tag = cur.tagName.toLowerCase();
                                const role = cur.getAttribute('role') || '';
                                const jsaction = cur.getAttribute('jsaction') || '';
                                const className = cur.className || '';

                                if (tag === 'button' || role === 'button' || role === 'menuitem' || role === 'option' || tag === 'a' || jsaction || className.includes('button') || className.includes('item')) {
                                    return cur;
                                }
                                cur = cur.parentElement;
                            }
                            return bestCandidate;
                        }""", "image")

                        if menu_item and menu_item.as_element():
                            target_name = "Tệp/Hình ảnh"
                            add_event({"step": "gemini_automation", "message": f"Đã tìm thấy nút chọn {target_name}. Đang click để mở hộp thoại tệp..."})
                            try:
                                with page.expect_file_chooser(timeout=8000) as fc_info:
                                    menu_item.as_element().click(no_wait_after=True, timeout=5000)
                                file_chooser = fc_info.value
                                file_chooser.set_files(media_path)
                                upload_triggered = True
                                add_event({"step": "gemini_automation", "message": f"Đã chọn tệp {os.path.basename(media_path)} thành công qua menu."})
                            except Exception as e_fc:
                                msg = f"Lỗi trigger file chooser qua menu: {e_fc}"
                                print(f"[Gemini Auto] {msg}")
                                add_event({"step": "gemini_automation", "message": msg})
                        else:
                            add_event({"step": "gemini_automation", "message": "Không tìm thấy nút tương ứng trên menu đính kèm, chuyển sang chế độ dự phòng..."})

                        # FALLBACK 1: Nếu click menu item thất bại hoặc không tìm thấy, thử tìm và set trực tiếp tất cả input file
                        if not upload_triggered:
                            file_inputs = page.query_selector_all('input[type="file"]')
                            if file_inputs:
                                add_event({"step": "gemini_automation", "message": f"Tìm thấy {len(file_inputs)} tệp input ẩn. Đang đính kèm trực tiếp làm dự phòng..."})
                                for idx, inp in enumerate(file_inputs):
                                    try:
                                        inp.set_input_files(media_path)
                                        upload_triggered = True
                                        print(f"[Gemini Auto] Đã set file thành công vào input ẩn index {idx}")
                                    except Exception as e_set:
                                        print(f"[Gemini Auto] Lỗi set file vào input ẩn index {idx}: {e_set}")
                    else:
                        add_event({"step": "gemini_automation", "message": "Không phát hiện nút đính kèm (+) trên giao diện, đang chuyển sang fallback..."})
                except Exception as e_attach:
                    print(f"[Gemini Auto] Lỗi tương tác nút đính kèm (+): {e_attach}")

                # Chế độ Fallback cuối cùng: Set file trực tiếp vào input file cuối cùng nếu các bước trên thất bại
                if not upload_triggered:
                    add_event({"step": "gemini_automation", "message": "Đang tìm kiếm tệp input ẩn để đính kèm trực tiếp..."})
                    file_inputs = page.query_selector_all('input[type="file"]')
                    file_input = file_inputs[-1] if file_inputs else None
                    if file_input:
                        try:
                            file_input.set_input_files(media_path)
                            upload_triggered = True
                        except Exception as e_input:
                            print(f"[Gemini Auto] Lỗi set_input_files trực tiếp: {e_input}")
                    else:
                        add_event({"step": "gemini_automation", "message": "Cảnh báo: Không tìm thấy bất kỳ input file nào."})

                if upload_triggered:
                    # Chờ cho tệp tải lên xong
                    add_event({"step": "gemini_automation", "message": "Đang chờ tệp tải lên hoàn tất (đợi nút Gửi sẵn sàng)..."})

                    upload_success = False
                    for i in range(90): # tăng timeout lên 90s cho video
                        time.sleep(1.0)
                        for sel in send_selectors:
                            try:
                                btn = page.query_selector(sel)
                                if btn and btn.is_enabled():
                                    upload_success = True
                                    break
                            except Exception:
                                pass
                        if upload_success:
                            time.sleep(3.0) # Tăng nhẹ thời gian chờ để tệp được render hoàn tất trên giao diện
                            add_event({"step": "gemini_automation", "message": f"Tệp đã tải lên hoàn tất sau {i+1} giây."})
                            break
                    if not upload_success:
                        add_event({"step": "gemini_automation", "message": "Cảnh báo: Hết thời gian chờ tệp tải lên, vẫn tiến hành gửi..."})
                else:
                    add_event({"step": "gemini_automation", "message": "Cảnh báo: Không thể kích hoạt tải tệp lên Gemini."})

            # 2. Nhấn nút dấu cộng (+) lần 2 để chuyển sang chế độ Video nếu có file đính kèm
            if media_path and os.path.exists(media_path):
                add_event({"step": "gemini_automation", "message": "Đang kích hoạt chế độ Video (Omni Video mode) của Gemini..."})
                try:
                    # Tìm nút cộng (+) lần 2
                    attach_btn2 = page.evaluate_handle("""() => {
                        const getEditor = () => {
                            const editors = Array.from(document.querySelectorAll('div[contenteditable="true"]')).filter(el => {
                                const rect = el.getBoundingClientRect();
                                return rect.width > 0 && rect.height > 0;
                            });
                            return editors[editors.length - 1] || document.querySelector('div[contenteditable="true"]');
                        };
                        const editor = getEditor();
                        if (!editor) return null;
                        const editorRect = editor.getBoundingClientRect();

                        const directSelectors = [
                            'button[aria-label*="Nội dung tải lên" i]',
                            'button[aria-label*="tải lên" i]',
                            'button[aria-label*="upload" i]',
                            'button[aria-label*="công cụ" i]',
                            'button:has(mat-icon[fonticon="plus"])',
                            'button:has(mat-icon[data-mat-icon-name="plus"])'
                        ];
                        for (const sel of directSelectors) {
                            const btn = document.querySelector(sel);
                            if (btn) return btn;
                        }

                        const candidates = document.querySelectorAll('button, [role="button"], gem-icon-button');
                        let best = null;
                        let minDistance = 1000;
                        for (const el of candidates) {
                            const rect = el.getBoundingClientRect();
                            if (rect.width > 0 && rect.height > 0 && rect.left < editorRect.left) {
                                const yDiff = Math.abs((rect.top + rect.height/2) - (editorRect.top + editorRect.height/2));
                                if (yDiff < 120) {
                                    const distance = editorRect.left - rect.right;
                                    if (distance >= -15 && distance < minDistance) {
                                        minDistance = distance;
                                        best = el;
                                    }
                                }
                            }
                        }
                        return best;
                    }""")

                    if attach_btn2 and attach_btn2.as_element():
                        add_event({"step": "gemini_automation", "message": "Đã bấm nút cộng (+) lần 2. Chờ menu hiển thị..."})
                        attach_btn2.as_element().click(no_wait_after=True)
                        time.sleep(2.5) # Chờ 2.5 giây để menu mở

                        # Tìm mục Video bằng thuật toán JS
                        video_item = page.evaluate_handle("""() => {
                            const targets = ['video'];
                            const elements = Array.from(document.querySelectorAll('*'));
                            let candidates = [];

                            for (const el of elements) {
                                const rect = el.getBoundingClientRect();
                                if (rect.width > 0 && rect.height > 0) {
                                    const text = (el.innerText || el.textContent || '').trim();
                                    const ariaLabel = (el.getAttribute('aria-label') || el.getAttribute('title') || el.getAttribute('arialabel') || '').trim();

                                    const textLower = text.toLowerCase();
                                    const labelLower = ariaLabel.toLowerCase();

                                    if (textLower === 'video' || labelLower === 'video' || (text.includes('Video') && text.length < 50)) {
                                        candidates.push({ el, text, ariaLabel });
                                    }
                                }
                            }

                            if (candidates.length === 0) return null;
                            candidates.sort((a, b) => a.text.length - b.text.length);
                            const bestCandidate = candidates[0].el;

                            let cur = bestCandidate;
                            for (let i = 0; i < 6 && cur; i++) {
                                const tag = cur.tagName.toLowerCase();
                                const role = cur.getAttribute('role') || '';
                                const jsaction = cur.getAttribute('jsaction') || '';
                                const className = cur.className || '';

                                if (tag === 'button' || role === 'button' || role === 'menuitem' || role === 'option' || tag === 'a' || jsaction || className.includes('button') || className.includes('item')) {
                                    return cur;
                                }
                                cur = cur.parentElement;
                            }
                            return bestCandidate;
                        }""")

                        if video_item and video_item.as_element():
                            add_event({"step": "gemini_automation", "message": "Đang click chọn Video để chuyển sang chế độ Video..."})
                            try:
                                with page.expect_file_chooser(timeout=6000) as fc_info:
                                    video_item.as_element().click(no_wait_after=True, timeout=3000)
                                file_chooser = fc_info.value
                                file_chooser.set_files([])
                                add_event({"step": "gemini_automation", "message": "Đã click chọn mục Video thành công."})
                            except Exception as e_vid_click:
                                print(f"[Gemini Auto] Lỗi khi xử lý File Chooser của Video: {e_vid_click}")
                                pass

                            # Chờ giao diện render xong badge Video
                            time.sleep(3.0)
                            add_event({"step": "gemini_automation", "message": "Kích hoạt chế độ Video thành công (giao diện đã sẵn sàng)."})
                        else:
                            add_event({"step": "error", "message": "Không tìm thấy nút Video trên menu đính kèm để kích hoạt chế độ Video."})
                    else:
                        add_event({"step": "error", "message": "Không mở được menu đính kèm để kích hoạt chế độ Video."})
                except Exception as e_vid_mode:
                    add_event({"step": "error", "message": f"Lỗi trong quá trình kích hoạt chế độ Video: {e_vid_mode}"})

            # 3. Sau khi đã upload xong và kích hoạt chế độ Video thành công, tiến hành điền prompt
            add_event({"step": "gemini_automation", "message": "Đang nhập prompt..."})
            try:
                page.focus('div[contenteditable="true"]')
                page.click('div[contenteditable="true"]')
                page.evaluate("""(text) => {
                    const getEditor = () => {
                        const editors = Array.from(document.querySelectorAll('div[contenteditable="true"]')).filter(el => {
                            const rect = el.getBoundingClientRect();
                            return rect.width > 0 && rect.height > 0;
                        });
                        return editors[editors.length - 1] || document.querySelector('div[contenteditable="true"]');
                    };
                    const el = getEditor();
                    if (el) {
                        el.innerText = text;
                        el.dispatchEvent(new Event("input", { bubbles: true }));
                    }
                }""", prompt_text)
                time.sleep(0.5)
                # Nhấn Space và Backspace để kích hoạt state
                page.keyboard.press("Space")
                page.keyboard.press("Backspace")
                time.sleep(1.5)
            except Exception as e_fill:
                print(f"[Gemini Auto] Lỗi điền prompt bằng evaluate: {e_fill}")
                page.fill('div[contenteditable="true"]', prompt_text)
                time.sleep(1.5)

            # Gửi tin nhắn
            sent_successfully = False
            for attempt in range(1, 6):
                if attempt > 1:
                    add_event({"step": "gemini_automation", "message": f"Thử gửi lại lần {attempt}..."})

                clicked = False
                for sel in send_selectors:
                    try:
                        btn = page.query_selector(sel)
                        if btn and btn.is_enabled():
                            btn.click(timeout=1500)
                            clicked = True
                            add_event({"step": "gemini_automation", "message": f"[Lần {attempt}] Đã click nút gửi Gemini."})
                            break
                    except Exception:
                        continue

                if not clicked:
                    try:
                        page.focus('div[contenteditable="true"]')
                        page.click('div[contenteditable="true"]')
                        page.keyboard.press("Enter")
                        add_event({"step": "gemini_automation", "message": f"[Lần {attempt}] Đã gửi lệnh phím Enter."})
                        clicked = True
                    except Exception as press_ex:
                        print(f"[Gemini Auto] Lỗi phím Enter: {press_ex}")

                time.sleep(2.0)

                # Kiểm tra xem ô chat có trống rỗng không
                try:
                    textarea_val = page.evaluate('document.querySelector(\'div[contenteditable="true"]\') ? document.querySelector(\'div[contenteditable="true"]\').innerText.trim() : ""')
                    if not textarea_val:
                        sent_successfully = True
                        add_event({"step": "gemini_automation", "message": "Gửi prompt thành công! Ô chat đã trống."})
                        break
                except Exception as e_check:
                    print(f"[Gemini Auto] Lỗi kiểm tra ô chat: {e_check}")
                    sent_successfully = True
                    break

            if not sent_successfully:
                add_event({"step": "gemini_automation", "message": "Cảnh báo: Đã thử gửi 5 lần nhưng ô nhập liệu vẫn còn nội dung. Tiếp tục chờ sinh kết quả..."})

            time.sleep(1.0)
            add_event({"step": "gemini_automation", "message": "Đã gửi prompt thành công. Đang chờ Gemini sinh ảnh/video mới..."})

            # Quét định kỳ phát hiện kết quả
            start_time = time.time()
            found_media = False
            media_base64_data = None
            found_type = "image"

            while time.time() - start_time < 300: # Timeout 5 phút
                time.sleep(3.0)
                try:
                    res = page.evaluate("""async (prevImgs, prevVids) => {
                        // 1. Uu tien quet trong phan hoi model-response moi nhat
                        const modelResponses = document.querySelectorAll('model-response');
                        if (modelResponses.length > 0) {
                            const lastResponse = modelResponses[modelResponses.length - 1];

                            // Kiem tra video trong phan hoi nay
                            const vids = Array.from(lastResponse.querySelectorAll('video'));
                            if (vids.length > 0) {
                                const lastVid = vids[vids.length - 1];
                                if (lastVid.src) {
                                    try {
                                        const response = await fetch(lastVid.src);
                                        const blob = await response.blob();
                                        const b64 = await new Promise((resolve, reject) => {
                                            const reader = new FileReader();
                                            reader.onloadend = () => resolve(reader.result);
                                            reader.onerror = () => reject(new Error('FileReader error'));
                                            reader.readAsDataURL(blob);
                                        });
                                        return { type: "video", data: b64 };
                                    } catch (err) {
                                        return { type: "video_url", data: lastVid.src };
                                    }
                                }
                            }

                            // Kiem tra anh trong phan hoi nay
                            const imgs = Array.from(lastResponse.querySelectorAll('img')).filter(img => {
                                const w = img.naturalWidth || img.width;
                                const h = img.naturalHeight || img.height;
                                if (w < 200 || h < 200) return false;
                                if (img.src.startsWith('data:image/svg')) return false;
                                return true;
                            });
                            if (imgs.length > 0) {
                                const lastImg = imgs[imgs.length - 1];
                                if (!lastImg.complete || lastImg.naturalWidth === 0) {
                                    return "loading";
                                }
                                try {
                                    const response = await fetch(lastImg.src);
                                    const blob = await response.blob();
                                    const b64 = await new Promise((resolve, reject) => {
                                        const reader = new FileReader();
                                        reader.onloadend = () => resolve(reader.result);
                                        reader.onerror = () => reject(new Error('FileReader error'));
                                        reader.readAsDataURL(blob);
                                    });
                                    return { type: "image", data: b64 };
                                } catch (err) {
                                    try {
                                        const canvas = document.createElement('canvas');
                                        canvas.width = lastImg.naturalWidth || lastImg.width;
                                        canvas.height = lastImg.naturalHeight || lastImg.height;
                                        const ctx = canvas.getContext('2d');
                                        ctx.drawImage(lastImg, 0, 0);
                                        return { type: "image", data: canvas.toDataURL('image/png') };
                                    } catch (canvasErr) {
                                        return "waiting";
                                    }
                                }
                            }
                        }

                        // 2. Fallback neu khong tim thay model-response (vi du giao dien Gemini thay doi)
                        const allImgs = Array.from(document.querySelectorAll('img')).filter(img => {
                            const w = img.naturalWidth || img.width;
                            const h = img.naturalHeight || img.height;
                            if (w < 200 || h < 200) return false;
                            if (img.src.startsWith('data:image/svg')) return false;
                            return true;
                        });
                        const allVids = Array.from(document.querySelectorAll('video'));

                        // Kiem tra xem co video moi khong
                        if (allVids.length > prevVids) {
                            const lastVid = allVids[allVids.length - 1];
                            if (lastVid.src) {
                                try {
                                    const response = await fetch(lastVid.src);
                                    const blob = await response.blob();
                                    const b64 = await new Promise((resolve, reject) => {
                                        const reader = new FileReader();
                                        reader.onloadend = () => resolve(reader.result);
                                        reader.onerror = () => reject(new Error('FileReader error'));
                                        reader.readAsDataURL(blob);
                                    });
                                    return { type: "video", data: b64 };
                                } catch (err) {
                                    return { type: "video_url", data: lastVid.src };
                                }
                            }
                        }

                        // Kiem tra xem co anh moi khong
                        if (allImgs.length > prevImgs) {
                            const lastImg = allImgs[allImgs.length - 1];
                            if (!lastImg.complete || lastImg.naturalWidth === 0) {
                                return "loading";
                            }

                            try {
                                const response = await fetch(lastImg.src);
                                const blob = await response.blob();
                                const b64 = await new Promise((resolve, reject) => {
                                    const reader = new FileReader();
                                    reader.onloadend = () => resolve(reader.result);
                                    reader.onerror = () => reject(new Error('FileReader error'));
                                    reader.readAsDataURL(blob);
                                });
                                return { type: "image", data: b64 };
                            } catch (err) {
                                try {
                                    const canvas = document.createElement('canvas');
                                    canvas.width = lastImg.naturalWidth || lastImg.width;
                                    canvas.height = lastImg.naturalHeight || lastImg.height;
                                    const ctx = canvas.getContext('2d');
                                    ctx.drawImage(lastImg, 0, 0);
                                    return { type: "image", data: canvas.toDataURL('image/png') };
                                } catch (canvasErr) {
                                    return "waiting";
                                }
                            }
                        }

                        return "waiting";
                    }""", (initial_imgs, initial_vids))

                    if res == "waiting" or res == "loading":
                        continue
                    elif isinstance(res, dict) and "data" in res:
                        media_base64_data = res["data"]
                        found_type = res["type"]
                        found_media = True
                        break
                except Exception as e_scan:
                    print(f"[Gemini Auto] Lỗi quét trang: {e_scan}")
                    continue

            if found_media and media_base64_data:
                add_event({"step": "gemini_automation", "message": f"Đã phát hiện {found_type} kết quả mới từ Gemini. Đang tải về..."})

                # File path
                ext = "mp4" if found_type.startswith("video") else "png"
                num = get_image_number_from_title(prompt_title)
                filename = f"{num}.{ext}"

                out_dir = Path(export_dir)
                if not out_dir.exists():
                    out_dir.mkdir(parents=True, exist_ok=True)
                dest_path = out_dir / filename

                if media_base64_data.startswith("data:"):
                    header, encoded = media_base64_data.split(",", 1)
                    bin_data = base64.b64decode(encoded)
                    dest_path.write_bytes(bin_data)
                else:
                    # Nếu là URL thuần (trong trường hợp video_url)
                    resp = requests.get(media_base64_data, timeout=60)
                    resp.raise_for_status()
                    dest_path.write_bytes(resp.content)

                add_event({
                    "step": "gemini_done",
                    "message": f"Tải {found_type} thành công! Đã lưu file: {filename}",
                    "file_path": str(dest_path),
                    "filename": filename
                })
            else:
                add_event({"step": "error", "message": "Quá thời gian chờ hoặc không phát hiện ảnh/video mới từ Gemini."})

    except Exception as exc:
        add_event({"step": "error", "message": f"Lỗi trong quá trình tự động hóa Gemini: {exc}"})


@app.post("/api/automation/gemini/send")
def api_gemini_send():
    try:
        payload = request.json or {}
        prompt_text = str(payload.get("prompt", "")).strip()
        media_base64 = payload.get("media", None)
        media_type = str(payload.get("media_type", "image")).strip().lower()
        prompt_title = payload.get("prompt_title", None)

        if not prompt_text:
            raise ValueError("Nội dung prompt không được trống.")

        config = load_config()
        export_dir = payload.get("export_dir", "").strip()
        if not export_dir:
            export_dir = config.get("openai", {}).get("export_dir", "").strip()
        if not export_dir:
            export_dir = str(Path.home() / "Downloads")

        temp_media_path = None
        if media_base64:
            if "," in media_base64:
                header, encoded = media_base64.split(",", 1)
            else:
                encoded = media_base64
            media_data = base64.b64decode(encoded)

            inbox_path = ROOT / config.get("paths", {}).get("inbox_dir", "inbox")
            inbox_path.mkdir(parents=True, exist_ok=True)

            ext = "mp4" if media_type == "video" else "png"
            temp_media_path = str(inbox_path / f"temp_gemini_upload.{ext}")
            with open(temp_media_path, "wb") as f:
                f.write(media_data)

        t = threading.Thread(
            target=run_gemini_automation_thread,
            args=(temp_media_path, prompt_text, export_dir, media_type, prompt_title)
        )
        t.daemon = True
        t.start()

        return jsonify({"status": "Tiến trình gửi lên Gemini đã được bắt đầu."})
    except Exception as exc:
        return error_response(exc, 400)


@app.post("/api/automation/image/reveal")
def api_image_reveal():
    try:
        payload = request.json or {}
        file_path_str = payload.get("file_path", "")
        if not file_path_str:
            raise ValueError("Thiếu đường dẫn tệp tin.")

        file_path = Path(file_path_str)
        if not file_path.exists():
            raise FileNotFoundError(f"Không tìm thấy tệp tin: {file_path_str}")

        subprocess.run(["explorer.exe", "/select,", str(file_path)])
        return jsonify({"status": "Đã mở thư mục và chọn file."})
    except Exception as exc:
        return error_response(exc, 400)


@app.post("/api/automation/clear-cache")
def api_clear_cache():
    try:
        # 1. Xóa file trong inbox
        inbox_dir = ROOT / "inbox"
        if inbox_dir.exists():
            for ext in ("*.png", "*.jpg", "*.jpeg", "*.mp4"):
                for f in inbox_dir.glob(ext):
                    try:
                        f.unlink()
                    except Exception:
                        pass

        # 2. Xóa file trong processed
        processed_dir = ROOT / "processed"
        if processed_dir.exists():
            for ext in ("*.png", "*.jpg", "*.jpeg", "*.mp4"):
                for f in processed_dir.glob(ext):
                    try:
                        f.unlink()
                    except Exception:
                        pass

        add_event({"step": "clear_cache", "message": "Đã xóa sạch bộ nhớ tạm và các ảnh/video kết quả cũ."})
        return jsonify({"success": True, "message": "Đã xóa cache thành công."})
    except Exception as exc:
        return error_response(exc, 400)


@app.get("/api/automation/images/list")
def api_list_downloaded_images():
    try:
        export_dir = request.args.get("export_dir", "").strip()
        if not export_dir:
            config = load_config()
            export_dir = config.get("openai", {}).get("export_dir", "").strip()
        if not export_dir:
            export_dir = str(Path.home() / "Downloads")

        out_dir = Path(export_dir)
        if not out_dir.exists():
            return jsonify([])

        img_files = []
        # Quét ở thư mục chính
        for ext in ("*.png", "*.jpg", "*.jpeg", "*.mp4", "*.webm"):
            for f in out_dir.glob(ext):
                name_lower = f.name.lower()
                is_numbered = re.match(r'^[1-9]\.(png|jpg|jpeg|mp4|webm|mov)$', name_lower) is not None
                if name_lower.startswith("chatgpt_") or name_lower.startswith("gemini_") or is_numbered:
                    img_files.append((f, out_dir))

        # Quét ở các thư mục con (Insight hoặc bất kỳ thư mục con nào)
        for ext in ("*/*.png", "*/*.jpg", "*/*.jpeg", "*/*.mp4", "*/*.webm"):
            for f in out_dir.glob(ext):
                if f.parent.name.startswith(".") or f.parent.name.lower() in ["output", "__pycache__"]:
                    continue
                name_lower = f.name.lower()
                is_numbered = re.match(r'^[1-9]\.(png|jpg|jpeg|mp4|webm|mov)$', name_lower) is not None
                if name_lower.startswith("chatgpt_") or name_lower.startswith("gemini_") or is_numbered or True:
                    img_files.append((f, out_dir))

        # Sắp xếp theo mtime của file
        img_files.sort(key=lambda x: x[0].stat().st_mtime, reverse=True)

        import urllib.parse
        results = []
        for f, base_dir in img_files[:24]:
            rel_path = str(f.relative_to(base_dir)).replace("\\", "/")
            display_name = rel_path
            quoted_export = urllib.parse.quote(export_dir)
            results.append({
                "name": display_name,
                "file_path": str(f),
                "url": f"/api/automation/images/view?name={rel_path}&export_dir={quoted_export}",
                "time": datetime.fromtimestamp(f.stat().st_mtime).strftime("%d/%m/%Y %H:%M:%S")
            })

        return jsonify(results)
    except Exception as exc:
        return error_response(exc, 400)


@app.get("/api/automation/images/view")
def api_view_downloaded_image():
    from flask import send_from_directory
    try:
        filename = request.args.get("name", "")
        if not filename:
            raise ValueError("Thiếu tên file.")

        export_dir = request.args.get("export_dir", "").strip()
        if not export_dir:
            config = load_config()
            export_dir = config.get("openai", {}).get("export_dir", "").strip()
        if not export_dir:
            export_dir = str(Path.home() / "Downloads")

        safe_base = Path(export_dir).resolve()
        filename_clean = filename.replace("\\", "/")
        file_path = (safe_base / filename_clean).resolve()

        if not str(file_path).startswith(str(safe_base)):
            return "Truy cập không hợp lệ", 403

        if not file_path.exists():
            return "File không tồn tại", 404

        return send_from_directory(str(file_path.parent), file_path.name)
    except Exception as exc:
        return error_response(exc, 400)


@app.get("/api/proxy-image")
def api_proxy_image():
    from flask import Response
    url = request.args.get("url", "").strip()
    if not url:
        return "Thiếu tham số url", 400
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        res = requests.get(url, headers=headers, timeout=15)
        res.raise_for_status()
        content_type = res.headers.get("Content-Type", "image/png")
        return Response(res.content, mimetype=content_type)
    except Exception as e:
        return f"Lỗi tải ảnh: {e}", 500



@app.get("/api/automation/latest-photo")
def api_get_latest_photo():
    try:
        config = load_config()
        inbox_dir = ROOT / config.get("paths", {}).get("inbox_dir", "inbox")

        # Tìm các file ảnh trong inbox
        photos = []
        for ext in ("*.png", "*.jpg", "*.jpeg"):
            photos.extend(inbox_dir.glob(ext))

        # Tìm các file ảnh trong drive_root / selected_drive_folder và gộp chung
        try:
            drive_root_path = Path(config.get("paths", {}).get("drive_root_dir", ""))
            selected_folder = config.get("paths", {}).get("selected_drive_folder", "")
            if drive_root_path.exists():
                target_dir = drive_root_path / selected_folder
                if target_dir.exists() and target_dir.is_dir():
                    for ext in ("*.png", "*.jpg", "*.jpeg"):
                        photos.extend(target_dir.glob(ext))
        except Exception as e_drive:
            print(f"[Latest Photo] Lỗi quét thư mục Drive: {e_drive}")

        if not photos:
            raise FileNotFoundError("Không tìm thấy ảnh nào trong thư mục inbox hoặc Google Drive.")

        # Lấy ảnh mới nhất theo thời gian sửa đổi
        latest_photo = max(photos, key=lambda x: x.stat().st_mtime)

        # Đọc ảnh và chuyển sang base64
        with open(latest_photo, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("utf-8")

        return jsonify({
            "name": latest_photo.name,
            "base64": f"data:image/png;base64,{encoded}"
        })
    except Exception as exc:
        return error_response(exc, 400)

def wait_for_port(port, host="127.0.0.1", timeout=20.0):
    import socket
    start_time = time.time()
    while True:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return True
        except (socket.timeout, ConnectionRefusedError):
            if time.time() - start_time > timeout:
                return False
            time.sleep(0.3)


def launch_desktop_gui():
    if os.environ.get("NO_GUI") == "1":
        print("[GUI] Bỏ qua khởi chạy GUI App Mode theo cấu hình NO_GUI=1.")
        return

    port = int(os.environ.get("PORT", "8765"))
    if not wait_for_port(port, timeout=20.0):
        print(f"Lỗi: Flask server không khởi động kịp trên cổng {port}")
        return

    # Tìm đường dẫn Chrome cài đặt trên Windows
    chrome_path = None
    paths = [
        Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.environ.get("LOCALAPPDATA", "C:\\Users\\datdt\\AppData\\Local")) / "Google" / "Chrome" / "Application" / "chrome.exe"
    ]
    for p in paths:
        if p.exists():
            chrome_path = str(p)
            break

    port = int(os.environ.get("PORT", "8765"))
    url = f"http://127.0.0.1:{port}"

    try:
        # Đường dẫn profile trình duyệt tạm thời để cô lập tiến trình
        profile_dir = Path(os.environ.get("LOCALAPPDATA", "C:\\Users\\datdt\\AppData\\Local")) / "MCPShopee" / "browser_profile"
        profile_dir.mkdir(parents=True, exist_ok=True)

        start_time = time.time()
        if chrome_path:
            # Chạy trực tiếp chrome.exe ở chế độ app mode với profile riêng biệt
            subprocess.run([
                chrome_path,
                f"--app={url}",
                f"--user-data-dir={profile_dir}",
                "--window-size=1320,880",
                "--no-first-run",
                "--no-default-browser-check"
            ])
        else:
            # Fallback msedge.exe
            edge_path = Path(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
            if edge_path.exists():
                subprocess.run([
                    str(edge_path),
                    f"--app={url}",
                    f"--user-data-dir={profile_dir}",
                    "--window-size=1320,880",
                    "--no-first-run",
                    "--no-default-browser-check"
                ])
            else:
                # Fallback cuối cùng: mở trình duyệt mặc định bằng webbrowser
                import webbrowser
                webbrowser.open(url)
                return  # Tránh tắt app khi mở bằng trình duyệt mặc định

        duration = time.time() - start_time
        # Chỉ thoát Flask server nếu Chrome chạy đủ lâu (người dùng dùng app bình thường và tự đóng)
        # Nếu Chrome thoát quá nhanh (< 3.0s), có thể do trùng profile hoặc delegate, ta giữ Flask chạy tiếp
        if duration > 3.0:
            os._exit(0)
        else:
            print(f"[GUI] Trình duyệt thoát quá nhanh ({duration:.2f}s). Giữ Flask server tiếp tục chạy.")
    except Exception as e:
        print(f"Lỗi khởi chạy GUI App Mode: {e}")


def cleanup_old_instances():
    import os
    import sys
    import time

    current_pid = os.getpid()
    print(f"[Cleanup] Đang dọn dẹp các tiến trình cũ (PID hiện tại: {current_pid})...")

    # 1. Tắt các tiến trình MCPShopee.exe cũ đang chạy ngầm (trừ chính nó)
    if getattr(sys, 'frozen', False):
        try:
            kill_mcp_shopee_except_current(current_pid)
            print("[Cleanup] Đã dọn dẹp các tiến trình MCPShopee.exe cũ.")
        except Exception as e:
            print(f"[Cleanup] Lỗi tắt app cũ: {e}")

    # 2. Tắt các tiến trình Chrome/Edge sử dụng profile MCPShopee
    try:
        kill_processes_by_commandline("chrome.exe", "MCPShopee")

        # Tắt thêm các tiến trình Chrome debug ChatGPT và Gemini bị treo cũ
        kill_processes_by_commandline("chrome.exe", "remote-debugging-port=9222")
        kill_processes_by_commandline("chrome.exe", "remote-debugging-port=9223")

        print("[Cleanup] Đã dọn dẹp các tiến trình Chrome cũ liên quan đến ứng dụng.")
    except Exception as e:
        print(f"[Cleanup] Lỗi tắt Chrome cũ: {e}")

    try:
        kill_processes_by_commandline("msedge.exe", "MCPShopee")
        print("[Cleanup] Đã dọn dẹp các tiến trình Edge cũ liên quan đến ứng dụng.")
    except Exception as e:
        print(f"[Cleanup] Lỗi tắt Edge cũ: {e}")

    # Chờ một khoảng thời gian ngắn để hệ điều hành giải phóng hoàn toàn cổng và file lock
    time.sleep(0.5)


def is_file_stable(cfg, remote_path, wait_seconds=1.5):
    # Lấy kích thước file lần 1
    cmd_size = f'stat -c %s "{remote_path}" 2>/dev/null || stat -f %z "{remote_path}" 2>/dev/null'
    try:
        size1 = pipeline.adb_command(cfg, "shell", cmd_size, check=False).stdout.strip()
        time.sleep(wait_seconds)
        size2 = pipeline.adb_command(cfg, "shell", cmd_size, check=False).stdout.strip()
        if not size1 or not size2:
            return False
        return size1 == size2
    except Exception:
        return False


def process_auto_media(cfg, media_path, folder_name):
    # Đảm bảo không tranh chấp với các tác vụ chụp/quay khác
    if not OPERATION_LOCK.acquire(blocking=True, timeout=5.0):
        print(f"[Watcher] Không thể acquire lock để xử lý file {media_path} do bận.")
        return

    try:
        # Kiểm tra độ ổn định của file (đảm bảo camera đã ghi xong file hoàn toàn)
        # Đối với video, ta cần chờ cho đến khi dừng quay (kích thước file ổn định)
        stable = False
        for _ in range(10): # Thử tối đa 15 giây
            if is_file_stable(cfg, media_path, wait_seconds=1.5):
                stable = True
                break
            time.sleep(1.0)

        if not stable:
            print(f"[Watcher] File {media_path} không ổn định sau nhiều lần thử. Bỏ qua.")
            return

        f_name = Path(media_path).name
        add_event({"step": "auto_detect", "message": f"Phát hiện phương tiện mới trên Pixel: {f_name}. Đang tự động kéo về Drive...", "file": f_name})

        # 1. Kéo file về máy tính
        pipeline.ensure_dirs(cfg)
        local_path = cfg.inbox_dir / f_name

        # Thử pull file
        res = pipeline.adb_command(cfg, "pull", media_path, str(local_path), check=False)
        if res.returncode != 0:
            raise RuntimeError(f"Không thể adb pull file {f_name}: {res.stderr}")

        add_event({"step": "pulled", "message": f"Đã kéo tự động file: {f_name}"})

        # 2. Tải lên thư mục Google Drive đang chọn
        folder = selected_drive_folder(folder_name)
        target = copy_media_to_drive(local_path, folder)
        add_event({"step": "drive_saved", "message": f"Đã chép tự động vào Drive: {f_name}", "file": str(target), "size": target.stat().st_size})

        # 3. Xóa file trên điện thoại Pixel và dọn dẹp file cục bộ
        cleanup = finalize_pixel_media(cfg, local_path)

        add_event({"step": "done", "message": f"Tự động xử lý hoàn tất file: {f_name}", "file": f_name})

    except Exception as e:
        add_event({"step": "error", "message": f"Lỗi xử lý tự động file {media_path}: {e}"})
    finally:
        OPERATION_LOCK.release()


def media_watcher_loop():
    import time
    last_known_epoch = None
    last_device_serial = None

    print("[Watcher] Luồng giám sát phương tiện mới trên Pixel đã bắt đầu.")

    while True:
        try:
            # 1. Nếu đang bận xử lý nút bấm chụp/quay từ web, ta tạm bỏ qua chu kỳ này
            if OPERATION_LOCK.locked():
                time.sleep(1.0)
                continue

            cfg = settings()
            serial = ""
            try:
                serial = adb_device_serial(cfg)
            except Exception:
                pass

            if not serial:
                # Không thấy thiết bị kết nối, reset trạng thái watcher
                last_known_epoch = None
                last_device_serial = None
                time.sleep(2.0)
                continue

            cfg.adb_serial = serial

            # Nếu đổi thiết bị, reset lại mốc thời gian ban đầu
            if serial != last_device_serial:
                last_device_serial = serial
                last_known_epoch = pipeline.device_epoch_seconds(cfg)
                print(f"[Watcher] Đã chuyển sang thiết bị {serial}. Mốc thời gian ban đầu: {last_known_epoch}")
                time.sleep(1.5)
                continue

            # 2. Kiểm tra xem có thư mục sản phẩm được chọn chưa
            folder_name = selected_folder_name()
            if not folder_name:
                # Chưa chọn thư mục, bỏ qua
                time.sleep(1.5)
                continue

            # 3. Lấy mốc thời gian nếu chưa có
            if last_known_epoch is None:
                last_known_epoch = pipeline.device_epoch_seconds(cfg)

            # 4. Quét tìm file mới nhất có mtime >= last_known_epoch
            patterns = ["*.jpg", "*.jpeg", "*.mp4"]
            latest_file = pipeline.latest_media_after(cfg, patterns, last_known_epoch)

            if latest_file:
                # Lấy mtime của file vừa quét được
                cmd_stat = f'stat -c %Y "{latest_file}" 2>/dev/null || stat -f %m "{latest_file}" 2>/dev/null'
                mtime_str = pipeline.adb_command(cfg, "shell", cmd_stat, check=False).stdout.strip()
                try:
                    file_mtime = int(mtime_str.splitlines()[-1])
                except Exception:
                    file_mtime = last_known_epoch

                # Cập nhật mốc thời gian tiếp theo để tránh trùng
                last_known_epoch = file_mtime + 1

                # Chạy thread xử lý file mới phát hiện
                threading.Thread(target=process_auto_media, args=(cfg, latest_file, folder_name), daemon=True).start()

        except Exception as e:
            print(f"[Watcher] Lỗi vòng lặp: {e}")

        time.sleep(1.5)


# ==========================================
# SHOPEE NOTION TO BIGSELLER SYNC API
# ==========================================
import sys
import logging

# Thêm đường dẫn shopee_sync vào sys.path để có thể import
SHOPEE_SYNC_ROOT = BUNDLE_DIR / "shopee_sync"
if str(SHOPEE_SYNC_ROOT) not in sys.path:
    sys.path.append(str(SHOPEE_SYNC_ROOT))

# Custom logging handler để đưa log của Shopee sync và Telegram bot lên web app console
class FlaskLogHandler(logging.Handler):
    def __init__(self, add_event_func):
        super().__init__()
        self.add_event_func = add_event_func

    def emit(self, record):
        try:
            msg = self.format(record)
            self.add_event_func({"step": "shopee_sync", "message": msg})
        except Exception:
            self.handleError(record)

# Cấu hình logging handler để bắt log
sync_logger = logging.getLogger("notion_sync")
bot_logger = logging.getLogger("telegram_bot")

shopee_log_handler = FlaskLogHandler(add_event)
shopee_log_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s', datefmt='%H:%M:%S'))
sync_logger.addHandler(shopee_log_handler)
bot_logger.addHandler(shopee_log_handler)
sync_logger.setLevel(logging.INFO)
bot_logger.setLevel(logging.INFO)

# Theo dõi luồng của bot và tiến trình sync
shopee_bot_thread = None
shopee_sync_thread = None
shopee_sync_active = False


def resolve_shopee_sync_export_dir(config: dict, selected_drive_path: str) -> str:
    """Chọn nơi xuất theo sản phẩm hiện tại, không tái dùng thư mục sản phẩm cũ."""
    drive_root_value = str(config.get("paths", {}).get("drive_root_dir", "")).strip()
    selected_value = str(selected_drive_path or "").strip()

    if drive_root_value and selected_value and "drive.google.com" not in selected_value.lower():
        try:
            drive_root_path = Path(drive_root_value).resolve()
            selected_path = Path(selected_value).resolve()
            if selected_path != drive_root_path and selected_path.is_relative_to(drive_root_path):
                return str(selected_path)
        except (OSError, ValueError):
            pass

    saved_export_dir = str(config.get("openai", {}).get("export_dir", "")).strip()
    if saved_export_dir:
        try:
            saved_path = Path(saved_export_dir).resolve()
            if drive_root_value:
                drive_root_path = Path(drive_root_value).resolve()
                # Một thư mục con của Drive là lựa chọn sản phẩm cũ, không phải fallback chung.
                if saved_path != drive_root_path and saved_path.is_relative_to(drive_root_path):
                    return str(Path.home() / "Downloads")
            return str(saved_path)
        except (OSError, ValueError):
            pass

    return str(Path.home() / "Downloads")

@app.get("/api/shopee/config")
def api_get_shopee_config():
    try:
        env_file = SHOPEE_SYNC_ROOT / ".env"
        config_data = {
            "NOTION_TOKEN": "",
            "NOTION_DATABASE_ID": "",
            "TELEGRAM_BOT_TOKEN": "",
            "MANAGER_CHAT_ID": "",
            "GEMINI_API_KEY": "",
            "PARTNER_ID": "0",
            "PARTNER_KEY": "",
            "SHOP_ID": "0",
            "MOCK_MODE": "True",
            "DRIVE_ROOT_FOLDER_ID": ""
        }
        if env_file.exists():
            content = env_file.read_text(encoding="utf-8")
            for line in content.splitlines():
                if "=" in line and not line.strip().startswith("#"):
                    k, v = line.split("=", 1)
                    config_data[k.strip()] = v.strip()
        return jsonify(config_data)
    except Exception as exc:
        return error_response(exc, 400)

@app.post("/api/shopee/config/save")
def api_save_shopee_config():
    try:
        payload = request.json or {}
        env_file = SHOPEE_SYNC_ROOT / ".env"

        # Tạo lại nội dung file .env
        lines = []
        lines.append("# Cấu hình Shopee Open Platform (BigSeller Sync)")
        lines.append(f"PARTNER_ID={payload.get('PARTNER_ID', '0')}")
        lines.append(f"PARTNER_KEY={payload.get('PARTNER_KEY', '')}")
        lines.append(f"SHOP_ID={payload.get('SHOP_ID', '0')}")
        lines.append("SHOPEE_API_URL=https://partner.test-stable.shopeemobile.com")
        lines.append("REDIRECT_URL=https://localhost/callback")
        lines.append(f"MOCK_MODE={payload.get('MOCK_MODE', 'True')}")
        lines.append("TOKEN_FILE_PATH=tokens.json")
        lines.append("")
        lines.append("# Cấu hình Telegram Bot và Notion")
        lines.append(f"TELEGRAM_BOT_TOKEN={payload.get('TELEGRAM_BOT_TOKEN', '')}")
        lines.append(f"NOTION_TOKEN={payload.get('NOTION_TOKEN', '')}")
        lines.append(f"NOTION_DATABASE_ID={payload.get('NOTION_DATABASE_ID', '')}")
        lines.append(f"GEMINI_API_KEY={payload.get('GEMINI_API_KEY', '')}")
        lines.append(f"MANAGER_CHAT_ID={payload.get('MANAGER_CHAT_ID', '')}")
        lines.append(f"DRIVE_ROOT_FOLDER_ID={payload.get('DRIVE_ROOT_FOLDER_ID', '')}")

        env_file.write_text("\n".join(lines), encoding="utf-8")

        # Nạp lại env cho các luồng hiện tại bằng cách gọi load_dotenv
        from dotenv import load_dotenv
        load_dotenv(env_file, override=True)

        return jsonify({"success": True, "message": "Đã lưu cấu hình Notion & Telegram thành công!"})
    except Exception as exc:
        return error_response(exc, 400)

@app.post("/api/shopee/config/test-gemini")
def api_test_gemini():
    try:
        data = request.json or {}
        api_key = data.get("api_key", "").strip()
        if not api_key:
            from dotenv import load_dotenv
            load_dotenv(SHOPEE_SYNC_ROOT / ".env")
            api_key = os.getenv("GEMINI_API_KEY", "").strip() or os.getenv("OPENAI_API_KEY", "").strip()
            
        if not api_key:
            return jsonify({"success": False, "error": "Chưa nhập API Key để kiểm tra."}), 400
            
        is_openai = api_key.startswith("sk-")
        if is_openai:
            url = "https://api.openai.com/v1/models"
            headers = {"Authorization": f"Bearer {api_key}"}
            res = requests.get(url, headers=headers, timeout=15)
            if res.status_code == 200:
                return jsonify({"success": True, "model": "GPT-4o mini", "message": "API Key OpenAI (GPT-4o mini) hoạt động hoàn hảo! Đã sẵn sàng viết bài."})
            else:
                err_msg = ""
                try:
                    err_msg = res.json().get("error", {}).get("message", res.text)
                except Exception:
                    err_msg = res.text
                return jsonify({"success": False, "error": f"Lỗi OpenAI: {err_msg}"}), 400
        else:
            # 1. Gọi ListModels trước để xác thực API Key và lấy danh sách model thực tế được cấp phép
            list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
            list_res = requests.get(list_url, timeout=15)
            
            if list_res.status_code != 200:
                err_text = "API Key không hợp lệ."
                try:
                    err_json = list_res.json()
                    err_text = err_json.get("error", {}).get("message", list_res.text)
                except Exception:
                    err_text = list_res.text
                return jsonify({"success": False, "error": f"Lỗi xác thực Gemini: {err_text}"}), 400
                
            # Trích xuất danh sách model hỗ trợ generateContent
            available_models = []
            try:
                models_data = list_res.json().get("models", [])
                for m in models_data:
                    m_name = m.get("name", "").replace("models/", "")
                    if "generateContent" in m.get("supportedGenerationMethods", []):
                        available_models.append(m_name)
            except Exception:
                pass
                
            # Ưu tiên chọn các dòng Gemini 3.7 / 3.6 / 3.5 Flash mới nhất
            flash_priorities = [
                "gemini-3.7-flash",
                "gemini-3.6-flash",
                "gemini-3.5-flash",
                "gemini-2.0-flash",
                "gemini-1.5-flash",
                "gemini-flash"
            ]
            candidate_models = []
            for p in flash_priorities:
                for m in available_models:
                    if (m == p or m.startswith(p)) and m not in candidate_models:
                        candidate_models.append(m)

            for m in available_models:
                if "flash" in m.lower() and m not in candidate_models:
                    candidate_models.append(m)

            if not candidate_models:
                candidate_models = ["gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]

            # Thử lần lượt các model candidate cho đến khi thành công
            success_model = None
            last_err = ""
            test_prompt = "Xin chào, phản hồi ngắn: 'API hoạt động tốt'."

            for c_model in candidate_models:
                gen_url = f"https://generativelanguage.googleapis.com/v1beta/models/{c_model}:generateContent?key={api_key}"
                headers = {"Content-Type": "application/json"}
                payload = {"contents": [{"parts": [{"text": test_prompt}]}]}
                try:
                    gen_res = requests.post(gen_url, headers=headers, json=payload, timeout=15)
                    if gen_res.status_code == 200:
                        success_model = c_model
                        break
                    else:
                        try:
                            last_err = gen_res.json().get("error", {}).get("message", gen_res.text)
                        except Exception:
                            last_err = gen_res.text
                except Exception as ex:
                    last_err = str(ex)

            if success_model:
                display_name = success_model.replace("gemini-", "Gemini ").title()
                return jsonify({
                    "success": True,
                    "model": display_name,
                    "message": f"API Key Gemini chính xác! Đã kết nối thành công với mô hình '{display_name}'."
                })
            else:
                return jsonify({"success": False, "error": f"Lỗi khởi tạo mô hình Gemini: {last_err}"}), 400
    except Exception as exc:
        return error_response(exc, 500)

@app.get("/api/shopee/bot/status")
def api_get_shopee_bot_status():
    try:
        global shopee_bot_thread
        try:
            from shopee_sync.src import telegram_bot
        except ImportError:
            from src import telegram_bot
        is_alive = shopee_bot_thread is not None and shopee_bot_thread.is_alive() and not telegram_bot.should_stop
        return jsonify({
            "running": is_alive,
            "message": "Bot Telegram đang hoạt động." if is_alive else "Bot Telegram đã dừng."
        })
    except Exception as exc:
        return error_response(exc, 500)

@app.post("/api/shopee/bot/start")
def api_start_shopee_bot():
    try:
        global shopee_bot_thread
        try:
            from shopee_sync.src import telegram_bot
        except ImportError:
            from src import telegram_bot

        # Kiểm tra cấu hình trước
        env_file = SHOPEE_SYNC_ROOT / ".env"
        if not env_file.exists():
            return jsonify({"success": False, "error": "Chưa cấu hình các thông số Notion/Telegram. Vui lòng cấu hình trước."}), 400

        is_alive = shopee_bot_thread is not None and shopee_bot_thread.is_alive() and not telegram_bot.should_stop
        if is_alive:
            return jsonify({"success": True, "message": "Bot Telegram đã đang chạy sẵn rồi."})

        # Thiết lập lại state và khởi chạy
        telegram_bot.should_stop = False

        def run_telegram_bot_wrapper():
            try:
                telegram_bot.run_bot()
            except Exception as e:
                add_event({"step": "shopee_sync", "message": f"Lỗi trong quá trình chạy Bot Telegram: {e}"})

        shopee_bot_thread = threading.Thread(target=run_telegram_bot_wrapper, daemon=True)
        shopee_bot_thread.start()

        add_event({"step": "shopee_sync", "message": "Đã khởi động Bot Telegram thành công!"})
        return jsonify({"success": True, "message": "Khởi động Bot Telegram thành công!"})
    except Exception as exc:
        return error_response(exc, 500)

@app.post("/api/shopee/bot/stop")
def api_stop_shopee_bot():
    try:
        global shopee_bot_thread
        try:
            from shopee_sync.src import telegram_bot
        except ImportError:
            from src import telegram_bot

        telegram_bot.stop_bot_process()
        add_event({"step": "shopee_sync", "message": "Đang tắt Bot Telegram..."})
        return jsonify({"success": True, "message": "Đã gửi lệnh dừng Bot Telegram."})
    except Exception as exc:
        return error_response(exc, 500)


shopee_generation_active = False

@app.get("/api/shopee/products/pending")
def api_get_pending_products():
    try:
        from notion_client import Client
        env_file = SHOPEE_SYNC_ROOT / ".env"
        if not env_file.exists():
            return jsonify([])

        from dotenv import load_dotenv
        load_dotenv(env_file, override=True)

        token = os.getenv("NOTION_TOKEN")
        if not token:
            return jsonify([])

        notion = Client(auth=token)
        try:
            from shopee_sync.src.notion_sync import call_notion_with_retry, find_local_product_folder
        except ImportError:
            from src.notion_sync import call_notion_with_retry, find_local_product_folder

        root = validate_drive_root(drive_root())

        # Quét từ cả 2 Database chính của 2 Shop: nhathuockh.pharma và khaihoanpharmacy
        SHOP_DATABASES = [
            ("nhathuockh.pharma", os.getenv("NOTION_DATABASE_ID", "").strip() or "ca055a7742824b9598abde7a7686d144"),
            ("khaihoanpharmacy", os.getenv("NOTION_DATABASE_ID_KHAIHOAN", "").strip() or "a1daa38950504cb5849bbdfde6e547ff")
        ]

        target_shop = request.args.get("shop", "").strip()
        if target_shop and target_shop.lower() != "all":
            active_dbs = [item for item in SHOP_DATABASES if item[0].lower() == target_shop.lower()]
            if not active_dbs:
                active_dbs = [(target_shop, SHOP_DATABASES[0][1])]
        else:
            active_dbs = SHOP_DATABASES

        pending_items = []

        for current_shop_name, db_main_id in active_dbs:
            try:
                db_meta = call_notion_with_retry(notion.databases.retrieve, database_id=db_main_id)
                data_sources = db_meta.get("data_sources", [])
                q_target = data_sources[0]["id"] if data_sources else db_main_id
                res = call_notion_with_retry(
                    notion.data_sources.query if data_sources else notion.databases.query,
                    **{"data_source_id" if data_sources else "database_id": q_target, "page_size": 100}
                )
                records = res.get("results", [])

                for page in records:
                    properties = page.get("properties", {})
                    title_list = properties.get("Tên sản phẩm", {}).get("title", [])
                    title = title_list[0].get("plain_text", "").strip() if title_list else ""
                    if not title:
                        continue

                    # Trạng thái Notion (select): Chờ đăng, Đã đăng, Lên đơn, Nội dung, Hủy...
                    st_sel = properties.get("Trạng thái", {}).get("select") or {}
                    notion_status = st_sel.get("name", "").strip() if isinstance(st_sel, dict) else ""
                    if not notion_status:
                        notion_status = "Chưa đặt"

                    p1 = properties.get("Giá biến thể 1", {}).get("number")
                    v1 = "".join([x.get("plain_text", "") for x in properties.get("Biến thể 1", {}).get("rich_text", [])]).strip()
                    p2 = properties.get("Giá biến thể 2", {}).get("number")
                    v2 = "".join([x.get("plain_text", "") for x in properties.get("Biến thể 2", {}).get("rich_text", [])]).strip()
                    media_url = properties.get("Media sản phẩm", {}).get("url") or ""
                    note = "".join([x.get("plain_text", "") for x in properties.get("Ghi chú", {}).get("rich_text", [])]).strip()

                    # Relation trỏ sang database Shopee Insight Library (88159c9046fb426db3c9a0d79358e76c)
                    rel_lib = properties.get("Insight Library", {}).get("relation", [])
                    insight_lib_id = rel_lib[0].get("id") if rel_lib else None

                    # Lấy số insight từ Insight Library nếu có
                    insight_count = 0
                    rel_insight_ids = []
                    lib_title = ""
                    if insight_lib_id:
                        try:
                            lib_page = call_notion_with_retry(notion.pages.retrieve, page_id=insight_lib_id)
                            lib_props = lib_page.get("properties", {})
                            lt_list = lib_props.get("Tên post Shopee", {}).get("title", [])
                            lib_title = lt_list[0].get("plain_text", "").strip() if lt_list else ""
                            rel_ins = lib_props.get("Danh sách Insight", {}).get("relation", [])
                            rel_insight_ids = [r.get("id") for r in rel_ins]
                            num_prop = lib_props.get("Số Insight", {}).get("rollup", {})
                            insight_count = int(num_prop.get("number") or len(rel_insight_ids))
                        except Exception as err:
                            print(f"[Pending Products] Lỗi đọc Insight Lib {insight_lib_id}: {err}")

                    # Tìm thư mục local/Drive theo đúng Shop
                    existing_shop = None
                    matched_folder_name = ""
                    matched_folder_path = None
                    if root and root.is_dir():
                        shop_dir = root / current_shop_name
                        if shop_dir.is_dir():
                            matched = find_local_product_folder(shop_dir, title)
                            if not matched and lib_title:
                                matched = find_local_product_folder(shop_dir, lib_title)
                        else:
                            matched = None

                        if not matched:
                            matched = find_local_product_folder(root, title)
                            if not matched and lib_title:
                                matched = find_local_product_folder(root, lib_title)

                        if matched and matched.is_dir():
                            matched_folder_name = matched.name
                            matched_folder_path = matched
                            try:
                                rel = matched.relative_to(root)
                                if len(rel.parts) > 1:
                                    existing_shop = rel.parts[0]
                                else:
                                    existing_shop = matched.name
                            except Exception:
                                existing_shop = current_shop_name

                    # Đánh giá tình trạng hoàn thành bài viết & hình ảnh
                    has_images_count = 0
                    if matched_folder_path and matched_folder_path.is_dir():
                        for sub in matched_folder_path.iterdir():
                            if sub.is_dir():
                                imgs = [x for x in sub.iterdir() if x.is_file() and x.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp", ".mp4"]]
                                if imgs:
                                    has_images_count += 1

                    if insight_count == 0:
                        ready_status = "Chưa có insight"
                    elif has_images_count >= insight_count and insight_count > 0:
                        ready_status = "Đủ bài & hình"
                    elif has_images_count > 0:
                        ready_status = f"Thiếu hình ({has_images_count}/{insight_count})"
                    else:
                        ready_status = "Thiếu hình"

                    # Ghép định dạng giá hiển thị
                    price_display = f"{int(p1):,}đ" if p1 else ""

                    pending_items.append({
                        "id": page.get("id"),
                        "title": title,
                        "insight_count": insight_count,
                        "status": ready_status,
                        "notion_status": notion_status,
                        "price": price_display,
                        "price_num": p1,
                        "classification": v1 or "Mặc định",
                        "variant_2": v2,
                        "drive_url": media_url,
                        "note": note,
                        "insight_lib_id": insight_lib_id,
                        "lib_title": lib_title,
                        "shop": existing_shop or current_shop_name,
                        "folder_name": matched_folder_name
                    })
            except Exception as query_err:
                print(f"[Pending Products] Lỗi query DB {db_main_id} ({current_shop_name}): {query_err}")

        # Sắp xếp ưu tiên:
        # 1. Chờ đăng lên đầu tiên (ưu tiên xử lý)
        # 2. Chưa đặt / Lên đơn
        # 3. Đã đăng
        status_priority = {
            "Chờ đăng": 0,
            "Chưa đặt": 1,
            "Lên đơn": 2,
            "Nội dung": 3,
            "Đã đăng": 4,
            "Hủy": 5
        }
        pending_items.sort(key=lambda x: (
            status_priority.get(x["notion_status"], 9),
            0 if x["status"] == "Đủ bài & hình" else 1,
            x["title"]
        ))
        return jsonify(pending_items)
    except Exception as exc:
        return error_response(exc, 500)


@app.post("/api/shopee/product/update-status")
def api_update_product_status():
    try:
        from notion_client import Client
        from dotenv import load_dotenv
        env_file = SHOPEE_SYNC_ROOT / ".env"
        if env_file.exists():
            load_dotenv(env_file, override=True)

        config = load_config()
        token = config.get("notion", {}).get("token", "").strip() or os.getenv("NOTION_TOKEN", "").strip()
        if not token:
            return jsonify({"success": False, "error": "Chưa cấu hình NOTION_TOKEN"}), 400

        data = request.json or {}
        page_id = data.get("page_id", "").strip()
        new_status = data.get("status", "").strip()
        if not page_id or not new_status:
            return jsonify({"success": False, "error": "Thiếu page_id hoặc status"}), 400

        notion = Client(auth=token)
        try:
            from shopee_sync.src.notion_sync import call_notion_with_retry
        except ImportError:
            from src.notion_sync import call_notion_with_retry

        call_notion_with_retry(
            notion.pages.update,
            page_id=page_id,
            properties={"Trạng thái": {"select": {"name": new_status}}}
        )
        return jsonify({"success": True, "message": f"Đã chuyển trạng thái sang '{new_status}'"})
    except Exception as exc:
        return error_response(exc, 500)


@app.post("/api/shopee/insights/save-to-notion")
def api_save_insights_to_notion():
    try:
        from notion_client import Client
        from dotenv import load_dotenv
        env_file = SHOPEE_SYNC_ROOT / ".env"
        if env_file.exists():
            load_dotenv(env_file, override=True)

        config = load_config()
        token = config.get("notion", {}).get("token", "").strip() or os.getenv("NOTION_TOKEN", "").strip()
        if not token:
            return jsonify({"success": False, "error": "Chưa cấu hình NOTION_TOKEN"}), 400

        notion = Client(auth=token)
        try:
            from shopee_sync.src.notion_sync import call_notion_with_retry, fetch_all_blocks_recursive, format_notion_blocks_to_text
        except ImportError:
            from src.notion_sync import call_notion_with_retry, fetch_all_blocks_recursive, format_notion_blocks_to_text

        data = request.json or {}
        parent_page_id = data.get("page_id", "").strip()
        product_name = data.get("product_name", "").strip()
        price_raw = data.get("price", "").strip()
        classification = data.get("classification", "").strip()
        variants = data.get("variants", "").strip()
        insights = data.get("insights", [])

        if not insights:
            return jsonify({"success": False, "error": "Không có insight nào để lưu."}), 400

        def build_rich_text_safe(text_val):
            if not text_val:
                return []
            s = str(text_val).strip()
            if not s:
                return []
            chunks = [s[i:i+1900] for i in range(0, len(s), 1900)]
            return [{"type": "text", "text": {"content": c}} for c in chunks]

        def convert_text_to_blocks(raw_text):
            blocks = []
            if not raw_text or not raw_text.strip():
                return blocks
            lines = raw_text.split("\n")
            for line in lines:
                l_strip = line.strip()
                if not l_strip:
                    continue
                if l_strip.startswith("⭐") or l_strip.startswith("## "):
                    clean_h = l_strip.lstrip("⭐").lstrip("#").strip()
                    blocks.append({
                        "object": "block",
                        "type": "heading_2",
                        "heading_2": {"rich_text": build_rich_text_safe(f"⭐ {clean_h}")}
                    })
                elif l_strip.startswith("🍀") or l_strip.startswith("# "):
                    clean_h = l_strip.lstrip("🍀").lstrip("#").strip()
                    blocks.append({
                        "object": "block",
                        "type": "heading_1",
                        "heading_1": {"rich_text": build_rich_text_safe(f"🍀 {clean_h}")}
                    })
                elif l_strip.startswith("📍") or l_strip.startswith("### "):
                    clean_h = l_strip.lstrip("📍").lstrip("#").strip()
                    blocks.append({
                        "object": "block",
                        "type": "heading_3",
                        "heading_3": {"rich_text": build_rich_text_safe(f"📍 {clean_h}")}
                    })
                elif l_strip.startswith("- ") or l_strip.startswith("• ") or l_strip.startswith("* "):
                    clean_bullet = l_strip[2:].strip()
                    blocks.append({
                        "object": "block",
                        "type": "bulleted_list_item",
                        "bulleted_list_item": {"rich_text": build_rich_text_safe(clean_bullet)}
                    })
                elif l_strip.startswith("> "):
                    clean_quote = l_strip[2:].strip()
                    blocks.append({
                        "object": "block",
                        "type": "quote",
                        "quote": {"rich_text": build_rich_text_safe(clean_quote)}
                    })
                else:
                    blocks.append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {"rich_text": build_rich_text_safe(l_strip)}
                    })
            return blocks

        updated_count = 0
        for item in insights:
            child_id = item.get("id", "").strip()
            if not child_id:
                continue

            c_title = item.get("title", "").strip()
            c_angle = item.get("angle", "").strip()
            c_keywords = item.get("keywords", "").strip()
            c_content = item.get("content", "").strip()

            try:
                c_page = call_notion_with_retry(notion.pages.retrieve, page_id=child_id)
                c_props = c_page.get("properties", {})
            except Exception as get_err:
                print(f"[Save Insight] Không thể đọc trang {child_id}: {get_err}")
                continue

            props_to_update = {}
            # 1. Title property
            title_prop_name = None
            for p_name, p_val in c_props.items():
                if p_val.get("type") == "title":
                    title_prop_name = p_name
                    break
            if title_prop_name and c_title:
                props_to_update[title_prop_name] = {"title": [{"type": "text", "text": {"content": c_title}}]}

            # 2. Angle property
            for p_name in c_props.keys():
                if p_name.lower() == "angle":
                    props_to_update[p_name] = {"rich_text": build_rich_text_safe(c_angle)}
                    break

            # 3. Keywords property
            for p_name in c_props.keys():
                if "từ khóa" in p_name.lower() or "keyword" in p_name.lower():
                    props_to_update[p_name] = {"rich_text": build_rich_text_safe(c_keywords)}
                    break

            # 4. Property "Nội dung đăng Shopee"
            for p_name in c_props.keys():
                if "nội dung" in p_name.lower() and "shopee" in p_name.lower():
                    props_to_update[p_name] = {"rich_text": build_rich_text_safe(c_content[:1900])}
                    break

            # Cập nhật properties
            if props_to_update:
                try:
                    call_notion_with_retry(notion.pages.update, page_id=child_id, properties=props_to_update)
                except Exception as up_err:
                    print(f"[Save Insight] Lỗi cập nhật properties trang {child_id}: {up_err}")

            # 5. Cập nhật Blocks nội dung bài viết nếu có thay đổi
            if c_content:
                try:
                    existing_blocks = fetch_all_blocks_recursive(notion, child_id)
                    existing_text = format_notion_blocks_to_text(existing_blocks)
                    if existing_text.strip() != c_content.strip():
                        top_blocks = call_notion_with_retry(notion.blocks.children.list, block_id=child_id).get("results", [])
                        for b in top_blocks:
                            try:
                                call_notion_with_retry(notion.blocks.delete, block_id=b["id"])
                            except Exception as del_err:
                                print(f"[Save Insight] Lỗi xoá block {b.get('id')}: {del_err}")

                        new_blocks = convert_text_to_blocks(c_content)
                        for chunk_idx in range(0, len(new_blocks), 10):
                            batch = new_blocks[chunk_idx:chunk_idx + 10]
                            try:
                                call_notion_with_retry(notion.blocks.children.append, block_id=child_id, children=batch)
                            except Exception as app_err:
                                print(f"[Save Insight] Lỗi thêm block mới cho {child_id}: {app_err}")
                except Exception as b_err:
                    print(f"[Save Insight] Lỗi cập nhật blocks cho {child_id}: {b_err}")

            updated_count += 1

        # Cập nhật trang cha nếu có
        if parent_page_id:
            try:
                p_page = call_notion_with_retry(notion.pages.retrieve, page_id=parent_page_id)
                p_props = p_page.get("properties", {})
                p_updates = {}
                if product_name:
                    p_title_name = None
                    for p_n, p_v in p_props.items():
                        if p_v.get("type") == "title":
                            p_title_name = p_n
                            break
                    if p_title_name:
                        p_updates[p_title_name] = {"title": [{"type": "text", "text": {"content": product_name}}]}

                if "Biến thể & giá" in p_props and (price_raw or classification or variants):
                    price_info_text = f"Phân loại: {classification}\nGiá sản phẩm: {price_raw}\nBiến thể / Giá:\n{variants}"
                    p_updates["Biến thể & giá"] = {"rich_text": build_rich_text_safe(price_info_text)}

                if p_updates:
                    call_notion_with_retry(notion.pages.update, page_id=parent_page_id, properties=p_updates)
            except Exception as p_err:
                print(f"[Save Insight] Lỗi cập nhật trang cha: {p_err}")

        # Cập nhật Master DB nếu có liên kết
        if price_raw or classification:
            try:
                import re
                price_digits = re.sub(r"\D", "", price_raw)
                price_num = int(price_digits) if price_digits else None
                master_db_id = "ca055a7742824b9598abde7a7686d144"
                db_meta = call_notion_with_retry(notion.databases.retrieve, database_id=master_db_id)
                ds = db_meta.get("data_sources", [])
                q_target = ds[0]["id"] if ds else master_db_id
                res_m = call_notion_with_retry(
                    notion.data_sources.query if ds else notion.databases.query,
                    **{"data_source_id" if ds else "database_id": q_target, "filter": {"property": "Insight Library", "relation": {"contains": parent_page_id}}}
                )
                if res_m.get("results"):
                    m_page = res_m["results"][0]
                    m_updates = {}
                    if price_num is not None:
                        m_updates["Giá biến thể 1"] = {"number": price_num}
                    if classification:
                        m_updates["Biến thể 1"] = {"rich_text": build_rich_text_safe(classification)}
                    if m_updates:
                        call_notion_with_retry(notion.pages.update, page_id=m_page["id"], properties=m_updates)
            except Exception as m_err:
                print(f"[Save Insight] Lỗi cập nhật Master DB: {m_err}")

        return jsonify({
            "success": True,
            "message": f"Đã lưu thành công {updated_count}/{len(insights)} Insight vào đúng trang Notion!",
            "updated_count": updated_count
        })
    except Exception as exc:
        return error_response(exc, 500)


@app.post("/api/shopee/insights/generate")
def api_generate_product_insights():
    try:
        global shopee_generation_active
        if shopee_generation_active:
            return jsonify({"success": False, "error": "Tiến trình tạo bài viết AI đang chạy, vui lòng đợi..."}), 400

        payload = request.json or {}
        page_id = payload.get("page_id", "").strip()
        if not page_id:
            return jsonify({"success": False, "error": "Thiếu thông tin page_id sản phẩm."}), 400

        shopee_generation_active = True
        add_event({"step": "shopee_sync", "message": f"Bắt đầu tiến trình sinh 5 Insight bằng AI cho sản phẩm..."})

        def run_generation_wrapper():
            global shopee_generation_active
            try:
                try:
                    from shopee_sync.src import insight_generator
                except ImportError:
                    from src import insight_generator

                def callback(msg):
                    add_event({"step": "shopee_sync", "message": f"[AI] {msg}"})

                insight_generator.generate_and_create_insights(page_id, progress_callback=callback)
                add_event({"step": "shopee_sync", "message": "🎉 Hoàn tất sinh bài viết thành công!"})
            except Exception as e:
                add_event({"step": "shopee_sync", "message": f"❌ Lỗi sinh bài viết AI: {str(e)}"})
            finally:
                shopee_generation_active = False

        t = threading.Thread(target=run_generation_wrapper, daemon=True)
        t.start()

        return jsonify({"success": True, "message": "Tiến trình sinh 5 Insight AI đã bắt đầu chạy ngầm."})
    except Exception as exc:
        return error_response(exc, 500)


@app.post("/api/shopee/sync/links")
def api_sync_shopee_links():
    try:
        global shopee_sync_thread, shopee_sync_active
        try:
            from shopee_sync.src import notion_sync
        except ImportError:
            from src import notion_sync

        if shopee_sync_active:
            return jsonify({"success": False, "error": "Tiến trình đồng bộ đang chạy ngầm, vui lòng đợi..."}), 400

        payload = request.json or {}
        drive_url = payload.get("drive_url", "").strip()
        page_id = payload.get("page_id", "").strip()
        if not page_id:
            return jsonify({"success": False, "error": "Thiếu sản phẩm cần đồng bộ link hình."}), 400

        shopee_sync_active = True
        add_event({"step": "shopee_sync", "message": "Khởi chạy tiến trình đồng bộ link hình lên Notion..."})

        def run_links_wrapper(override_url, selected_page_id):
            global shopee_sync_active
            try:
                updated = notion_sync.sync_only_image_links_to_notion(
                    override_drive_url=override_url,
                    target_page_id=selected_page_id,
                    replace_existing=True,
                )
                if not updated:
                    add_event({
                        "step": "shopee_sync",
                        "message": "Không có link hình nào cần cập nhật (Tất cả đã có hình hoặc không tìm thấy thư mục con)."
                    })
                else:
                    add_event({
                        "step": "shopee_sync",
                        "message": f"🎉 Đã cập nhật thành công link hình Drive cho {len(updated)} trang Insight Notion con!"
                    })
            except Exception as e:
                add_event({"step": "shopee_sync", "message": f"❌ Lỗi đồng bộ link hình: {str(e)}"})
            finally:
                shopee_sync_active = False

        shopee_sync_thread = threading.Thread(target=run_links_wrapper, args=(drive_url, page_id), daemon=True)
        shopee_sync_thread.start()

        return jsonify({"success": True, "message": "Tiến trình đồng bộ link hình Notion đã bắt đầu chạy ngầm."})
    except Exception as exc:
        return error_response(exc, 500)

@app.post("/api/shopee/sync/run")
def api_run_shopee_sync():
    try:
        global shopee_sync_thread, shopee_sync_active
        try:
            from shopee_sync.src import notion_sync
        except ImportError:
            from src import notion_sync

        if shopee_sync_active:
            return jsonify({"success": False, "error": "Tiến trình đồng bộ đang chạy ngầm, vui lòng đợi..."}), 400

        payload = request.json or {}
        drive_url = payload.get("drive_url", "").strip()
        page_id = payload.get("page_id", "").strip()
        if not page_id:
            return jsonify({"success": False, "error": "Thiếu sản phẩm cần đồng bộ. Vui lòng chọn lại sản phẩm."}), 400

        # Thư mục sản phẩm đang chọn phải thắng export_dir đã lưu từ lần chạy trước.
        config = load_config()
        export_dir = resolve_shopee_sync_export_dir(config, drive_url)

        os.environ["BIGSELLER_EXPORT_DIR"] = export_dir

        shopee_sync_active = True
        add_event({"step": "shopee_sync", "message": "Bắt đầu tiến trình đồng bộ Notion -> BigSeller thủ công..."})

        def run_sync_wrapper(override_url, selected_page_id):
            global shopee_sync_active
            try:
                excel_path, titles = notion_sync.sync_notion_to_bigseller_excel(
                    override_drive_url=override_url,
                    target_page_id=selected_page_id,
                )
                if not titles:
                    add_event({
                        "step": "shopee_sync",
                        "message": "Không tìm thấy sản phẩm mới nào cần đồng bộ (Bài viết = True và Trạng thái shopee = False)."
                    })
                else:
                    add_event({
                        "step": "shopee_sync",
                        "message": f"🎉 Đồng bộ thành công {len(titles)} sản phẩm! File đã xuất: {Path(excel_path).name}"
                    })
            except Exception as e:
                add_event({"step": "shopee_sync", "message": f"❌ Lỗi đồng bộ: {str(e)}"})
            finally:
                shopee_sync_active = False

        shopee_sync_thread = threading.Thread(target=run_sync_wrapper, args=(drive_url, page_id), daemon=True)
        shopee_sync_thread.start()

        return jsonify({"success": True, "message": "Tiến trình đồng bộ Notion đã bắt đầu chạy ngầm."})
    except Exception as exc:
        return error_response(exc, 500)


@app.get("/api/shopee/excel/list")
def api_list_shopee_excel():
    try:
        config = load_config()
        export_dir = config.get("openai", {}).get("export_dir", "").strip()
        if not export_dir:
            export_dir = str(Path.home() / "Downloads")

        out_dir = Path(export_dir) if export_dir else Path.home() / "Downloads"

        search_dirs = [out_dir, SHOPEE_SYNC_ROOT / "output"]
        try:
            prod_dir = selected_drive_folder()
            if prod_dir.is_dir():
                search_dirs.append(prod_dir)
        except Exception:
            pass

        seen_names = set()
        excel_files = []
        for s_dir in search_dirs:
            if s_dir.exists() and s_dir.is_dir():
                for f in s_dir.glob("bigseller_sync_*.xlsx"):
                    if f.name not in seen_names:
                        seen_names.add(f.name)
                        excel_files.append(f)

        try:
            d_root = validate_drive_root(drive_root())
            if d_root and d_root.exists():
                for f in d_root.rglob("bigseller_sync_*.xlsx"):
                    if f.name not in seen_names:
                        seen_names.add(f.name)
                        excel_files.append(f)
        except Exception:
            pass

        excel_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

        results = []
        for f in excel_files[:24]:
            results.append({
                "name": f.name,
                "file_path": str(f),
                "url": f"/api/automation/images/view?name={f.name}",
                "time": datetime.fromtimestamp(f.stat().st_mtime).strftime("%d/%m/%Y %H:%M:%S")
            })
        return jsonify(results)
    except Exception as exc:
        return error_response(exc, 400)


@app.post("/api/shopee/excel/delete")
def api_delete_shopee_excel():
    try:
        data = request.json or {}
        filename = data.get("name", "").strip()
        req_file_path = data.get("file_path", "").strip()
        if not filename and not req_file_path:
            return jsonify({"success": False, "error": "Thiếu tên file"}), 400

        target_name = filename or Path(req_file_path).name
        if not (target_name.startswith("bigseller_sync_") and target_name.endswith(".xlsx")):
            return jsonify({"success": False, "error": "Tên file không hợp lệ"}), 400

        deleted = False
        permission_error_file = None

        # 1. Xóa trực tiếp theo đường dẫn file_path nếu hợp lệ
        if req_file_path:
            p = Path(req_file_path)
            if p.exists() and p.name.startswith("bigseller_sync_") and p.name.endswith(".xlsx"):
                try:
                    p.unlink()
                    deleted = True
                except PermissionError:
                    permission_error_file = p.name
                except Exception as e:
                    print(f"[Excel Delete] Không xóa được file_path: {e}")

        # 2. Quét xóa ở out_dir, output_dir và selected_drive_folder
        config = load_config()
        export_dir = config.get("openai", {}).get("export_dir", "").strip()
        out_dir = Path(export_dir) if export_dir else Path.home() / "Downloads"

        search_dirs = [out_dir, SHOPEE_SYNC_ROOT / "output"]
        try:
            prod_dir = selected_drive_folder()
            if prod_dir.is_dir():
                search_dirs.append(prod_dir)
        except Exception:
            pass

        for s_dir in search_dirs:
            if s_dir.exists() and s_dir.is_dir():
                f_p = s_dir / target_name
                if f_p.exists():
                    try:
                        f_p.unlink()
                        deleted = True
                    except PermissionError:
                        permission_error_file = f_p.name
                    except Exception:
                        pass

        # 3. Quét xóa trong toàn bộ Drive root nếu có
        try:
            d_root = validate_drive_root(drive_root())
            if d_root and d_root.exists():
                for f in d_root.rglob(target_name):
                    try:
                        f.unlink()
                        deleted = True
                    except PermissionError:
                        permission_error_file = f.name
                    except Exception:
                        pass
        except Exception:
            pass

        if deleted:
            return jsonify({"success": True, "message": f"Đã xóa file {target_name}"})
        elif permission_error_file:
            return jsonify({"success": False, "error": f"File '{permission_error_file}' đang được mở bởi ứng dụng khác (ví dụ Microsoft Excel). Vui lòng đóng file Excel trước khi xóa."}), 400
        else:
            return jsonify({"success": True, "message": "File đã được xóa hoặc không tồn tại."})
    except Exception as exc:
        return error_response(exc, 500)


@app.post("/api/shopee/excel/delete-all")
def api_delete_all_shopee_excel():
    try:
        config = load_config()
        export_dir = config.get("openai", {}).get("export_dir", "").strip()
        out_dir = Path(export_dir) if export_dir else Path.home() / "Downloads"

        search_dirs = [out_dir, SHOPEE_SYNC_ROOT / "output"]
        try:
            prod_dir = selected_drive_folder()
            if prod_dir.is_dir():
                search_dirs.append(prod_dir)
        except Exception:
            pass

        deleted_count = 0
        seen_deleted = set()
        locked_files = []

        for s_dir in search_dirs:
            if s_dir.exists() and s_dir.is_dir():
                for f in s_dir.glob("bigseller_sync_*.xlsx"):
                    f_str = str(f.resolve())
                    if f_str not in seen_deleted:
                        try:
                            f.unlink()
                            deleted_count += 1
                            seen_deleted.add(f_str)
                        except PermissionError:
                            locked_files.append(f.name)
                        except Exception as e:
                            print(f"[Excel Delete All] Không xóa được file {f.name}: {e}")

        # Quét xóa tất cả bản sao trong Drive
        try:
            d_root = validate_drive_root(drive_root())
            if d_root and d_root.exists():
                for f in d_root.rglob("bigseller_sync_*.xlsx"):
                    f_str = str(f.resolve())
                    if f_str not in seen_deleted:
                        try:
                            f.unlink()
                            deleted_count += 1
                            seen_deleted.add(f_str)
                        except PermissionError:
                            locked_files.append(f.name)
                        except Exception as e:
                            print(f"[Excel Delete All] Không xóa được file {f.name} trên Drive: {e}")
        except Exception:
            pass

        msg = f"Đã xóa thành công {deleted_count} file Excel."
        if locked_files:
            unique_locked = list(set(locked_files))
            msg += f" Chú ý: Có {len(unique_locked)} file đang mở trong Microsoft Excel nên Windows không cho phép xóa ({', '.join(unique_locked)}). Vui lòng đóng Excel và bấm xóa lại."

        return jsonify({"success": True, "message": msg})
    except Exception as exc:
        return error_response(exc, 500)


@app.post("/api/shopee/download-image")
def api_shopee_download_image():
    try:
        data = request.json or {}
        url = data.get("url", "").strip()
        if not url:
            return jsonify({"success": False, "error": "Thiếu link ảnh"}), 400

        import re
        drive_match = re.search(r'drive\.google\.com/file/d/([a-zA-Z0-9_-]+)', url)
        if not drive_match:
            drive_match = re.search(r'id=([a-zA-Z0-9_-]+)', url)

        if drive_match:
            file_id = drive_match.group(1)
            url = f"https://drive.google.com/uc?export=download&id={file_id}"

        import requests
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        res = requests.get(url, headers=headers, timeout=15)
        if not res.ok:
            if "drive.google.com" in url:
                return jsonify({
                    "success": False,
                    "error": "Không tải được ảnh từ Google Drive. Hãy kiểm tra xem file đã được mở chia sẻ công khai (Bất kỳ ai có liên kết đều có thể xem) chưa."
                }), 400
            return jsonify({"success": False, "error": f"Tải ảnh thất bại. HTTP Status {res.status_code}"}), 400

        content_type = res.headers.get("Content-Type", "")
        if not content_type.startswith("image/"):
            if "text/html" in content_type and "drive.google.com" in url:
                return jsonify({
                    "success": False,
                    "error": "Google Drive trả về trang HTML thay vì ảnh. Có thể file quá nặng (yêu cầu quét virus) hoặc chưa được mở chia sẻ công khai ở chế độ 'Bất kỳ ai có liên kết'."
                }), 400
            return jsonify({"success": False, "error": f"Định dạng file tải về không phải là ảnh hợp lệ ({content_type})."}), 400

        import base64
        b64_data = base64.b64encode(res.content).decode("utf-8")
        mime = content_type or "image/png"

        return jsonify({
            "success": True,
            "base64": f"data:{mime};base64,{b64_data}",
            "mime": mime
        })
    except Exception as exc:
        return error_response(exc, 500)



# ==========================================
# NEW ENDPOINTS FOR SHOOPEE INSIGHTS TOOL
# ==========================================

def get_chrome_path():
    import os
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None

def ensure_gemini_chrome_running():
    import socket
    import subprocess
    import time
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.5)
    try:
        s.connect(("127.0.0.1", 9223))
        s.close()
        return True
    except Exception:
        try:
            chrome_path = get_chrome_path()
            if not chrome_path:
                return False
            user_data_dir = str(ROOT / "chrome_profile_debug_gemini")
            kill_processes_by_commandline("chrome.exe", "remote-debugging-port=9223")
            time.sleep(0.3)
            cmd = [
                chrome_path,
                "https://gemini.google.com",
                "--remote-debugging-port=9223",
                f"--user-data-dir={user_data_dir}"
            ]
            subprocess.Popen(cmd)
            time.sleep(4.0)
            return True
        except Exception:
            return False

def connect_gemini_playwright():
    from playwright.sync_api import sync_playwright
    import time
    p = sync_playwright().start()
    try:
        browser = p.chromium.connect_over_cdp("http://localhost:9223")
        context = browser.contexts[0]
        page = None
        for p_page in context.pages:
            if "gemini.google.com" in p_page.url:
                page = p_page
                break
        if not page:
            page = context.new_page()
            page.goto("https://gemini.google.com")
            page.wait_for_load_state("load")
        return p, browser, page
    except Exception as e:
        p.stop()
        raise e

def check_gemini_login_local():
    if not ensure_gemini_chrome_running():
        return False, "Không thể mở hoặc kết nối tới Chrome Debug Gemini (9223)."

    p = None
    browser = None
    try:
        p, browser, page = connect_gemini_playwright()
        url = page.url
        if "accounts.google.com" in url or "ServiceLogin" in url:
            return False, "Chưa đăng nhập Google."

        try:
            page.wait_for_selector('div[contenteditable="true"]', timeout=5000)
            return True, "Gemini đã sẵn sàng."
        except Exception:
            body_text = page.locator("body").inner_text()
            if any(x in body_text for x in ["Sign in", "Đăng nhập", "Log in", "Welcome to Gemini"]):
                return False, "Gemini chưa đăng nhập."
            return False, "Không nhận diện được trạng thái login."
    except Exception as e:
        return False, f"Lỗi: {str(e)}"
    finally:
        if browser:
            browser.close()
        if p:
            p.stop()

def attach_image_to_gemini_python(page, media_path):
    import time
    upload_triggered = False
    for selector in ['input[type="file"]', 'input[accept*="image"]', 'input[accept*="png"]']:
        try:
            input_el = page.query_selector(selector)
            if input_el:
                input_el.set_input_files(media_path)
                upload_triggered = True
                break
        except Exception:
            pass

    if not upload_triggered:
        try:
            attach_btn_js = """() => {
                const getEditor = () => {
                    const editors = Array.from(document.querySelectorAll('div[contenteditable="true"]')).filter(el => {
                        const rect = el.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                    });
                    return editors[editors.length - 1] || document.querySelector('div[contenteditable="true"]');
                };
                const editor = getEditor();
                if (!editor) return null;
                const directSelectors = [
                    'button[aria-label*="tải lên" i]',
                    'button[aria-label*="upload" i]',
                    'button[aria-label*="công cụ" i]',
                    'gem-icon-button[arialabel*="tải lên" i] button',
                    'gem-icon-button[arialabel*="upload" i] button',
                    'button:has(mat-icon[fonticon="plus"])',
                    'button:has(mat-icon[data-mat-icon-name="plus"])'
                ];
                for (const sel of directSelectors) {
                    const btn = document.querySelector(sel);
                    if (btn) {
                        const r = btn.getBoundingClientRect();
                        if (r.width > 0 && r.height > 0) return btn;
                    }
                }
                return null;
            }"""
            attach_btn = page.evaluate_handle(attach_btn_js)
            if attach_btn and attach_btn.as_element():
                attach_btn.as_element().click()
                time.sleep(2.0)

                menu_item_js = """() => {
                    const exactTargets = ['tệp', 'file', 'files', 'upload', 'tải tệp lên', 'tải tệp', 'upload from computer'];
                    const partialTargets = ['hình ảnh', 'images', 'ảnh', 'photos', 'tải ảnh'];
                    const elements = Array.from(document.querySelectorAll('*')).filter(el => {
                        const rect = el.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                    });

                    // 1. Ưu tiên so khớp chính xác trước (như nút Tệp ở hàng trên)
                    for (const el of elements) {
                        const text = (el.innerText || el.textContent || '').trim().toLowerCase();
                        const ariaLabel = (el.getAttribute('aria-label') || el.getAttribute('title') || '').trim().toLowerCase();
                        if (exactTargets.some(t => text === t || ariaLabel === t)) {
                            return el;
                        }
                    }

                    // 2. So khớp chứa nhưng loại bỏ các nút tính năng tạo ảnh/video AI của Gemini
                    for (const el of elements) {
                        const text = (el.innerText || el.textContent || '').trim().toLowerCase();
                        const ariaLabel = (el.getAttribute('aria-label') || el.getAttribute('title') || '').trim().toLowerCase();
                        if (text.includes('tạo và') || text.includes('chỉnh sửa') || text.includes('hiện thực hóa') || text.includes('ý tưởng')) {
                            continue;
                        }
                        if (exactTargets.some(t => text.includes(t) || ariaLabel.includes(t))) {
                            return el;
                        }
                        if (partialTargets.some(t => text.includes(t) || ariaLabel.includes(t))) {
                            return el;
                        }
                    }
                    return null;
                }"""
                menu_item = page.evaluate_handle(menu_item_js)
                if menu_item and menu_item.as_element():
                    with page.expect_file_chooser(timeout=8000) as fc_info:
                        menu_item.as_element().click(no_wait_after=True)
                    file_chooser = fc_info.value
                    file_chooser.set_files(media_path)
                    upload_triggered = True
        except Exception:
            pass

    if not upload_triggered:
        try:
            inputs = page.query_selector_all('input[type="file"]')
            if inputs:
                inputs[-1].set_input_files(media_path)
                upload_triggered = True
        except Exception:
            pass

    if upload_triggered:
        send_selectors = [
            'button.send-button',
            'button[aria-label="Gửi tin nhắn"]',
            'button[aria-label="Send message"]',
            'div.send-button-container button'
        ]
        upload_success = False
        for _ in range(30):
            time.sleep(1.0)
            for sel in send_selectors:
                try:
                    btn = page.query_selector(sel)
                    if btn and btn.is_enabled():
                        upload_success = True
                        break
                except Exception:
                    pass
            if upload_success:
                time.sleep(2.0)
                break
        return upload_success
    return False

def build_seo_insight_prompt(product_name_hint, keywords_hint, use_cases_hint, insight_prompt):
    prompt_editor_section = ""
    if insight_prompt and insight_prompt.strip():
        prompt_editor_section = f"\n\nYêu cầu người dùng muốn AI bám theo:\n{insight_prompt.strip()}\n\nLưu ý: phần yêu cầu trên chỉ được dùng để chỉnh văn văn phong/góc bán hàng, không được làm sai JSON và không được đổi số lượng/field insight.\n"

    return f"""
Bạn đang hỗ trợ phân tích catalog nội bộ cho sản phẩm Shopee.
Hãy đọc ảnh sản phẩm đã được đính kèm trong cuộc trò chuyện và tạo nội dung bán hàng thực tế.

Ngữ cảnh người dùng đã nhập:
- Tên sản phẩm gợi ý: {product_name_hint or "Không có"}
- Keyword gợi ý: {keywords_hint or "Không có"}
- Công dụng / ghi chú: {use_cases_hint or "Không có"}
{prompt_editor_section}

Yêu cầu phân tích:
1. Trích xuất tên sản phẩm rõ nhất từ bao bì.
2. Tóm tắt chữ nổi bật nhìn thấy trên bao bì.
3. Suy luận công dụng chính ngắn gọn, thực tế.
4. Gợi ý từ khóa chính, ngăn cách bằng dấu phẩy.
5. Tạo đúng 5 insight bán hàng Shopee.

Quy chuẩn cho 5 insight:
- angle là góc bán hàng ngắn gọn, súc tích (ví dụ: Ngăn ngừa côn trùng cho gia đình).
- postTitle là tiêu đề SEO, tối đa 100 ký tự.
- postTitle phải nhét càng nhiều từ khóa liên quan càng tốt nhưng vẫn tự nhiên, dễ đọc.
- Ưu tiên đưa tên sản phẩm, hoạt chất/thành phần, công dụng, vấn đề khách hàng và đối tượng dùng vào postTitle khi phù hợp.
- insightContent phải bám đúng tiêu đề tương ứng, giải thích rõ góc bán hàng của tiêu đề đó.
- insightContent viết 1-2 câu, thực tế, không hoa mỹ, không nói quá.
- keywords là cụm từ khóa chính cho insight đó, ngăn cách bằng dấu phẩy, không viết thành câu dài.
- 5 insight phải khác góc nhau, tránh lặp ý.

Chỉ trả về đúng khối JSON nằm giữa hai marker sau, không thêm giải thích:
BEGIN_CONTEXT_JSON
{{
  "productName": "",
  "visibleText": "",
  "guessedUseCase": "",
  "suggestedKeywords": "",
  "insights": [
    {{
      "angle": "",
      "postTitle": "",
      "insightContent": "",
      "keywords": ""
    }},
    {{
      "angle": "",
      "postTitle": "",
      "insightContent": "",
      "keywords": ""
    }},
    {{
      "angle": "",
      "postTitle": "",
      "insightContent": "",
      "keywords": ""
    }},
    {{
      "angle": "",
      "postTitle": "",
      "insightContent": "",
      "keywords": ""
    }},
    {{
      "angle": "",
      "postTitle": "",
      "insightContent": "",
      "keywords": ""
    }}
  ]
}}
END_CONTEXT_JSON
""".strip()

def build_rewrite_insight_prompt(product_name, visible_text, guessed_use_case, suggested_keywords, current_insight, reviewer_comment):
    return f"""
Bạn đang chỉnh lại 1 insight Shopee theo comment của người dùng.
Hãy bóc insight hiện tại ra, xác định điểm chưa chuẩn theo comment, rồi viết lại đúng 1 insight mới tốt hơn.

Thông tin sản phẩm:
- Tên sản phẩm: {product_name or "Không rõ"}
- Chữ nhìn thấy trên bao bì: {visible_text or "Không có"}
- Công dụng suy luận: {guessed_use_case or "Không có"}
- Từ khóa gợi ý: {suggested_keywords or "Không có"}

Insight hiện tại:
- angle: {current_insight.get("angle", "")}
- postTitle: {current_insight.get("postTitle", "")}
- insightContent: {current_insight.get("insightContent", "")}
- keywords: {current_insight.get("keywords", "")}

Comment cần sửa:
{reviewer_comment or "Làm lại insight này cho rõ, đúng SEO và sát sản phẩm hơn."}

Quy chuẩn insight mới:
- angle là góc bán hàng ngắn gọn, súc tích (ví dụ: Ngăn ngừa côn trùng cho gia đình).
- postTitle là tiêu đề SEO, tối đa 100 ký tự.
- postTitle phải nhét nhiều từ khóa liên quan nhất có thể nhưng vẫn tự nhiên.
- insightContent phải bám đúng tiêu đề mới, giải thích rõ góc bán hàng của tiêu đề đó.
- keywords là cụm từ khóa chính, ngăn cách bằng dấu phẩy.
- Không thêm cảnh báo y tế thừa, không nói quá, không dùng văn phong hoa mỹ.

Chỉ trả về đúng khối JSON nằm giữa hai marker sau, không thêm giải thích:
BEGIN_CONTEXT_JSON
{{
  "insight": {{
    "angle": "",
    "postTitle": "",
    "insightContent": "",
    "keywords": ""
  }}
}}
END_CONTEXT_JSON
""".strip()

def parse_gemini_json_block(text):
    import json
    import re
    start_marker = "BEGIN_CONTEXT_JSON"
    end_marker = "END_CONTEXT_JSON"

    start_idx = text.rfind(start_marker)
    if start_idx == -1:
        # Nếu không thấy marker, thử tìm dấu ngoặc { đầu tiên của JSON
        start_idx = text.find("{")
        if start_idx == -1:
            return None
        json_str = text[start_idx:]
    else:
        json_str = text[start_idx + len(start_marker):].strip()

    # Cắt đến end_marker nếu có
    end_idx = json_str.find(end_marker)
    if end_idx != -1:
        json_str = json_str[:end_idx].strip()
    else:
        # Nếu không có end_marker, tự động cắt đến dấu } cuối cùng
        last_brace = json_str.rfind("}")
        if last_brace != -1:
            json_str = json_str[:last_brace + 1].strip()

    # Làm sạch markdown code block if any
    if json_str.startswith("```"):
        lines = json_str.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        json_str = "\n".join(lines).strip()

    try:
        res = json.loads(json_str)
        if isinstance(res, list) and len(res) > 0:
            res = res[0]
        return res
    except Exception as e:
        print(f"Lỗi parse JSON trong parse_gemini_json_block: {e}")
        return None

def check_insight_valid(item):
    if not isinstance(item, dict):
        return False

    def safe_strip(val):
        if val is None:
            return ""
        return str(val).strip()

    angle = safe_strip(item.get("angle") or item.get("GocViet") or item.get("gocViet"))
    title = safe_strip(item.get("postTitle") or item.get("title") or item.get("tieuDe"))
    content = safe_strip(item.get("insightContent") or item.get("content") or item.get("noiDung"))

    if angle and title and content:
        return True
    return False

def wait_for_json_response(page, expected_ends, mode="analyze", timeout=150):
    import time
    start_time = time.time()

    print(f"[Wait Gemini] Bắt đầu đợi phản hồi JSON (mode={mode}, timeout={timeout}s)...")
    time.sleep(3.0) # Đợi 3 giây đầu tiên để Gemini bắt đầu xử lý

    last_text = ""
    try:
        last_text = page.evaluate("() => document.body.innerText")
    except Exception:
        pass

    stable_count = 0
    while time.time() - start_time < timeout:
        time.sleep(2.0)
        try:
            current_text = page.evaluate("() => document.body.innerText")

            # 1. Thử parse và kiểm tra tính hợp lệ của JSON block hiện tại
            parsed = parse_gemini_json_block(current_text)
            if parsed:
                if mode == "analyze":
                    if "insights" in parsed and isinstance(parsed["insights"], list):
                        valid_list = [item for item in parsed["insights"] if check_insight_valid(item)]
                        if len(valid_list) == 5:
                            print("[Wait Gemini] Đã nhận được đủ 5 insight hợp lệ từ Gemini!")
                            return parsed
                elif mode == "rewrite":
                    if "insight" in parsed and check_insight_valid(parsed["insight"]):
                        print("[Wait Gemini] Đã nhận được insight viết lại hợp lệ từ Gemini!")
                        return parsed

            # 2. Nếu chưa có JSON hợp lệ, kiểm tra xem text có đang thay đổi (Gemini đang viết) hay không
            if len(current_text) > len(last_text) or current_text != last_text:
                last_text = current_text
                stable_count = 0
                print(f"[Wait Gemini] Gemini đang viết... (Độ dài text hiện tại: {len(current_text)})")
            else:
                stable_count += 1
                print(f"[Wait Gemini] Văn bản không thay đổi ({stable_count}/10)...")

                # Nếu văn bản hoàn toàn không thay đổi trong 10 lần kiểm tra liên tiếp (20 giây đứng hình)
                # và vẫn không có JSON hợp lệ, ta coi như Gemini đã viết xong nhưng không sinh được JSON hợp lệ hoặc lỗi
                if stable_count >= 10:
                    print("[Wait Gemini] Gemini đứng hình quá lâu và không có JSON hợp lệ. Kết thúc chờ.")
                    break
        except Exception as e:
            print(f"[Wait Gemini] Lỗi trong vòng lặp chờ: {e}")

    print("[Wait Gemini] Hết thời gian chờ hoặc không lấy được JSON insight hợp lệ từ Gemini.")
    return None

def send_prompt_to_gemini(page, prompt_text):
    import time
    composer_selector = 'div[contenteditable="true"]'
    page.wait_for_selector(composer_selector, timeout=10000)
    page.click(composer_selector)
    try:
        page.evaluate("""(text) => {
            const getEditor = () => {
                const editors = Array.from(document.querySelectorAll('div[contenteditable="true"]')).filter(el => {
                    const rect = el.getBoundingClientRect();
                    return rect.width > 0 && rect.height > 0;
                });
                return editors[editors.length - 1] || document.querySelector('div[contenteditable="true"]');
            };
            const editor = getEditor();
            if (editor) {
                editor.focus();
                editor.innerText = text;
                editor.dispatchEvent(new Event('input', { bubbles: true }));
            }
        }""", prompt_text)
        time.sleep(0.5)
        page.keyboard.press("Space")
        page.keyboard.press("Backspace")
    except Exception:
        page.fill(composer_selector, prompt_text)

    time.sleep(1.0)

    send_selectors = [
        'button.send-button',
        'button[aria-label="Gửi tin nhắn"]',
        'button[aria-label="Send message"]',
        'div.send-button-container button',
        'button:has(svg path[d*="M2 "])'
    ]
    clicked = False
    for sel in send_selectors:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_enabled():
                btn.click()
                clicked = True
                break
        except Exception:
            pass

    if not clicked:
        page.click(composer_selector)
        page.keyboard.press("Enter")

# Flask routes definitions

@app.post("/api/check-gemini-login")
def api_check_gemini_login_shopee():
    try:
        ok, message = check_gemini_login_local()
        return jsonify({"loggedIn": ok, "message": message})
    except Exception as exc:
        return error_response(exc, 500)

@app.post("/api/analyze-product")
def api_analyze_product_shopee():
    import tempfile
    import os
    try:
        product_name = request.form.get("productName", "").strip()
        price = request.form.get("productPrice", "").strip()
        variants = request.form.get("productVariants", "").strip()
        classification = request.form.get("productClassification", "").strip()
        keywords = request.form.get("keywords", "").strip()
        use_cases = request.form.get("useCases", "").strip()
        insight_prompt = request.form.get("insightPrompt", "").strip()

        image_file = request.files.get("image")
        if not image_file:
            return jsonify({"error": "Hãy paste hoặc chọn ảnh sản phẩm trước khi phân tích."}), 400

        temp_dir = tempfile.mkdtemp()
        temp_img_path = os.path.join(temp_dir, image_file.filename or "product_image.png")
        image_file.save(temp_img_path)

        if not ensure_gemini_chrome_running():
            return jsonify({"error": "Không thể kết nối hoặc khởi chạy Chrome Gemini."}), 500

        p = None
        browser = None
        try:
            p, browser, page = connect_gemini_playwright()
            attached = attach_image_to_gemini_python(page, temp_img_path)
            if not attached:
                return jsonify({"error": "Không đính kèm được ảnh lên Gemini. Vui lòng thử lại."}), 500

            import time
            time.sleep(1.5) # Chờ DOM ổn định để đếm chính xác số khối JSON cũ trên trang
            body_text_before = page.evaluate("() => document.body.innerText")
            expected_ends = body_text_before.count("END_CONTEXT_JSON") + 1

            prompt_text = build_seo_insight_prompt(product_name, keywords, use_cases, insight_prompt)
            send_prompt_to_gemini(page, prompt_text)

            result = wait_for_json_response(page, expected_ends, mode="analyze", timeout=150)

            # Ghi log debug
            import json
            os.makedirs("logs", exist_ok=True)
            with open("logs/debug_analyze.log", "w", encoding="utf-8") as debug_f:
                debug_f.write("--- LOG DEBUG PHAN TICH ANH ---\n")
                debug_f.write(f"Product Name Input: {product_name}\n")
                if result:
                    debug_f.write(f"Parsed JSON from Gemini:\n{json.dumps(result, ensure_ascii=False, indent=2)}\n")
                else:
                    debug_f.write("wait_for_json_response returned None (Timeout or Parse Error)\n")

            if not result:
                return jsonify({"error": "Gemini chưa trả về JSON insight hoàn chỉnh. Vui lòng kiểm tra tab Chrome và thử lại."}), 500

            response_data = {
                "productName": product_name or result.get("productName", ""),
                "visionContext": {
                    "visibleText": result.get("visibleText", ""),
                    "guessedUseCase": result.get("guessedUseCase", ""),
                    "suggestedKeywords": result.get("suggestedKeywords", "")
                },
                "insights": result.get("insights", [])
            }

            with open("logs/debug_analyze.log", "a", encoding="utf-8") as debug_f:
                debug_f.write(f"Response Data to Frontend:\n{json.dumps(response_data, ensure_ascii=False, indent=2)}\n")

            return jsonify(response_data)
        except Exception as exc:
            return jsonify({"error": f"Lỗi tự động hóa Gemini: {str(exc)}"}), 500
        finally:
            if browser:
                browser.close()
            if p:
                p.stop()
            try:
                if os.path.exists(temp_img_path):
                    os.remove(temp_img_path)
                if os.path.exists(temp_dir):
                    os.rmdir(temp_dir)
            except Exception:
                pass
    except Exception as exc:
        return error_response(exc, 500)

@app.post("/api/sync-gemini-result")
def api_sync_gemini_result_shopee():
    try:
        if not ensure_gemini_chrome_running():
            return jsonify({"error": "Không thể kết nối hoặc khởi chạy Chrome Gemini."}), 500

        p = None
        browser = None
        try:
            p, browser, page = connect_gemini_playwright()
            body_text = page.evaluate("() => document.body.innerText")
            parsed = parse_gemini_json_block(body_text)

            if not parsed:
                return jsonify({"error": "Không tìm thấy khối JSON insight nào (BEGIN_CONTEXT_JSON ... END_CONTEXT_JSON) trên trang Gemini. Vui lòng đảm bảo Gemini đã viết xong."}), 404

            # Nhận diện xem là kết quả phân tích 5 insight hay viết lại single insight
            if "insights" in parsed:
                return jsonify({
                    "type": "analyze",
                    "data": {
                        "productName": parsed.get("productName", ""),
                        "visionContext": {
                            "visibleText": parsed.get("visibleText", ""),
                            "guessedUseCase": parsed.get("guessedUseCase", ""),
                            "suggestedKeywords": parsed.get("suggestedKeywords", "")
                        },
                        "insights": parsed.get("insights", [])
                    }
                })
            elif "insight" in parsed:
                return jsonify({
                    "type": "rewrite",
                    "data": {
                        "insight": parsed.get("insight", {})
                    }
                })
            else:
                return jsonify({"error": "Tìm thấy khối JSON nhưng không đúng cấu trúc insights hoặc insight đơn lẻ."}), 400

        except Exception as exc:
            return jsonify({"error": f"Lỗi đồng bộ Playwright: {str(exc)}"}), 500
        finally:
            if browser:
                browser.close()
            if p:
                p.stop()
    except Exception as exc:
        return error_response(exc, 500)

@app.post("/api/rewrite-insight")
def api_rewrite_insight_shopee():
    try:
        payload = request.json or {}
        product_name = payload.get("productName", "")
        vision_context = payload.get("visionContext", {})
        insight = payload.get("insight", {})
        comment = payload.get("comment", "")

        if not insight or not comment.strip():
            return jsonify({"error": "Thiếu insight hoặc nội dung comment sửa."}), 400

        if not ensure_gemini_chrome_running():
            return jsonify({"error": "Không thể kết nối hoặc khởi chạy Chrome Gemini."}), 500

        p = None
        browser = None
        try:
            p, browser, page = connect_gemini_playwright()
            import time
            time.sleep(1.5) # Chờ DOM ổn định
            body_text_before = page.evaluate("() => document.body.innerText")
            expected_ends = body_text_before.count("END_CONTEXT_JSON") + 1

            prompt_text = build_rewrite_insight_prompt(
                product_name,
                vision_context.get("visibleText", ""),
                vision_context.get("guessedUseCase", ""),
                vision_context.get("suggestedKeywords", ""),
                insight,
                comment
            )
            send_prompt_to_gemini(page, prompt_text)

            result = wait_for_json_response(page, expected_ends, mode="rewrite", timeout=120)
            if not result or "insight" not in result:
                return jsonify({"error": "Gemini chưa viết lại xong insight hoặc trả về sai cấu trúc."}), 500

            return jsonify({"insight": result["insight"]})
        except Exception as exc:
            return jsonify({"error": f"Lỗi viết lại insight: {str(exc)}"}), 500
        finally:
            if browser:
                browser.close()
            if p:
                p.stop()
    except Exception as exc:
        return error_response(exc, 500)

@app.get("/api/shopee/product/details")
def api_get_product_details():
    try:
        page_id = request.args.get("page_id", "").strip()
        if not page_id:
            return jsonify({"error": "Thiếu page_id"}), 400

        env_file = SHOPEE_SYNC_ROOT / ".env"
        from dotenv import load_dotenv
        if env_file.exists():
            load_dotenv(env_file, override=True)

        config = load_config()
        notion_token = config.get("notion", {}).get("token", "").strip() or os.getenv("NOTION_TOKEN", "").strip()
        if not notion_token:
            return jsonify({"error": "Chưa cấu hình NOTION_TOKEN"}), 400

        from notion_client import Client
        notion = Client(auth=notion_token)
        try:
            from shopee_sync.src.notion_sync import call_notion_with_retry, get_rich_text_content, fetch_insight_page_content, find_local_product_folder
            from shopee_sync.src import convert_zicum
        except ImportError:
            from src.notion_sync import call_notion_with_retry, get_rich_text_content, fetch_insight_page_content, find_local_product_folder
            import convert_zicum

        page = call_notion_with_retry(notion.pages.retrieve, page_id=page_id)
        properties = page.get("properties", {})

        # Kiểm tra xem page này thuộc DB1 (Shopee - Xử lý sản phẩm đăng) hay DB2 (Shopee Insight Library)
        is_from_product_db = ("Insight Library" in properties) or ("Giá biến thể 1" in properties)
        
        rel_insights = []
        master_page = None
        master_title = ""
        price = ""
        classification = ""
        variants = ""
        master_info = {}
        drive_url = properties.get("Media sản phẩm", {}).get("url") or properties.get("URL", {}).get("url") or ""
        note = "".join([t.get("plain_text", "") for t in properties.get("Ghi chú", {}).get("rich_text", [])]).strip()
        st_sel = properties.get("Trạng thái", {}).get("select") or {}
        notion_status = st_sel.get("name", "").strip() if isinstance(st_sel, dict) else ""

        if is_from_product_db:
            # 1. Page từ DB Xử lý sản phẩm đăng: Lấy trực tiếp thông tin giá, biến thể
            title_list = properties.get("Tên sản phẩm", {}).get("title", [])
            title = title_list[0].get("plain_text", "").strip() if title_list else ""
            if not title:
                for pv in properties.values():
                    if pv.get("type") == "title":
                        tl = pv.get("title", [])
                        if tl:
                            title = tl[0].get("plain_text", "").strip()
                        break

            master_title = title
            p1 = properties.get("Giá biến thể 1", {}).get("number")
            v1 = "".join([t.get("plain_text", "") for t in properties.get("Biến thể 1", {}).get("rich_text", [])]).strip()
            p2 = properties.get("Giá biến thể 2", {}).get("number")
            v2 = "".join([t.get("plain_text", "") for t in properties.get("Biến thể 2", {}).get("rich_text", [])]).strip()

            classification = v1 or "Mặc định"
            price = f"{int(p1):,}đ" if p1 else ""
            var_lines = []
            if v1 and p1:
                var_lines.append(f"{v1}: {int(p1):,}đ")
            if v2 and p2:
                var_lines.append(f"{v2}: {int(p2):,}đ")
            variants = "\n".join(var_lines) if var_lines else (f"{int(p1):,}đ" if p1 else "")

            master_info = {
                "id": page_id,
                "title": master_title,
                "variant_1": v1,
                "price_1": p1,
                "variant_2": v2,
                "price_2": p2,
                "status": notion_status,
                "note": note
            }

            # Trỏ đúng sang Insight Library để lấy danh sách insight con
            rel_lib = properties.get("Insight Library", {}).get("relation", [])
            lib_title = ""
            if rel_lib:
                lib_id = rel_lib[0].get("id")
                try:
                    lib_page = call_notion_with_retry(notion.pages.retrieve, page_id=lib_id)
                    lib_props = lib_page.get("properties", {})
                    lt_list = lib_props.get("Tên post Shopee", {}).get("title", [])
                    lib_title = lt_list[0].get("plain_text", "").strip() if lt_list else ""
                    rel_insights = lib_props.get("Danh sách Insight", {}).get("relation", [])
                except Exception as lib_err:
                    print(f"[Product Details] Lỗi truy vấn Insight Library {lib_id}: {lib_err}")
        else:
            # 2. Fallback: Page từ Insight Library
            title_list = properties.get("Tên post Shopee", {}).get("title", []) or properties.get("Tên sản phẩm", {}).get("title", [])
            title = title_list[0].get("plain_text", "").strip() if title_list else ""
            lib_title = title
            rel_insights = properties.get("Danh sách Insight", {}).get("relation", [])

            master_db_id = "ca055a7742824b9598abde7a7686d144"
            try:
                db_meta = call_notion_with_retry(notion.databases.retrieve, database_id=master_db_id)
                ds = db_meta.get("data_sources", [])
                q_target = ds[0]["id"] if ds else master_db_id
                
                res_m = call_notion_with_retry(
                    notion.data_sources.query if ds else notion.databases.query,
                    **{"data_source_id" if ds else "database_id": q_target, "filter": {"property": "Insight Library", "relation": {"contains": page_id}}}
                )
                if res_m.get("results"):
                    master_page = res_m["results"][0]

                if not master_page:
                    res_all = call_notion_with_retry(
                        notion.data_sources.query if ds else notion.databases.query,
                        **{"data_source_id" if ds else "database_id": q_target, "page_size": 50}
                    )
                    clean_t = convert_zicum.clean_name(title)
                    for mp in res_all.get("results", []):
                        mp_title = "".join([t.get("plain_text", "") for t in mp.get("properties", {}).get("Tên sản phẩm", {}).get("title", [])])
                        clean_mp = convert_zicum.clean_name(mp_title)
                        if clean_t and (clean_t in clean_mp or clean_mp in clean_t):
                            master_page = mp
                            break
            except Exception as m_err:
                print(f"[Product Details] Lỗi truy vấn Master DB: {m_err}")

            if master_page:
                mp_props = master_page.get("properties", {})
                master_title = "".join([t.get("plain_text", "") for t in mp_props.get("Tên sản phẩm", {}).get("title", [])]).strip()
                v1 = "".join([t.get("plain_text", "") for t in mp_props.get("Biến thể 1", {}).get("rich_text", [])]).strip()
                p1 = mp_props.get("Giá biến thể 1", {}).get("number")
                v2 = "".join([t.get("plain_text", "") for t in mp_props.get("Biến thể 2", {}).get("rich_text", [])]).strip()
                p2 = mp_props.get("Giá biến thể 2", {}).get("number")

                classification = v1 or "Mặc định"
                price = f"{int(p1):,}đ" if p1 else ""
                var_lines = []
                if v1 and p1:
                    var_lines.append(f"{v1}: {int(p1):,}đ")
                if v2 and p2:
                    var_lines.append(f"{v2}: {int(p2):,}đ")
                variants = "\n".join(var_lines) if var_lines else (f"{int(p1):,}đ" if p1 else "")

                m_status_sel = (mp_props.get("Trạng thái") or {}).get("select") or {}
                master_info = {
                    "id": master_page.get("id"),
                    "title": master_title,
                    "variant_1": v1,
                    "price_1": p1,
                    "variant_2": v2,
                    "price_2": p2,
                    "status": m_status_sel.get("name", "") if isinstance(m_status_sel, dict) else ""
                }

        # 2. Tìm thư mục cục bộ của sản phẩm trên Drive
        matched_folder_name = ""
        matched_folder_path = ""
        matched_shop = ""
        try:
            root = validate_drive_root(drive_root())
            if root and root.exists():
                matched_folder = find_local_product_folder(root, title)
                if not matched_folder and master_title:
                    matched_folder = find_local_product_folder(root, master_title)
                if not matched_folder and lib_title:
                    matched_folder = find_local_product_folder(root, lib_title)
                if matched_folder:
                    matched_folder_name = matched_folder.name
                    matched_folder_path = str(matched_folder)
                    try:
                        rel = matched_folder.relative_to(root)
                        if len(rel.parts) > 1:
                            matched_shop = rel.parts[0]
                    except Exception:
                        pass
        except Exception as e:
            print(f"[Product Details] Lỗi tìm thư mục local: {e}")

        # 3. Lấy danh sách các Insight con và nội dung chuẩn bị sẵn
        insights_data = []
        for idx, rel in enumerate(rel_insights):
            c_id = rel.get("id")
            try:
                c_title, c_desc, c_link = fetch_insight_page_content(notion, c_id)
                c_page = call_notion_with_retry(notion.pages.retrieve, page_id=c_id)
                c_props = c_page.get("properties", {})

                angle = ""
                for k, v in c_props.items():
                    if k.lower() == "angle":
                        angle = _notion_property_text(v)
                        break

                keywords = ""
                for k, v in c_props.items():
                    if "từ khóa" in k.lower() or "keyword" in k.lower():
                        keywords = _notion_property_text(v)
                        break

                order_val = c_props.get("Thứ tự", {}).get("number") or (idx + 1)
                clean_folder = re.sub(r'[\\/*?:"<>|]', '-', c_title).strip()
                clean_folder = re.sub(r'-+', '-', clean_folder).strip()

                # Kiểm tra ảnh trong thư mục con này nếu đã có thư mục local
                image_files = []
                if matched_folder_path:
                    ins_dir = Path(matched_folder_path) / clean_folder
                    if not ins_dir.exists():
                        clean_t_ins = convert_zicum.clean_name(clean_folder)
                        for sub_d in Path(matched_folder_path).iterdir():
                            if not sub_d.is_dir():
                                continue
                            sub_d_clean = convert_zicum.clean_name(sub_d.name)
                            if (clean_t_ins and (sub_d_clean == clean_t_ins or clean_t_ins in sub_d_clean or sub_d_clean in clean_t_ins)) or \
                               (clean_folder.lower() in sub_d.name.lower() or sub_d.name.lower() in clean_folder.lower()):
                                ins_dir = sub_d
                                break
                    if ins_dir.exists() and ins_dir.is_dir():
                        from urllib.parse import quote
                        for f in ins_dir.iterdir():
                            if f.is_file() and f.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp", ".mp4"]:
                                image_files.append({
                                    "name": f.name,
                                    "url": f"/api/automation/images/view?name={f.name}&export_dir={quote(str(ins_dir))}",
                                    "file_path": str(f),
                                    "is_video": f.suffix.lower() == ".mp4"
                                })
                        image_files.sort(key=lambda x: x["name"])

                insights_data.append({
                    "id": c_id,
                    "order": order_val,
                    "title": c_title,
                    "folder_name": clean_folder,
                    "angle": angle,
                    "keywords": keywords,
                    "description": c_desc,
                    "drive_url": c_link or (c_props.get("Link Drive bộ ảnh", {}).get("url") or ""),
                    "image_count": len(image_files),
                    "images": image_files
                })
            except Exception as c_err:
                print(f"[Product Details] Lỗi đọc insight con {c_id}: {c_err}")

        insights_data.sort(key=lambda x: x["order"])

        return jsonify({
            "id": page_id,
            "title": title,
            "master_title": master_title or title,
            "price": price,
            "classification": classification,
            "variants": variants,
            "drive_url": drive_url,
            "shop": matched_shop,
            "selected_folder": matched_folder_name,
            "selected_folder_path": matched_folder_path,
            "master": master_info,
            "notion_status": notion_status,
            "note": note,
            "insights": insights_data
        })
    except Exception as exc:
        return error_response(exc, 500)

def compact_product_description(description, max_sentences=3, max_words=70):
    """Giữ mô tả Shopee ngắn gọn, không lặp lại các mục chi tiết phía dưới."""
    if isinstance(description, list):
        description = " ".join(str(item) for item in description if item)

    text = re.sub(r"\s+", " ", str(description or "")).strip()
    if not text:
        return ""

    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]
    selected = []
    word_count = 0
    for sentence in sentences[:max_sentences]:
        sentence_words = sentence.split()
        if selected and word_count + len(sentence_words) > max_words:
            break
        selected.append(sentence)
        word_count += len(sentence_words)

    compact = " ".join(selected) if selected else text
    words = compact.split()
    if len(words) > max_words:
        compact = " ".join(words[:max_words]).rstrip(",;:-") + "."
    return compact


DEFAULT_POST_PROMPT_ID = "default-shopee-post-prompt"
DEFAULT_POST_PROMPT_CONTENT = """Bạn là Dược sĩ / Chuyên viên tư vấn da liễu và copywriter bán hàng cho Khai Hoàn Skincare / Khai Hoàn Derma.

Hãy viết bài giới thiệu sản phẩm Shopee tự nhiên, chân thật, thuyết phục, giàu tính cá nhân hóa theo từng Angle và Insight. Mỗi bài cần có cách mở đầu, ngôn từ và hoạt cảnh sử dụng khác nhau; tránh thay tên sản phẩm vào cùng một khuôn câu.

YÊU CẦU GIỌNG VĂN:
- Đi thẳng vào sản phẩm, lợi ích nổi bật và trải nghiệm sử dụng thực tế.
- Viết như đang tư vấn tận tâm cho đúng nhóm khách hàng của sản phẩm.
- Không dùng văn phong máy móc hoặc các cụm từ: "đáp ứng nỗi đau của khách hàng", "chuẩn SEO Shopee", "vượt trội hàng đầu", "lựa chọn hoàn hảo".
- Phần description viết một đoạn ngắn 2 - 3 câu, khoảng 45 - 65 từ; không lặp lại thành phần, công dụng, đối tượng, cách dùng hoặc lưu ý ở các mục bên dưới.
- Xác định đúng đối tượng theo bản chất sản phẩm; không mặc định độ tuổi hoặc tình trạng da khi dữ liệu không cung cấp.
- Tạo 8 - 12 hashtag người mua thực tế có thể tìm kiếm, gồm tên sản phẩm, loại sản phẩm/công dụng và thương hiệu Khai Hoàn; không dùng #ShopeeSEO hoặc hashtag vô nghĩa.

Có thể dùng các biến sau trong prompt tùy chỉnh:
{{product_name}}, {{classification}}, {{product_description}}, {{post_title}}, {{angle}}, {{insight_content}}, {{keywords}}."""


def render_post_prompt_template(template, **values):
    rendered = str(template or DEFAULT_POST_PROMPT_CONTENT)
    for key, value in values.items():
        rendered = rendered.replace("{{" + key + "}}", str(value or ""))
    return rendered.strip()


def generate_single_post_body(api_key, product_name, angle, post_title, insight_content, keywords, product_desc="", classification="", custom_prompt=""):
    import requests
    import json
    import re
    import unicodedata

    # Tạo hashtag tên sản phẩm viết liền không dấu
    clean_tag = unicodedata.normalize('NFKD', product_name).encode('ascii', 'ignore').decode('utf-8')
    clean_tag = re.sub(r'[^a-zA-Z0-9]', '', clean_tag).lower()

    prompt_instructions = render_post_prompt_template(
        custom_prompt or DEFAULT_POST_PROMPT_CONTENT,
        product_name=product_name,
        classification=classification,
        product_description=product_desc,
        post_title=post_title,
        angle=angle,
        insight_content=insight_content,
        keywords=keywords,
    )

    prompt = f"""{prompt_instructions}

THÔNG TIN SẢN PHẨM:
- Tên sản phẩm: "{product_name}"
- Phân loại / Quy cách: "{classification}"
- Thông tin / Ghi chú bán hàng từ shop: "{product_desc}"
- Tiêu đề bài đăng Shopee: "{post_title}"
- Góc tiếp cận / Khía cạnh nổi bật (Angle): "{angle}"
- Tóm tắt điểm nhấn cốt lõi (Insight): "{insight_content}"
- Từ khóa quan trọng: "{keywords}"

GUARDRAIL BẮT BUỘC CỦA HỆ THỐNG:
- Không dùng từ khẳng định chữa bệnh: "đặc trị", "trị mụn", "điều trị", "dứt điểm", "chữa khỏi", "thuốc". Ưu tiên "hỗ trợ", "giúp", "chăm sóc", "cải thiện".
- Không dùng claim nói quá như "100%", "tốt nhất", "số 1", "cam kết", "vĩnh viễn" và không tự bịa thành phần, công dụng, độ tuổi hoặc phản hồi khách hàng.
- Bài hoàn chỉnh có thể dài khoảng 350 - 500 từ, nhưng từng mục phải rõ ràng, dễ đọc và bám sát dữ liệu được cung cấp.
- Dù prompt mẫu yêu cầu cách thể hiện nào, kết quả cuối cùng vẫn phải trả đúng JSON bên dưới để tool ghi Notion an toàn.

BẮT BUỘC TRẢ VỀ JSON DUY NHẤT VỚI CẤU TRÚC:
{{
  "description": "Một đoạn duy nhất gồm 2 - 3 câu, 45 - 65 từ: giới thiệu sản phẩm, lợi ích chính đúng Angle/Insight và chỉ thêm quy cách/độ tiện dụng nếu cần; không lặp nội dung các mục bên dưới.",
  "ingredients": [
    "Tên thành phần 1: giải thích công dụng cụ thể...",
    "Tên thành phần 2: giải thích công dụng cụ thể..."
  ],
  "benefits": [
    "Công dụng nổi bật 1 (viết câu sinh động, tự nhiên)...",
    "Công dụng nổi bật 2...",
    "Công dụng nổi bật 3..."
  ],
  "target_users": [
    "Đối tượng phù hợp 1 (sát với loại da/vấn đề của sản phẩm)...",
    "Đối tượng phù hợp 2..."
  ],
  "usage": "Hướng dẫn sử dụng chi tiết từng bước: 1. Làm sạch... 2. Thoa một lượng vừa đủ... 3. Tần suất...",
  "notes": [
    "Lưu ý sử dụng an toàn 1 (VD: chỉ chấm nốt mụn, tránh vùng mắt)...",
    "Bảo quản nơi khô ráo thoáng mát, tránh ánh nắng trực tiếp..."
  ],
  "hashtags": "#{clean_tag} #congdung1 #congdung2 #khaihoanskincare #khaihoanderma #myphamchinhhang"
}}
"""
    is_openai = api_key and api_key.startswith("sk-")
    try:
        raw_text = ""
        if is_openai:
            url = "https://api.openai.com/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "response_format": {"type": "json_object"}
            }
            res = requests.post(url, headers=headers, json=payload, timeout=60)
            if res.status_code == 200:
                raw_text = res.json()["choices"][0]["message"]["content"]
        else:
            # Mặc định sử dụng Gemini 3.7 Flash và các dòng Flash thế hệ mới
            for g_model in ["gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{g_model}:generateContent?key={api_key}"
                headers = {"Content-Type": "application/json"}
                payload = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "response_mime_type": "application/json"
                    }
                }
                res = requests.post(url, headers=headers, json=payload, timeout=60)
                if res.status_code == 200:
                    raw_text = res.json()["candidates"][0]["content"]["parts"][0]["text"]
                    break

        parsed_json = None
        if raw_text:
            cleaned = re.sub(r'```(?:json)?', '', raw_text, flags=re.IGNORECASE).strip()
            json_match = re.search(r'\{.*\}', cleaned, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                try:
                    parsed_json = json.loads(json_str)
                except Exception:
                    try:
                        fixed_str = re.sub(r'(?<!\\)\n', r'\\n', json_str)
                        fixed_str = re.sub(r'(?<!\\)\r', r'\\r', fixed_str)
                        fixed_str = re.sub(r'(?<!\\)\t', r'\\t', fixed_str)
                        parsed_json = json.loads(fixed_str)
                    except Exception:
                        pass

        if isinstance(parsed_json, dict):
            desc = parsed_json.get("description", "")
            if not custom_prompt or custom_prompt.strip() == DEFAULT_POST_PROMPT_CONTENT.strip():
                desc = compact_product_description(desc)
            ing = parsed_json.get("ingredients", [])
            ben = parsed_json.get("benefits", [])
            tar = parsed_json.get("target_users", [])
            usg = parsed_json.get("usage", "")
            nts = parsed_json.get("notes", [])
            hash_tags = parsed_json.get("hashtags", "")

            if desc and ing and ben and tar and usg:
                return {
                    "description": desc,
                    "ingredients": ing,
                    "benefits": ben,
                    "target_users": tar,
                    "usage": usg,
                    "notes": nts if nts else ["Bảo quản nơi khô ráo thoáng mát, tránh ánh nắng trực tiếp."],
                    "hashtags": hash_tags if hash_tags else f"#{clean_tag} #khaihoanskincare #khaihoanderma #myphamchinhhang"
                }
    except Exception as e:
        print(f"[AI Post Gen] Lỗi khi gọi AI tạo bài viết: {e}")

    # Bộ sinh nội dung thông minh tự nhiên (Smart Dynamic Fallback khi offline / lỗi API key)
    is_acne = any(k in (product_name + ' ' + keywords + ' ' + insight_content + ' ' + angle).lower() for k in ['mụn', 'mun', 'clinoper', 'clascon', 'aldocont', 'adapalene', 'benzoyl', 'clindamycin', 'zicum'])
    
    if is_acne:
        desc = f"{product_name} là sản phẩm hỗ trợ chăm sóc vùng da có mụn sưng đỏ và bít tắc. Công thức chấm trực tiếp giúp làm dịu vùng da mụn, hỗ trợ gom cồi và chăm sóc tập trung tại vị trí cần thiết."
        ing = [
            f"Hoạt chất chăm sóc cốt lõi trong {product_name}: Hỗ trợ kháng khuẩn, làm dịu vùng da mụn và gom cồi nhanh chóng.",
            "Các dưỡng chất bổ trợ lành tính: Giúp duy trì độ ẩm tự nhiên, củng cố hàng rào bảo vệ da khỏe mạnh."
        ]
        ben = [
            f"Hỗ trợ làm dịu nhanh tình trạng sưng đỏ, căng tức tại các nốt mụn theo góc {angle}.",
            "Hỗ trợ gom cồi mụn, giúp quá trình làm sạch mụn diễn ra nhẹ nhàng và tự nhiên.",
            "Kiểm soát bã nhờn, làm thông thoáng bề mặt da và hạn chế hình thành thâm sẹo sau mụn."
        ]
        target = [
            "Người có làn da đang bị mụn sưng đỏ, mụn bọc, mụn viêm hoặc mụn ẩn dai dẳng.",
            "Người có làn da dầu mụn, lỗ chân lông bít tắc cần giải pháp chấm mụn hiệu quả và êm dịu."
        ]
        usage = "1. Rửa sạch mặt với sữa rửa mặt dịu nhẹ và thấm khô bằng khăn mềm.\n2. Lấy một lượng gel/kem vừa đủ chấm trực tiếp lên các nốt mụn cần chăm sóc (không thoa toàn mặt).\n3. Sử dụng đều đặn 1 - 2 lần mỗi ngày (sáng và tối) để đạt hiệu quả tối ưu."
        notes = [
            "Chỉ sử dụng chấm nốt mụn ngoài da, tránh tiếp xúc trực tiếp với mắt, môi và niêm mạc.",
            "Bảo quản nơi khô ráo, thoáng mát, tránh ánh nắng trực tiếp và nhiệt độ cao."
        ]
        hashtags = f"#{clean_tag} #gelchammun #giammunviem #gomcoimun #chamsocdamun #khaihoanskincare #khaihoanderma #myphamchinhhang"
    else:
        desc = f"{product_name} là sản phẩm hỗ trợ chăm sóc hằng ngày theo thông tin được cung cấp. Công thức và quy cách sản phẩm hướng đến trải nghiệm sử dụng gọn nhẹ, thuận tiện theo đúng hướng dẫn trên bao bì."
        ing = [f"Thành phần chính của {product_name}: Cung cấp dưỡng chất thiết yếu giúp chăm sóc và bảo vệ hiệu quả."]
        ben = [
            f"Hỗ trợ cải thiện rõ rệt theo nhu cầu {angle}.",
            "Mang lại cảm giác dễ chịu, an toàn và duy trì trạng thái khỏe mạnh cho làn da."
        ]
        target = [
            "Người có nhu cầu chăm sóc và phục hồi chuyên sâu theo đúng tính năng sản phẩm.",
            "Phù hợp cho cả nam và nữ muốn tìm kiếm sản phẩm chính hãng, chất lượng."
        ]
        usage = "1. Làm sạch vùng da cần chăm sóc.\n2. Lấy lượng sản phẩm vừa đủ thoa đều và vỗ nhẹ để dưỡng chất thẩm thấu.\n3. Sử dụng 1 - 2 lần mỗi ngày."
        notes = ["Bảo quản nơi khô ráo, tránh ánh nắng trực tiếp.", "Đậy kín nắp sau khi sử dụng."]
        hashtags = f"#{clean_tag} #khaihoanskincare #khaihoanderma #myphamchinhhang #chamsocda"

    return {
        "description": desc,
        "ingredients": ing,
        "benefits": ben,
        "target_users": target,
        "usage": usage,
        "notes": notes,
        "hashtags": hashtags
    }


@app.post("/api/insight/generate-all-posts")
def api_generate_all_posts():
    try:
        from dotenv import load_dotenv
        load_dotenv(SHOPEE_SYNC_ROOT / ".env")
        api_key = os.getenv("GEMINI_API_KEY", "").strip() or os.getenv("OPENAI_API_KEY", "").strip()
        
        data = request.json or {}
        product_name = data.get("productName", "").strip()
        product_desc = data.get("productDescription", "").strip()
        classification = data.get("classification", "").strip()
        insights = data.get("insights", [])
        writing_prompt = str(data.get("writingPrompt", "")).strip()
        force_regenerate = bool(data.get("forceRegenerate", False))
        
        full_posts = []
        for idx, item in enumerate(insights):
            if not force_regenerate and item.get("full_post") and isinstance(item.get("full_post"), dict):
                full_posts.append(item.get("full_post"))
                continue
                
            angle = item.get("angle", f"Insight {idx+1}")
            post_title = item.get("postTitle", f"{product_name} - Insight {idx+1}")
            insight_content = item.get("insightContent", "")
            keywords = item.get("keywords", "")
            
            post_body = generate_single_post_body(
                api_key,
                product_name,
                angle,
                post_title,
                insight_content,
                keywords,
                product_desc=product_desc,
                classification=classification,
                custom_prompt=writing_prompt,
            )
            full_posts.append(post_body)
            
        return jsonify({"success": True, "full_posts": full_posts})
    except Exception as exc:
        return error_response(exc, 500)


@app.post("/api/insight/generate-single-post")
def api_generate_single_post():
    try:
        from dotenv import load_dotenv
        load_dotenv(SHOPEE_SYNC_ROOT / ".env")
        api_key = os.getenv("GEMINI_API_KEY", "").strip() or os.getenv("OPENAI_API_KEY", "").strip()
        
        data = request.json or {}
        product_name = data.get("productName", "").strip()
        product_desc = data.get("productDescription", "").strip()
        classification = data.get("classification", "").strip()
        angle = data.get("angle", "").strip()
        post_title = data.get("postTitle", "").strip()
        insight_content = data.get("insightContent", "").strip()
        keywords = data.get("keywords", "").strip()
        writing_prompt = str(data.get("writingPrompt", "")).strip()
        
        post_body = generate_single_post_body(
            api_key,
            product_name,
            angle,
            post_title,
            insight_content,
            keywords,
            product_desc=product_desc,
            classification=classification,
            custom_prompt=writing_prompt,
        )
        return jsonify({"success": True, "full_post": post_body})
    except Exception as exc:
        return error_response(exc, 500)


@app.post("/api/review-save")
def api_review_save_shopee():
    from dotenv import load_dotenv
    import os
    try:
        payload = request.json or {}
        product_data = payload.get("product", {})
        product_name = payload.get("productName", "") or product_data.get("name", "")
        insights = payload.get("insights", [])
        writing_prompt = str(payload.get("writingPrompt", "")).strip()
        force_regenerate = bool(payload.get("forceRegenerate", False))
        product_page_id = product_data.get("productPageId", "").strip()

        # Tự động xuất file insights_data.json vào đúng thư mục sản phẩm để tab AI Edit/Video có thể quét được
        try:
            root = validate_drive_root(drive_root())
            product_folder = None
            
            if root and root.exists():
                try:
                    from shopee_sync.src import convert_zicum
                except ImportError:
                    from src import convert_zicum
                    
                target_clean = convert_zicum.clean_name(product_name)
                for item in root.iterdir():
                    if item.is_dir() and convert_zicum.clean_name(item.name) == target_clean:
                        product_folder = item
                        break
                        
                # Nếu chưa có thư mục nào khớp, tự động tạo mới thư mục đúng theo tên sản phẩm
                if not product_folder:
                    product_folder = root / product_name
                    product_folder.mkdir(parents=True, exist_ok=True)
                    
            if product_folder and product_folder.exists() and product_folder.is_dir():
                json_path = product_folder / "insights_data.json"
                insights_save_data = {
                    "productName": product_name,
                    "productDescription": product_data.get("description", ""),
                    "insights": insights
                }
                json_path.write_text(json.dumps(insights_save_data, indent=2, ensure_ascii=False), encoding="utf-8")
                print(f"[Notion Save] Đã lưu thành công insights_data.json tại: {json_path}")
                
                # Cập nhật selected_drive_folder trong config.json sang đúng sản phẩm này
                try:
                    cfg = load_config()
                    if "paths" not in cfg:
                        cfg["paths"] = {}
                    cfg["paths"]["selected_drive_folder"] = product_folder.name
                    save_config(cfg)
                except Exception as cf_err:
                    print(f"[Notion Save] Lỗi cập nhật config selected_drive_folder: {cf_err}")
        except Exception as e:
            print(f"[Notion Save] Lỗi ghi file insights_data.json: {e}")

        if not insights or len(insights) == 0:
            return jsonify({"error": "Thiếu danh sách insights."}), 400

        load_dotenv(SHOPEE_SYNC_ROOT / ".env")
        notion_token = os.getenv("NOTION_TOKEN", "").strip()
        api_key = os.getenv("GEMINI_API_KEY", "").strip() or os.getenv("OPENAI_API_KEY", "").strip()

        if not notion_token:
            return jsonify({"error": "Chưa cấu hình NOTION_TOKEN trong file .env."}), 400
        if not api_key:
            return jsonify({"error": "Chưa cấu hình GEMINI_API_KEY (hoặc OpenAI key) để AI viết bài."}), 400

        from notion_client import Client
        notion = Client(auth=notion_token)
        insight_database_id = "88159c90-46fb-426d-b3c9-a0d79358e76c"

        saved_product_page_id = product_page_id

        variant_lines = [x.strip() for x in product_data.get("variants", "").split("\n") if x.strip()]
        variant_price_text = ""
        parts = []
        if product_data.get("price"):
            parts.append(f"Giá sản phẩm: {product_data['price']}")
        if product_data.get("classification"):
            parts.append(f"Phân loại: {product_data['classification']}")
        if product_data.get("variants"):
            parts.append(f"Biến thể / giá:\n{product_data['variants']}")
        variant_price_text = "\n".join(parts)

        classification_options = [x.strip() for x in product_data.get("classification", "").split(",") if x.strip()]

        product_props_to_save = {
            "Tên sản phẩm": {"title": [{"text": {"content": product_name}}]}
        }
        if variant_price_text:
            product_props_to_save["Biến thể & giá"] = {"rich_text": [{"text": {"content": variant_price_text}}]}
        if classification_options:
            product_props_to_save["Biến thể"] = {"multi_select": [{"name": x} for x in classification_options]}

        parent_db_id = os.getenv("NOTION_DATABASE_ID", "").strip() or "ca055a7742824b9598abde7a7686d144"
        if not parent_db_id:
            return jsonify({"error": "Chưa cấu hình NOTION_DATABASE_ID sản phẩm."}), 400

        from shopee_sync.src.notion_sync import call_notion_with_retry
        saved_product_page_id = None

        # 1. Kiểm tra product_page_id được truyền lên xem có đúng là trang của product_name không
        if product_page_id:
            try:
                chk_page = call_notion_with_retry(notion.pages.retrieve, page_id=product_page_id)
                chk_props = chk_page.get("properties", {})
                chk_title_list = chk_props.get("Tên sản phẩm", {}).get("title", [])
                chk_title = chk_title_list[0].get("plain_text", "").strip() if chk_title_list else ""
                if chk_title and chk_title.lower() == product_name.lower():
                    saved_product_page_id = product_page_id
                else:
                    print(f"[Notion Save] productPageId {product_page_id} có tiêu đề '{chk_title}' không khớp với tên '{product_name}'. Sẽ tìm hoặc tạo trang mới.")
            except Exception as e:
                print(f"[Notion Save] Không thể kiểm tra page_id {product_page_id}: {e}")

        # 2. Nếu chưa xác định được page_id, tìm kiếm trong database Notion theo tên sản phẩm chính xác
        if not saved_product_page_id:
            try:
                db_meta = call_notion_with_retry(notion.databases.retrieve, database_id=parent_db_id)
                data_sources = db_meta.get("data_sources", [])
                if data_sources:
                    ds_id = data_sources[0].get("id")
                    query_res = call_notion_with_retry(notion.data_sources.query, data_source_id=ds_id)
                    for rec in query_res.get("results", []):
                        r_props = rec.get("properties", {})
                        r_title_list = r_props.get("Tên sản phẩm", {}).get("title", [])
                        r_title = r_title_list[0].get("plain_text", "").strip() if r_title_list else ""
                        if r_title and r_title.lower() == product_name.lower():
                            saved_product_page_id = rec.get("id")
                            print(f"[Notion Save] Tìm thấy trang sẵn có cho sản phẩm '{product_name}': {saved_product_page_id}")
                            break
            except Exception as q_err:
                print(f"[Notion Save] Lỗi khi tìm kiếm trang sản phẩm trong database: {q_err}")

        # 3. Nếu vẫn chưa có trang nào, tạo mới trang sản phẩm
        if not saved_product_page_id:
            try:
                from shopee_sync.src.notion_sync import create_notion_page_safe
            except ImportError:
                from src.notion_sync import create_notion_page_safe

            product_page = create_notion_page_safe(
                notion,
                parent_db_id,
                product_props_to_save
            )
            saved_product_page_id = product_page["id"]
        else:
            # Cập nhật thông tin biến thể & giá cho trang sản phẩm sẵn có
            if variant_price_text or classification_options:
                try:
                    from shopee_sync.src.notion_sync import update_notion_page_safe
                except ImportError:
                    from src.notion_sync import update_notion_page_safe

                try:
                    update_notion_page_safe(
                        notion,
                        page_id=saved_product_page_id,
                        properties=product_props_to_save
                    )
                except Exception as e:
                    print(f"[Notion Update Product] Lỗi khi cập nhật biến thể sản phẩm: {e}")

        created_pages_info = []

        from shopee_sync.src.notion_sync import call_notion_with_retry

        # Lấy driveUrl từ dữ liệu frontend truyền lên hoặc từ trang sản phẩm Notion
        drive_url = product_data.get("driveUrl", "").strip()
        if not drive_url and saved_product_page_id:
            try:
                product_page = notion.pages.retrieve(page_id=saved_product_page_id)
                drive_url = product_page.get("properties", {}).get("Media sản phẩm", {}).get("url", "") or ""
            except Exception:
                pass

        # Phân tích product_folder_id và lấy các thư mục con của nó trên Drive
        product_folder_id = None
        if drive_url and '/folders/' in drive_url:
            folder_match = re.search(r'/folders/([a-zA-Z0-9_-]+)', drive_url)
            if folder_match:
                product_folder_id = folder_match.group(1)

        # Nếu chưa trích xuất được ID từ URL (do dán đường dẫn local hoặc chưa chọn), tự tìm thư mục sản phẩm trên Drive
        if not product_folder_id:
            try:
                from shopee_sync.src import convert_zicum
            except ImportError:
                from src import convert_zicum
            
            root_folder_id = os.getenv("DRIVE_ROOT_FOLDER_ID", "").strip() or "1XrOmOCqdZ3xfkeVaBc0Vr77Q7yRW0PxZ"
            product_folder_id = convert_zicum.find_product_folder(root_folder_id, product_name)

        subfolders = {}
        if product_folder_id:
            try:
                from shopee_sync.src import convert_zicum
            except ImportError:
                from src import convert_zicum
            try:
                subfolders = convert_zicum.get_subfolders_of_drive_folder(product_folder_id)
                print(f"[Notion Save] Đã lấy {len(subfolders)} thư mục con cho product_folder_id={product_folder_id}")
            except Exception as e:
                print(f"[Notion Save] Lỗi khi cào thư mục con từ Drive: {e}")

        for idx, item in enumerate(insights):
            order_num = idx + 1
            angle = item.get("angle", "").strip() or f"Insight {order_num}"
            post_title = item.get("postTitle", f"{product_name} - Insight {order_num}")
            insight_content = item.get("insightContent", "")
            keywords = item.get("keywords", "")

            # Tìm link hình cho Insight con này
            insight_drive_url = None
            if subfolders:
                try:
                    from shopee_sync.src import convert_zicum
                except ImportError:
                    from src import convert_zicum
                
                clean_angle = convert_zicum.clean_name(angle)
                clean_folder_name = convert_zicum.clean_name(f"Insight {order_num}")
                
                target_folder_id = None
                if clean_angle in subfolders:
                    target_folder_id = subfolders[clean_angle]
                elif clean_folder_name in subfolders:
                    target_folder_id = subfolders[clean_folder_name]
                else:
                    for sf_name, sf_id in subfolders.items():
                        if clean_folder_name in sf_name or sf_name in clean_folder_name or clean_angle in sf_name or sf_name in clean_angle:
                            target_folder_id = sf_id
                            break
                if target_folder_id:
                    insight_drive_url = f"https://drive.google.com/drive/folders/{target_folder_id}"

            # Fallback về link thư mục sản phẩm chính trên Drive nếu chưa khớp thư mục con
            if not insight_drive_url and product_folder_id:
                insight_drive_url = f"https://drive.google.com/drive/folders/{product_folder_id}"

            # 1. Lấy bài viết chi tiết đã được xem/sửa (hoặc tự động sinh nếu chưa có)
            if not force_regenerate and item.get("full_post") and isinstance(item.get("full_post"), dict):
                body = item.get("full_post")
            else:
                product_desc = product_data.get("description", "") or product_data.get("note", "") or ""
                classification = product_data.get("classification", "") or ""
                body = generate_single_post_body(
                    api_key, 
                    product_name, 
                    angle, 
                    post_title, 
                    insight_content, 
                    keywords,
                    product_desc=product_desc,
                    classification=classification,
                    custom_prompt=writing_prompt,
                )

            # 2. Tạo trang con Notion
            page_properties = {
                "Tên post Shopee": {"title": [{"text": {"content": post_title}}]},
                "Angle": {"rich_text": [{"text": {"content": angle}}]},
                "Insight": {"rich_text": [{"text": {"content": insight_content}}]},
                "Từ khóa chính cho insight": {"rich_text": [{"text": {"content": keywords}}]},
                "Thứ tự": {"number": order_num},
                "Sản phẩm Shopee": {"relation": [{"id": saved_product_page_id}]},
                "Trạng thái duyệt": {"select": {"name": "Chờ duyệt"}},
                "Trạng thái tạo hình": {"select": {"name": "Chờ tạo hình"}},
                "Format": {"select": {"name": "Shopee Post"}}
            }
            if insight_drive_url:
                page_properties["Link hình"] = {"url": insight_drive_url}

            try:
                from shopee_sync.src.notion_sync import create_notion_page_safe
            except ImportError:
                from src.notion_sync import create_notion_page_safe

            new_insight_page = create_notion_page_safe(
                notion,
                insight_database_id,
                page_properties
            )
            new_page_id = new_insight_page["id"]
            created_pages_info.append({
                "page_id": new_page_id,
                "angle": angle
            })

            # 3. Soạn nội dung các block bài viết chi tiết an toàn cho Notion API
            def build_rich_text_safe(text_val):
                if not text_val:
                    return [{"type": "text", "text": {"content": "Chưa có thông tin"}}]
                s = str(text_val).strip()
                if not s:
                    return [{"type": "text", "text": {"content": "Chưa có thông tin"}}]
                chunks = [s[i:i+1900] for i in range(0, len(s), 1900)]
                return [{"type": "text", "text": {"content": c}} for c in chunks]

            blocks = []
            if post_title:
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {"rich_text": build_rich_text_safe(post_title)}
                })
            
            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {"rich_text": [{"type": "text", "text": {"content": "Mô tả sản phẩm"}}]}
            })

            desc_text = body.get("description", "")
            if isinstance(desc_text, list):
                desc_text = "\n\n".join([str(x) for x in desc_text])
            
            for paragraph_str in str(desc_text).split("\n\n"):
                if paragraph_str.strip():
                    blocks.append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {"rich_text": build_rich_text_safe(paragraph_str.strip())}
                    })

            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {"rich_text": [{"type": "text", "text": {"content": "Thành phần nổi bật"}}]}
            })

            ingredients = body.get("ingredients", [])
            if isinstance(ingredients, str):
                ingredients = [x.strip() for x in ingredients.split("\n") if x.strip()]
            for ing in ingredients:
                if str(ing).strip():
                    blocks.append({
                        "object": "block",
                        "type": "bulleted_list_item",
                        "bulleted_list_item": {"rich_text": build_rich_text_safe(str(ing).strip())}
                    })

            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {"rich_text": [{"type": "text", "text": {"content": "Công dung hỗ trợ"}}]}
            })
            benefits = body.get("benefits", [])
            if isinstance(benefits, str):
                benefits = [x.strip() for x in benefits.split("\n") if x.strip()]
            for ben in benefits:
                if str(ben).strip():
                    blocks.append({
                        "object": "block",
                        "type": "bulleted_list_item",
                        "bulleted_list_item": {"rich_text": build_rich_text_safe(str(ben).strip())}
                    })

            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {"rich_text": [{"type": "text", "text": {"content": "Đối tượng sử dụng"}}]}
            })
            target_users = body.get("target_users", [])
            if isinstance(target_users, str):
                target_users = [x.strip() for x in target_users.split("\n") if x.strip()]
            for target in target_users:
                if str(target).strip():
                    blocks.append({
                        "object": "block",
                        "type": "bulleted_list_item",
                        "bulleted_list_item": {"rich_text": build_rich_text_safe(str(target).strip())}
                    })

            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {"rich_text": [{"type": "text", "text": {"content": "Cách dùng"}}]}
            })
            usage_text = body.get("usage", "")
            if isinstance(usage_text, list):
                usage_text = "\n".join([str(x) for x in usage_text])
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": build_rich_text_safe(str(usage_text).strip())}
            })

            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {"rich_text": [{"type": "text", "text": {"content": "Lưu ý"}}]}
            })
            notes = body.get("notes", [])
            if isinstance(notes, str):
                notes = [x.strip() for x in notes.split("\n") if x.strip()]
            for note in notes:
                if str(note).strip():
                    blocks.append({
                        "object": "block",
                        "type": "bulleted_list_item",
                        "bulleted_list_item": {"rich_text": build_rich_text_safe(str(note).strip())}
                    })

            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {"rich_text": [{"type": "text", "text": {"content": "Hashtag"}}]}
            })
            hashtags_text = body.get("hashtags", "")
            if isinstance(hashtags_text, list):
                hashtags_text = " ".join([str(x) for x in hashtags_text])
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": build_rich_text_safe(str(hashtags_text).strip())}
            })

            # Gửi từng batch 10 blocks để tránh lỗi payload hoặc quá số ký tự Notion API
            for chunk_idx in range(0, len(blocks), 10):
                batch = blocks[chunk_idx:chunk_idx + 10]
                try:
                    call_notion_with_retry(
                        notion.blocks.children.append,
                        block_id=new_page_id,
                        children=batch
                    )
                except Exception as b_err:
                    print(f"[Notion Block Append] Lỗi khi thêm batch block Notion: {b_err}")

        # 4. Cập nhật thuộc tính Insight Library của trang sản phẩm cha
        rich_text_list = []
        for idx, created_item in enumerate(created_pages_info):
            rich_text_list.append({
                "type": "text",
                "text": {"content": f"{idx+1}. {created_item['angle']}: "}
            })
            rich_text_list.append({
                "type": "mention",
                "mention": {
                    "type": "page",
                    "page": {"id": created_item["page_id"]}
                }
            })
            if idx < len(created_pages_info) - 1:
                rich_text_list.append({
                    "type": "text",
                    "text": {"content": "\n"}
                })

        try:
            from shopee_sync.src.notion_sync import update_notion_page_safe
        except ImportError:
            from src.notion_sync import update_notion_page_safe

        update_notion_page_safe(
            notion,
            page_id=saved_product_page_id,
            properties={
                "Insight Library": {"rich_text": rich_text_list},
                "Bài viết": {"checkbox": True},
                "Content xong": {"checkbox": False},
                "Trạng thái xử lý": {"select": {"name": "Content đang làm"}}
            }
        )

        return jsonify({
            "productPageId": saved_product_page_id,
            "createdInsightIds": [p["page_id"] for p in created_pages_info]
        })
    except Exception as exc:
        return error_response(exc, 500)


def _notion_property_text(prop: dict) -> str:
    """Đọc text từ property title/rich_text mà không phụ thuộc tên cột."""
    if not isinstance(prop, dict):
        return ""
    prop_type = prop.get("type", "")
    items = prop.get(prop_type, []) if prop_type in {"title", "rich_text"} else []
    return "".join(str(item.get("plain_text", "")) for item in items).strip()


def _notion_page_mentions(prop: dict) -> list[str]:
    if not isinstance(prop, dict):
        return []
    prop_type = prop.get("type", "")
    items = prop.get(prop_type, []) if prop_type in {"title", "rich_text"} else []
    page_ids = []
    for item in items:
        mention = item.get("mention", {}) if isinstance(item, dict) else {}
        if mention.get("type") == "page":
            page_id = str(mention.get("page", {}).get("id", "")).strip()
            if page_id:
                page_ids.append(page_id)
    return page_ids


def _normalized_product_name(value: str) -> str:
    import unicodedata

    normalized = unicodedata.normalize("NFKD", str(value or ""))
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii").lower()
    return " ".join(re.findall(r"[a-z0-9]+", ascii_text))


def _product_name_match_score(folder_name: str, product_name: str) -> float:
    folder_clean = _normalized_product_name(folder_name)
    product_clean = _normalized_product_name(product_name)
    if not folder_clean or not product_clean:
        return 0.0
    if folder_clean == product_clean:
        return 10.0
    if folder_clean in product_clean or product_clean in folder_clean:
        return 8.0 + min(len(folder_clean), len(product_clean)) / max(len(folder_clean), len(product_clean))

    folder_tokens = set(folder_clean.split())
    product_tokens = set(product_clean.split())
    overlap = len(folder_tokens & product_tokens)
    if not overlap:
        return 0.0
    return overlap / max(len(folder_tokens), 1)


def load_notion_insights_for_product(product_hint: str, shop_hint: str = "") -> list[dict]:
    """Lấy danh sách Insight trực tiếp từ Notion (Shopee Insight Library hoặc Product DB) khớp tên sản phẩm/thư mục."""
    from dotenv import load_dotenv

    load_dotenv(SHOPEE_SYNC_ROOT / ".env")
    config = load_config()
    notion_token = str(config.get("notion", {}).get("token", "")).strip() or os.getenv("NOTION_TOKEN", "").strip()
    if not notion_token:
        return []

    from notion_client import Client
    from shopee_sync.src.notion_sync import call_notion_with_retry
    from shopee_sync.src import convert_zicum

    notion = Client(auth=notion_token)

    # 1. Ưu tiên tìm trong Shopee Insight Library của shop tương ứng
    target_shop = shop_hint.strip() or selected_shop_name()
    ins_ds_id = get_notion_insight_ds_for_shop(notion, target_shop)
    try:
        ins_res = call_notion_with_retry(notion.data_sources.query, data_source_id=ins_ds_id, page_size=100)
        best_match_page = None
        best_score = 0.0
        best_title = ""
        for p in ins_res.get("results", []):
            p_props = p.get("properties", {})
            p_title = _notion_property_text(p_props.get("Tên post Shopee", {}))
            if not p_title:
                for pv in p_props.values():
                    if pv.get("type") == "title":
                        tl = pv.get("title", [])
                        if tl:
                            p_title = tl[0].get("plain_text", "").strip()
                        break
            score = _product_name_match_score(product_hint, p_title)
            if score > best_score:
                best_score = score
                best_match_page = p
                best_title = p_title

        if best_match_page and best_score >= 0.6:
            rel_insights = best_match_page.get("properties", {}).get("Danh sách Insight", {}).get("relation", [])
            if rel_insights:
                insights = []
                for m_idx, rel in enumerate(rel_insights):
                    c_id = rel.get("id")
                    try:
                        c_page = call_notion_with_retry(notion.pages.retrieve, page_id=c_id)
                        c_props = c_page.get("properties", {})
                        order_num = c_props.get("Thứ tự", {}).get("number")
                        try:
                            order_num = int(order_num)
                        except (TypeError, ValueError):
                            order_num = m_idx + 1

                        post_title = _notion_property_text(c_props.get("Tên post Shopee", {}))
                        if not post_title:
                            for cpv in c_props.values():
                                if cpv.get("type") == "title":
                                    ctl = cpv.get("title", [])
                                    if ctl:
                                        post_title = ctl[0].get("plain_text", "").strip()
                                    break
                        angle = _notion_property_text(c_props.get("Angle", {}))
                        insight_content = _notion_property_text(c_props.get("Insight", {}))
                        keywords = _notion_property_text(c_props.get("Từ khóa chính cho insight", {}))
                        folder_name = re.sub(r'[\\/*?:"<>|]', '-', post_title).strip()
                        folder_name = re.sub(r'-+', '-', folder_name).strip()

                        insights.append({
                            "page_id": c_id,
                            "order_num": order_num,
                            "display_name": post_title or angle or f"Insight {order_num}",
                            "post_title": post_title,
                            "folder_name": folder_name,
                            "angle": angle,
                            "notion_description": insight_content,
                            "keywords": keywords,
                            "product_title": best_title,
                        })
                    except Exception as c_err:
                        print(f"[load_notion_insights] Lỗi đọc page con {c_id}: {c_err}")
                if insights:
                    insights.sort(key=lambda item: item.get("order_num", 999))
                    return insights
    except Exception as exc:
        print(f"[load_notion_insights] Không đọc được Shopee Insight Library, thử database sản phẩm chính: {exc}")

    # 2. Fallback sang database sản phẩm chính (ca055a7742824b9598abde7a7686d144)
    product_database_id = os.getenv("NOTION_DATABASE_ID", "").strip() or "ca055a7742824b9598abde7a7686d144"
    try:
        database = call_notion_with_retry(notion.databases.retrieve, database_id=product_database_id)
        data_sources = database.get("data_sources", [])
        if not data_sources:
            return []

        candidates = []
        cursor = None
        while True:
            query_args = {"data_source_id": data_sources[0].get("id"), "page_size": 100}
            if cursor:
                query_args["start_cursor"] = cursor
            response = call_notion_with_retry(notion.data_sources.query, **query_args)
            for page in response.get("results", []):
                properties = page.get("properties", {})
                title = _notion_property_text(properties.get("Tên sản phẩm", {}))
                score = _product_name_match_score(product_hint, title)
                if score > 0:
                    candidates.append((score, page, title))
            if not response.get("has_more") or not response.get("next_cursor"):
                break
            cursor = response.get("next_cursor")

        if not candidates:
            return []

        candidates.sort(key=lambda item: item[0], reverse=True)
        score, product_page, product_title = candidates[0]
        if score < 0.75:
            return []

        product_page = call_notion_with_retry(notion.pages.retrieve, page_id=product_page.get("id"))
        insight_ids = _notion_page_mentions(product_page.get("properties", {}).get("Insight Library", {}))
        if not insight_ids:
            return []

        insights = []
        for mention_index, insight_id in enumerate(insight_ids):
            page = call_notion_with_retry(notion.pages.retrieve, page_id=insight_id)
            properties = page.get("properties", {})
            order_num = properties.get("Thứ tự", {}).get("number")
            try:
                order_num = int(order_num)
            except (TypeError, ValueError):
                order_num = mention_index + 1

            post_title = _notion_property_text(properties.get("Tên post Shopee", {}))
            angle = _notion_property_text(properties.get("Angle", {}))
            insight_content = _notion_property_text(properties.get("Insight", {}))
            keywords = _notion_property_text(properties.get("Từ khóa chính cho insight", {}))
            insights.append({
                "page_id": insight_id,
                "order_num": order_num,
                "display_name": post_title or angle or f"Insight {order_num}",
                "post_title": post_title,
                "angle": angle,
                "notion_description": insight_content,
                "keywords": keywords,
                "product_title": product_title,
            })

        insights.sort(key=lambda item: item.get("order_num", 999))
        return insights
    except Exception as exc:
        print(f"[load_notion_insights] Lỗi truy vấn database sản phẩm chính: {exc}")
        return []


@app.post("/api/automation/scan-insights")
def api_scan_insights():
    import base64
    from shopee_sync.src import convert_zicum
    try:
        data = request.json or {}
        export_dir = data.get("export_dir", "").strip()
        if not export_dir:
            return jsonify({"success": False, "error": "Thiếu đường dẫn thư mục lưu ảnh."}), 400

        target_dir = Path(export_dir)
        if not target_dir.exists() or not target_dir.is_dir():
            return jsonify({"success": False, "error": f"Thư mục không tồn tại: {export_dir}"}), 400

        # 1. Tìm file insights_data.json nếu có
        insights_data = {}
        json_file = target_dir / "insights_data.json"
        if json_file.exists() and json_file.is_file():
            try:
                insights_data = json.loads(json_file.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"[Scan Insights] Lỗi đọc insights_data.json: {e}")

        target_shop_hint = ""
        try:
            if target_dir.parent and target_dir.parent.name in list_shop_names():
                target_shop_hint = target_dir.parent.name
        except Exception:
            pass
        if not target_shop_hint:
            target_shop_hint = selected_shop_name()

        # 2. Dữ liệu live từ Notion (Shopee Insight Library hoặc Product DB)
        notion_insights = []
        try:
            notion_insights = load_notion_insights_for_product(target_dir.name, shop_hint=target_shop_hint)
        except Exception as exc:
            print(f"[Scan Insights] Không lấy được Insight từ Notion, dùng dữ liệu cục bộ: {exc}")

        notion_by_order = {
            item.get("order_num"): item
            for item in notion_insights
            if item.get("order_num") is not None
        }
        notion_by_clean_name = {}
        for item in notion_insights:
            for k in [item.get("post_title"), item.get("folder_name"), item.get("display_name")]:
                if k:
                    notion_by_clean_name[convert_zicum.clean_name(k)] = item

        # 3. Liệt kê TẤT CẢ các thư mục con trong target_dir
        subfolders = [
            f for f in target_dir.iterdir()
            if f.is_dir() and not f.name.startswith(".") and f.name.lower() not in ["output", "__pycache__"]
        ]

        def _get_sort_key(f):
            m = re.search(r'\d+', f.name)
            return int(m.group()) if m else 999
        subfolders.sort(key=_get_sort_key)

        insights_list = []
        for idx_folder, folder in enumerate(subfolders):
            folder_name = folder.name

            # Quét file media đầu tiên trong thư mục này
            media_file = None
            media_path = None
            media_url = None
            media_base64 = None
            is_video = False

            files = []
            for f in folder.iterdir():
                if f.is_file() and f.suffix.lower() in [".png", ".jpg", ".jpeg", ".webp", ".mp4"]:
                    files.append(f)

            if files:
                files.sort(key=lambda x: x.name)
                first_file = files[0]
                media_file = f"{folder_name}/{first_file.name}"
                media_path = str(first_file)
                media_url = f"/api/automation/images/view?name={folder_name}/{first_file.name}"
                is_video = first_file.suffix.lower() == ".mp4"

                try:
                    file_bytes = first_file.read_bytes()
                    encoded_body = base64.b64encode(file_bytes).decode("utf-8")
                    mime_type = "video/mp4" if is_video else f"image/{first_file.suffix.lower().replace('.', '')}"
                    media_base64 = f"data:{mime_type};base64,{encoded_body}"
                except Exception as e:
                    print(f"[Scan Insights] Lỗi đọc base64 file {first_file.name}: {e}")

            order_num = None
            match = re.search(r'\d+', folder_name)
            if match:
                order_num = int(match.group())

            # Tìm kiếm dữ liệu Notion khớp nhất cho folder này
            clean_f_name = convert_zicum.clean_name(folder_name)
            notion_info = notion_by_clean_name.get(clean_f_name)

            if not notion_info:
                for k, v in notion_by_clean_name.items():
                    if k and (k in clean_f_name or clean_f_name in k):
                        notion_info = v
                        break

            if not notion_info and order_num is not None:
                notion_info = notion_by_order.get(order_num)

            if not notion_info and idx_folder < len(notion_insights):
                notion_info = notion_insights[idx_folder]

            notion_info = notion_info or {}

            insight_info = {}
            if insights_data and "insights" in insights_data and isinstance(insights_data["insights"], list):
                idx = (order_num - 1) if order_num is not None else idx_folder
                if 0 <= idx < len(insights_data["insights"]):
                    insight_info = insights_data["insights"][idx]

            post_title = (
                notion_info.get("post_title", "")
                or insight_info.get("postTitle", "")
                or insight_info.get("title", "")
                or insight_info.get("tieuDe", "")
                or folder_name
            )
            angle = notion_info.get("angle", "") or insight_info.get("angle", "") or folder_name
            notion_description = (
                notion_info.get("notion_description", "")
                or insight_info.get("insightContent", "")
                or insight_info.get("content", "")
                or insight_info.get("noiDung", "")
                or insights_data.get("productDescription", "")
            )
            keywords = (
                notion_info.get("keywords", "")
                or insight_info.get("keywords", "")
                or insight_info.get("keyword", "")
                or insight_info.get("tuKhoa", "")
                or insight_info.get("insight_summary", "")
            )
            display_name = notion_info.get("display_name", "") or post_title or angle or folder_name

            insights_list.append({
                "folder_name": folder_name,
                "order_num": order_num or (idx_folder + 1),
                "media_file": media_file,
                "media_path": media_path,
                "media_url": media_url,
                "media_base64": media_base64,
                "media_type": "video" if is_video else "image",
                "notion_description": notion_description,
                "keywords": keywords,
                "angle": angle,
                "post_title": post_title,
                "display_name": display_name,
                "notion_page_id": notion_info.get("page_id", ""),
                "data_source": "notion" if notion_info else ("local" if insight_info else "folder")
            })

        insights_list.sort(key=lambda x: x["order_num"])

        return jsonify({
            "success": True,
            "insights": insights_list
        })
    except Exception as exc:
        return error_response(exc, 500)


def start_media_watcher():
    threading.Thread(target=media_watcher_loop, daemon=True).start()


if __name__ == "__main__":
    cleanup_old_instances()
    start_media_watcher()
    threading.Thread(target=launch_desktop_gui, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8765")), debug=False, threaded=True)
