from dotenv import load_dotenv
import os
import re
import uuid
import tempfile
from fastapi import FastAPI, HTTPException, status, BackgroundTasks, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, field_validator
import yt_dlp
from groq import Groq
from anthropic import Anthropic
from sqlalchemy import create_engine, Column, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func # handle server-side timestamps
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
import jwt
from datetime import datetime

load_dotenv() # Loads variables from .env into the system's environment

# ---------------------------------------------------------------------
# 1. Database Configuration (PostgreSQL)
# ---------------------------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine) # @dev what is this doing? 
Base = declarative_base()

class VideoRecord(Base):
    __tablename__ = "processed_videos"

    # UUID as primary key for secure, non-sequential identification
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    user_id  = Column(String, index=True, nullable=False) # @dev if implement multiple providers, this id could be repeated, so users can get cross-generation list -> found a solution @important 
    # Native YouTube ID for fast existence checks
    youtube_id = Column(String, unique=True, index=True, nullable=False)
    url = Column(String, nullable=False)
    
    # Status tracking: "processing", "completed", "failed"
    status = Column(String, default="processing", nullable=False)
    
    # Nullable initially, populated once background task finishes
    transcript = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)

    created_at  = Column(DateTime(timezone=True), server_default=func.now(), index=True) # @dev is absolute UNIX time for this

    messages = relationship("ChatMessage", back_populates="video", cascade="all, delete-orphan")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    video_id = Column(String, ForeignKey("processed_videos.id"), index=True, nullable=False)
    role = Column(String, nullable=False)  # "user" or "assistant"
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    # NEW: Relationship reference back to the parent video
    video = relationship("VideoRecord", back_populates="messages")




# @dev how should I handle this on prd? create apart and just connect?
# Create tables automatically (For production, use Alembic for migrations)
Base.metadata.create_all(bind=engine)


# ---------------------------------------------------------------------
# 1.2. Authentication & Verification Dependency
# ---------------------------------------------------------------------
security_scheme = HTTPBearer()

# @dev try to understand this syntax on the function params
def get_current_user_id(credentials: HTTPAuthorizationCredentials = Depends(security_scheme)) -> str:
    """
    Extracts the Google ID token from the Bearer header and decodes the user identity.
    """
    token = credentials.credentials
    try:
        # NOTE: When connecting your frontend, pass your Google Client ID into 'audience'
        # For local dev without verifying signatures against Google's public keys, use options below.
        # In full production, use google-auth library or verify signature using Google's JWKS endpoint. @dev
        payload = jwt.decode(token, options={"verify_signature": False})
        
        user_id = payload.get("sub") # 'sub' is the permanent unique Google User ID
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token claims: Missing user identifier."
            )
        return user_id
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired. Please log in again.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication token.")




# ---------------------------------------------------------------------
# 2. Pydantic Schemas & Helpers
# ---------------------------------------------------------------------
def extract_youtube_id(url: str) -> str:
    """Extracts the 11-character YouTube video ID from standard URLs."""
    match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", url)
    if not match:
        raise ValueError("Could not extract YouTube ID.")
    return match.group(1)

class ProcessRequest(BaseModel):
    youtube_url: str

    @field_validator("youtube_url")
    @classmethod
    def validate_youtube_url(cls, value: str) -> str:
        youtube_regex = r"^(https?://)?(www\.)?(youtube\.com|youtu\.be)/.+"
        if not re.match(youtube_regex, value):
            raise ValueError("Invalid YouTube URL format.")
        return value

class ProcessInitResponse(BaseModel):
    video_id: str
    status: str

class VideoStatusResponse(BaseModel):
    status: str
    video_id: str
    transcript: str | None = None
    summary: str | None = None

class VideoListItemResponse(BaseModel):
    id: str
    url: str
    status: str
    created_at: datetime # Directly maps the Python datetime object

    class Config:
        from_attributes = True # @dev what is this?

class VideoListResponse(BaseModel):
    total_count: int
    page: int
    limit: int
    items: list[VideoListItemResponse]


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    role: str
    content: str


# ---------------------------------------------------------------------
# 3. Core Background Pipeline Function
# ---------------------------------------------------------------------
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

# ---------------------------------------------------------------------
# 4. FastAPI Routing Application
# ---------------------------------------------------------------------
app = FastAPI(title="Nexus.yt Video Processing Engine")

@app.post("/api/process", response_model=ProcessInitResponse, status_code=status.HTTP_202_ACCEPTED)
async def process_video(
    payload: ProcessRequest, 
    background_tasks: BackgroundTasks, # @dev how is exactly working the background task stuff?
    user_id: str = Depends(get_current_user_id)
    ): 
    """
    Initiates video processing. Returns immediately while AI pipeline runs in the background.
    """
    db = SessionLocal()
    try:
        yt_id = extract_youtube_id(payload.youtube_url)
        
        # Check if user already have this video in the database
        existing_record = db.query(VideoRecord).filter(
            VideoRecord.youtube_id == yt_id,
            VideoRecord.user_id == user_id
        ).first()
        
        if existing_record:
            # Re-trigger background task if it failed previously
            if existing_record.status == "failed":
                existing_record.status = "processing"
                db.commit() # @dev what is this doing?
                background_tasks.add_task(pipeline_process_video, existing_record.id, payload.youtube_url)
            
            return {"video_id": existing_record.id, "status": existing_record.status}

        # If new, create record and spawn background task
        new_record = VideoRecord(
            user_id=user_id,
            youtube_id=yt_id, 
            url=payload.youtube_url, 
            status="processing"
        )
        db.add(new_record)
        db.commit()
        db.refresh(new_record) # @dev what does this?

        background_tasks.add_task(pipeline_process_video, new_record.id, payload.youtube_url) # @dev what happen if this spawn fails?

        return {"video_id": new_record.id, "status": new_record.status}

    except Exception as general_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"An error occurred: {str(general_err)}"
        )
    finally:
        db.close()


@app.get("/api/video/{video_id}", response_model=VideoStatusResponse)
async def get_video_status(
    video_id: str,
    user_id: str = Depends(get_current_user_id)
    ):
    """
    Poll this endpoint to check the status of the video and retrieve AI data once completed.
    """
    db = SessionLocal()
    try:
        record = db.query(VideoRecord).filter(VideoRecord.id == video_id, VideoRecord.user_id == user_id).first()
        
        if not record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Video not found."
            )

        # If it's still processing or failed, return just the status
        if record.status in ["processing", "failed"]:
            return {
                "video_id": record.id,
                "status": record.status
            }

        # If completed, return everything
        return {
            "status": record.status,
            "video_id": record.id,
            "transcript": record.transcript,
            "summary": record.summary
        }
    finally:
        db.close()


@app.get("/api/videos", response_model=VideoListResponse)
async def get_user_videos(
    page: int = 1,
    limit: int = 10,
    user_id: str = Depends(get_current_user_id)
):
    """
    Returns a paginated list of all video processing tasks initiated by the authenticated user.
    Ordered from strictly newest to oldest using the created_at timestamp.
    """
    
    # @dev create an schema to evaluate this instead of writting it here directly
    if page < 1:
        page = 1
    if limit < 1 or limit > 100:
        limit = 10

    db = SessionLocal()
    try:
        base_query = db.query(VideoRecord).filter(VideoRecord.user_id == user_id)
        total_count = base_query.count()
        
        # Calculate offset
        offset_value = (page - 1) * limit
        
        items = (
            base_query
            .order_by(VideoRecord.created_at.desc())
            .offset(offset_value)
            .limit(limit)
            .all()
        )
        
        return {
            "total_count": total_count,
            "page": page,
            "limit": limit,
            "items": items
        }
    finally:
        db.close()



@app.post("/api/video/{video_id}/chat", response_model=ChatResponse)
async def chat_with_video(
    video_id: str,
    payload: ChatRequest,
    user_id: str = Depends(get_current_user_id)
):
    """
    Interacts with the cheap Claude-3-Haiku model about a processed video's context.
    """
    db = SessionLocal()
    anthropic_client = Anthropic()

    try:
        # Verify the record exists, belongs to the user, and is fully completed
        record = db.query(VideoRecord).filter(VideoRecord.id == video_id, VideoRecord.user_id == user_id).first()
        if not record:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found.")
        if record.status != "completed":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Video context is not ready for chat.")

        # Save the user's incoming message to the database first
        user_msg = ChatMessage(video_id=video_id, role="user", content=payload.message)
        db.add(user_msg)
        db.commit()

        # Fetch historic conversation thread ordered by time to maintain dialog integrity
        history = db.query(ChatMessage).filter(ChatMessage.video_id == video_id).order_by(ChatMessage.created_at.asc()).all()

        # Build Anthropic message payload format from db history records
        formatted_messages = [
            {"role": msg.role, "content": msg.content} for msg in history
        ]

        # Structure the system prompt injecting the raw transcript text context
        system_prompt = (
            "You are a helpful AI assistant. You are answering questions exclusively about a video transcript "
            "provided below. Rely only on the clear facts mentioned. If the information is not in the transcript, "
            "gently state that you cannot find it.\n\n"
            f"--- VIDEO TRANSCRIPT ---\n{record.transcript}"
        )

        # Call Anthropic using the fast, cost-effective Haiku model
        response = anthropic_client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=800,
            temperature=0.5,
            system=system_prompt,
            messages=formatted_messages
        )
        ai_reply = response.content[0].text

        # Persist the generated assistant response to database logs
        assistant_msg = ChatMessage(video_id=video_id, role="assistant", content=ai_reply)
        db.add(assistant_msg)
        db.commit()

        return {"role": "assistant", "content": ai_reply}

    except Exception as chat_err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Chat generation error: {str(chat_err)}"
        )
    finally:
        db.close()


'''
ToDo:
- Instead of handling a global videos register, make a key-pair for each userId-video AKA generate again -> to evaluate this idea
- Create a new endpoint to return the list of user-videos -> so I can show on frontend the list of requested videos among status -> to evaluate, beacause I can keep this on the user's browser 
- Get credentials for third party tools
- Build UI

Notice: By now, "userId" is any kind of browser identification, because probably i will be storing so much data on local storage. In near future, we'll implement a fully working users management system, to also then incorporate stripe (probably use Supabase for all of this)


User flow for device based out -> 
- Cookies and Local Storage: store a unique generated alphanumeric tokens in browser's storage. Use such token to identify device 
- On every request, send it and use it for auth and billing
- 


'''