import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# 確保 data 目錄存在
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_DATA_DIR = os.path.join(_BASE_DIR, "..", "data")
os.makedirs(_DATA_DIR, exist_ok=True)

DATABASE_URL = f"sqlite:///{os.path.join(_DATA_DIR, 'market_sentinel.db')}"

engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def init_db():
    """建立所有資料表（若不存在）"""
    import models  # noqa: F401 — 確保所有 ORM model 已載入
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


