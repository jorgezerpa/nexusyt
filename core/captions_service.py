import re
import logging
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter

import psutil


# Set up logging for this module
logger = logging.getLogger(__name__)

def _extract_video_id(youtube_url: str) -> str | None:
    """
    Helper function to safely extract the 11-character YouTube video ID 
    from various standard URL formats.
    """
    pattern = r'(?:https?:\/\/)?(?:www\.)?(?:youtube\.com\/(?:[^\/\n\s]+\/\S+\/|(?:v|e(?:mbed)?)\/|\S*?[?&]v=)|youtu\.be\/)([a-zA-Z0-9_-]{11})'
    match = re.search(pattern, youtube_url)
    
    return match.group(1) if match else None

def fetch_youtube_captions(youtube_url: str) -> str | None:
    """
    Fetches auto-generated or manual captions from a YouTube video.
    Returns a single concatenated string of the transcript, or None if disabled/unavailable.
    """
    video_id = _extract_video_id(youtube_url)
    
    if not video_id:
        logger.error(f"Could not extract a valid YouTube video ID from: {youtube_url}")
        return None
        
    try:
        # Fetch the transcript. By default, it tries English first. 
        # You can add a list of fallbacks using languages=['en', 'es', 'fr']
        ytt_api = YouTubeTranscriptApi()
        transcript_raw = ytt_api.fetch(video_id=video_id)

        # Use the built-in TextFormatter to convert the JSON-like list into a clean string
        formatter = TextFormatter()
        transcript_string = formatter.format_transcript(transcript_raw)
        
        # Clean up the formatting (removes excessive newlines from caption chunks)
        # to ensure it's token-efficient for the downstream Claude analysis
        clean_transcript = " ".join(transcript_string.split())
        
        if not clean_transcript: return None
        return clean_transcript
        
    except Exception as e:
        # Broad exception catch handles TranscriptsDisabled, NoTranscriptFound, VideoUnavailable, etc.
        # Logged as INFO instead of ERROR because falling back to Whisper is an expected pipeline path.
        logger.info(f"Captions unavailable for video {video_id}. Reason: {str(e)}")
        return None
    

    
# if __name__ == "__main__":
#     transcript = fetch_youtube_captions(youtube_url="https://www.youtube.com/watch?v=BHY0FxzoKZE")
#     print(transcript)


# tbytes for a 13min ted talk   -> 3509776  -> 360702
# min  -> 0.009339 -> 0.00018976306399473778
# hour -> 0.560354 -> 0.011385783839684267