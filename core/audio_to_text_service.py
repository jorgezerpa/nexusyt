from dotenv import load_dotenv
import os
import tempfile
import yt_dlp
from groq import Groq
from anthropic import Anthropic
##
from database import SessionLocal
from models import VideoRecord

load_dotenv() 

def download_audio_temporarily(url: str) -> str | None:
    """
    Implementation target: Use `yt-dlp` via Python wrapper.
    Configured to extract lowest quality audio (e.g., m4a/opus) to a /tmp/ folder.
    Must return the exact file path to the downloaded temp file.
    """
    # --- Step 1: Audio Extraction ---
    temp_dir = tempfile.gettempdir() # @tdev how will this work in prd? maybe I should create a file with Docker for this
    ydl_opts = {
        'format': 'm4a/bestaudio/best',
        'outtmpl': os.path.join(temp_dir, '%(id)s.%(ext)s'),
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'm4a',
        }],
        'quiet': True,
        'no_warnings': True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        downloaded_filename = ydl.prepare_filename(info)
        base, _ = os.path.splitext(downloaded_filename)
        audio_path = f"{base}.m4a"
    
    return audio_path







def transcribe_with_groq(audio_path: str) -> str:
    """
    Implementation target: Groq Python SDK.
    Model: 'whisper-large-v3' (or turbo).
    Sends the audio file and returns the raw text transcript.
    """
    groq_client = Groq() 
    
    with open(audio_path, "rb") as file:
        transcription_completion = groq_client.audio.transcriptions.create(
            file=(os.path.basename(audio_path), file.read()),
            model="whisper-large-v3",
            response_format="text"
        )
    raw_transcript = str(transcription_completion).strip()

    return raw_transcript