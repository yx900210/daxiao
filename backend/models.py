import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Text, DateTime, UniqueConstraint, ForeignKey,
)
from sqlalchemy.orm import relationship
from backend.database import Base


class Video(Base):
    __tablename__ = "videos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    douyin_video_id = Column(String(64), unique=True, nullable=False, index=True)
    title = Column(Text)
    cover_url = Column(Text)
    publish_time = Column(DateTime)
    duration = Column(Float)
    like_count = Column(Integer, default=0)
    comment_count = Column(Integer, default=0)
    share_count = Column(Integer, default=0)
    local_video_path = Column(Text)
    fetch_status = Column(String(16), default="pending", index=True)
    error_msg = Column(Text)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    subtitles = relationship("Subtitle", back_populates="video", cascade="all, delete-orphan")
    frames = relationship("Frame", back_populates="video", cascade="all, delete-orphan")
    bonsai = relationship("BonsaiScreenshot", back_populates="video", cascade="all, delete-orphan")
    result = relationship("VideoResult", back_populates="video", uselist=False, cascade="all, delete-orphan")


class Frame(Base):
    __tablename__ = "frames"

    id = Column(Integer, primary_key=True, autoincrement=True)
    video_id = Column(Integer, ForeignKey("videos.id"), nullable=False)
    frame_index = Column(Integer, nullable=False)
    frame_timestamp = Column(Float)
    full_screenshot = Column(Text)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    video = relationship("Video", back_populates="frames")
    __table_args__ = (UniqueConstraint("video_id", "frame_index"),)


class Subtitle(Base):
    __tablename__ = "subtitles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    video_id = Column(Integer, ForeignKey("videos.id"), nullable=False)
    frame_index = Column(Integer, nullable=False)
    frame_timestamp = Column(Float)
    screenshot_path = Column(Text)
    raw_text = Column(Text)
    confidence = Column(Float)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    video = relationship("Video", back_populates="subtitles")
    __table_args__ = (UniqueConstraint("video_id", "frame_index"),)


class BonsaiScreenshot(Base):
    __tablename__ = "bonsai_screenshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    video_id = Column(Integer, ForeignKey("videos.id"), nullable=False)
    frame_index = Column(Integer, nullable=False)
    frame_timestamp = Column(Float)
    screenshot_path = Column(Text)
    record_time = Column(Text)
    species = Column(Text)
    description = Column(Text)
    meaning = Column(Text)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    video = relationship("Video", back_populates="bonsai")
    __table_args__ = (UniqueConstraint("video_id", "frame_index"),)


class VideoResult(Base):
    __tablename__ = "video_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    video_id = Column(Integer, ForeignKey("videos.id"), unique=True, nullable=False)
    full_subtitle = Column(Text)
    subtitle_word_count = Column(Integer)
    stock_summary = Column(Text)
    stock_keywords = Column(Text)
    stock_sentiment = Column(String(8))
    bonsai_summary = Column(Text)
    llm_model = Column(String(32))
    vl_model = Column(String(32))
    processed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    video = relationship("Video", back_populates="result")


class ScrapeLog(Base):
    __tablename__ = "scrape_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    started_at = Column(DateTime, nullable=False)
    finished_at = Column(DateTime)
    total_videos = Column(Integer, default=0)
    new_videos = Column(Integer, default=0)
    status = Column(String(16), default="running")
    error_msg = Column(Text)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class Setting(Base):
    __tablename__ = "settings"

    key = Column(String(64), primary_key=True)
    value = Column(Text, default="")
    updated_at = Column(DateTime, default=datetime.datetime.utcnow)
