import os
import re
import tempfile # securely creates temporary files, then removes it after use
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, HttpUrl, field_validator
import yt_dlp # command line, we use it specifically to download youtube's video audio
from groq import Groq # Grok whisper to convert audio to text
from anthropic import Anthropic # generate video summary and posteriorly chat about it -- we pass the groq whisper generated text to this
from sqlalchemy import create_engine, Column, Integer, String, Text 
from sqlalchemy.orm import declarative_base, sessionmaker

# ---------------------------------------------------------------------
# 1. Database Configuration (SQLite)
# ---------------------------------------------------------------------
DATABASE_URL = "sqlite:///./nexus.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class VideoRecord(Base):
    __tablename__ = "processed_videos"

    id = Column(Integer, primary_key=True, index=True)
    url = Column(String, unique=True, index=True)
    transcript = Column(Text)
    summary = Column(Text)

# Create tables automatically on startup
Base.metadata.create_all(bind=engine)

# ---------------------------------------------------------------------
# 2. Pydantic Schemas
# ---------------------------------------------------------------------
class ProcessRequest(BaseModel):
    youtube_url: str

    @field_validator("youtube_url")
    @classmethod
    def validate_youtube_url(cls, value: str) -> str:
        # Strict validation for both youtube.com and youtu.be links
        youtube_regex = r"^(https?://)?(www\.)?(youtube\.com|youtu\.be)/.+"
        if not re.match(youtube_regex, value):
            raise ValueError("Invalid YouTube URL format.")
        return value

class ProcessResponse(BaseModel):
    transcript: str
    summary: str

# ---------------------------------------------------------------------
# 3. Core Isolated Pipeline Function
# ---------------------------------------------------------------------
def pipeline_process_video(url: str) -> dict:
    """
    Executes the full pipeline: Audio Extraction -> Transcription -> Summarization -> Storage & Cleanup.
    Can be called from endpoints, background tasks, or CLI tools.
    """
    # Initialize Clients (Picks up GROQ_API_KEY and ANTHROPIC_API_KEY from environment variables)
    groq_client = Groq()
    anthropic_client = Anthropic()

    audio_path = None

    try:
        # --- Step 1: Audio Extraction ---
        temp_dir = tempfile.gettempdir()
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
            # Ensure the path reflects the post-processed extension (.m4a)
            base, _ = os.path.splitext(downloaded_filename)
            audio_path = f"{base}.m4a"

        # --- Step 2: Transcription via Groq Whisper ---
        with open(audio_path, "rb") as file:
            transcription_completion = groq_client.audio.transcriptions.create(
                file=(os.path.basename(audio_path), file.read()),
                model="whisper-large-v3",
                response_format="text"
            )
        # Groq returns standard string when response_format="text"
        raw_transcript = str(transcription_completion).strip()

        if not raw_transcript:
            raise Exception("Whisper returned an empty transcript.")

        # --- Step 3: Summarization via Claude ---
        system_prompt = (
            "You are an expert content analyzer. Provide a high-quality, professional, "
            "and structured Markdown summary of the provided video transcript. Use clean headers, "
            "bullet points, and bold terms for scannability."
        )
        
        message = anthropic_client.messages.create(
            model="claude-3-5-sonnet-20240620",
            max_tokens=1500,
            temperature=0.3,
            system=system_prompt,
            messages=[
                {"role": "user", "content": raw_transcript}
            ]
        )
        summary_text = message.content[0].text

        # --- Step 4: Storage ---
        db = SessionLocal()
        try:
            # Check if record already exists to avoid duplication
            existing_record = db.query(VideoRecord).filter(VideoRecord.url == url).first()
            if existing_record:
                existing_record.transcript = raw_transcript
                existing_record.summary = summary_text
            else:
                new_record = VideoRecord(url=url, transcript=raw_transcript, summary=summary_text)
                db.add(new_record)
            
            db.commit()
        finally:
            db.close()

        return {
            "transcript": raw_transcript,
            "summary": summary_text
        }

    except Exception as e:
        # Propagation of errors up to the controller layer
        raise RuntimeError(f"Pipeline Failed: {str(e)}")

    finally:
        # --- Step 5: Cleanup ---
        if audio_path and os.path.exists(audio_path):
            try:
                os.remove(audio_path)
            except OSError:
                pass # Prevent crashing if file lock issues happen

# ---------------------------------------------------------------------
# 4. FastAPI Routing Application
# ---------------------------------------------------------------------
app = FastAPI(title="Nexus.yt Video Processing Engine")

@app.get("/")
async def read_test():
    return {"test": "test"}

@app.post("/api/process", response_model=ProcessResponse, status_code=status.HTTP_200_OK)
async def process_video(payload: ProcessRequest):
    """
    Accepts a YouTube URL, runs it through the processing pipeline, 
    and returns both the raw transcript and a structured summary.
    """
    try:
        # Executing the isolated pipeline function
        result = pipeline_process_video(payload.youtube_url)
        return result
    except RuntimeError as pipeline_err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(pipeline_err)
        )
    except Exception as general_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"An unexpected error occurred: {str(general_err)}"
        )