from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, status, BackgroundTasks, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from anthropic import Anthropic
import jwt
##
from database import SessionLocal
from models import ChatMessage, VideoRecord
from schemas import ProcessRequest, ProcessInitResponse, VideoListResponse, VideoStatusResponse, ChatRequest, ChatResponse
from helpers import extract_youtube_id
from core.pipeline import pipeline_process_video

load_dotenv() # Loads variables from .env into the system's environment

# ---------------------------------------------------------------------
# 0. Route dependencies
# ---------------------------------------------------------------------
security_scheme = HTTPBearer()

# @dev try to understand this syntax on the function params
def get_current_user_id(credentials: HTTPAuthorizationCredentials = Depends(security_scheme)) -> str:
    """
    Authentication & Verification Dependency.
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
# 1. FastAPI Routing Application
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
        existing_record = db.query(VideoRecord).filter(VideoRecord.youtube_id == yt_id,VideoRecord.user_id == user_id).first()
        
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

        background_tasks.add_task(pipeline_process_video, new_record.id, payload.youtube_url) # @dev what happen if this spawn fails? Previous register will be 4ever pending, should make this first or undo the change on the failure handling block

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