import os
import logging

from core.captions_service import fetch_youtube_captions as _fetch_youtube_captions
from core.audio_to_text_service import download_audio_temporarily, transcribe_with_groq as _download_audio_temporarily, _transcribe_with_groq
from core.claude_summary_service import generate_summary_with_claude as _generate_summary_with_claude

# Set up basic logging
logger = logging.getLogger(__name__)

def process_link(youtube_url: str) -> dict:
    """
    Core orchestrator for the Nexus video analysis pipeline.
    
    Strategy: 
    1. Try Captions (cheapest, fastest, safest).
    2. Fallback to temporary Cloud Audio -> Groq Whisper transcription.
    3. Analyze with Claude Haiku.
    4. Enforce strict deletion of raw media.
    """
    logger.info(f"Starting pipeline for URL: {youtube_url}")
    
    transcript = None
    retrieval_method = None
    temp_audio_path = None

    try:
        # ==========================================
        # PATH 1: Captions-First (Cheapest & Fastest)
        # ==========================================
        logger.info("Attempting Path 1: Captions-first retrieval...")
        transcript = _fetch_youtube_captions(youtube_url)
        
        if transcript:
            retrieval_method = "captions"
            logger.info("Captions successfully retrieved.")
        else:
            # ==========================================
            # PATH 2: Cloud Fallback + Groq Transcription
            # ==========================================
            logger.info("Captions unavailable. Attempting Path 2: Cloud retrieval...")
            temp_audio_path = _download_audio_temporarily(youtube_url)
            
            if not temp_audio_path:
                raise Exception("Failed to retrieve media via cloud fallback.")
            
            logger.info("Audio downloaded temporarily. Sending to Groq Whisper...")
            transcript = _transcribe_with_groq(temp_audio_path)
            retrieval_method = "cloud_audio"
            
    except Exception as e:
        logger.error(f"Retrieval pipeline failed: {str(e)}")
        return {
            "status": "error",
            "message": "Could not retrieve video content. Video might be restricted."
        }
        
    finally:
        # ==========================================
        # COMPLIANCE: Strict Temporary Processing
        # ==========================================
        # This is an analizer. Once analized the data source is deleted.
        if temp_audio_path and os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)
            logger.info(f"Compliance cleanup: Deleted temporary audio at {temp_audio_path}")

    if not transcript:
        return {
            "status": "error",
            "message": "Transcription failed. No usable text obtained."
        }
    
    # ==========================================
    # PATH 3: AI Understanding Layer (Claude)
    # ==========================================
    try:
        logger.info("Transcript acquired. Generating insights via Claude Haiku...")
        summary = _generate_summary_with_claude(transcript)
        
        return {
            "status": "success",
            "retrieval_method": retrieval_method,
            "data": {
                "transcript": transcript,
                "summary": summary,
            }
        }
    except Exception as e:
        logger.error(f"AI Analysis failed: {str(e)}")
        return {
            "status": "error",
            "message": "Failed to analyze transcript."
        }
    


if __name__ == "__main__":
    transcript = process_link(youtube_url="https://www.youtube.com/watch?v=BHY0FxzoKZE")
    print(transcript)




