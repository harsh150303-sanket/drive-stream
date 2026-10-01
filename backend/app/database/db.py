from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import create_engine, String, Integer, Float, DateTime, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from ..config import settings, BASE_DIR

DB_URL = settings.database_url
if DB_URL.startswith("sqlite:///./"):
    db_path = BASE_DIR / DB_URL.replace("sqlite:///./", "")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    DB_URL = f"sqlite:///{db_path}"

engine = create_engine(DB_URL, connect_args={"check_same_thread": False} if DB_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

class Base(DeclarativeBase): pass

class FileCache(Base):
    __tablename__ = "files"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    google_drive_id: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(500))
    mime_type: Mapped[str] = mapped_column(String(200), default="")
    size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    modified_time: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_time: Mapped[str | None] = mapped_column(String(100), nullable=True)
    parent_id: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    thumbnail_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_folder: Mapped[int] = mapped_column(Integer, default=0)
    cached_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

class WatchHistory(Base):
    __tablename__ = "watch_history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    google_drive_id: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    filename: Mapped[str] = mapped_column(String(500), default="")
    position: Mapped[float] = mapped_column(Float, default=0)
    duration: Mapped[float] = mapped_column(Float, default=0)
    last_watched: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

class Favorite(Base):
    __tablename__ = "favorites"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    google_drive_id: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")

class OAuthToken(Base):
    __tablename__ = "oauth_tokens"
    session_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    token_json: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

def init_db():
    Base.metadata.create_all(engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
