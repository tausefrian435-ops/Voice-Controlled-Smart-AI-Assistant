"""
Voice Rian v5 — Push-to-talk + file upload + URL fetch + interrupt.

Uses gTTS + pygame for audio, native Anthropic PDF/vision support for files,
and requests + BeautifulSoup for fetching web pages.

Controls:
  - HOLD  `      : Record voice while held. Release to send.
  - TAP   `      : Interrupt Claude mid-sentence.
  - PRESS F12    : Open file picker. Queued for next message.
  - PRESS F11    : Open URL dialog. Fetches the page and queues it.
  - SAY  "goodbye" or press CTRL+C to exit.

Supported attachments:
  - Files: .pdf, .jpg/.jpeg/.png/.gif/.webp, plus text/code files
  - URLs: any public web page (works best on news, Wikipedia, blog posts, docs)

To change the keys or limits, edit the constants in the Config section below.
"""

import os
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "hide"

import base64
import tempfile
import time
import tkinter as tk
from tkinter import filedialog, simpledialog

import keyboard
import pyaudio
import pygame
import requests
import speech_recognition as sr
from anthropic import Anthropic
from bs4 import BeautifulSoup
from gtts import gTTS

# --- Config ---
TRIGGER_KEY = "`"          # Push-to-talk + interrupt
UPLOAD_KEY = "f12"         # Open file picker
URL_KEY = "f11"            # Open URL fetch dialog
SAMPLE_RATE = 16000
CHUNK = 1024
CHANNELS = 1
SAMPLE_WIDTH = 2
MAX_TEXT_FILE_SIZE = 50_000   # ~50KB per text/code file
MAX_WEB_PAGE_SIZE = 50_000    # ~50KB per fetched page

TEXT_EXTENSIONS = {
    ".txt", ".md", ".csv", ".py", ".js", ".ts", ".html", ".css", ".json",
    ".xml", ".yaml", ".yml", ".sql", ".sh", ".bat", ".log", ".ini", ".cfg",
    ".java", ".cpp", ".c", ".h", ".rb", ".go", ".rs", ".php",
}
IMAGE_MEDIA_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
}

# --- Setup ---
client = Anthropic()
recognizer = sr.Recognizer()
pygame.mixer.init()
conversation = []
pending_attachments = []  # Content blocks queued to attach to next message

SYSTEM_PROMPT = (
    "You are a helpful voice assistant connected to a microphone and speakers. "
    "The user holds the backtick key to talk and taps it to interrupt you. "
    "They can also attach files (PDFs, images, text/code) and fetched web pages "
    "for you to read and discuss. Keep responses concise and conversational since "
    "they are spoken aloud. Avoid markdown, bullet points, code blocks, or special "
    "formatting. Aim for 1-3 sentences unless the user asks for more depth or "
    "attaches content needing analysis."
)


def wait_for_release(key):
    """Block until the given key is fully released."""
    while keyboard.is_pressed(key):
        time.sleep(0.03)


# ---------- Audio ----------

def record_audio():
    """Record audio while TRIGGER_KEY is held. Returns transcript or None."""
    pa = pyaudio.PyAudio()
    stream = pa.open(
        format=pyaudio.paInt16,
        channels=CHANNELS,
        rate=SAMPLE_RATE,
        input=True,
        frames_per_buffer=CHUNK,
    )

    print("🎤 Recording... (release ` when done)")
    frames = []
    while keyboard.is_pressed(TRIGGER_KEY):
        data = stream.read(CHUNK, exception_on_overflow=False)
        frames.append(data)

    stream.stop_stream()
    stream.close()
    pa.terminate()

    if not frames:
        return None

    audio = sr.AudioData(b"".join(frames), SAMPLE_RATE, SAMPLE_WIDTH)
    try:
        text = recognizer.recognize_google(audio)
        print(f"You: {text}")
        return text
    except sr.UnknownValueError:
        print("(Couldn't catch that — try again)")
        return None
    except sr.RequestError as e:
        print(f"STT service error: {e}")
        return None


def speak(text):
    """Synthesize text via gTTS, play via pygame, allow trigger-key interrupt."""
    print(f"Claude: {text}")

    try:
        tts = gTTS(text=text, lang="en", slow=False)
    except Exception as e:
        print(f"  (TTS generation error: {e})")
        return

    fd, temp_path = tempfile.mkstemp(suffix=".mp3")
    os.close(fd)
    try:
        tts.save(temp_path)
        pygame.mixer.music.load(temp_path)
        pygame.mixer.music.play()

        time.sleep(0.3)  # debounce

        while pygame.mixer.music.get_busy():
            if keyboard.is_pressed(TRIGGER_KEY):
                pygame.mixer.music.stop()
                print("  (interrupted)")
                break
            time.sleep(0.05)

        pygame.mixer.music.unload()
    finally:
        try:
            os.remove(temp_path)
        except Exception:
            pass


# ---------- File handling ----------

def open_file_picker():
    """Open native Windows file dialog. Returns path or None."""
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    file_path = filedialog.askopenfilename(
        title="Select a file to attach",
        filetypes=[
            ("All supported", "*.txt *.md *.csv *.py *.js *.html *.json *.pdf *.jpg *.jpeg *.png *.gif *.webp"),
            ("Text & code", "*.txt *.md *.csv *.py *.js *.html *.css *.json *.xml *.yaml"),
            ("PDF files", "*.pdf"),
            ("Images", "*.jpg *.jpeg *.png *.gif *.webp"),
            ("All files", "*.*"),
        ],
    )
    root.destroy()
    return file_path or None


def process_file(file_path):
    """Convert a file into a Claude API content block. Returns dict or None."""
    ext = os.path.splitext(file_path)[1].lower()
    filename = os.path.basename(file_path)

    if ext in TEXT_EXTENSIONS:
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read(MAX_TEXT_FILE_SIZE + 1)
            if len(content) > MAX_TEXT_FILE_SIZE:
                content = content[:MAX_TEXT_FILE_SIZE] + "\n[... truncated]"
            return {
                "type": "text",
                "text": f"[Attached file: {filename}]\n\n{content}\n\n[End of {filename}]",
            }
        except Exception as e:
            print(f"  ⚠️ Couldn't read text file: {e}")
            return None

    elif ext == ".pdf":
        try:
            with open(file_path, "rb") as f:
                pdf_b64 = base64.standard_b64encode(f.read()).decode("utf-8")
            return {
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": pdf_b64,
                },
            }
        except Exception as e:
            print(f"  ⚠️ Couldn't read PDF: {e}")
            return None

    elif ext in IMAGE_MEDIA_TYPES:
        try:
            with open(file_path, "rb") as f:
                img_b64 = base64.standard_b64encode(f.read()).decode("utf-8")
            return {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": IMAGE_MEDIA_TYPES[ext],
                    "data": img_b64,
                },
            }
        except Exception as e:
            print(f"  ⚠️ Couldn't read image: {e}")
            return None

    else:
        print(f"  ⚠️ Unsupported file type: {ext}")
        return None


def handle_file_upload():
    """Open file picker, queue selected file for next message."""
    print("\n📂 Opening file picker...")
    file_path = open_file_picker()
    if not file_path:
        print("  (cancelled)")
        return

    block = process_file(file_path)
    if block is None:
        speak("Sorry, I couldn't read that file.")
        return

    pending_attachments.append(block)
    filename = os.path.basename(file_path)
    print(f"  📎 Queued: {filename}")
    speak("File attached. What would you like to know about it?")


# ---------- URL fetching ----------

def open_url_dialog():
    """Show a small dialog asking for a URL. Returns URL string or None."""
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    url = simpledialog.askstring(
        "Fetch URL",
        "Paste URL to fetch (the page will be sent to Claude):",
        parent=root,
    )
    root.destroy()
    return url.strip() if url else None


def fetch_url(url):
    """Fetch a URL and extract its main text. Returns content block or None."""
    # Add https:// if missing
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"  ⚠️ Couldn't fetch URL: {e}")
        return None

    # Parse HTML and strip out non-content elements
    try:
        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
    except Exception as e:
        print(f"  ⚠️ Couldn't parse page: {e}")
        return None

    if not text.strip():
        print("  ⚠️ No readable text found on that page (possibly JavaScript-only)")
        return None

    # Truncate very long pages
    if len(text) > MAX_WEB_PAGE_SIZE:
        text = text[:MAX_WEB_PAGE_SIZE] + "\n[... page content truncated]"

    return {
        "type": "text",
        "text": f"[Web page fetched from: {url}]\n\n{text}\n\n[End of page: {url}]",
    }


def handle_url_fetch():
    """Open URL dialog, fetch the page, queue for next message."""
    print("\n🌐 Opening URL dialog...")
    url = open_url_dialog()
    if not url:
        print("  (cancelled)")
        return

    print(f"  Fetching: {url}")
    block = fetch_url(url)
    if block is None:
        speak("Sorry, I couldn't fetch that page.")
        return

    pending_attachments.append(block)
    print(f"  📎 Page queued from: {url}")
    speak("Page fetched. What would you like to know about it?")


# ---------- Main control flow ----------

def wait_for_action():
    """Wait for talk/upload/url key. Returns ('talk', transcript), ('upload', None), or ('url', None)."""
    queued = f" [{len(pending_attachments)} attachment(s) queued]" if pending_attachments else ""
    print(f"\n[Hold ` to talk, F12 for file, F11 for URL]{queued}")

    wait_for_release(TRIGGER_KEY)
    wait_for_release(UPLOAD_KEY)
    wait_for_release(URL_KEY)

    while True:
        if keyboard.is_pressed(URL_KEY):
            wait_for_release(URL_KEY)
            return ("url", None)
        if keyboard.is_pressed(UPLOAD_KEY):
            wait_for_release(UPLOAD_KEY)
            return ("upload", None)
        if keyboard.is_pressed(TRIGGER_KEY):
            transcript = record_audio()
            return ("talk", transcript)
        time.sleep(0.05)


def ask_claude(user_message):
    """Send message + history to Claude. Includes any pending attachments."""
    if pending_attachments:
        content = pending_attachments + [{"type": "text", "text": user_message}]
    else:
        content = user_message

    conversation.append({"role": "user", "content": content})

    try:
        response = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=conversation,
        )
    except Exception:
        conversation.pop()
        raise

    if pending_attachments:
        pending_attachments.clear()

    reply = response.content[0].text
    conversation.append({"role": "assistant", "content": reply})
    return reply


def main():
    print("=" * 65)
    print("Voice Claude v5 — Push-to-Talk + File Upload + URL Fetch")
    print("  HOLD  `   : record")
    print("  TAP   `   : interrupt Claude")
    print("  PRESS F12 : attach a file (PDF / image / text)")
    print("  PRESS F11 : fetch a web page by URL")
    print("  SAY  'goodbye' or CTRL+C to exit")
    print("=" * 65)
    speak("Hello! Hold backtick to talk, F12 for a file, or F11 to fetch a web page.")

    while True:
        action, data = wait_for_action()

        if action == "upload":
            handle_file_upload()
            continue
        if action == "url":
            handle_url_fetch()
            continue

        # action == "talk"
        user_input = data
        if user_input is None:
            continue

        if any(word in user_input.lower() for word in ["goodbye", "exit", "quit", "stop talking"]):
            speak("Goodbye!")
            break

        try:
            reply = ask_claude(user_input)
            speak(reply)
        except Exception as e:
            print(f"⚠️  Error: {e}")
            speak("Sorry, something went wrong. Try again.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 Exiting. Bye!")
