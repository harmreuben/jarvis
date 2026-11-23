import json
import os

def get_api():
    try:
      
        with open('config/config.json') as config_file:
            config = json.load(config_file)
            API = config.get('GROQ_API')
            if API is None:
                raise ValueError("GROQ_API URL not found in config file")
            return API
    except FileNotFoundError:
        print("Config file not found.")
    except json.JSONDecodeError:
        print("Error decoding JSON in config file.")
    except Exception as e:
        print(f"Error reading config file: {e}")
    return None

_groq_key = get_api()
if not _groq_key:
    raise SystemExit("Put your Groq API key in config/config.json (GROQ_API) before starting JARVIS.")
os.environ['GROQ_API'] = _groq_key

# Imports below need GROQ_API to already be set, so they come after the config is loaded.
import threading
import base64
from threading import Lock
import mtranslate as mt
import eel
import pyautogui
from dotenv import load_dotenv
load_dotenv()
from backend.modules.automodel import Operate
from backend.modules.basic.listenpy import Listen
from backend.modules.extra import GuiMessagesConverter, LoadMessages

def run_docker():
    """Starts the optional Perplexica search stack. JARVIS keeps working if Docker is not installed or not running."""
    import shutil, subprocess
    if not shutil.which("docker"):
        print("Docker not found - Perplexica web search is disabled (optional).")
        return
    try:
        subprocess.run(["docker", "compose", "up", "-d"], cwd=os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend", "AI", "Perplexica"), check=False)
    except Exception as e:
        print(f"Could not start Perplexica with Docker: {e}")

thread = threading.Thread(target=run_docker)
thread.start()

load_dotenv()
state = 'Available...'
messages = LoadMessages()
WEBCAM = False
js_messageslist = []
working: list[threading.Thread] = []
InputLanguage = os.environ['InputLanguage']
Username = os.environ['NickName']
lock = Lock()

def UniversalTranslator(Text: str) -> str:
    """Translates text to English."""
    english_translation = mt.translate(Text, 'en', 'auto')
    return english_translation.capitalize()

def MainExecution(Query: str):
    """Main execution function for handling user queries."""
    global WEBCAM, state
    Query = UniversalTranslator(Query) if 'en' not in InputLanguage.lower() else Query.capitalize()

    if state != 'Available...':
        return
    state = 'Thinking...'
    Decision = Operate(Query)

    if 'realtime-webcam' in Decision:
        python_call_to_start_video()
        print('Video Started')
        WEBCAM = True
    elif 'close_webcam' in Decision:
        print('Video Stopped')
        python_call_to_stop_video()
        WEBCAM = False

    return Decision

@eel.expose
def js_messages():
    """Fetches new messages to update the GUI."""
    global messages, js_messageslist
    with lock:
        messages = LoadMessages()
    if js_messageslist != messages:
        new_messages = GuiMessagesConverter(messages[len(js_messageslist):])
        js_messageslist = messages
        return new_messages
    return []

@eel.expose
def js_state(stat=None):
    """Updates or retrieves the current state."""
    global state
    if stat:
        state = stat
    return state

@eel.expose
def js_mic(transcription):
    """Handles microphone input."""
    print(transcription)
    if not working:
        work = threading.Thread(target=process_input, args=(transcription,), daemon=True)
        work.start()
        working.append(work)
    else:
        if working[0].is_alive():
            return
        working.pop()
        work = threading.Thread(target=process_input, args=(transcription,), daemon=True)
        work.start()
        working.append(work)

def process_input(transcription):
    global WEBCAM
    result = MainExecution(transcription)
    if result == "close_webcam":
        print('Video Stopped')
        python_call_to_stop_video()
        WEBCAM = False

@eel.expose
def python_call_to_start_video():
    """Starts the video capture."""
    eel.startVideo()

@eel.expose
def python_call_to_stop_video():
    """Stops the video capture."""
    eel.stopVideo()

@eel.expose
def python_call_to_capture():
    """Captures an image from the video."""
    eel.capture()

@eel.expose
def handle_captured_image(image_data):
    """Handles the captured image data from the web interface."""
    js_capture(image_data)

@eel.expose
def js_page(cpage=None):
    """Navigates to the specified page."""
    if cpage == 'home':
        eel.openHome()
    elif cpage == 'settings':
        eel.openSettings()

@eel.expose
def setup():
    """Sets up the GUI window."""
    pyautogui.hotkey('win', 'up')

@eel.expose
def js_language():
    """Returns the input language."""
    return str(InputLanguage)

@eel.expose
def js_assistantname():
    """Returns the assistant's name."""
    return "JARVIS"

@eel.expose
def js_capture(image_data):
    """Saves the captured image."""
    image_bytes = base64.b64decode(image_data.split(',')[1])
    with open('capture.png', 'wb') as f:
        f.write(image_bytes)

# Initialize Eel and start the application
eel.init('web')
eel.start('spider.html', port=44444)