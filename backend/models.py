# pyrefly: ignore [missing-import]
from sqlalchemy import Column, String, Text, Integer, Float, ForeignKey, DateTime
from database import Base


class RawNews(Base):
    """原始新聞資料表 — 對應 §3.1 爬蟲輸出"""
    __tablename__ = "raw_news"
    raw_id = Column(String, primary_key=True, index=True)
    source = Column(String, index=True)
    url = Column(String, unique=True)
    title = Column(String)
    content = Column(Text)
    published_at = Column(String)
    crawled_at = Column(String)


class CleanNews(Base):
    """清理後新聞資料表 — 對應 §3.2 輸出"""
    __tablename__ = "clean_news"
    news_id = Column(String, primary_key=True, index=True)
    raw_id = Column(String, ForeignKey("raw_news.raw_id"))
    clean_title = Column(String)
    clean_content = Column(Text)
    content_hash = Column(String, index=True)
    embedding = Column(Text, nullable=True)  # JSON string of float[], 供語意相似度比對


class Company(Base):
    """公司基本資料表 — 對應 §3.3.3"""
    __tablename__ = "companies"
    company_id = Column(String, primary_key=True, index=True)
    company_name = Column(String, index=True)
    ticker = Column(String)
    industry = Column(String)
    business_description = Column(Text)
    supply_chain_tags = Column(String)  # Stored as JSON string
    embedding = Column(Text, nullable=True)  # JSON string of float[], 公司描述 embedding


class RelevanceResult(Base):
    """AI 相關性判斷結果 — 對應 §3.3 輸出"""
    __tablename__ = "relevance_results"
    id = Column(Integer, primary_key=True, autoincrement=True)
    news_id = Column(String, ForeignKey("clean_news.news_id"), index=True)
    company_id = Column(String, ForeignKey("companies.company_id"), index=True)
    company_name = Column(String)
    relation_type = Column(String)  # "direct" | "indirect"
    relevance_score = Column(Float)  # 0-100
    reasoning = Column(Text)  # AI 判斷理由


class Event(Base):
    """事件聚合資料表 — 對應 §3.4 輸出"""
    __tablename__ = "events"
    event_id = Column(String, primary_key=True, index=True)
    event_title = Column(String)
    related_news_ids = Column(String)  # JSON list
    related_companies = Column(String)  # JSON list
    first_reported_at = Column(String)
    event_summary = Column(Text)


class ImpactAnalysis(Base):
    """金融影響分析結果 — 對應 §3.5 輸出"""
    __tablename__ = "impact_analysis"
    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String, ForeignKey("events.event_id"), nullable=True)
    news_id = Column(String, ForeignKey("clean_news.news_id"), nullable=True)
    company_id = Column(String, ForeignKey("companies.company_id"))
    sentiment_label = Column(String)   # Positive | Neutral | Negative
    positive_score = Column(Float)     # 0-1 機率
    neutral_score = Column(Float)      # 0-1 機率
    negative_score = Column(Float)     # 0-1 機率
    market_direction = Column(String)  # Bullish | Bearish | Neutral
    impact_score = Column(Float)       # 0-100
    surprise_score = Column(Float)     # 0-100
    time_horizon = Column(String)      # Short-term | Long-term
    classification = Column(String)    # Signal | Noise
    confidence = Column(Float)         # 0-1
    analysis_notes = Column(Text)

