"""Text-to-speech: Microsoft Edge neural voices (online), with the built-in Windows voice as offline fallback."""
import asyncio
import os
import re
import subprocess
import sys
import tempfile
import threading
import time

_speak_lock = threading.Lock()
_mixer_ready = False


def clean_for_speech(text: str) -> str:
    text = re.sub(r"```.*?```", " (code shown on screen) ", text, flags=re.DOTALL)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[*_#`>|]+", "", text)
    return re.sub(r"\s+", " ", text).strip()


def shorten_for_speech(text: str, limit: int = 450) -> str:
    """Long answers: read the first two sentences aloud, the full text stays on screen."""
    if len(text) <= limit:
        return text
    sentences = re.split(r"(?<=[.!?])\s+", text)
    short = " ".join(sentences[:3])
    if len(short) > limit:
        short = short[:limit].rsplit(" ", 1)[0] + "."
    return short + " The rest is on the screen."


_stop = threading.Event()
_proc = None  # running Windows-voice process, so it can be stopped


def stop() -> None:
    """Stops whatever JARVIS is saying right now."""
    _stop.set()
    try:
        import pygame
        if _mixer_ready:
            pygame.mixer.music.stop()
    except Exception:
        pass
    p = _proc
    if p is not None and p.poll() is None:
        p.kill()


def _chunks(text: str, size: int = 180):
    """Splits text into sentence groups so speech can start before the whole reply is synthesized."""
    sentences = re.split(r"(?<=[.!?;:])\s+", text)
    out, cur = [], ""
    for s in sentences:
        if cur and len(cur) + len(s) > size:
            out.append(cur)
            cur = s
        else:
            cur = (cur + " " + s).strip()
    if cur:
        out.append(cur)
    return out


def _play_mp3(path: str) -> None:
    global _mixer_ready
    import pygame
    if not _mixer_ready:
        pygame.mixer.init()
        _mixer_ready = True
    pygame.mixer.music.load(path)
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy() and not _stop.is_set():
        time.sleep(0.03)
    pygame.mixer.music.stop()
    pygame.mixer.music.unload()


def _synthesize(text: str, voice: str) -> str:
    import edge_tts
    fd, path = tempfile.mkstemp(suffix=".mp3", prefix="jarvis_tts_")
    os.close(fd)
    try:
        asyncio.run(edge_tts.Communicate(text, voice, rate="+10%").save(path))
        if os.path.getsize(path) == 0:
            raise RuntimeError("edge-tts returned no audio")
        return path
    except Exception:
        _remove(path)
        raise


def _remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def _edge_tts_streaming(text: str, voice: str) -> None:
    """Synthesizes sentence groups in the background while earlier ones are already playing."""
    import queue
    parts = _chunks(text)
    q = queue.Queue(maxsize=2)

    def producer():
        for part in parts:
            if _stop.is_set():
                break
            try:
                q.put(("ok", _synthesize(part, voice)))
            except Exception as e:
                q.put(("error", e))
                return
        q.put(("end", None))

    threading.Thread(target=producer, daemon=True).start()
    played = 0
    while True:
        kind, value = q.get()
        if kind == "end":
            return
        if kind == "error":
            if played == 0:
                raise value  # nothing spoken yet: let the caller use the Windows voice
            print(f"[voice] online voice stopped mid-reply: {value}")
            return
        try:
            if not _stop.is_set():
                _play_mp3(value)
                played += 1
        finally:
            _remove(value)
        if _stop.is_set():
            # drain anything already synthesized
            while True:
                kind, value = q.get()
                if kind == "ok":
                    _remove(value)
                else:
                    return


def _windows_tts(text: str) -> subprocess.CompletedProcess:
    global _proc
    script = ("[Console]::InputEncoding = [System.Text.Encoding]::UTF8; "
              "Add-Type -AssemblyName System.Speech; "
              "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
              "$s.Speak([Console]::In.ReadToEnd())")
    _proc = subprocess.Popen(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                             stdin=subprocess.PIPE, text=True, encoding="utf-8",
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        _proc.communicate(text, timeout=180)
    except subprocess.TimeoutExpired:
        _proc.kill()
    rc = _proc.returncode
    _proc = None
    return subprocess.CompletedProcess([], rc if not _stop.is_set() else 0)


def speak(text: str, voice: str = "en-GB-RyanNeural") -> bool:
    """Speaks the text. Returns True if audio was played (or stopped on request), False if no voice was available."""
    text = clean_for_speech(shorten_for_speech(str(text)))
    if not text:
        return True
    with _speak_lock:
        _stop.clear()
        try:
            _edge_tts_streaming(text, voice)
            return True
        except Exception as e:
            print(f"[voice] Online voice unavailable ({e}); using the Windows voice.")
        if _stop.is_set():
            return True
        if sys.platform == "win32":
            try:
                result = _windows_tts(text)
                if result.returncode == 0:
                    return True
                print(f"[voice] Windows voice failed (exit code {result.returncode}).")
            except Exception as e:
                print(f"[voice] Windows voice failed: {e}")
        return False
