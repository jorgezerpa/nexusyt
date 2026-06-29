import uuid
from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func # handle server-side timestamps
from sqlalchemy.orm import relationship
from database import Base

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
# Base.metadata.create_all(bind=engine)