import io
import csv
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from database import SessionLocal
from models import Event, ImpactAnalysis, Company, CleanNews, RawNews

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
    import json
    events = db.query(Event).order_by(Event.first_reported_at.desc()).limit(limit).all()
    
    result = []
    for e in events:
        # 計算該事件的最高 impact score 作為事件重要性參考
        impacts = db.query(ImpactAnalysis).filter(ImpactAnalysis.event_id == e.event_id).all()
        max_impact = max([imp.impact_score for imp in impacts]) if impacts else 0
        
        # 取得關聯的原始新聞連結
        source_links = []
        try:
            news_ids = json.loads(e.related_news_ids) if e.related_news_ids else []
            for nid in news_ids:
                clean_news = db.query(CleanNews).filter(CleanNews.news_id == nid).first()
                if clean_news:
                    raw_news = db.query(RawNews).filter(RawNews.raw_id == clean_news.raw_id).first()
                    if raw_news and raw_news.url:
                        source_links.append({
                            "source": raw_news.source,
                            "url": raw_news.url
                        })
        except Exception as ex:
            import traceback
            traceback.print_exc()
            pass
            
        result.append({
            "event_id": e.event_id,
            "event_title": e.event_title,
            "event_summary": e.event_summary,
            "first_reported_at": e.first_reported_at,
            "max_impact_score": max_impact,
            "impact_count": len(impacts),
            "source_links": source_links
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
            "positive_score": imp.positive_score,
            "neutral_score": imp.neutral_score,
            "negative_score": imp.negative_score,
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
        "股票名稱", "新聞標題", "新聞摘要",
        "Positive", "Neutral", "Negative",
        "Sentiment", "Impact Score", "Surprise Score",
        "Time Horizon", "Classification", "Confidence"
    ])
    
    # 寫入資料
    for imp, event, comp in results:
        writer.writerow([
            comp.company_name,
            event.event_title,
            event.event_summary,
            imp.positive_score,
            imp.neutral_score,
            imp.negative_score,
            imp.market_direction,
            imp.impact_score,
            imp.surprise_score,
            imp.time_horizon,
            imp.classification,
            imp.confidence
        ])
        
    csv_content = output.getvalue()
    
    # 儲存一份固定的 CSV 到 data 資料夾，供 Power BI 自動連結
    import os
    data_dir = os.path.join(os.path.dirname(__file__), "..", "data")
    os.makedirs(data_dir, exist_ok=True)
    fixed_csv_path = os.path.join(data_dir, "market_sentinel_export.csv")
    with open(fixed_csv_path, "w", encoding="utf-8-sig", newline="") as f:
        f.write(csv_content)
    
    # 準備下載回應 (供使用者手動下載備用)
    output.seek(0)
    response = StreamingResponse(
        iter([csv_content]), 
        media_type="text/csv"
    )
    response.headers["Content-Disposition"] = "attachment; filename=market_sentinel_export.csv"
    
    return response

@app.get("/api/companies/{company_id}/impacts")
def get_company_impacts(company_id: str, db: Session = Depends(get_db)):
    """取得單一公司近期的所有事件影響紀錄"""
    impacts = (
        db.query(ImpactAnalysis, Event)
        .join(Event, ImpactAnalysis.event_id == Event.event_id)
        .filter(ImpactAnalysis.company_id == company_id)
        .order_by(Event.first_reported_at.desc())
        .limit(20)
        .all()
    )
    
    result = []
    for imp, evt in impacts:
        result.append({
            "event_id": evt.event_id,
            "event_title": evt.event_title,
            "first_reported_at": evt.first_reported_at,
            "sentiment_label": imp.sentiment_label,
            "market_direction": imp.market_direction,
            "impact_score": imp.impact_score,
            "surprise_score": imp.surprise_score,
            "classification": imp.classification,
            "analysis_notes": imp.analysis_notes
        })
        
    return result


@app.get("/api/report/daily")
def generate_daily_report(db: Session = Depends(get_db)):
    """動態呼叫 LLM 產生今日市場深度分析報告"""
    from core.llm_service import get_llm_json_response
    import json
    
    # 取得最新 10 個重要事件及其影響力
    events = db.query(Event).order_by(Event.first_reported_at.desc()).limit(10).all()
    
    if not events:
        return {"report_html": "<p>目前沒有足夠的事件資料來生成報告。</p>"}
        
    event_summaries = []
    for e in events:
        impacts = db.query(ImpactAnalysis, Company).join(Company).filter(ImpactAnalysis.event_id == e.event_id).all()
        impact_strs = [f"{comp.company_name}({imp.market_direction}, 分數:{imp.impact_score})" for imp, comp in impacts]
        event_summaries.append(f"事件: {e.event_title}\n摘要: {e.event_summary}\n受影響公司: {', '.join(impact_strs)}")
        
    context_str = "\n\n".join(event_summaries)
    
    sys_prompt = """你是一位資深量化與基本面分析師。
請根據提供的今日市場事件與受影響公司，撰寫一份專業的「今日市場深度分析報告」。
報告必須包含 HTML 格式，使用 <h3>, <ul>, <p>, <strong> 等標籤進行排版。
請著重於市場趨勢、主要受惠/受害產業鍊的分析。
回傳格式必須為 JSON：
```json
{
  "report_html": "你的 HTML 格式報告"
}
```"""
    
    user_prompt = f"以下是今日的市場重大事件與 AI 初步影響力分析：\n\n{context_str}"
    
    try:
        response = get_llm_json_response(user_prompt, sys_prompt)
        return {"report_html": response.get("report_html", "<p>報告生成失敗。</p>")}
    except Exception as e:
        return {"report_html": f"<p>發生錯誤: {str(e)}</p>"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
