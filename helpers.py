import re

def extract_youtube_id(url: str) -> str:
    """Extracts the 11-character YouTube video ID from standard URLs."""
    match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", url)
    if not match:
        raise ValueError("Could not extract YouTube ID.")
    return match.group(1)