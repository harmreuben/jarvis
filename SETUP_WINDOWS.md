# JARVIS-MARK5 (repaired) - Windows 11 setup

## Install (once)

1. Download it from https://github.com/harmreuben/jarvis (Code -> Download ZIP), unzip it, and put the `jarvis-main` folder somewhere simple, for example `C:\Users\<you>\jarvis`
   (a short path outside OneDrive is best).
2. Double-click **`setup_windows.bat`**. It will:
   - install Python 3.12 if it's missing (using winget),
   - create a private Python environment in the `venv` folder and install all packages
     (about 1-2 GB the first time, 5-15 minutes),
   - open https://aistudio.google.com/apikey so you can create a **free Google Gemini API key** and ask you to paste it
     (or press Enter to use a free Groq key from https://console.groq.com/keys instead; you can add both),
   - run a self-test and put a **JARVIS** shortcut on your desktop.
3. If Windows SmartScreen warns about the .bat file, click "More info" -> "Run anyway".

You can run `setup_windows.bat` again at any time; it repairs or updates the install.

## Use

- Start JARVIS with the **JARVIS** desktop icon (or `run_jarvis.bat`). It opens in Chrome
  (or Edge if Chrome isn't installed). Closing that window stops JARVIS.
- **It's hands-free:** JARVIS starts listening as soon as it opens. The first time, click **Allow**
  for the microphone (if it asks you to, click anywhere in the window first).
- **Start every voice command with "Jarvis"**: "Jarvis, open YouTube". Anything said without
  "Jarvis" is ignored, so people talking nearby won't trigger it. You can also say just "Jarvis",
  wait for "Yes?", then say the command.
- **Ctrl+Space** (or clicking the mic) turns listening off and on.
- **Type:** use the text box. Typed commands don't need "Jarvis".
- Change the interface, your AI keys and provider, your name, the speech language or the wake word under **Settings** (⚙).
- To make every phrase a command (no wake word), set `"REQUIRE_WAKE_WORD": false` in `config\config.json`.

## Interfaces

Open **Settings** (the ⚙ button, or type `/settings`) and pick an interface. It switches immediately and is remembered:

| Interface | Look |
|---|---|
| **Iron Man HUD** (default) | Arc-reactor core that pulses with your voice and when JARVIS talks, clock, live CPU/memory/battery, conversation panel |
| **Chat app** | Clean chat bubbles with a light/dark switch - best for reading long answers |
| **Minimal orb** | Just a glowing orb that reacts to sound, with live captions (⌨ button to type) |
| **Terminal** | Green sci-fi console with typing effect; `/help`, `/clear`, `/mic`, `/settings` |
| **Classic** | The original JARVIS-MARK5 screen |

All interfaces work the same way: hands-free "Jarvis, ..." voice, Ctrl+Space, typing, and the same settings.

## What JARVIS can do

Start voice commands with "Jarvis". Say **"Jarvis, stop"** at any time to cut it off. Anything risky
(deleting, sending messages, shutting down, running code) shows a **Yes/No box** first; nothing happens unless you click Yes.

| Area | Examples |
|---|---|
| Questions | "Who invented the telephone?", "explain black holes simply" |
| Web | "What's the weather in Nairobi?", "latest football scores", "open github.com", "google cheap flights to Mombasa", "play Sauti Sol on YouTube" |
| The page you're on | "Summarise this page", "what does this article say about prices?" (click your browser first) |
| Downloads | "Download https://example.com/file.pdf" (saved to Downloads) |
| Apps & windows | "Open Spotify", "close Chrome", "switch to Word", "minimize this", "show the desktop" |
| Keyboard & mouse | "Type: I'll be there at 5", "press ctrl+s", "scroll down", "click on Submit" |
| Media & sound | "Pause the music", "next song", "volume 40", "mute" |
| Windows | "Brightness 70", "dark mode", "move the taskbar left", "open Wi-Fi settings", "lock the PC", "sleep", "shut down" / "cancel shutdown", "how much battery / disk space do I have?" |
| Screen & camera | "What's on my screen?", "explain this error", "what am I holding?", "take a screenshot" |
| Files & folders | "Find my CV", "open the budget spreadsheet", "read my report and summarise it" (PDF, Word, Excel, PowerPoint, text), "what's in my Downloads?", "make a folder called Invoices on the desktop", "move the report to Documents", "rename notes to groceries", "delete old_junk.txt" (Recycle Bin), "write a note: buy milk" |
| Contacts | "Save John's number as +254712345678", "save John's email as john@example.com", "list my contacts" |
| WhatsApp | "Send John a WhatsApp: running late" (uses WhatsApp Desktop, or WhatsApp Web if not installed) |
| Email | "Email John: meeting moved to 3pm", "check my email", "any new emails?" |
| Reminders | "Remind me to call mom at 6pm", "set a timer for 10 minutes", "what are my reminders?", "cancel the mom reminder" |
| Office | "Make a presentation about solar energy" |
| Anything else | "Put all the PDFs in Downloads into a folder called PDFs" - JARVIS writes a small program and shows it to you before running |

### Setting up messages and email (optional)
- **WhatsApp**: install WhatsApp Desktop from the Microsoft Store and log in. Save contacts by voice, or enter your
  phone **country code** in Settings so numbers starting with 0 work.
- **Email (Gmail)**: turn on 2-Step Verification, then create an app password at https://myaccount.google.com/apppasswords.
  In JARVIS Settings enter your Gmail address and that 16-letter app password. (Yahoo, iCloud and Zoho work the same way.
  Outlook/Hotmail don't allow app passwords any more; for them JARVIS opens a ready-to-send draft in your mail app.)

## AI providers

| Provider | Key | Notes |
|---|---|---|
| **Google Gemini** (recommended) | free at https://aistudio.google.com/apikey | fast, good at PC control, can see your screen and camera |
| **Groq** | free at https://console.groq.com/keys | very fast; free models change over time and currently can't see images |
| **Ollama** (open source, runs on your PC) | no key, no limits | install from https://ollama.com, then in a terminal run `ollama pull qwen3` (and `ollama pull gemma3` for images); tick "Also use Ollama" in Settings. Needs a strong PC (16 GB RAM or a good graphics card) |

Add more than one: JARVIS uses the first that works and switches automatically if one fails or runs out.

## Speed and limits

- JARVIS uses one AI request for most commands, and starts speaking after the first sentence.
- Free AI plans have daily limits per model. When one model runs out, JARVIS switches to the next model, and then to
  your other provider if you've added a second key (Gemini + Groq is a good pair);
  if all are used up it tells you, and the limits reset during the day.
- `jarvis.log` in the JARVIS folder records each request, which tools ran and how long each step took.
  If something is slow or wrong, send that file.

## Updating to a new version

You never need to delete or reinstall JARVIS. Close the JARVIS window and double-click **`update_jarvis.bat`**.

It checks https://github.com/harmreuben/jarvis for a newer version, downloads it, replaces only the
program files, installs any new packages (usually seconds) and keeps your AI keys and other settings, contacts,
reminders and chat history (they live in the `config` folder and `ChatLog.json`, which updates never replace).
If it says "already up to date", you have the latest version.

If the folder is linked to GitHub with git (for example you cloned it or opened it in VS Code), the updater uses
`git pull` instead of downloading a zip, and always re-checks the Python packages afterwards.

Without internet access to GitHub you can still update from a zip: put the `jarvis-main.zip` from GitHub in Downloads
(or drag it onto `update_jarvis.bat`).

## If something doesn't work

- Double-click **`check_setup.bat`**. It tests the API key, AI replies, web search, voice,
  speakers, browser, screen capture and webcam, and says exactly what failed.
- **"API key was rejected"**: create a new key (Gemini: https://aistudio.google.com/apikey, Groq: https://console.groq.com/keys)
  and paste it in Settings.
- **Empty or no AI replies**: run `check_setup.bat`; the "AI provider" line shows which models are in use.
  Adding a second provider's key gives JARVIS a backup.
- **Mic does nothing**: make sure you start with "Jarvis", and that the status under the orb says
  "Listening". Allow microphone access for the JARVIS window (click the lock/mic icon in its address area),
  and check Windows Settings -> Privacy & security -> Microphone. Voice input needs internet.
- **No sound**: check the speaker volume; if the online voice is unreachable JARVIS uses the built-in Windows voice.
- **Webcam questions fail**: Windows Settings -> Privacy & security -> Camera -> allow desktop apps.
- The black console window shows what JARVIS is doing and any errors.

## What changed from the original repository

The original code could not start (syntax error, missing imports, retired AI models, wrong function calls) and
most features depended on dead free APIs. This version:

- uses a free Google Gemini or Groq key (or local Ollama models) for chat, PC control and image understanding, and picks models that are
  currently available on your account automatically (so retired models don't break it);
- shows replies in the window, keeps chat history (`ChatLog.json`), works by voice or text;
- never runs AI-written code without your explicit "Yes";
- no longer needs Docker, PostgreSQL, Ollama, Perplexica or the many unofficial "free GPT" services.
  Their code is still in the repository but is not used. Image generation was removed (it depended on a
  Hugging Face demo that is no longer reliable).
- the original `jarvis.py` is kept at `legacy/jarvis_original.py` for reference.
