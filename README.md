# Voice-Controlled-Smart-AI-Assistant

**Stack:** Python · Anthropic API · Speech Recognition · Web Scraping

End-to-end voice assistant integrating Anthropic's Claude API with real-time speech-to-text (Google STT), text-to-speech (gTTS), and audio playback (pygame). Features push-to-talk recording, mid-sentence interrupt, multi-modal file analysis (PDF, images, text), and on-demand web page fetching with HTML parsing.

## Demo

[![Watch the demo](https://img.youtube.com/vi/AaamF4kGLSM/0.jpg)](https://youtu.be/AaamF4kGLSM)

## Features

- 🎤 **Push-to-talk** — hold backtick (`) to record, release to send
- ⏹️ **Mid-sentence interrupt** — tap backtick during playback to cut off and read instead
- 📂 **File analysis** — press F12 to attach PDFs, images, or text/code files
- 🌐 **URL fetching** — press F11 to paste a URL; the page text gets sent to Claude
- 🚀 **One-keystroke launch** — runs from any directory via custom batch launcher

## Tech Stack

- **Language:** Python 3.12
- **LLM:** Anthropic Claude (Haiku 4.5)
- **Speech-to-Text:** Google Speech Recognition (via `speech_recognition`)
- **Text-to-Speech:** Google TTS (`gTTS`) + `pygame.mixer` for playback control
- **Audio capture:** `PyAudio`
- **Web scraping:** `requests` + `BeautifulSoup`
- **Hotkeys:** `keyboard`
- **File picker:** `tkinter`

## Installation

```bash
pip install anthropic SpeechRecognition pyttsx3 pyaudio gtts pygame keyboard requests beautifulsoup4
```

Set your Anthropic API key:
```bash
setx ANTHROPIC_API_KEY "sk-ant-..."
```

## Usage

```bash
python voice_rian.py
```

| Action | Key |
|--------|-----|
| Talk | Hold ` |
| Interrupt AI | Tap ` |
| Attach file | Press F12 |
| Fetch URL | Press F11 |
| Exit | Say "goodbye" or Ctrl+C |

## License

MIT
Practical Demonstration video link: https://www.youtube.com/watch?v=AaamF4kGLSM
