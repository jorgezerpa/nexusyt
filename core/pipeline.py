from dotenv import load_dotenv
import os
import tempfile
import yt_dlp
from groq import Groq
from anthropic import Anthropic
##
from database import SessionLocal
from models import VideoRecord


# ---------------------------------------------------------------------
# Core Background Pipeline Function -> MAIN FUNCTION. This is the heart of the product. 
# ---------------------------------------------------------------------
# @dev how to handle the temp file path on a server? or if I deployed on cloud or using a container?
# @dev atually, if not prev registered, it just gonna lose all the work? will not be better to assert for id existance first?
def pipeline_process_video(record_id: str, url: str):
    # @dev how is this handling failures on any step?
    """
    Executes asynchronously. Updates the database record upon completion or failure.
    """

    # @dev how to use this? where I'm I setting creds?
    groq_client = Groq() 
    anthropic_client = Anthropic()
    audio_path = None
    db = SessionLocal()

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
            base, _ = os.path.splitext(downloaded_filename)
            audio_path = f"{base}.m4a"

        # --- Step 2: Transcription via Groq Whisper ---
        with open(audio_path, "rb") as file:
            transcription_completion = groq_client.audio.transcriptions.create(
                file=(os.path.basename(audio_path), file.read()),
                model="whisper-large-v3",
                response_format="text"
            )
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

        # --- Step 4: Storage Update ---
        record = db.query(VideoRecord).filter(VideoRecord.id == record_id).first()
        if record:
            record.transcript = raw_transcript
            record.summary = summary_text
            record.status = "completed"
            db.commit()

    except Exception as e:
        # Log the error in production. Mark status as failed so client doesn't poll forever.
        print(f"Background Task Failed for {record_id}: {str(e)}")
        record = db.query(VideoRecord).filter(VideoRecord.id == record_id).first()
        if record:
            record.status = "failed"
            db.commit()

    finally:
        db.close()
        # --- Step 5: Cleanup ---
        if audio_path and os.path.exists(audio_path):
            try:
                os.remove(audio_path)
            except OSError:
                pass 

if __name__ == "__main__":
    # Replace these with real test values
    TEST_RECORD_ID = "1" 
    TEST_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    
    print(f"Starting test for record {TEST_RECORD_ID}...")
    pipeline_process_video(TEST_RECORD_ID, TEST_URL)
    print("Process complete.")