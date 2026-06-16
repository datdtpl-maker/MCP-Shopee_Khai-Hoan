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
CURRENT_VERSION = "v2.1.4"


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

DEFAULT_DRIVE_ROOT = r"G:\My Drive\Test hình ảnh shopee"
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
  <link rel="icon" type="image/x-icon" href="/favicon.ico?v=2.1.4">
  <link rel="shortcut icon" type="image/x-icon" href="/favicon.ico?v=2.1.4">
  <title>MCP Shopee - Khải Hoàn</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Plus+Jakarta+Sans:wght@500;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {
      color-scheme: dark;
      --bg: #0b0d17;
      --panel: rgba(26, 32, 53, 0.75);
      --panel-border: rgba(255, 255, 255, 0.08);
      --soft: rgba(255, 255, 255, 0.04);
      --line: rgba(255, 255, 255, 0.06);
      --text: #f9fafb;
      --muted: #9ca3af;
      --brand: #ee4d2d;
      --brand-hover: #f14d2a;
      --brand-gradient: linear-gradient(135deg, #ee4d2d 0%, #ff7337 100%);
      --brand-glow: rgba(238, 77, 45, 0.25);
      --ok: #10b981;
      --okbg: rgba(16, 185, 129, 0.1);
      --warn: #f59e0b;
      --warnbg: rgba(245, 158, 11, 0.1);
      --danger: #ef4444;
      --danger-hover: #dc2626;
      --danger-gradient: linear-gradient(135deg, #ef4444 0%, #b91c1c 100%);
      --shadow: 0 20px 40px rgba(0, 0, 0, 0.4);
      font-family: 'Inter', system-ui, -apple-system, sans-serif;
    }
    
    body.theme-light {
      color-scheme: light;
      --bg: #f5f6fa;
      --panel: rgba(255, 255, 255, 0.88);
      --panel-border: rgba(0, 0, 0, 0.06);
      --soft: rgba(0, 0, 0, 0.02);
      --line: rgba(0, 0, 0, 0.04);
      --text: #1e293b;
      --muted: #64748b;
      --brand: #ee4d2d;
      --brand-hover: #d73d1e;
      --brand-glow: rgba(238, 77, 45, 0.15);
      --ok: #059669;
      --okbg: rgba(5, 150, 105, 0.08);
      --warn: #d97706;
      --warnbg: rgba(217, 119, 6, 0.08);
      --danger: #dc2626;
      --danger-hover: #b91c1c;
      --shadow: 0 10px 30px rgba(238, 77, 45, 0.03);
    }
    
    /* Light Mode Form & Input UI Overrides */
    body.theme-light .panel input,
    body.theme-light .panel select,
    body.theme-light .panel textarea {
      background-color: #ffffff !important;
      border: 1px solid #000000 !important;
      color: #000000 !important;
    }
    body.theme-light .panel input[readonly],
    body.theme-light .panel input:disabled,
    body.theme-light .panel textarea[readonly],
    body.theme-light .panel textarea:disabled {
      background-color: #ffffff !important;
      color: #000000 !important;
      border: 1px solid #000000 !important;
    }
    body.theme-light .panel label,
    body.theme-light .panel h4,
    body.theme-light .panel h3,
    body.theme-light .panel-head h3 {
      color: #000000 !important;
    }
    body.theme-light #contentImgDropzone,
    body.theme-light #sampleImgDropzone {
      background-color: #ffffff !important;
      border: 2px dashed #000000 !important;
    }
    body.theme-light #contentImgDropzone span,
    body.theme-light #sampleImgDropzone span,
    body.theme-light #contentImgDropzone svg,
    body.theme-light #sampleImgDropzone svg {
      color: #000000 !important;
    }
    body.theme-light #automationLogBox {
      background-color: #ffffff !important;
      border: 1px solid #000000 !important;
      color: #000000 !important;
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
      background: radial-gradient(circle at top left, rgba(238, 77, 45, 0.08), transparent 45%),
                  radial-gradient(circle at bottom right, rgba(139, 92, 246, 0.06), transparent 45%),
                  var(--bg);
      color: var(--text);
      min-height: 100vh;
      transition: background 0.3s, color 0.3s;
    }
    button, input, select { font: inherit; }
    button {
      min-height: 42px;
      border: 0;
      border-radius: 10px;
      padding: 10px 16px;
      background: var(--brand-gradient);
      color: #fff;
      font-weight: 700;
      font-family: 'Plus Jakarta Sans', sans-serif;
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
      transform: translateY(-2px);
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
      background: rgba(255, 255, 255, 0.06);
      color: var(--text);
      border: 1px solid rgba(255, 255, 255, 0.08);
      box-shadow: none;
      transition: background 0.3s, color 0.3s, border-color 0.3s;
    }
    body.theme-light button.secondary {
      background: rgba(0, 0, 0, 0.03);
      color: var(--text);
      border: 1px solid rgba(0, 0, 0, 0.08);
    }
    button.secondary:hover {
      background: rgba(255, 255, 255, 0.12);
      border-color: rgba(255, 255, 255, 0.15);
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
    }
    body.theme-light button.secondary:hover {
      background: rgba(0, 0, 0, 0.06);
      border-color: rgba(0, 0, 0, 0.12);
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
    }
    button.ghost {
      background: transparent;
      color: var(--muted);
      border: 1px solid rgba(255, 255, 255, 0.05);
      box-shadow: none;
    }
    body.theme-light button.ghost {
      border-color: rgba(0, 0, 0, 0.05);
    }
    button.ghost:hover {
      background: rgba(255, 255, 255, 0.05);
      color: var(--text);
      border-color: rgba(255, 255, 255, 0.1);
    }
    body.theme-light button.ghost:hover {
      background: rgba(0, 0, 0, 0.03);
      color: var(--text);
      border-color: rgba(0, 0, 0, 0.1);
    }
    button.danger {
      background: var(--danger-gradient);
      box-shadow: 0 4px 12px rgba(239, 68, 68, 0.2);
    }
    button.danger:hover {
      background: var(--danger-hover);
      box-shadow: 0 6px 18px rgba(239, 68, 68, 0.3);
    }
    button.btn-capture {
      background: linear-gradient(135deg, #2563eb 0%, #4f46e5 100%);
      box-shadow: 0 4px 14px rgba(79, 70, 229, 0.3);
    }
    button.btn-capture:hover {
      background: linear-gradient(135deg, #3b82f6 0%, #6366f1 100%);
      box-shadow: 0 6px 20px rgba(79, 70, 229, 0.4);
    }
    button.btn-record {
      background: linear-gradient(135deg, #f43f5e 0%, #e11d48 100%);
      box-shadow: 0 4px 14px rgba(225, 29, 72, 0.3);
    }
    button.btn-record:hover {
      background: linear-gradient(135deg, #fb7185 0%, #f43f5e 100%);
      box-shadow: 0 6px 20px rgba(225, 29, 72, 0.4);
    }
    button.btn-stop {
      background: linear-gradient(135deg, #7c2d12 0%, #b91c1c 100%);
      box-shadow: 0 4px 14px rgba(185, 28, 28, 0.3);
    }
    button.btn-stop:hover {
      background: linear-gradient(135deg, #991b1b 0%, #dc2626 100%);
      box-shadow: 0 6px 20px rgba(185, 28, 28, 0.4);
    }
    input, select, textarea {
      width: 100%;
      min-height: 44px;
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: 10px;
      background: rgba(13, 17, 28, 0.6);
      padding: 10px 14px;
      color: var(--text);
      outline: none;
      transition: all 0.2s;
    }
    body.theme-light input, body.theme-light select, body.theme-light textarea {
      background: #fff;
      border-color: #cbd5e1;
      color: var(--text);
    }
    input:focus, select:focus, textarea:focus {
      border-color: var(--brand);
      box-shadow: 0 0 0 3px var(--brand-glow);
    }
    label {
      display: block;
      margin-bottom: 8px;
      font-weight: 600;
      font-size: 13px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      color: var(--muted);
      font-family: 'Plus Jakarta Sans', sans-serif;
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
      padding: 20px 32px;
      background: rgba(10, 14, 23, 0.7);
      border-bottom: 1px solid var(--panel-border);
      position: sticky;
      top: 0;
      z-index: 10;
      backdrop-filter: blur(16px);
      -webkit-backdrop-filter: blur(16px);
      transition: background 0.3s, border-color 0.3s;
    }
    body.theme-light .topbar {
      background: rgba(240, 244, 248, 0.85);
    }
    .topbar h2 {
      margin: 0;
      font-size: 22px;
      font-weight: 800;
      font-family: 'Plus Jakarta Sans', sans-serif;
      background: linear-gradient(135deg, #fff 40%, #a5b4fc 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      transition: all 0.3s;
    }
    body.theme-light .topbar h2 {
      background: linear-gradient(135deg, #0f172a 40%, #1e3a8a 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }
    .topbar p {
      margin: 6px 0 0;
      color: var(--muted);
      font-size: 14px;
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
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid var(--panel-border);
      border-radius: 12px;
      padding: 4px;
      gap: 4px;
    }
    body.theme-light .action-group {
      background: rgba(0, 0, 0, 0.02);
    }
    .action-group-label {
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--muted);
      padding: 0 10px 0 6px;
      user-select: none;
      border-right: 1px solid var(--panel-border);
      margin-right: 2px;
      height: 20px;
      display: inline-flex;
      align-items: center;
    }
    .action-group button.group-btn {
      min-height: 36px;
      padding: 8px 12px;
      border-radius: 8px;
      font-size: 13px;
      font-weight: 600;
      box-shadow: none !important;
    }
    .action-group button.group-btn:hover {
      transform: translateY(-1px);
    }
    .action-group button.group-btn:active {
      transform: translateY(0);
    }
    .content {
      padding: 32px;
      flex: 1;
      max-width: 1600px;
      width: 100%;
      margin: 0 auto;
    }
    .workspace {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 440px;
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
      top: 112px;
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
      border-radius: 14px;
      box-shadow: var(--shadow);
      padding: 18px;
      min-height: 96px;
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    }
    .metric:hover {
      transform: translateY(-2px);
      border-color: rgba(59, 130, 246, 0.25);
      box-shadow: 0 12px 30px rgba(59, 130, 246, 0.08);
    }
    body.theme-light .metric strong {
      color: #0f172a;
    }
    .metric small {
      display: block;
      color: var(--muted);
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.8px;
      margin-bottom: 8px;
    }
    .metric strong {
      display: block;
      font-size: 15px;
      font-weight: 700;
      color: #fff;
      overflow-wrap: anywhere;
    }
    .badge {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border-radius: 999px;
      padding: 4px 10px;
      font-size: 12px;
      font-weight: 700;
      gap: 6px;
      line-height: 1.2;
    }
    .badge.ok {
      background: var(--okbg);
      color: var(--ok);
      border: 1px solid rgba(16, 185, 129, 0.15);
    }
    .badge.ok::before {
      content: '';
      display: inline-block;
      width: 6px;
      height: 6px;
      background: var(--ok);
      border-radius: 50%;
      box-shadow: 0 0 8px var(--ok);
      animation: pulse 1.8s infinite;
    }
    .badge.warn {
      background: var(--warnbg);
      color: var(--warn);
      border: 1px solid rgba(245, 158, 11, 0.15);
    }
    .badge.warn::before {
      content: '';
      display: inline-block;
      width: 6px;
      height: 6px;
      background: var(--warn);
      border-radius: 50%;
      box-shadow: 0 0 8px var(--warn);
      animation: pulse 1.8s infinite;
    }
    .badge.danger {
      background: rgba(239, 68, 68, 0.15);
      color: #ef4444;
      border: 1px solid rgba(239, 68, 68, 0.15);
    }
    .badge.danger::before {
      content: '';
      display: inline-block;
      width: 6px;
      height: 6px;
      background: #ef4444;
      border-radius: 50%;
      box-shadow: 0 0 8px #ef4444;
    }
    @keyframes pulse {
      0% { transform: scale(0.95); opacity: 0.6; }
      50% { transform: scale(1.15); opacity: 1; box-shadow: 0 0 10px currentColor; }
      100% { transform: scale(0.95); opacity: 0.6; }
    }
    .panel {
      background: var(--panel);
      border: 1px solid var(--panel-border);
      border-radius: 16px;
      box-shadow: var(--shadow);
      overflow: hidden;
      backdrop-filter: blur(16px);
      -webkit-backdrop-filter: blur(16px);
      transition: background 0.3s, border-color 0.3s, box-shadow 0.3s;
    }
    .panel-head {
      padding: 20px 24px;
      border-bottom: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.01);
      transition: border-color 0.3s;
    }
    .panel-head h3 {
      margin: 0;
      font-size: 18px;
      font-weight: 700;
      font-family: 'Plus Jakarta Sans', sans-serif;
      color: #fff;
      transition: color 0.3s;
    }
    body.theme-light .panel-head h3 {
      color: #0f172a;
    }
    .panel-head p {
      margin: 6px 0 0;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.45;
    }
    .panel-body {
      padding: 24px;
      display: grid;
      gap: 20px;
    }
    .layout {
      display: grid;
      grid-template-columns: minmax(0, 1.35fr) minmax(320px, 0.65fr);
      gap: 24px;
      align-items: start;
    }
    .two {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 16px;
    }
    .field-action {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 12px;
      align-items: end;
    }
    .hint {
      color: var(--muted);
      font-size: 13px;
      line-height: 1.45;
      display: flex;
      align-items: flex-start;
      gap: 6px;
    }
    .hint::before {
      content: 'ℹ';
      color: var(--brand);
      font-weight: bold;
    }
    .steps {
      display: grid;
      gap: 12px;
    }
    .step {
      display: grid;
      grid-template-columns: 32px 1fr;
      gap: 12px;
      padding: 14px;
      background: rgba(255, 255, 255, 0.02);
      border: 1px solid rgba(255, 255, 255, 0.04);
      border-radius: 12px;
      transition: all 0.25s;
    }
    body.theme-light .step {
      background: rgba(0, 0, 0, 0.01);
      border-color: rgba(0, 0, 0, 0.04);
    }
    .step:hover {
      background: rgba(255, 255, 255, 0.04);
      border-color: rgba(255, 255, 255, 0.08);
      transform: translateX(4px);
    }
    body.theme-light .step:hover {
      background: rgba(0, 0, 0, 0.03);
      border-color: rgba(0, 0, 0, 0.08);
    }
    .step span {
      display: grid;
      place-items: center;
      width: 32px;
      height: 32px;
      border-radius: 50%;
      background: rgba(59, 130, 246, 0.15);
      color: #60a5fa;
      font-weight: 800;
      font-family: 'Plus Jakarta Sans', sans-serif;
      transition: all 0.3s;
    }
    body.theme-light .step span {
      background: rgba(37, 99, 235, 0.08);
      color: #2563eb;
    }
    .step b {
      display: block;
      margin-bottom: 4px;
      font-size: 14px;
      color: #fff;
      transition: color 0.3s;
    }
    body.theme-light .step b {
      color: #0f172a;
    }
    .step small {
      display: block;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.4;
    }
    .control-grid {
      display: grid;
      grid-template-columns: minmax(220px, 320px) minmax(0, 1fr);
      gap: 20px;
      align-items: end;
    }
    .control-note {
      padding: 16px;
      border: 1px solid rgba(255, 255, 255, 0.04);
      background: rgba(255, 255, 255, 0.02);
      border-radius: 12px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.5;
      transition: background 0.3s, border-color 0.3s;
    }
    body.theme-light .control-note {
      background: rgba(0, 0, 0, 0.015);
      border-color: rgba(0, 0, 0, 0.05);
    }
    .logbox {
      background: #090c13;
      border-radius: 12px;
      border: 1px solid rgba(255, 255, 255, 0.06);
      overflow: hidden;
      box-shadow: inset 0 4px 12px rgba(0, 0, 0, 0.5);
      transition: background 0.3s, border-color 0.3s, box-shadow 0.3s;
    }
    body.theme-light .logbox {
      background: #f8fafc;
      border-color: #e2e8f0;
      box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.02);
    }
    .loghead {
      display: flex;
      justify-content: space-between;
      padding: 12px 16px;
      color: var(--text);
      background: rgba(255, 255, 255, 0.02);
      border-bottom: 1px solid rgba(255, 255, 255, 0.06);
      font-size: 13px;
      font-weight: 700;
      font-family: 'Plus Jakarta Sans', sans-serif;
      transition: background 0.3s, border-color 0.3s, color 0.3s;
    }
    body.theme-light .loghead {
      background: #f1f5f9;
      border-bottom-color: #e2e8f0;
      color: #334155;
    }
    .log {
      min-height: 520px;
      max-height: calc(100vh - 250px);
      overflow: auto;
      padding: 16px;
      font: 13px/1.5 Consolas, "Cascadia Mono", monospace;
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    .log-item {
      border-left: 3px solid var(--brand);
      padding: 8px 12px;
      border-radius: 0 6px 6px 0;
      background: rgba(255, 255, 255, 0.015);
      animation: fadeIn 0.3s ease-out;
      transition: background 0.3s, border-color 0.3s;
    }
    body.theme-light .log-item {
      background: #fff;
      border: 1px solid #e2e8f0;
      border-left-width: 3px;
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02);
    }
    .log-item.log-error {
      border-left-color: var(--danger);
      background: rgba(239, 68, 68, 0.05);
    }
    body.theme-light .log-item.log-error {
      border-left-color: var(--danger);
      background: rgba(239, 68, 68, 0.02);
    }
    .log-item.log-success {
      border-left-color: var(--ok);
      background: rgba(16, 185, 129, 0.05);
    }
    body.theme-light .log-item.log-success {
      border-left-color: var(--ok);
      background: rgba(16, 185, 129, 0.02);
    }
    .log-item.log-warning {
      border-left-color: var(--warn);
      background: rgba(245, 158, 11, 0.05);
    }
    body.theme-light .log-item.log-warning {
      border-left-color: var(--warn);
      background: rgba(245, 158, 11, 0.02);
    }
    .log-time {
      color: #6b7280;
      font-size: 11px;
      font-weight: 600;
      display: block;
      margin-bottom: 4px;
    }
    .log-text {
      margin: 0;
      white-space: pre-wrap;
      word-break: break-all;
      color: #e5e7eb;
      transition: color 0.3s;
    }
    body.theme-light .log-text {
      color: #1e293b;
    }
    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(4px); }
      to { opacity: 1; transform: translateY(0); }
    }
    .buttons {
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
    }
    @media(max-width: 1280px) {
      .workspace { grid-template-columns: 1fr; }
      .work-log { position: static; }
      .log { min-height: 280px; max-height: 420px; }
    }
    @media(max-width: 960px) {
      .metrics { grid-template-columns: repeat(3, 1fr); }
      .layout, .control-grid { grid-template-columns: 1fr; }
      .topbar { flex-direction: column; align-items: stretch; padding: 18px 24px; }
      .actions { margin-top: 12px; }
    }
    @media(max-width: 640px) {
      .metrics { grid-template-columns: 1fr; }
      .two, .field-action { grid-template-columns: 1fr; }
      .content { padding: 16px; }
      .action-group { width: 100%; flex-direction: column; align-items: stretch; gap: 8px; padding: 10px; }
      .action-group-label { border-right: none; border-bottom: 1px solid var(--panel-border); padding: 0 0 8px; margin-right: 0; margin-bottom: 4px; height: auto; justify-content: center; }
      .buttons button, .actions button { width: 100%; }
    }
    /* Poster Editor Styles */
    .spinner {
      border: 4px solid var(--soft);
      border-top-color: var(--brand);
      border-radius: 50%;
      width: 48px;
      height: 48px;
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
      border-radius: 8px;
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
      width: 20px;
      height: 20px;
      border-radius: 50%;
      background: var(--danger);
      color: #fff;
      display: grid;
      place-items: center;
      font-size: 11px;
      font-weight: bold;
      cursor: pointer;
      border: none;
      padding: 0;
      min-height: auto;
      box-shadow: 0 2px 6px rgba(0,0,0,0.3);
      transition: background 0.2s;
    }
    .thumbnail-wrapper .remove-btn:hover {
      background: var(--danger-hover);
    }
    .poster-card {
      position: relative;
      border-radius: 12px;
      overflow: hidden;
      border: 1px solid var(--panel-border);
      background: var(--soft);
      box-shadow: var(--shadow);
      transition: all 0.3s;
    }
    .poster-card:hover {
      transform: translateY(-4px);
      border-color: rgba(238, 77, 45, 0.3);
    }
    .poster-card img {
      width: 100%;
      height: auto;
      aspect-ratio: inherit;
      display: block;
      object-fit: contain;
      background: #000;
    }
    .poster-card .card-actions {
      position: absolute;
      bottom: 0;
      left: 0;
      right: 0;
      background: linear-gradient(to top, rgba(0,0,0,0.85) 0%, transparent 100%);
      padding: 24px 16px 16px;
      display: flex;
      justify-content: flex-end;
      gap: 8px;
      opacity: 0;
      transition: opacity 0.3s;
    }
    .poster-card:hover .card-actions {
      opacity: 1;
    }
    .quantity-selector button {
      min-height: 38px;
      padding: 4px;
    }
    
    /* Dropdown CSS cho thanh dieu khien */
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
      z-index: 100;
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
    @keyframes dropdownFade {
      from { opacity: 0; transform: translateY(-8px); }
      to { opacity: 1; transform: translateY(0); }
    }
    .dropdown:hover .dropdown-content {
      display: block;
    }
    .dropdown-content button, .dropdown-content a {
      width: 100%;
      text-align: left;
      justify-content: flex-start;
      background: transparent;
      border: none;
      box-shadow: none;
      padding: 10px 14px;
      border-radius: 8px;
      font-size: 13px;
      color: var(--text);
      min-height: auto;
      display: flex;
      align-items: center;
      gap: 10px;
      transition: background 0.2s, color 0.2s;
    }
    .dropdown-content button:hover {
      background: var(--soft);
      transform: none;
      box-shadow: none;
      color: var(--brand);
    }
    .dropdown-content button svg {
      opacity: 0.8;
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
        <div style="display: flex; align-items: center; gap: 15px;">
          <img src="/favicon.ico" style="width: 50px; height: 50px; border-radius: 50%; border: 2.5px solid var(--brand); box-shadow: 0 0 15px var(--brand-glow); background: #fff;" />
          <div>
            <h2 style="font-size: 24px; font-weight: 800; font-family: 'Plus Jakarta Sans', sans-serif; display: flex; align-items: center; gap: 8px; margin: 0;">
              MCP Shopee - Khải Hoàn <span style="font-size: 11px; padding: 2px 8px; border-radius: 20px; background: rgba(238, 77, 45, 0.12); color: var(--brand); font-weight: 700; border: 1.5px solid rgba(238, 77, 45, 0.2);">Pro</span>
            </h2>
            <p style="margin: 4px 0 0; color: var(--muted); font-size: 13.5px;">Hệ thống chụp sản phẩm và đồng bộ dữ liệu Notion & Telegram sang BigSeller</p>
          </div>
        </div>
        <div class="actions" style="display: flex; align-items: center; gap: 10px;">
          <!-- Dropdown 1: Thiết bị & Hệ thống -->
          <div class="dropdown">
            <button class="secondary" style="font-size: 13px; font-weight: 600; min-height: 38px; display: inline-flex; align-items: center; gap: 6px; padding: 6px 12px; border-radius: 8px;">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>
              Hệ thống & Thiết bị
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" style="opacity: 0.7; margin-left: 2px;"><polyline points="6 9 12 15 18 9"/></svg>
            </button>
            <div class="dropdown-content">
              <button id="updateAppBtn" onclick="checkAppUpdate(false)" style="color: var(--brand); font-weight: 700;">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/></svg>
                Cập nhật: <span id="updateAppText">v1.1.0</span>
              </button>
              <button id="themeToggleBtn" onclick="toggleTheme()">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"></circle><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>
                Giao diện Sáng/Tối
              </button>
              <button onclick="refresh()">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/></svg>
                Làm mới trang
              </button>
              <hr style="border: 0; border-top: 1px solid var(--line); margin: 6px 0;" />
              <button onclick="togglePixelScreen()">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M18.36 6.64a9 9 0 1 1-12.73 0"></path><line x1="12" y1="2" x2="12" y2="12"></line></svg>
                Bật/Tắt màn hình Pixel
              </button>
              <button id="previewBtn" onclick="togglePreview()">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="3" width="20" height="14" rx="2" ry="2"></rect><line x1="8" y1="21" x2="16" y2="21"></line><line x1="12" y1="17" x2="12" y2="21"></line></svg>
                <span id="previewBtnText">Xem Pixel</span>
              </button>
            </div>
          </div>

          <!-- Dropdown 2: Tính năng mở rộng -->
          <div class="dropdown">
            <button class="secondary" style="font-size: 13px; font-weight: 600; min-height: 38px; display: inline-flex; align-items: center; gap: 6px; padding: 6px 12px; border-radius: 8px; background: linear-gradient(135deg, rgba(238, 77, 45, 0.08) 0%, rgba(255, 115, 55, 0.08) 100%); border-color: rgba(238, 77, 45, 0.25);">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 2 7 12 12 22 7 12 2"></polygon><polyline points="2 17 12 22 22 17"></polyline><polyline points="2 12 12 17 22 12"></polyline></svg>
              Tính năng mở rộng
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" style="opacity: 0.7; margin-left: 2px;"><polyline points="6 9 12 15 18 9"/></svg>
            </button>
            <div class="dropdown-content">
              <button onclick="showPosterDashboard()">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color: #a855f7;"><polygon points="12 2 2 7 12 12 22 7 12 2"></polygon><polyline points="2 17 12 22 22 17"></polyline><polyline points="2 12 12 17 22 12"></polyline></svg>
                AI Edit Image/Video
              </button>
              <button onclick="showShopeeSyncDashboard()">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color: #ee4d2d;"><circle cx="9" cy="21" r="1"></circle><circle cx="20" cy="21" r="1"></circle><path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"></path></svg>
                Đồng bộ Shopee
              </button>
            </div>
          </div>

          <div style="width: 1px; height: 20px; background: var(--line); margin: 0 4px;"></div>

          <!-- Các nút tác vụ chính -->
          <button class="btn-capture" onclick="capture()" style="min-height: 38px; padding: 6px 14px; border-radius: 8px; font-size: 13.5px;" title="Chụp ảnh sản phẩm">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"></path><circle cx="12" cy="13" r="4"></circle></svg>
            Chụp ảnh
          </button>
          <button class="btn-record" onclick="record()" style="min-height: 38px; padding: 6px 14px; border-radius: 8px; font-size: 13.5px;" title="Quay video sản phẩm">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="23 7 16 12 23 17 23 7"></polygon><rect x="1" y="5" width="15" height="14" rx="2" ry="2"></rect></svg>
            Quay video
          </button>
          <button id="btnStop" class="btn-stop" onclick="stopOperation()" style="min-height: 38px; padding: 6px 14px; border-radius: 8px; font-size: 13.5px;" title="Dừng tác vụ hiện tại">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="4" width="16" height="16" rx="2" ry="2"></rect></svg>
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
                <div><label for="driveRoot">Đường dẫn thư mục chính</label><input id="driveRoot" value="G:\My Drive\Test hình ảnh shopee"></div>
                <button onclick="saveDriveRoot()">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"></path><polyline points="17 21 17 13 7 13 7 21"></polyline><polyline points="7 3 7 8 15 8"></polyline></svg>
                  Lưu & quét lại
                </button>
              </div>
              <div class="two">
                <div><label for="folderSelect">Chọn thư mục sản phẩm</label><select id="folderSelect" onchange="selectFolder()"><option value="">-- Chưa chọn thư mục --</option></select></div>
                <div><label for="newFolder">Tạo thư mục sản phẩm mới</label><div class="field-action"><input id="newFolder" placeholder="Ví dụ: Eskar Tears 15ml"><button onclick="createFolder()"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>Tạo</button></div></div>
              </div>
              <div class="buttons">
                <button class="secondary" onclick="scanFolders()">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
                  Quét lại thư mục
                </button>
                <button class="danger" onclick="deleteFolder()">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg>
                  Xóa thư mục đang chọn
                </button>
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
      <header class="topbar" style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--panel-border); padding-bottom: 16px; margin-bottom: 24px;">
        <div style="display: flex; align-items: center; gap: 16px;">
          <button class="ghost" onclick="showCaptureDashboard()" style="min-height: 38px; padding: 8px 12px;" title="Quay lại Bảng điều khiển">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="19" y1="12" x2="5" y2="12"></line><polyline points="12 19 5 12 12 5"></polyline></svg>
          </button>
          <h2 style="font-family: 'Plus Jakarta Sans', sans-serif; font-weight: 800; font-size: 22px;">AI Edit Image / Video</h2>
        </div>
        <div class="actions" style="display: flex; gap: 16px; align-items: center; flex-wrap: wrap;">
          <!-- ChatGPT Chrome Debug Status -->
          <div style="display: flex; align-items: center; gap: 8px;">
            <div id="chromeStatusBadge" class="badge danger" style="padding: 8px 16px; font-weight: 700; font-size: 13px; display: flex; align-items: center; gap: 8px; border-radius: 99px;">
              <span id="chromeStatusText">ChatGPT Chrome: Offline</span>
            </div>
            <button type="button" class="btn-capture" onclick="startChromeDebug()" style="min-height: 36px; padding: 0 16px; font-size: 12px; background: var(--brand); border-radius: 8px; font-weight: 700;">
              Mở Chrome ChatGPT
            </button>
          </div>
          <!-- Gemini Chrome Debug Status -->
          <div style="display: flex; align-items: center; gap: 8px;">
            <div id="geminiStatusBadge" class="badge danger" style="padding: 8px 16px; font-weight: 700; font-size: 13px; display: flex; align-items: center; gap: 8px; border-radius: 99px;">
              <span id="geminiStatusText">Gemini Chrome: Offline</span>
            </div>
            <button type="button" class="btn-capture" onclick="startChromeGemini()" style="min-height: 36px; padding: 0 16px; font-size: 12px; background: linear-gradient(135deg, #a855f7 0%, #7c3aed 100%); border-radius: 8px; font-weight: 700; border: none; box-shadow: 0 4px 12px rgba(124, 58, 237, 0.3);">
              Mở Chrome Gemini
            </button>
          </div>
        </div>
      </header>
      
      <div class="content" style="padding: 0; display: grid; grid-template-columns: 340px 1fr 360px; gap: 24px; width: 100%; align-items: start;">
        <!-- Cột 1: Thư viện Prompt (Prompts Library) -->
        <aside class="panel" style="display: flex; flex-direction: column; gap: 16px; padding: 20px; height: 1040px;">
          <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--panel-border); padding-bottom: 12px;">
            <h4 style="margin: 0; font-family: 'Plus Jakarta Sans', sans-serif; font-weight: 700; font-size: 15px;">Thư viện Prompt</h4>
            <div style="display: flex; gap: 8px;">
              <button class="ghost" onclick="triggerImportPrompt()" style="padding: 4px 8px; font-size: 12px; color: var(--ok); font-weight: 700; background: none; border: none; cursor: pointer;" title="Nhập danh sách prompt từ file .txt">+ Nhập file</button>
              <button class="ghost" onclick="openPromptModal()" style="padding: 4px 8px; font-size: 12px; color: var(--brand); font-weight: 700; background: none; border: none; cursor: pointer;">+ Thêm</button>
            </div>
          </div>
          <input type="file" id="promptImportInput" accept=".txt" onchange="handlePromptImport(event)" style="display: none;">
          
          <!-- Lọc danh mục -->
          <div style="display: flex; gap: 8px; align-items: center; width: 100%;">
            <select id="promptCategoryFilter" onchange="filterPromptsList()" style="font-size: 12px; min-height: 34px; flex: 1;">
              <option value="all">Tất cả danh mục</option>
            </select>
            <button class="ghost" onclick="openCategoryModal()" style="padding: 6px; min-height: 34px; display: flex; align-items: center; justify-content: center; cursor: pointer; border: 1px solid var(--panel-border); border-radius: 8px;" title="Quản lý danh mục">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="color: var(--muted);"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>
            </button>
          </div>
          
          <!-- Danh sách prompts -->
          <div id="promptsLibraryContainer" style="display: flex; flex-direction: column; gap: 8px; flex: 1; overflow-y: auto; padding-right: 4px;">
            <!-- Load động từ API -->
          </div>
        </aside>
        
        <!-- Cột 2: Bảng điều khiển và Soạn thảo (Control Panel) -->
        <main class="panel" style="display: flex; flex-direction: column; gap: 12px; padding: 16px 20px; min-height: 1040px; height: 1040px; box-sizing: border-box;">
          <div style="border-bottom: 1px solid var(--panel-border); padding-bottom: 12px;">
            <h4 style="margin: 0; font-family: 'Plus Jakarta Sans', sans-serif; font-weight: 700; font-size: 15px;">Bảng Điều Khiển Gửi</h4>
          </div>
          <!-- Đường dẫn lưu ảnh kết quả -->
          <div style="margin-bottom: 4px;">
            <label style="margin-bottom: 6px; display: block; font-weight: 600; font-size: 13px; color: #000000;">Thư mục lưu ảnh kết quả</label>
            <div style="display: flex; gap: 8px;">
              <input type="text" id="posterExportDir" placeholder="Mặc định: Downloads" style="flex: 1; min-height: 36px; padding: 6px 12px; font-size: 13px; background: #ffffff; border: 1px solid #000000; border-radius: 8px; color: #000000;" readonly>
              <button type="button" class="secondary" onclick="browseExportDirectory()" style="min-height: 36px; padding: 0 14px; font-size: 12px; border-radius: 8px; font-weight: 600; cursor: pointer;">Chọn...</button>
            </div>
          </div>
          
          <!-- File sản phẩm được chọn -->
          <div>
            <label style="margin-bottom: 6px; display: block; font-weight: 600; font-size: 13px; color: #000000;">File sản phẩm thô (Ảnh/Video)</label>
            <div style="display: grid; grid-template-columns: 1fr auto; gap: 12px;">
              <div id="contentImgDropzone" onclick="document.getElementById('contentImgFile').click()" style="border: 2px dashed #000000; border-radius: 12px; height: 70px; display: flex; flex-direction: column; align-items: center; justify-content: center; cursor: pointer; transition: all 0.3s; background: #ffffff; flex: 1;">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color: #333333; margin-bottom: 4px;"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="17 8 12 3 7 8"></polyline><line x1="12" y1="3" x2="12" y2="15"></line></svg>
                <span id="contentImgLabel" style="font-size: 11px; color: #333333; text-align: center; padding: 0 10px; font-weight: 500;">Bấm hoặc Kéo thả ảnh/video sản phẩm</span>
                <input type="file" id="contentImgFile" accept="image/*,video/*" style="display: none;" onchange="handleContentImageSelect(this.files)">
              </div>
              <div id="contentImgPreviewContainer" style="width: 70px; height: 70px; border-radius: 12px; border: 1px solid var(--panel-border); display: none; overflow: hidden; position: relative; background: var(--bg);">
                <img id="contentImgPreview" src="" style="width: 100%; height: 100%; object-fit: contain; display: none;">
                <video id="contentVideoPreview" src="" style="width: 100%; height: 100%; object-fit: contain; display: none;" autoplay loop muted playsinline></video>
                <button type="button" onclick="clearContentImage()" style="position: absolute; top: 4px; right: 4px; background: rgba(0,0,0,0.7); border: none; border-radius: 50%; width: 20px; height: 20px; display: grid; place-items: center; color: #fff; cursor: pointer; font-size: 11px; z-index: 10;">×</button>
              </div>
            </div>
            <!-- Nút lấy file Pixel mới nhất -->
            <button type="button" class="secondary" onclick="useLatestPixelPhoto()" style="width: 100%; min-height: 32px; font-size: 11px; margin-top: 8px; display: flex; align-items: center; justify-content: center; gap: 6px; font-weight: 700; border-radius: 6px;">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path><polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline><line x1="12" y1="22.08" x2="12" y2="12"></line></svg>
              Lấy ảnh/video Pixel vừa chụp mới nhất
            </button>
          </div>
          
          <!-- File ảnh mẫu tham khảo -->
          <div>
            <label style="margin-bottom: 6px; display: block; font-weight: 600; font-size: 13px; color: #000000;">Ảnh mẫu tham khảo phong cách (Tùy chọn)</label>
            <!-- Vùng hiển thị ảnh Preview (khi đã chọn/dán thành công) -->
            <div id="sampleImgPreviewContainer" style="width: 100%; height: 120px; border-radius: 12px; border: 1px solid var(--panel-border); display: none; overflow: hidden; position: relative; background: var(--bg); margin-bottom: 8px;">
              <img id="sampleImgPreview" src="" style="width: 100%; height: 100%; object-fit: contain;">
              <button type="button" onclick="clearSampleImage()" style="position: absolute; top: 6px; right: 6px; background: rgba(0,0,0,0.7); border: none; border-radius: 50%; width: 22px; height: 22px; display: grid; place-items: center; color: #fff; cursor: pointer; font-size: 12px; z-index: 10;">×</button>
            </div>
            
            <!-- Vùng chọn ảnh (chỉ hiển thị khi chưa có ảnh) -->
            <div id="sampleImgSelectorContainer" style="display: flex; flex-direction: column; gap: 8px;">
              <!-- Dropzone kéo thả/chọn file -->
              <div id="sampleImgDropzone" onclick="document.getElementById('sampleImgFile').click()" style="border: 2px dashed #000000; border-radius: 12px; height: 60px; display: flex; flex-direction: column; align-items: center; justify-content: center; cursor: pointer; transition: all 0.3s; background: #ffffff;">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color: #333333; margin-bottom: 4px;"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="17 8 12 3 7 8"></polyline><line x1="12" y1="3" x2="12" y2="15"></line></svg>
                <span id="sampleImgLabel" style="font-size: 11px; color: #333333; text-align: center; font-weight: 500;">Bấm hoặc Kéo thả ảnh mẫu tham khảo</span>
                <input type="file" id="sampleImgFile" accept="image/*" style="display: none;" onchange="handleSampleImageSelect(this.files)">
              </div>
              
              <!-- Ô dán URL riêng biệt -->
              <input type="text" id="sampleImgUrlInput" placeholder="Hoặc dán link URL ảnh mẫu vào đây..." oninput="handleSampleImageUrlChange(this.value)" style="width: 100%; height: 26px; font-size: 10px; border-radius: 8px; border: 1px solid #000000; padding: 0 10px; background: #ffffff; color: #000000; outline: none;">
            </div>
          </div>
          
          <!-- Thông tin sản phẩm từ Notion -->
          <div style="display: flex; flex-direction: column; gap: 6px;">
            <label for="notionContentInput" style="font-weight: 600; font-size: 13px; color: #000000;">Thông tin sản phẩm từ Notion</label>
            <textarea id="notionContentInput" placeholder="Dán nội dung thuộc tính từ Notion..." style="width: 100%; height: 60px; min-height: 60px; resize: none; font-size: 12px; line-height: 1.4; border-radius: 8px; padding: 8px; background: #ffffff; border: 1px solid #000000; color: #000000;"></textarea>
          </div>
          
          <!-- Từ khóa chính của insight -->
          <div style="display: flex; flex-direction: column; gap: 6px;">
            <label for="keywordsInput" style="font-weight: 600; font-size: 13px; color: #000000;">Từ khóa chính của insight</label>
            <input type="text" id="keywordsInput" placeholder="Ví dụ: trẻ trung, sang trọng, năng động..." style="width: 100%; min-height: 36px; padding: 6px 12px; font-size: 12px; background: #ffffff; border: 1px solid #000000; border-radius: 8px; color: #000000;">
          </div>
          
          <!-- Nội dung Prompt soạn thảo -->
          <div style="display: flex; flex-direction: column; height: 120px; min-height: 120px;">
            <label for="contentEditorPrompt" style="margin-bottom: 8px; display: block; font-weight: 600; font-size: 13px; color: #000000;">Nội dung Prompt</label>
            <textarea id="contentEditorPrompt" placeholder="Nhập yêu cầu bối cảnh ở đây hoặc click chọn từ thư viện bên trái..." style="width: 100%; height: 85px; min-height: 85px; resize: none; font-size: 13px; line-height: 1.4; border-radius: 8px; padding: 10px; background: #ffffff; border: 1px solid #000000; color: #000000;"></textarea>
          </div>
          
          <!-- Khung gửi tin nhắn -->
          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
            <button class="btn-capture" id="btnSendToChatGPT" onclick="sendToChatGPT()" style="font-size: 14px; padding: 12px; border-radius: 8px; font-weight: 700; display: flex; align-items: center; justify-content: center; gap: 8px;">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>
              Gửi Lên ChatGPT
            </button>
            <button class="btn-capture" id="btnSendToGemini" onclick="sendToGemini()" style="font-size: 14px; padding: 12px; border-radius: 8px; font-weight: 700; display: flex; align-items: center; justify-content: center; gap: 8px; background: linear-gradient(135deg, #a855f7 0%, #7c3aed 100%); box-shadow: 0 4px 12px rgba(124, 58, 237, 0.3); border: none;">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>
              Gửi Lên Gemini
            </button>
          </div>
          
          <!-- Nhật ký tiến trình (Live Log) -->
          <div style="display: flex; flex-direction: column; height: 180px; min-height: 180px; margin-bottom: 4px;">
            <label style="margin-bottom: 6px; font-size: 13px; font-weight: 600; color: #000000;">Nhật ký tiến trình (Realtime Log)</label>
            <div id="automationLogBox" style="flex: 1; background: #ffffff; border: 1px solid #000000; border-radius: 8px; padding: 12px; font-family: monospace; font-size: 11.5px; overflow-y: auto; color: #000000; line-height: 1.5; height: 145px;">
              Chưa có hoạt động nào. Hãy kết nối Chrome và gửi ảnh để bắt đầu.
            </div>
          </div>
        </main>
        
        <!-- Cột 3: Danh sách ảnh kết quả tải về (Results Panel) -->
        <aside class="panel" style="display: flex; flex-direction: column; gap: 16px; padding: 20px; height: 1040px;">
          <div style="border-bottom: 1px solid var(--panel-border); padding-bottom: 12px; display: flex; justify-content: space-between; align-items: center;">
            <h4 style="margin: 0; font-family: 'Plus Jakarta Sans', sans-serif; font-weight: 700; font-size: 15px;">Ảnh kết quả</h4>
            <div style="display: flex; gap: 8px;">
              <button class="ghost" onclick="clearToolCache()" style="padding: 4px 8px; font-size: 12px; color: var(--danger); background: none; border: none; cursor: pointer; font-weight: 700;" title="Xóa toàn bộ ảnh tạm và ảnh kết quả cũ">Xóa cache</button>
              <button class="ghost" onclick="loadDownloadedImages()" style="padding: 4px 8px; font-size: 12px; color: var(--brand); background: none; border: none; cursor: pointer; font-weight: 700;">Làm mới</button>
            </div>
          </div>
          
          <!-- Khung danh sách ảnh kết quả -->
          <div id="downloadedImagesList" style="flex: 1; overflow-y: auto; display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; align-content: start; padding-right: 4px;">
            <!-- Load động từ API -->
          </div>
        </aside>
      </div>
    </div>

    <!-- Shopee Notion to BigSeller Auto Sync Tab -->
    <div id="shopeeSyncDashboard" style="display: none; flex-direction: column; width: 100%;">
      <header class="topbar" style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--panel-border); padding-bottom: 16px; margin-bottom: 24px;">
        <div style="display: flex; align-items: center; gap: 16px;">
          <button class="ghost" onclick="showCaptureDashboard()" style="min-height: 38px; padding: 8px 12px; background: none; border: none; color: var(--text); cursor: pointer;" title="Quay lại Bảng điều khiển">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="19" y1="12" x2="5" y2="12"></line><polyline points="12 19 5 12 12 5"></polyline></svg>
          </button>
          <h2 style="font-family: 'Plus Jakarta Sans', sans-serif; font-weight: 800; font-size: 22px; margin: 0;">Đồng bộ Shopee / BigSeller</h2>
        </div>
        <div class="actions" style="display: flex; gap: 16px; align-items: center;">
          <div id="shopeeBotStatusBadge" class="badge danger" style="padding: 8px 16px; font-weight: 700; font-size: 13px; display: flex; align-items: center; gap: 8px; border-radius: 99px;">
            <span id="shopeeBotStatusText">Bot Telegram: OFFLINE</span>
          </div>
          <button type="button" id="btnToggleShopeeBot" class="btn-capture" onclick="toggleShopeeBot()" style="min-height: 36px; padding: 0 16px; font-size: 12px; background: var(--brand); border-radius: 8px; font-weight: 700; border: none; cursor: pointer; color: #fff;">
            Khởi động Telegram Bot
          </button>
        </div>
      </header>
      
      <div class="workspace" style="display: flex; gap: 24px;">
        <!-- Cột 1: Cấu hình kết nối Notion / Telegram / API -->
        <div style="flex: 1; display: flex; flex-direction: column; gap: 24px; max-width: 450px; min-width: 320px;">
          <section class="panel">
            <div class="panel-head">
              <h3>Cấu hình Notion & Telegram</h3>
              <p>Thiết lập thông tin kết nối Notion Database và Telegram Bot.</p>
            </div>
            <div class="panel-body" style="display: flex; flex-direction: column; gap: 16px;">
              <div>
                <label for="shopeeNotionToken" style="font-size: 13px; font-weight: 600; margin-bottom: 6px; display: block;">Notion Integration Token (NOTION_TOKEN)</label>
                <input id="shopeeNotionToken" type="password" placeholder="ntn_..." style="width: 100%; border-radius: 8px; padding: 10px; background: rgba(0,0,0,0.12); border: 1px solid var(--panel-border); color: var(--text);">
              </div>
              <div>
                <label for="shopeeNotionDbId" style="font-size: 13px; font-weight: 600; margin-bottom: 6px; display: block;">Notion Database ID (NOTION_DATABASE_ID)</label>
                <input id="shopeeNotionDbId" type="text" placeholder="Ví dụ: ca055a7742824b9598abde7a7686d144" style="width: 100%; border-radius: 8px; padding: 10px; background: rgba(0,0,0,0.12); border: 1px solid var(--panel-border); color: var(--text);">
              </div>
              <div>
                <label for="shopeeTelegramToken" style="font-size: 13px; font-weight: 600; margin-bottom: 6px; display: block;">Telegram Bot Token (TELEGRAM_BOT_TOKEN)</label>
                <input id="shopeeTelegramToken" type="password" placeholder="Mã token của Bot Telegram..." style="width: 100%; border-radius: 8px; padding: 10px; background: rgba(0,0,0,0.12); border: 1px solid var(--panel-border); color: var(--text);">
              </div>
              <div>
                <label for="shopeeManagerChatId" style="font-size: 13px; font-weight: 600; margin-bottom: 6px; display: block;">Manager Chat ID (MANAGER_CHAT_ID)</label>
                <input id="shopeeManagerChatId" type="text" placeholder="ID người quản lý nhận thông báo..." style="width: 100%; border-radius: 8px; padding: 10px; background: rgba(0,0,0,0.12); border: 1px solid var(--panel-border); color: var(--text);">
              </div>
              <div>
                <label for="shopeeGeminiApiKey" style="font-size: 13px; font-weight: 600; margin-bottom: 6px; display: block;">Gemini/OpenAI API Key (GEMINI_API_KEY)</label>
                <input id="shopeeGeminiApiKey" type="password" placeholder="sk-... hoặc API Key của Gemini..." style="width: 100%; border-radius: 8px; padding: 10px; background: rgba(0,0,0,0.12); border: 1px solid var(--panel-border); color: var(--text);">
              </div>
              
              <button onclick="saveShopeeConfig()" style="width: 100%; min-height: 40px; font-weight: 700; background: var(--brand); border-radius: 8px; display: flex; align-items: center; justify-content: center; gap: 8px; border: none; color: #fff; cursor: pointer;">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"></path><polyline points="17 21 17 13 7 13 7 21"></polyline><polyline points="7 3 7 8 15 8"></polyline></svg>
                Lưu cấu hình
              </button>
            </div>
          </section>
        </div>
        
        <!-- Cột 2: Bảng điều khiển & Realtime Logs -->
        <div style="flex: 2; display: flex; flex-direction: column; gap: 24px;">
          <section class="panel" style="flex: 1; display: flex; flex-direction: column; height: 1040px; padding: 20px;">
            <div class="panel-head" style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--panel-border); padding-bottom: 12px; margin-bottom: 16px;">
              <div>
                <h3 style="margin: 0;">Đồng bộ Notion sang BigSeller</h3>
                <p style="margin: 4px 0 0; font-size: 12px; color: var(--muted);">Khởi chạy tiến trình đồng bộ dữ liệu Notion và xuất Excel thủ công.</p>
              </div>
              <button class="secondary" onclick="runShopeeSync()" style="background: linear-gradient(135deg, rgba(16, 185, 129, 0.15) 0%, rgba(5, 150, 105, 0.15) 100%); border-color: rgba(16, 185, 129, 0.3); font-weight: 700; padding: 10px 20px; border-radius: 8px; cursor: pointer; color: #10b981; display: flex; align-items: center; gap: 8px;" title="Chạy đồng bộ ngay">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon></svg>
                Đồng bộ ngay lập tức
              </button>
            </div>
            <div class="panel-body" style="flex: 1; display: flex; flex-direction: column; gap: 12px; height: calc(100% - 70px);">
              <label style="font-weight: 600; font-size: 13px;">Nhật ký đồng bộ (Realtime Log)</label>
              <!-- Ô log tiến trình đồng bộ -->
              <div id="shopeeSyncLogBox" style="flex: 1; height: 800px; background: rgba(0,0,0,0.2); border: 1px solid var(--panel-border); border-radius: 8px; padding: 16px; font-family: 'Consolas', 'Courier New', monospace; font-size: 12px; line-height: 1.6; overflow-y: auto; color: var(--text-muted);">
                <!-- Log hiển thị thời gian thực -->
              </div>
            </div>
          </section>
        </div>
        
        <!-- Cột 3: Danh sách file Excel xuất bản -->
        <aside class="panel" style="flex: 1; display: flex; flex-direction: column; gap: 16px; padding: 20px; max-width: 320px; min-width: 250px; height: 1040px;">
          <div style="border-bottom: 1px solid var(--panel-border); padding-bottom: 12px; display: flex; justify-content: space-between; align-items: center;">
            <h4 style="margin: 0; font-family: 'Plus Jakarta Sans', sans-serif; font-weight: 700; font-size: 15px;">Excel BigSeller đã tạo</h4>
            <button class="ghost" onclick="loadShopeeExcelList()" style="padding: 4px 8px; font-size: 12px; color: var(--brand); background: none; border: none; cursor: pointer; font-weight: 700;">Làm mới</button>
          </div>
          
          <div id="shopeeExcelList" style="flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 12px; align-content: start; padding-right: 4px;">
            <!-- Load động từ API -->
          </div>
        </aside>
      </div>
    </div>
  </main>
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
        const shopeeLogBox = document.getElementById("shopeeSyncLogBox");
        if (shopeeLogBox) {
          const timeStr = new Date().toLocaleTimeString();
          const escMsg = escapeHtml(v.message || text);
          let color = "var(--text-muted)";
          if (escMsg.toLowerCase().includes("thành công") || escMsg.toLowerCase().includes("thanh cong") || escMsg.toLowerCase().includes("hoàn thành") || escMsg.toLowerCase().includes("success")) color = "#22c55e";
          else if (escMsg.toLowerCase().includes("lỗi") || escMsg.toLowerCase().includes("error") || escMsg.toLowerCase().includes("failed") || escMsg.toLowerCase().includes("hỏng")) color = "#ef4444";
          else if (escMsg.toLowerCase().includes("cảnh báo") || escMsg.toLowerCase().includes("warning")) color = "#eab308";
          
          shopeeLogBox.innerHTML += `<div style="color: ${color}; margin-bottom: 4px;">[${timeStr}] ${escMsg}</div>`;
          shopeeLogBox.scrollTop = shopeeLogBox.scrollHeight;
        }
        if (v.message && (v.message.includes("thành công") || v.message.includes("thanh cong") || v.message.includes("Sync completed") || v.message.includes("thực tế"))) {
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
  function escapeHtml(s){return String(s).replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[m]))}
  function render(d){document.getElementById("adbMetric").innerHTML=d.adb_device?`<span class="badge ok">${d.adb_device}</span>`:`<span class="badge warn">Chưa thấy Pixel</span>`;document.getElementById("driveMetric").innerHTML=d.drive_ready?`<span class="badge ok">Đã kết nối</span>`:`<span class="badge warn">Không tìm thấy</span>`;document.getElementById("selectedMetric").textContent=d.selected_folder||"Chưa chọn";document.getElementById("folderMetric").textContent=(d.folders||[]).length;document.getElementById("busyMetric").innerHTML=d.operation_busy?`<span class="badge warn">Đang xử lý</span>`:`<span class="badge ok">Sẵn sàng</span>`;document.getElementById("navFolders").textContent=(d.folders||[]).length;document.getElementById("navDrive").textContent=d.drive_ready?"OK":"Lỗi";document.getElementById("navAdb").textContent=d.adb_device?"OK":"Offline";document.getElementById("driveRoot").value=d.drive_root;document.getElementById("connMode").value=d.connection_mode||"usb";document.getElementById("wifiIp").value=d.wifi_ip||"";document.getElementById("adbPathInput").value=d.adb_path||"";document.getElementById("scrcpyPathInput").value=d.scrcpy_path||"";changeConnMode();const s=document.getElementById("folderSelect"),current=d.selected_folder||s.value;s.innerHTML='<option value="">-- Chưa chọn thư mục --</option>'+d.folders.map(f=>`<option value="${escapeHtml(f)}">${escapeHtml(f)}</option>`).join("");s.value=current;const pb=document.getElementById("previewBtn"),pt=document.getElementById("previewBtnText");if(pb&&pt){if(d.scrcpy_running){pb.classList.add("pulse-warn");pt.textContent="Đóng xem Pixel"}else{pb.classList.remove("pulse-warn");pt.textContent="Xem Pixel"}}}
  async function refresh(){try{render(await api("/api/status"))}catch(e){log(e)}}
  async function scanFolders(){try{render(await api("/api/status"));log({status:"Đã quét lại danh sách thư mục."})}catch(e){log(e)}}
  async function togglePreview(){try{const txt=document.getElementById("previewBtnText").textContent;if(txt==="Đóng xem Pixel"){log(await api("/api/close-preview",{}))}else{log(await api("/api/open-preview",{}))}refresh()}catch(e){log(e)}}
  async function saveDriveRoot(){try{log(await api("/api/drive-root",{drive_root:document.getElementById("driveRoot").value}));await refresh()}catch(e){log(e)}}
  async function saveToolPaths(){try{const adb=document.getElementById("adbPathInput").value.trim();const scrcpy=document.getElementById("scrcpyPathInput").value.trim();log(await api("/api/pixel/paths",{adb_path:adb,scrcpy_path:scrcpy}));await refresh()}catch(e){log(e)}}
  async function createFolder(){try{const d=await api("/api/folders",{name:document.getElementById("newFolder").value});document.getElementById("newFolder").value="";log(d);await refresh()}catch(e){log(e)}}
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
    document.getElementById("captureDashboard").style.display = "none";
    document.getElementById("shopeeSyncDashboard").style.display = "none";
    document.getElementById("posterDashboard").style.display = "flex";
    // Tải cấu hình OpenAI từ backend lên UI
    loadOpenAIConfig();
  }
  
  function showCaptureDashboard() {
    document.getElementById("posterDashboard").style.display = "none";
    document.getElementById("shopeeSyncDashboard").style.display = "none";
    document.getElementById("captureDashboard").style.display = "block";
  }

  function showShopeeSyncDashboard() {
    document.getElementById("captureDashboard").style.display = "none";
    document.getElementById("posterDashboard").style.display = "none";
    document.getElementById("shopeeSyncDashboard").style.display = "flex";
    loadShopeeConfig();
    loadShopeeExcelList();
    checkShopeeBotStatus();
  }

  async function loadShopeeConfig() {
    try {
      const d = await api("/api/shopee/config");
      document.getElementById("shopeeNotionToken").value = d.NOTION_TOKEN || "";
      document.getElementById("shopeeNotionDbId").value = d.NOTION_DATABASE_ID || "";
      document.getElementById("shopeeTelegramToken").value = d.TELEGRAM_BOT_TOKEN || "";
      document.getElementById("shopeeManagerChatId").value = d.MANAGER_CHAT_ID || "";
      document.getElementById("shopeeGeminiApiKey").value = d.GEMINI_API_KEY || "";
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
      
      const payload = {
        NOTION_TOKEN: notionToken,
        NOTION_DATABASE_ID: notionDbId,
        TELEGRAM_BOT_TOKEN: telegramToken,
        MANAGER_CHAT_ID: managerChatId,
        GEMINI_API_KEY: geminiApiKey,
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
    
    try {
      const d = await api("/api/shopee/sync/run", {});
      log({step: "shopee_sync", message: d.message});
    } catch(e) {
      log({step: "shopee_sync", message: "Lỗi đồng bộ: " + (e.error || e.message || JSON.stringify(e))});
      alert("Lỗi kích hoạt đồng bộ: " + (e.error || e.message || JSON.stringify(e)));
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
            📁 ${escapeHtml(f.name)}
          </div>
          <div style="font-size: 11px; color: var(--muted); display: flex; justify-content: space-between;">
            <span>${f.time}</span>
            <a href="${f.url}" download="${escapeHtml(f.name)}" style="color: var(--brand); text-decoration: none; font-weight: 700;">Tải về</a>
          </div>
        </div>
      `).join("");
    } catch(e) {
      console.error("Lỗi tải danh sách file Excel:", e);
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
  const CURRENT_VERSION = "v2.1.4";
  let promptsList = [];
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
        <div style="position: absolute; top: 10px; right: 10px; display: flex; gap: 6px; z-index: 10;">
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
          prompt_title: selectedPromptTitle
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
          prompt_title: selectedPromptTitle
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
    if (!confirm("Bạn có chắc chắn muốn xóa toàn bộ ảnh/video tạm trong inbox và các file kết quả cũ không?")) {
      return;
    }
    try {
      const response = await fetch("/api/automation/clear-cache", { method: "POST" });
      const data = await response.json();
      if (response.ok && data.success) {
        clearContentImage();
        await loadDownloadedImages();
        const logBox = document.getElementById("automationLogBox");
        if (logBox) {
          logBox.innerHTML = "Đã xóa sạch cache. Sẵn sàng cho tác vụ mới.";
        }
        alert("Đã xóa sạch bộ nhớ tạm và các file kết quả cũ thành công!");
      } else {
        alert("Lỗi xóa cache: " + (data.error || data.message));
      }
    } catch (e) {
      alert("Lỗi kết nối khi xóa cache: " + e.message);
    }
  }

  async function loadDownloadedImages() {
    try {
      const response = await fetch("/api/automation/images/list");
      const images = await response.json();
      renderDownloadedImages(images);
    } catch(e) {
      console.error("Lỗi lấy danh sách kết quả đã tải:", e);
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
        ? `<video src="${img.url}" style="width: 100%; height: auto; display: block; object-fit: contain; background: #000;" autoplay loop muted playsinline></video>`
        : `<img src="${img.url}" alt="${img.name}">`;
        
      card.innerHTML = `
        ${mediaElement}
        <div class="card-actions" style="flex-direction: column; gap: 6px; align-items: stretch; justify-content: flex-end; padding: 12px; background: linear-gradient(to top, rgba(0,0,0,0.95) 0%, rgba(0,0,0,0.5) 60%, transparent 100%);">
          <div style="font-size: 10px; color: #fff; font-weight: 600; text-align: center; text-shadow: 0 1px 2px rgba(0,0,0,0.8); margin-bottom: 6px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; line-height: 1.3; word-break: break-all;">
            ${img.name}
          </div>
          <div style="display: flex; flex-direction: column; gap: 5px; width: 100%;">
            <button class="ghost" onclick="event.stopPropagation(); revealImageFolder('${img.file_path.replace(/\\/g, '\\\\')}')" style="min-height: 28px; font-size: 10.5px; padding: 4px 8px; font-weight: 700; border-radius: 6px; background: rgba(255,255,255,0.18); border: 1px solid rgba(255,255,255,0.25); color: #fff; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 4px; text-shadow: 0 1px 1px rgba(0,0,0,0.5); width: 100%;">
              📂 Mở thư mục
            </button>
            <button onclick="event.stopPropagation(); window.open('https://www.canva.com', '_blank')" style="min-height: 28px; font-size: 10.5px; padding: 4px 8px; font-weight: 700; border-radius: 6px; background: var(--brand); border: none; color: #fff; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 4px; text-shadow: 0 1px 1px rgba(0,0,0,0.3); width: 100%;">
              🎨 Mở Canva
            </button>
          </div>
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
  loadDownloadedImages();
  checkChromeStatus();
  chromeStatusInterval = setInterval(checkChromeStatus, 4000);
  checkAppUpdate(true);
  startPoll();
</script>
<!-- Modal them/sua prompt -->
<div id="promptModal" class="modal-overlay" style="display: none; position: fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.6); backdrop-filter:blur(4px); z-index:9999; justify-content:center; align-items:center;">
  <div class="panel" style="width: 460px; padding: 24px; display: flex; flex-direction: column; gap: 16px; border: 1px solid var(--panel-border); box-shadow: 0 20px 25px -5px rgb(0 0 0 / 0.5); background: var(--bg);">
    <h3 id="promptModalTitle" style="font-family: 'Plus Jakarta Sans', sans-serif; font-weight: 700; margin: 0 0 4px 0; font-size: 18px;">Thêm Prompt Mới</h3>
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
    <h3 style="font-family: 'Plus Jakarta Sans', sans-serif; font-weight: 700; margin: 0 0 4px 0; font-size: 18px;">Quản Lý Danh Mục</h3>
    
    <div style="font-size: 11px; color: var(--muted); margin-bottom: 2px; line-height: 1.4;">
      * Lưu ý: Khi đổi tên hoặc xóa danh mục, các prompt mẫu thuộc danh mục đó sẽ được tự động đồng bộ hóa tương ứng.
    </div>

    <div id="categoriesListContainer" style="display: flex; flex-direction: column; gap: 10px; max-height: 280px; overflow-y: auto; padding-right: 4px; margin-bottom: 4px;">
      <!-- Danh sach danh muc se duoc render bang JS -->
    </div>
    
    <button type="button" class="secondary" onclick="addCategoryRowInModal()" style="width: 100%; min-height: 36px; font-weight: 600; font-size: 13px; display: flex; align-items: center; justify-content: center; gap: 6px;">
      ➕ Thêm danh mục mới
    </button>
    
    <div style="display: flex; justify-content: flex-end; gap: 12px; margin-top: 8px; border-top: 1px solid var(--panel-border); padding-top: 16px;">
      <button type="button" class="secondary" onclick="closeCategoryModal()" style="min-height: 36px; padding: 0 16px; font-size: 13px; font-weight: 600;">Hủy</button>
      <button type="button" class="btn-capture" onclick="saveCategoriesFromModal()" style="min-height: 36px; padding: 0 20px; font-size: 13px; font-weight: 700;">Lưu thay đổi</button>
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


def load_config() -> dict[str, Any]:
    with CONFIG_LOCK:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def save_config(config: dict[str, Any]) -> None:
    with CONFIG_LOCK:
        temp_path = CONFIG_PATH.with_suffix(".json.tmp")
        temp_path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(temp_path, CONFIG_PATH)


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


def list_drive_folders() -> list[str]:
    root = validate_drive_root(drive_root())
    return sorted((path.name for path in root.iterdir() if path.is_dir()), key=str.casefold)


def validate_folder_name(name: str) -> str:
    cleaned = name.strip().rstrip(". ")
    if not cleaned:
        raise ValueError("Tên thư mục sản phẩm không được để trống.")
    if any(char in cleaned for char in '<>:"/\\|?*'):
        raise ValueError("Tên thư mục chứa ký tự không hợp lệ trên Windows.")
    if cleaned in {".", ".."}:
        raise ValueError("Tên thư mục không hợp lệ.")
    return cleaned


def selected_drive_folder(requested: str | None = None) -> Path:
    root = validate_drive_root(drive_root())
    name = validate_folder_name((requested or selected_folder_name()).strip())
    target = (root / name).resolve()
    if target.parent != root or not target.is_dir():
        raise ValueError("Thư mục sản phẩm không tồn tại. Hãy quét lại và chọn đúng thư mục.")
    return target


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
    rendered_html = HTML.replace('const CURRENT_VERSION = "v1.1.0";', f'const CURRENT_VERSION = "{CURRENT_VERSION}";')
    rendered_html = rendered_html.replace('<span id="updateAppText">v1.1.0</span>', f'<span id="updateAppText">{CURRENT_VERSION}</span>')
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
        "selected_folder": selected_folder_name(), 
        "folders": folders, 
        "operation_busy": OPERATION_LOCK.locked(),
        "connection_mode": connection_mode,
        "wifi_ip": wifi_ip,
        "scrcpy_running": scrcpy_running,
        "adb_path": pixel_cfg.get("adb_path", ""),
        "scrcpy_path": pixel_cfg.get("scrcpy_path", "")
    })


@app.post("/api/drive-root")
def api_drive_root():
    try:
        value = str((request.json or {}).get("drive_root", "")).strip()
        root = validate_drive_root(Path(value).expanduser())
        save_path_setting("drive_root_dir", str(root))
        save_path_setting("selected_drive_folder", "")
        return jsonify({"status": "Đã lưu thư mục Drive.", "drive_root": str(root), "folders": list_drive_folders()})
    except Exception as exc:
        return error_response(exc, 400)


@app.post("/api/folders")
def api_create_folder():
    try:
        root = validate_drive_root(drive_root())
        name = validate_folder_name(str((request.json or {}).get("name", "")))
        target = root / name
        created = not target.exists()
        target.mkdir(exist_ok=True)
        if not target.is_dir():
            raise ValueError("Đường dẫn đã tồn tại nhưng không phải thư mục.")
        save_path_setting("selected_drive_folder", name)
        return jsonify({"status": "Đã tạo thư mục." if created else "Thư mục đã tồn tại, app đã chọn lại.", "folder": name, "path": str(target)})
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
        if any(target.iterdir()):
            raise ValueError("Thư mục không rỗng. Hãy kiểm tra và di chuyển hoặc xóa file bên trong trước.")
        target.rmdir()
        if selected_folder_name() == target.name:
            save_path_setting("selected_drive_folder", "")
        add_event({"step": "folder_deleted", "message": "Đã xóa thư mục rỗng.", "folder": target.name})
        return jsonify({"status": "Đã xóa thư mục rỗng.", "folder": target.name})
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


@app.post("/api/utils/select-directory")
def api_select_directory():
    try:
        import tkinter as tk
        from tkinter import filedialog
        
        # Tạo cửa sổ gốc ẩn
        root = tk.Tk()
        root.withdraw()
        # Đưa lên phía trước
        root.attributes('-topmost', True)
        
        selected_dir = filedialog.askdirectory(title="Chọn thư mục xuất hình")
        root.destroy()
        
        if selected_dir:
            return jsonify({"directory": os.path.normpath(selected_dir)})
        else:
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

def load_prompts():
    if not PROMPTS_FILE.exists():
        return []
    try:
        with open(PROMPTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_prompts(prompts_list):
    try:
        with open(PROMPTS_FILE, "w", encoding="utf-8") as f:
            json.dump(prompts_list, f, ensure_ascii=False, indent=2)
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

        if not download_url:
            download_url = release_data.get("zipball_url", "")

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
                page.wait_for_selector("#prompt-textarea", timeout=15000)
            except Exception:
                add_event({"step": "error", "message": "Không tìm thấy ô nhập liệu '#prompt-textarea'. Vui lòng kiểm tra lại trang web ChatGPT."})
                return
                
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
                page.focus("#prompt-textarea")
                page.click("#prompt-textarea")
                # Điền nội dung prompt bằng innerHTML và phát sự kiện input để kích hoạt React state của ChatGPT
                page.evaluate("""(text) => {
                    const el = document.getElementById("prompt-textarea");
                    if (el) {
                        el.innerHTML = `<p>${text}</p>`;
                        el.dispatchEvent(new Event("input", { bubbles: true }));
                    }
                }""", prompt_text)
                time.sleep(0.5)
                # Nhấn Space và Backspace để React chắc chắn nhận diện thay đổi state
                page.keyboard.press("Space")
                page.keyboard.press("Backspace")
                time.sleep(1.5)
            except Exception as e_fill:
                print(f"[ChatGPT Auto] Lỗi điền prompt bằng evaluate: {e_fill}")
                page.fill("#prompt-textarea", prompt_text)
                time.sleep(1.5)
            
            # Đếm số ảnh lớn hiện có trên toàn trang trước khi gửi prompt mới
            initial_img_count = 0
            try:
                initial_img_count = page.evaluate("""() => {
                    const imgs = Array.from(document.querySelectorAll('img'));
                    const largeImgs = imgs.filter(img => {
                        const w = img.naturalWidth || img.width;
                        const h = img.naturalHeight || img.height;
                        if (w < 200 || h < 200) return false;
                        if (img.src.startsWith('data:image/svg')) return false;
                        return true;
                    });
                    return largeImgs.length;
                }""")
                print(f"[ChatGPT Auto] So luong anh lon ban dau: {initial_img_count}")
            except Exception as e_count:
                print(f"[ChatGPT Auto] Loi dem anh ban dau: {e_count}")
            
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
                
                # Nếu không click được, thử nhấn Enter
                if not clicked:
                    try:
                        page.focus("#prompt-textarea")
                        page.click("#prompt-textarea")
                        page.keyboard.press("Enter")
                        add_event({"step": "chatgpt_automation", "message": f"[Lần {attempt}] Đã gửi lệnh phím Enter."})
                        clicked = True
                    except Exception as press_ex:
                        print(f"[ChatGPT Auto] Lỗi phím Enter: {press_ex}")
                        try:
                            page.press("#prompt-textarea", "Enter", timeout=1500)
                            clicked = True
                        except Exception:
                            pass
                
                # Đợi 2 giây để kiểm tra xem tin nhắn đã gửi đi chưa (ô chat trống)
                time.sleep(2.0)
                
                # Kiểm tra xem ô chat có trống rỗng không
                try:
                    textarea_val = page.evaluate('document.getElementById("prompt-textarea") ? document.getElementById("prompt-textarea").innerText.trim() : ""')
                    # Nếu ô chat trống trơn, tức là đã gửi đi thành công!
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
            
            # Quét định kỳ để phát hiện ảnh mới
            start_time = time.time()
            found_image = False
            image_base64_data = None
            
            while time.time() - start_time < 240: # Tăng timeout lên 240 giây (4 phút)
                time.sleep(3.0)
                try:
                    res = page.evaluate("""async (prevCount) => {
                        const imgs = Array.from(document.querySelectorAll('img'));
                        const largeImgs = imgs.filter(img => {
                            const w = img.naturalWidth || img.width;
                            const h = img.naturalHeight || img.height;
                            if (w < 200 || h < 200) return false;
                            if (img.src.startsWith('data:image/svg')) return false;
                            return true;
                        });
                        
                        if (largeImgs.length <= prevCount) {
                            return "waiting";
                        }
                        
                        const lastImg = largeImgs[largeImgs.length - 1];
                        if (!lastImg.complete || lastImg.naturalWidth === 0) {
                            return "loading";
                        }
                        
                        try {
                            const response = await fetch(lastImg.src);
                            const blob = await response.blob();
                            return await new Promise((resolve, reject) => {
                                const reader = new FileReader();
                                reader.onloadend = () => resolve(reader.result);
                                reader.onerror = () => reject(new Error('FileReader error'));
                                reader.readAsDataURL(blob);
                            });
                        } catch (err) {
                            try {
                                const canvas = document.createElement('canvas');
                                canvas.width = lastImg.naturalWidth || lastImg.width;
                                canvas.height = lastImg.naturalHeight || lastImg.height;
                                const ctx = canvas.getContext('2d');
                                ctx.drawImage(lastImg, 0, 0);
                                return canvas.toDataURL('image/png');
                            } catch (canvasErr) {
                                return 'error: ' + err.message + ' | canvas: ' + canvasErr.message;
                            }
                        }
                    }""", initial_img_count)
                    
                    if res == "waiting" or res == "loading":
                        continue
                    elif res and res.startswith("error:"):
                        continue
                    elif res and res.startswith("data:image/"):
                        image_base64_data = res
                        found_image = True
                        break
                except Exception:
                    continue
            
            if found_image and image_base64_data:
                add_event({"step": "chatgpt_automation", "message": "Đã phát hiện ảnh kết quả mới từ ChatGPT. Đang tải về..."})
                
                header, encoded = image_base64_data.split(",", 1)
                img_data = base64.b64decode(encoded)
                
                num = get_image_number_from_title(prompt_title)
                filename = f"{num}.png"
                
                out_dir = Path(export_dir)
                if not out_dir.exists():
                    out_dir.mkdir(parents=True, exist_ok=True)
                
                dest_path = out_dir / filename
                dest_path.write_bytes(img_data)
                
                add_event({
                    "step": "chatgpt_done", 
                    "message": f"Tải ảnh thành công! Đã lưu file: {filename}",
                    "file_path": str(dest_path),
                    "filename": filename
                })
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
                        
        # 3. Xóa file chatgpt_* và gemini_* trong export_dir
        config = load_config()
        export_dir = config.get("openai", {}).get("export_dir", "").strip()
        if not export_dir:
            export_dir = str(Path.home() / "Downloads")
        out_dir = Path(export_dir)
        if out_dir.exists():
            for ext in ("*.png", "*.jpg", "*.jpeg", "*.mp4", "*.webm"):
                for f in out_dir.glob(ext):
                    name_lower = f.name.lower()
                    is_numbered = re.match(r'^[1-9]\.(png|jpg|jpeg|mp4|webm|mov)$', name_lower) is not None
                    if name_lower.startswith("chatgpt_") or name_lower.startswith("gemini_") or is_numbered:
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
        config = load_config()
        export_dir = config.get("openai", {}).get("export_dir", "").strip()
        if not export_dir:
            export_dir = str(Path.home() / "Downloads")
            
        out_dir = Path(export_dir)
        if not out_dir.exists():
            return jsonify([])
            
        img_files = []
        for ext in ("*.png", "*.jpg", "*.jpeg", "*.mp4", "*.webm"):
            for f in out_dir.glob(ext):
                name_lower = f.name.lower()
                is_numbered = re.match(r'^[1-9]\.(png|jpg|jpeg|mp4|webm|mov)$', name_lower) is not None
                if name_lower.startswith("chatgpt_") or name_lower.startswith("gemini_") or is_numbered:
                    img_files.append(f)
                    
        img_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        
        results = []
        for f in img_files[:24]:
            results.append({
                "name": f.name,
                "file_path": str(f),
                "url": f"/api/automation/images/view?name={f.name}",
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
            
        config = load_config()
        export_dir = config.get("openai", {}).get("export_dir", "").strip()
        if not export_dir:
            export_dir = str(Path.home() / "Downloads")
            
        return send_from_directory(export_dir, filename)
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
            "MOCK_MODE": "True"
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
        
        env_file.write_text("\n".join(lines), encoding="utf-8")
        
        # Nạp lại env cho các luồng hiện tại bằng cách gọi load_dotenv
        from dotenv import load_dotenv
        load_dotenv(env_file, override=True)
        
        return jsonify({"success": True, "message": "Đã lưu cấu hình Notion & Telegram thành công!"})
    except Exception as exc:
        return error_response(exc, 400)

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
            
        # Thiết lập thư mục export Downloads
        config = load_config()
        export_dir = config.get("openai", {}).get("export_dir", "").strip()
        if not export_dir:
            export_dir = str(Path.home() / "Downloads")
            
        os.environ["BIGSELLER_EXPORT_DIR"] = export_dir
        
        shopee_sync_active = True
        add_event({"step": "shopee_sync", "message": "Bắt đầu tiến trình đồng bộ Notion -> BigSeller thủ công..."})
        
        def run_sync_wrapper():
            global shopee_sync_active
            try:
                excel_path, titles = notion_sync.sync_notion_to_bigseller_excel()
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
                
        shopee_sync_thread = threading.Thread(target=run_sync_wrapper, daemon=True)
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
            
        out_dir = Path(export_dir)
        if not out_dir.exists():
            return jsonify([])
            
        excel_files = []
        for f in out_dir.glob("bigseller_sync_*.xlsx"):
            excel_files.append(f)
            
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


def start_media_watcher():
    threading.Thread(target=media_watcher_loop, daemon=True).start()


if __name__ == "__main__":
    cleanup_old_instances()
    start_media_watcher()
    threading.Thread(target=launch_desktop_gui, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8765")), debug=False, threaded=True)
