from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from backend.config import DB_PATH
import os

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

engine = create_engine(f"sqlite:///{DB_PATH}", echo=False, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    import backend.models  # noqa: F401
    Base.metadata.create_all(bind=engine)

def get_setting(key: str, default: str = "") -> str:
    from sqlalchemy import text
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT value FROM settings WHERE key = :k"), {"k": key}
            ).scalar()
            return result if result else default
    except Exception:
        return default
