"""Web search, reading web pages (including the one open in your browser) and downloads."""
import os
import re
import time
import urllib.parse
import webbrowser

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/130.0 Safari/537.36", "Accept-Language": "en-US,en;q=0.9"}


def search(query: str, max_results: int = 6) -> str:
    from ddgs import DDGS
    results = DDGS().text(query, max_results=max_results)
    if not results:
        return "No web results found."
    return "\n\n".join(f"[{i + 1}] {r.get('title', '')}\n{r.get('body', '')}\n{r.get('href', '')}" for i, r in enumerate(results))


def google(query: str) -> str:
    webbrowser.open("https://www.google.com/search?q=" + urllib.parse.quote_plus(query))
    return f"Here are the Google results for {query}."


def current_browser_url() -> str:
    """Copies the address of the active browser tab (Chrome, Edge, Firefox...) without losing the clipboard."""
    import pyautogui
    import pyperclip
    try:
        previous = pyperclip.paste()
    except Exception:
        previous = None
    pyperclip.copy("")
    pyautogui.hotkey("ctrl", "l")
    time.sleep(0.25)
    pyautogui.hotkey("ctrl", "c")
    time.sleep(0.25)
    pyautogui.press("esc")
    url = (pyperclip.paste() or "").strip()
    if previous is not None:
        try:
            pyperclip.copy(previous)
        except Exception:
            pass
    if not re.match(r"^https?://", url):
        if re.match(r"^[\w.-]+\.[a-z]{2,}(/|$)", url):
            url = "https://" + url
        else:
            raise RuntimeError("I couldn't read the address of a web page. Click on your browser window first, then ask again.")
    return url


def page_text(url: str, max_chars: int = 12000) -> str:
    import requests
    from bs4 import BeautifulSoup
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    ctype = r.headers.get("Content-Type", "")
    if "pdf" in ctype:
        import fitz
        with fitz.open(stream=r.content, filetype="pdf") as doc:
            text = "\n".join(p.get_text() for p in doc)
    else:
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "noscript", "header", "footer", "nav", "svg", "form"]):
            tag.decompose()
        title = soup.title.get_text(strip=True) if soup.title else ""
        main = soup.find("article") or soup.find("main") or soup.body or soup
        text = (title + "\n\n" if title else "") + main.get_text("\n", strip=True)
    text = re.sub(r"\n{2,}", "\n", text)
    return f"Page: {url}\n\n" + (text[:max_chars] + "\n...(truncated)" if len(text) > max_chars else text)


def read_current_page() -> str:
    return page_text(current_browser_url())


def download(url: str) -> str:
    import requests
    folder = os.path.join(os.path.expanduser("~"), "Downloads")
    os.makedirs(folder, exist_ok=True)
    with requests.get(url, headers=HEADERS, stream=True, timeout=30) as r:
        r.raise_for_status()
        name = ""
        cd = r.headers.get("Content-Disposition", "")
        m = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', cd)
        if m:
            name = urllib.parse.unquote(m.group(1))
        if not name:
            name = os.path.basename(urllib.parse.urlparse(url).path) or "download"
        name = re.sub(r'[<>:"/\\|?*]+', "_", name)
        path = os.path.join(folder, name)
        base, ext = os.path.splitext(path)
        n = 1
        while os.path.exists(path):
            path = f"{base} ({n}){ext}"
            n += 1
        with open(path, "wb") as f:
            for chunk in r.iter_content(1 << 16):
                f.write(chunk)
    return f"Downloaded to {path}"
