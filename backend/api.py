import io
import csv
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from database import SessionLocal
from models import Event, ImpactAnalysis, Company, CleanNews

app = FastAPI(title="Market Sentinel API", description="REST API for Market Sentinel Dashboard")

# 允許跨網域請求 (CORS) - 開發階段允許所有來源
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 正式環境需限制
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/api/events")
def get_events(limit: int = 50, db: Session = Depends(get_db)):
    """取得最近分析的事件列表"""
    events = db.query(Event).order_by(Event.first_reported_at.desc()).limit(limit).all()
    
    result = []
    for e in events:
        # 計算該事件的最高 impact score 作為事件重要性參考
        impacts = db.query(ImpactAnalysis).filter(ImpactAnalysis.event_id == e.event_id).all()
        max_impact = max([imp.impact_score for imp in impacts]) if impacts else 0
        
        result.append({
            "event_id": e.event_id,
            "event_title": e.event_title,
            "event_summary": e.event_summary,
            "first_reported_at": e.first_reported_at,
            "max_impact_score": max_impact,
            "impact_count": len(impacts)
        })
        
    return result


@app.get("/api/events/{event_id}/impacts")
def get_event_impacts(event_id: str, db: Session = Depends(get_db)):
    """取得單一事件對各公司的影響力分析"""
    impacts = (
        db.query(ImpactAnalysis, Company)
        .join(Company, ImpactAnalysis.company_id == Company.company_id)
        .filter(ImpactAnalysis.event_id == event_id)
        .order_by(ImpactAnalysis.impact_score.desc())
        .all()
    )
    
    if not impacts:
        raise HTTPException(status_code=404, detail="Event impacts not found")
        
    result = []
    for imp, comp in impacts:
        result.append({
            "company_id": comp.company_id,
            "company_name": comp.company_name,
            "ticker": comp.ticker,
            "sentiment_label": imp.sentiment_label,
            "market_direction": imp.market_direction,
            "impact_score": imp.impact_score,
            "surprise_score": imp.surprise_score,
            "time_horizon": imp.time_horizon,
            "classification": imp.classification,
            "confidence": imp.confidence,
            "analysis_notes": imp.analysis_notes
        })
        
    return result


@app.get("/api/companies")
def get_companies(db: Session = Depends(get_db)):
    """取得所有監控中的公司名單"""
    companies = db.query(Company).all()
    return [{"company_id": c.company_id, "company_name": c.company_name, "ticker": c.ticker, "industry": c.industry} for c in companies]


@app.get("/api/export/powerbi")
def export_powerbi(db: Session = Depends(get_db)):
    """
    一鍵匯出供 Power BI 使用的扁平化 CSV 資料
    包含：事件名稱、公司名稱、代號、情緒、方向、影響分數、分析說明等
    """
    results = (
        db.query(ImpactAnalysis, Event, Company)
        .join(Event, ImpactAnalysis.event_id == Event.event_id)
        .join(Company, ImpactAnalysis.company_id == Company.company_id)
        .order_by(Event.first_reported_at.desc())
        .all()
    )
    
    output = io.StringIO()
    writer = csv.writer(output, delimiter=',', quoting=csv.QUOTE_MINIMAL)
    
    # 寫入 CSV 標頭
    writer.writerow([
        "Event ID", "Event Title", "First Reported At", 
        "Company Ticker", "Company Name", "Industry",
        "Sentiment", "Market Direction", "Impact Score", "Surprise Score",
        "Time Horizon", "Classification", "Confidence", "Analysis Notes"
    ])
    
    # 寫入資料
    for imp, event, comp in results:
        writer.writerow([
            event.event_id,
            event.event_title,
            event.first_reported_at,
            comp.ticker,
            comp.company_name,
            comp.industry,
            imp.sentiment_label,
            imp.market_direction,
            imp.impact_score,
            imp.surprise_score,
            imp.time_horizon,
            imp.classification,
            imp.confidence,
            imp.analysis_notes
        ])
    
    # 準備下載回應
    output.seek(0)
    response = StreamingResponse(
        iter([output.getvalue()]), 
        media_type="text/csv"
    )
    response.headers["Content-Disposition"] = "attachment; filename=market_sentinel_export.csv"
    
    return response

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
