# jarvis
My Personal Ai System

A hands-free JARVIS voice assistant for **Windows 10/11**. Say *"Jarvis, …"* and it answers, searches the web,
controls your PC, works with your files, sends WhatsApp messages and email, and sets reminders.

This is a working, rebuilt version of [Likhithsai2580/JARVIS-MARK5](https://github.com/Likhithsai2580/JARVIS-MARK5)
(MIT licence). The original code could not start; this version replaces its core with a new Groq-powered brain,
a hands-free voice interface and a one-click Windows installer.

## Install

1. Click **Code → Download ZIP** above, unzip it, and move the `jarvis-main` folder somewhere short,
   e.g. `C:\Users\<you>\jarvis`.
2. Double-click **`setup_windows.bat`**. It installs Python 3.12 if needed and everything else, then asks for a
   free API key from [console.groq.com/keys](https://console.groq.com/keys).
3. Start JARVIS from the **JARVIS** icon it puts on your desktop.

## Update

Close JARVIS and double-click **`update_jarvis.bat`**. It downloads the latest version from this repository and
keeps your settings, contacts, reminders and chat history.

## Use

- Hands-free: it listens as soon as it opens. Start commands with **"Jarvis"**; say **"Jarvis, stop"** to interrupt.
  **Ctrl+Space** turns listening on/off. You can also type.
- Five interfaces (Iron Man HUD, Chat app, Minimal orb, Terminal, Classic): pick one in **Settings (⚙)**.
- Deleting files, sending messages, shutting down and running generated code always ask **Yes/No** first.

Full list of commands, email/WhatsApp setup and troubleshooting: **[SETUP_WINDOWS.md](SETUP_WINDOWS.md)**.
If something goes wrong, run **`check_setup.bat`**; `jarvis.log` records what JARVIS did and how long each step took.

## Requirements

Windows 10/11 64-bit, a microphone and speakers, internet, Chrome or Edge, and a free Groq API key.

## Credits

- Original project: [Likhithsai2580/JARVIS-MARK5](https://github.com/Likhithsai2580/JARVIS-MARK5), MIT licence
  (see [LICENSE](LICENSE); original README in [docs/ORIGINAL_README.md](docs/ORIGINAL_README.md)).
- Classic interface artwork is downloaded during setup from [Divy0The0Fire/J4E](https://github.com/Divy0The0Fire/J4E)
  and is not part of this repository.
