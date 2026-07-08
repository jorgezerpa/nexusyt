from dotenv import load_dotenv
from anthropic import Anthropic

load_dotenv()

def generate_summary_with_claude(transcript_text: str) -> str:
    """
    Implementation target: Anthropic Python SDK.
    Model: 'claude-3-haiku-20240307' (or 4.5).
    Instructs the LLM to output a JSON payload containing 'summary' and 'key_points'.
    """
    anthropic_client = Anthropic()

    system_prompt = (
        "You are an expert content analyzer. Provide a high-quality, professional, "
        "and structured Markdown summary of the provided video transcript. Use clean headers, "
        "bullet points, and bold terms for scannability."
    )
        
    message = anthropic_client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1500,
        temperature=0.3,
        system=system_prompt,
        messages=[
            {"role": "user", "content": transcript_text}
        ]
    )
    summary_text = message.content[0].text

    return summary_text