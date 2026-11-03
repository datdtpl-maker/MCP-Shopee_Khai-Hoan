import subprocess
import sys
import shutil
import os
from pathlib import Path

def find_or_install_inno_setup():
    """Tim duong dan ISCC.exe cua Inno Setup, hoac tu dong cai dat qua winget neu chua co."""
    # 1. Thu tim trong PATH he thong
    iscc_path = shutil.which("iscc")
    if iscc_path:
        return iscc_path
        
    # 2. Thu kiem tra cac duong dan mac dinh tren Windows
    possible_paths = [
        Path(os.environ.get("LOCALAPPDATA", r"C:\Users\datdt\AppData\Local")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Inno Setup 6" / "ISCC.exe"
    ]
    for p in possible_paths:
        if p.exists():
            return str(p)
            
    # 3. Neu khong tim thay, tien hanh cai dat tu dong bang winget
    print("Khong tim thay Inno Setup tren may. Dang tien hanh cai dat tu dong qua winget...")
    try:
        cmd = [
            "winget", "install", "--id", "jrsoftware.InnoSetup",
            "--silent", "--accept-source-agreements", "--accept-package-agreements"
        ]
        res = subprocess.run(cmd, shell=True)
        if res.returncode == 0:
            print("Cai dat Inno Setup thanh cong!")
            for p in possible_paths:
                if p.exists():
                    return str(p)
        else:
            print(f"Lenh winget cai dat that bai voi ma loi: {res.returncode}")
    except Exception as e:
        print(f"Loi khi goi winget de cai dat Inno Setup: {e}")
        
    return None

def build():
    print("=== BAT DAU TIEN TRINH DONG GOI EXE & SETUP ===")
    
    # 1. Kiem tra PyInstaller
    try:
        import PyInstaller
        print("PyInstaller da duoc cai dat.")
    except ImportError:
        print("Dang cai dat PyInstaller...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)
        print("Cai dat PyInstaller thanh cong.")
        
    # 2. Xac dinh duong dan
    root = Path(__file__).resolve().parent
    spec_file = root / "MCPShopee.spec"
    dist_dir = root / "dist" / "MCPShopee_build"
    
    # Don dep thu muc build cu truoc de tranh loi lock file
    for old_dir in [dist_dir, root / "dist" / "MCPShopee"]:
        if old_dir.exists():
            print(f"Dang don dep thu muc cu tai: {old_dir}...")
            try:
                shutil.rmtree(old_dir)
            except Exception as e:
                print(f"Canh bao: Khong the xoa hoan toan thu muc {old_dir}: {e}")
    
    # 3. Chay lenh PyInstaller voi file spec day du
    print("Dang chay PyInstaller theo MCPShopee.spec...")
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--clean",
        "--noconfirm",
        str(spec_file)
    ]
    
    res = subprocess.run(cmd, shell=False, cwd=str(root))
    
    if res.returncode != 0:
        print("\n=== DONG GOI PYINSTALLER THAT BAI! ===")
        sys.exit(res.returncode)
        
    print("\n=== DONG GOI PYINSTALLER THANH CONG! ===")
    
    # Dam bao cac file cau hinh duoc copy day du vao thu muc dist de copy qua la chay ngay
    files_to_sync = [
        (root / "config.json", dist_dir / "config.json"),
        (root / "config.example.json", dist_dir / "config.example.json"),
        (root / ".env", dist_dir / ".env"),
        (root / "shopee_sync" / ".env", dist_dir / "shopee_sync" / ".env"),
        (root / "content_prompts.json", dist_dir / "content_prompts.json"),
        (root / "run_debug_chrome.bat", dist_dir / "run_debug_chrome.bat"),
    ]
    for src_f, dst_f in files_to_sync:
        if src_f.exists():
            dst_f.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_f, dst_f)
            print(f"[Config Sync] Da dong bo: {src_f.name} -> {dst_f}")

    # 4. Dong goi thanh bo cai dat Setup (.exe) su dung Inno Setup
    iscc_path = find_or_install_inno_setup()
    if iscc_path:
        print(f"\nDang bien dich file Setup bang Inno Setup (ISCC: {iscc_path})...")
        iss_file = root / "installer.iss"
        setup_res = subprocess.run([iscc_path, str(iss_file)], shell=False, cwd=str(root))
        if setup_res.returncode == 0:
            print("\n=== TAO BO CAI DAT SETUP THANH CONG! ===")
            setup_exe = root / "dist" / "MCPShopeeSetup.exe"
            print(f"File cai dat: {setup_exe}")
        else:
            print(f"\n=== LOI: Bien dich Inno Setup that bai! Ma loi: {setup_res.returncode} ===")
    else:
        print("\n=== CANH BAO: Khong tim thay Inno Setup ===")

    # 5. Dong goi ban Portable ZIP de copy qua may khac la dung luon
    print("\nDang tao ban Portable .ZIP...")
    try:
        portable_zip = root / "dist" / "MCPShopee_Windows_Portable"
        shutil.make_archive(str(portable_zip), 'zip', str(dist_dir))
        print(f"Ban Portable ZIP: {portable_zip}.zip")
    except Exception as z_err:
        print(f"Canh bao khi nen file ZIP: {z_err}")

    print("\n=== HOAN TAT TOAN BO TIEN TRINH BUILD! ===")
    print(f"1. Thu muc Portable (chay ngay): {dist_dir}")
    print(f"2. File nen Portable ZIP:        {root / 'dist' / 'MCPShopee_Windows_Portable.zip'}")
    print(f"3. Bo cai dat Windows Setup:     {root / 'dist' / 'MCPShopeeSetup.exe'}")

if __name__ == "__main__":
    build()
