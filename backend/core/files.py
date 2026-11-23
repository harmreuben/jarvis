"""File and folder access for JARVIS. Searches the user's own folders; deleting goes to the Recycle Bin after a Yes."""
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime

from backend.core import actions

HOME = os.path.expanduser("~")
SKIP_DIRS = {"node_modules", "__pycache__", ".git", "venv", ".venv", "AppData", "site-packages", "$RECYCLE.BIN"}
TEXT_EXT = {".txt", ".md", ".csv", ".json", ".py", ".js", ".html", ".css", ".xml", ".log", ".ini", ".yaml", ".yml", ".bat", ".ps1"}
TYPE_EXT = {
    "pdf": {".pdf"}, "word": {".docx", ".doc"}, "excel": {".xlsx", ".xls", ".csv"}, "powerpoint": {".pptx", ".ppt"},
    "image": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".heic"}, "video": {".mp4", ".mkv", ".avi", ".mov", ".wmv"},
    "music": {".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg"}, "text": TEXT_EXT, "zip": {".zip", ".rar", ".7z"},
    "program": {".exe", ".msi"},
}


def user_folders():
    names = ["Desktop", "Documents", "Downloads", "Pictures", "Music", "Videos"]
    found = [os.path.join(HOME, n) for n in names]
    onedrive = os.environ.get("OneDrive") or os.path.join(HOME, "OneDrive")
    if os.path.isdir(onedrive):
        found += [os.path.join(onedrive, n) for n in ("Desktop", "Documents", "Pictures")] + [onedrive]
    seen, out = set(), []
    for f in found:
        if os.path.isdir(f) and os.path.realpath(f) not in seen:
            seen.add(os.path.realpath(f))
            out.append(f)
    return out


def resolve_folder(name: str) -> str:
    """'desktop', 'downloads', 'documents\\reports', or a full path -> absolute folder path."""
    if not name:
        return os.path.join(HOME, "Documents")
    name = os.path.expandvars(os.path.expanduser(name.strip().strip('"')))
    if os.path.isabs(name):
        return name
    first, _, rest = name.replace("/", "\\").partition("\\")
    for base in user_folders():
        if os.path.basename(base).lower() == first.lower().replace("my ", ""):
            return os.path.join(base, rest) if rest else base
    return os.path.join(HOME, "Documents", name)


def _score(name: str, words) -> int:
    n = name.lower()
    stem = os.path.splitext(n)[0]
    if stem == " ".join(words):
        return 100
    return sum(10 for w in words if w in n) - len(n) // 40


def find(query: str, folder: str = "", file_type: str = "", limit: int = 10, max_seconds: float = 8.0):
    """Returns a list of (path, modified time) best matching the name words, newest first among equals."""
    import time
    words = [w for w in re.split(r"[\s_\-.]+", (query or "").lower()) if w and w not in ("the", "my", "file", "a")]
    exts = TYPE_EXT.get((file_type or "").lower())
    roots = [resolve_folder(folder)] if folder else user_folders()
    results, deadline = [], time.time() + max_seconds
    for root in roots:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
            for fn in filenames + [d for d in dirnames]:
                if exts and os.path.splitext(fn)[1].lower() not in exts:
                    continue
                score = _score(fn, words) if words else 1
                if score <= 0 or (words and not any(w in fn.lower() for w in words)):
                    continue
                path = os.path.join(dirpath, fn)
                try:
                    results.append((score, os.path.getmtime(path), path))
                except OSError:
                    pass
            if time.time() > deadline:
                break
    results.sort(key=lambda r: (-r[0], -r[1]))
    seen, out = set(), []
    for _, mtime, path in results:
        if path not in seen:
            seen.add(path)
            out.append((path, mtime))
        if len(out) >= limit:
            break
    return out


def locate(path_or_name: str, file_type: str = "") -> str:
    """A full path that exists, or the best search match. Raises FileNotFoundError."""
    p = os.path.expandvars(os.path.expanduser((path_or_name or "").strip().strip('"')))
    if p and os.path.isabs(p) and os.path.exists(p):
        return p
    if p and not os.path.isabs(p):
        candidate = resolve_folder(p)  # 'downloads', 'documents\\reports', ...
        if os.path.exists(candidate):
            return candidate
    hits = find(path_or_name, file_type=file_type, limit=1)
    if not hits:
        raise FileNotFoundError(f"I couldn't find '{path_or_name}' in your Desktop, Documents, Downloads, Pictures, Music or Videos.")
    return hits[0][0]


def describe(paths) -> str:
    lines = []
    for path, mtime in paths:
        lines.append(f"{path}  (modified {datetime.fromtimestamp(mtime):%d %b %Y %H:%M})")
    return "\n".join(lines) if lines else "No matching files found."


def open_path(path_or_name: str) -> str:
    path = locate(path_or_name)
    if sys.platform == "win32":
        os.startfile(path)
    else:
        subprocess.Popen(["xdg-open", path])
    return f"Opening {os.path.basename(path)}."


def read_text(path_or_name: str, max_chars: int = 12000) -> str:
    path = locate(path_or_name)
    ext = os.path.splitext(path)[1].lower()
    if os.path.isdir(path):
        return list_folder(path)
    if ext == ".pdf":
        import fitz
        with fitz.open(path) as doc:
            text = "\n".join(page.get_text() for page in doc)
    elif ext == ".docx":
        import docx
        text = "\n".join(p.text for p in docx.Document(path).paragraphs)
    elif ext == ".pptx":
        from pptx import Presentation
        text = "\n".join(sh.text_frame.text for s in Presentation(path).slides for sh in s.shapes if sh.has_text_frame)
    elif ext in (".xlsx", ".xlsm"):
        import openpyxl
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        rows = []
        for ws in wb.worksheets:
            rows.append(f"## Sheet {ws.title}")
            for row in ws.iter_rows(values_only=True):
                if any(v is not None for v in row):
                    rows.append(" | ".join("" if v is None else str(v) for v in row))
                if len(rows) > 400:
                    break
        text = "\n".join(rows)
    elif ext in TEXT_EXT or os.path.getsize(path) < 200_000:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read(max_chars * 2)
    else:
        return f"I can't read the contents of {os.path.basename(path)} ({ext} files)."
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) > max_chars:
        text = text[:max_chars] + "\n...(truncated)"
    return f"File: {path}\n\n{text or '(the file has no readable text)'}"


def list_folder(folder: str) -> str:
    path = resolve_folder(folder) if not os.path.isdir(folder or "") else folder
    if not os.path.isdir(path):
        raise FileNotFoundError(f"The folder {path} doesn't exist.")
    entries = sorted(os.scandir(path), key=lambda e: e.stat().st_mtime, reverse=True)
    lines = [f"{'[folder] ' if e.is_dir() else ''}{e.name}" for e in entries[:60]]
    more = f"\n...and {len(entries) - 60} more" if len(entries) > 60 else ""
    return f"{path} ({len(entries)} items, newest first):\n" + "\n".join(lines) + more


def create_folder(name: str, location: str = "") -> str:
    path = os.path.join(resolve_folder(location or "desktop"), name.strip())
    os.makedirs(path, exist_ok=True)
    return f"Created the folder {path}"


def write_file(name: str, content: str, location: str = "") -> str:
    folder = resolve_folder(location) if location else os.path.join(HOME, "Documents", "JARVIS Notes")
    os.makedirs(folder, exist_ok=True)
    name = re.sub(r'[<>:"/\\|?*]+', "", name.strip()) or f"Note {datetime.now():%Y-%m-%d %H%M}"
    if not os.path.splitext(name)[1]:
        name += ".txt"
    path = os.path.join(folder, name)
    if os.path.exists(path) and not actions.confirm("confirm", f"{path} already exists.\n\nReplace it?"):
        return "Okay, I left the existing file alone."
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"Saved {path}"


def move_copy(source: str, destination: str, mode: str = "move") -> str:
    src = locate(source)
    dest_dir = resolve_folder(destination)
    os.makedirs(dest_dir, exist_ok=True)
    target = os.path.join(dest_dir, os.path.basename(src))
    if os.path.exists(target):
        return f"There's already a {os.path.basename(src)} in {dest_dir}; I didn't overwrite it."
    if mode == "copy":
        (shutil.copytree if os.path.isdir(src) else shutil.copy2)(src, target)
        return f"Copied {os.path.basename(src)} to {dest_dir}."
    shutil.move(src, target)
    return f"Moved {os.path.basename(src)} to {dest_dir}."


def rename(path_or_name: str, new_name: str) -> str:
    src = locate(path_or_name)
    new_name = re.sub(r'[<>:"/\\|?*]+', "", new_name.strip())
    if not os.path.splitext(new_name)[1] and os.path.isfile(src):
        new_name += os.path.splitext(src)[1]
    target = os.path.join(os.path.dirname(src), new_name)
    if os.path.exists(target):
        return f"{new_name} already exists there."
    os.rename(src, target)
    return f"Renamed {os.path.basename(src)} to {new_name}."


def delete(path_or_name: str) -> str:
    path = locate(path_or_name)
    if os.path.realpath(path) in {os.path.realpath(p) for p in user_folders() + [HOME]}:
        return "I won't delete one of your main folders."
    if not actions.confirm("confirm delete", f"Move this to the Recycle Bin?\n\n{path}"):
        return "Okay, I didn't delete it."
    from send2trash import send2trash
    send2trash(path)
    return f"Moved {os.path.basename(path)} to the Recycle Bin."
