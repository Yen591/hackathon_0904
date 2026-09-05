"""
Market Sentinel — 主流程 Pipeline
串接：Crawl → Clean → Relevance → Impact Analysis → Store

使用方式：
    python main.py                  # 執行完整流程（爬蟲 + 分析）
    python main.py --init           # 初始化資料庫 + 載入公司種子資料
    python main.py --test           # 用測試新聞跑 Demo（不爬蟲）
    python main.py --crawl-only     # 只爬蟲不分析
"""
import os
import sys
import json
import argparse
import logging
from datetime import datetime

# 確保 import 路徑正確
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal, init_db
from sqlalchemy.orm import Session
from models import RawNews, CleanNews, RelevanceResult, ImpactAnalysis, Company
from core.cleaning import process_raw_news
from core.relevance_engine import analyze_relevance
from core.impact_analysis import analyze_impact
from core.embedding_service import embedding_to_json
from crawler import crawl_all_sources

# ===== Logging 設定 =====
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            os.path.join(os.path.dirname(__file__), "..", "data", "pipeline.log"),
            encoding="utf-8",
        ),
    ],
)
logger = logging.getLogger("MarketSentinel")


# ===== Demo 測試新聞 =====
DEMO_NEWS = [
    {
        "raw_id": "demo-003",
        "source": "經濟日報",
        "url": "https://example.com/demo-003",
        "title": "台積電宣布赴日本熊本設第三座晶圓廠",
        "content": (
            "台積電今日正式宣布，將於日本熊本縣興建第三座晶圓廠，"
            "投資金額預估超過 200 億美元。新廠將導入 6 奈米及 7 奈米製程，"
            "主要供應日本及全球車用半導體與工業應用晶片需求。"
            "日本政府將提供高額補助，預計 2027 年量產。"
            "業界分析，此舉將大幅強化台積電在全球的產能布局，"
            "同時帶動日本半導體設備供應鏈與相關材料廠商的訂單成長。"
            "受此消息激勵，半導體族群今日全面走揚。"
        ),
        "published_at": datetime.now().isoformat(),
        "crawled_at": datetime.now().isoformat(),
    },
]


def step_init():
    """步驟 0：初始化資料庫 + 載入公司種子資料"""
    logger.info("=" * 60)
    logger.info("步驟 0：初始化資料庫")
    init_db()
    logger.info("資料表建立完成")

    from core.seed_companies import load_seed_companies
    count = load_seed_companies(generate_embeddings=True)
    logger.info(f"公司種子資料載入完成：{count} 家")
    logger.info("=" * 60)


def step_crawl() -> list[dict]:
    """步驟 1：爬取新聞"""
    logger.info("=" * 60)
    logger.info("步驟 1：爬取新聞")

    db = SessionLocal()
    try:
        # 取得已抓取的 URL（避免重複）
        existing_urls = set(
            row[0] for row in db.query(RawNews.url).all()
        )
        logger.info(f"資料庫中已有 {len(existing_urls)} 篇新聞")
    finally:
        db.close()

    raw_news = crawl_all_sources(existing_urls)

    # 存入資料庫
    db = SessionLocal()
    try:
        saved = 0
        for news in raw_news:
            # 再次檢查 URL 避免重複
            exists = db.query(RawNews).filter(RawNews.url == news["url"]).first()
            if exists:
                continue
            db.add(RawNews(**news))
            saved += 1
        db.commit()
        logger.info(f"新聞儲存完成：{saved} 篇新增")
    except Exception as e:
        db.rollback()
        logger.error(f"儲存新聞失敗: {e}")
    finally:
        db.close()

    logger.info("=" * 60)
    return raw_news


def step_clean(raw_news: list[dict]) -> list[dict]:
    """步驟 2：新聞清理 + 去重"""
    logger.info("=" * 60)
    logger.info("步驟 2：新聞清理 / 去重")

    # 取得已存在的 content_hash
    db = SessionLocal()
    try:
        existing_hashes = set(
            row[0] for row in db.query(CleanNews.content_hash).all()
        )
    finally:
        db.close()

    clean_news = process_raw_news(raw_news, existing_hashes)

    # 存入資料庫
    db = SessionLocal()
    try:
        for cn in clean_news:
            db.add(CleanNews(
                news_id=cn["news_id"],
                raw_id=cn["raw_id"],
                clean_title=cn["clean_title"],
                clean_content=cn["clean_content"],
                content_hash=cn["content_hash"],
            ))
        db.commit()
        logger.info(f"清理新聞儲存完成：{len(clean_news)} 篇新增")
    except Exception as e:
        db.rollback()
        logger.error(f"儲存清理新聞失敗: {e}")
    finally:
        db.close()

    # 如果全部重複（0 篇新增），載入資料庫既有的 CleanNews 供後續分析
    if not clean_news:
        logger.info("無新增清理新聞，載入資料庫既有的 CleanNews 進行斷點續跑")
        db = SessionLocal()
        try:
            all_clean = db.query(CleanNews).all()
            clean_news = [
                {
                    "news_id": cn.news_id,
                    "raw_id": cn.raw_id,
                    "clean_title": cn.clean_title,
                    "clean_content": cn.clean_content,
                    "content_hash": cn.content_hash,
                }
                for cn in all_clean
            ]
            logger.info(f"已從資料庫載入 {len(clean_news)} 篇既有清理新聞")
        finally:
            db.close()

    logger.info("=" * 60)
    return clean_news


def step_analyze(clean_news: list[dict]) -> dict:
    """步驟 3+4：AI 相關性判斷 + 事件聚合 + 金融影響分析"""
    logger.info("=" * 60)
    logger.info("步驟 3：AI 相關性判斷 + 步驟 4：事件聚合與金融影響分析")

    # 載入公司資料
    db = SessionLocal()
    try:
        companies = db.query(Company).all()
        companies_data = [
            {
                "company_id": c.company_id,
                "company_name": c.company_name,
                "industry": c.industry,
                "business_description": c.business_description,
                "supply_chain_tags": c.supply_chain_tags,
                "embedding": c.embedding,
            }
            for c in companies
        ]
        
        # 載入近期事件 (假設我們只取過去 24 小時，這裡簡化為全取)
        from models import Event
        recent_events_objs = db.query(Event).all()
        recent_events = [
            {
                "event_id": e.event_id,
                "related_news_ids": e.related_news_ids,
                "related_companies": e.related_companies,
            } for e in recent_events_objs
        ]
        
        # 載入近期新聞 (為了取得代表新聞的 embedding 供相似度比對)
        import json
        recent_news_records = {}
        # 簡單載入所有 clean_news
        all_clean = db.query(CleanNews).all()
        from core.embedding_service import json_to_embedding
        for cn in all_clean:
            recent_news_records[cn.news_id] = {
                "embedding": json_to_embedding(cn.embedding) if cn.embedding else None,
                "title": cn.clean_title,
                "content": cn.clean_content
            }

    finally:
        db.close()

    if not companies_data:
        logger.error("公司資料庫為空！請先執行 --init 初始化")
        return {"relevance_count": 0, "impact_count": 0}

    logger.info(f"已載入 {len(companies_data)} 家公司資料, {len(recent_events)} 個既有事件")

    total_relevance = 0
    total_impact = 0

    from core.event_clustering import cluster_news_into_events

    # 取得已分析過的 news_id（用於斷點續跑）
    db = SessionLocal()
    try:
        analyzed_news_ids = set(
            row[0] for row in db.query(RelevanceResult.news_id).distinct().all()
        )
    finally:
        db.close()

    skipped_count = 0

    for i, news in enumerate(clean_news):
        # 斷點續跑：跳過已分析的新聞
        if news["news_id"] in analyzed_news_ids:
            skipped_count += 1
            continue

        logger.info(f"\n--- 分析第 {i+1}/{len(clean_news)} 篇 (已跳過 {skipped_count} 篇已完成): {news['clean_title'][:40]}... ---")

        # 3. 相關性判斷
        relevance_results, news_embedding = analyze_relevance(
            news["clean_content"],
            news["clean_title"],
            companies_data,
        )

        # 存入相關性結果和新聞 embedding
        db = SessionLocal()
        try:
            if news_embedding:
                clean_record = db.query(CleanNews).filter(
                    CleanNews.news_id == news["news_id"]
                ).first()
                if clean_record:
                    clean_record.embedding = embedding_to_json(news_embedding)

            for rel in relevance_results:
                db.add(RelevanceResult(
                    news_id=news["news_id"],
                    company_id=rel["company_id"],
                    company_name=rel["company_name"],
                    relation_type=rel.get("relation_type", "unknown"),
                    relevance_score=rel.get("relevance_score", 0),
                    reasoning=rel.get("reasoning", ""),
                ))
                total_relevance += 1

            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"儲存相關性結果失敗: {e}")
        finally:
            db.close()

        if not relevance_results:
            logger.info("無相關公司，跳過後續分析")
            continue
            
        # 更新 recent_news_records 以供後續同批次的新聞 clustering 使用
        recent_news_records[news["news_id"]] = {
            "embedding": news_embedding,
            "title": news["clean_title"],
            "content": news["clean_content"]
        }

        # 4. 事件聚合
        event_dict, is_new_event = cluster_news_into_events(
            new_news=news,
            new_news_embedding=news_embedding,
            relevance_results=relevance_results,
            recent_events=recent_events,
            recent_news_records=recent_news_records
        )
        
        if not event_dict:
            continue
            
        db = SessionLocal()
        from models import Event
        try:
            if is_new_event:
                db.add(Event(
                    event_id=event_dict["event_id"],
                    event_title=event_dict["event_title"],
                    related_news_ids=event_dict["related_news_ids"],
                    related_companies=event_dict["related_companies"],
                    first_reported_at=event_dict["first_reported_at"],
                    event_summary=event_dict["event_summary"],
                ))
                # 加到 in-memory recent_events 供下一篇新聞比對
                recent_events.append(event_dict)
                logger.info(f"成功建立新事件: {event_dict['event_title']}")
            else:
                existing_event = db.query(Event).filter(Event.event_id == event_dict["event_id"]).first()
                if existing_event:
                    existing_event.related_news_ids = event_dict["related_news_ids"]
                    existing_event.related_companies = event_dict["related_companies"]
                logger.info(f"新聞已併入既有事件 (ID: {event_dict['event_id']})，不重複進行影響分析。")
                
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"儲存事件失敗: {e}")
        finally:
            db.close()

        # 5. 金融影響分析 (只針對新事件)
        if not is_new_event:
            continue

        impact_results = analyze_impact(
            news_title=event_dict["event_title"],
            news_content=event_dict["event_summary"],
            relevant_companies=relevance_results,  
            event_id=event_dict["event_id"],
        )

        # 存入影響分析結果
        db = SessionLocal()
        try:
            for imp in impact_results:
                sentiment = imp.get("sentiment_label", "Neutral")
                db.add(ImpactAnalysis(
                    event_id=event_dict["event_id"],
                    company_id=imp.get("company_id", ""),
                    sentiment_label=sentiment,
                    positive_score=imp.get("positive_score", 0.0),
                    neutral_score=imp.get("neutral_score", 0.0),
                    negative_score=imp.get("negative_score", 0.0),
                    time_horizon=imp.get("time_horizon", ""),
                    classification=imp.get("classification", ""),
                    analysis_notes=imp.get("analysis_notes", ""),
                    # 向下相容欄位
                    market_direction="Bullish" if sentiment == "Positive" else ("Bearish" if sentiment == "Negative" else "Neutral"),
                    impact_score=0.0,
                    surprise_score=0.0,
                    confidence=1.0,
                ))
                total_impact += 1

            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"儲存影響分析失敗: {e}")
        finally:
            db.close()

    logger.info(f"\n分析完成：{total_relevance} 筆相關性結果，{total_impact} 筆影響分析")
    logger.info("=" * 60)
    return {"relevance_count": total_relevance, "impact_count": total_impact}


def print_results():
    """列印最新分析結果摘要"""
    db = SessionLocal()
    from models import Event
    try:
        logger.info("\n" + "=" * 60)
        logger.info("📊 分析結果摘要 (Event-based)")
        logger.info("=" * 60)

        # 取最新的影響分析
        results = (
            db.query(ImpactAnalysis, Event, Company)
            .join(Event, ImpactAnalysis.event_id == Event.event_id)
            .join(Company, ImpactAnalysis.company_id == Company.company_id)
            .order_by(ImpactAnalysis.id.desc())
            .limit(20)
            .all()
        )

        for impact, event, company in results:
            signal_icon = "🔴" if impact.classification == "Signal" else "⚪"
            sentiment_icon = {"Positive": "📈", "Negative": "📉", "Neutral": "➡️"}.get(
                impact.sentiment_label, "➡️"
            )

            pos = impact.positive_score if impact.positive_score is not None else 0.0
            neu = impact.neutral_score if impact.neutral_score is not None else 0.0
            neg = impact.negative_score if impact.negative_score is not None else 0.0

            logger.info(
                f"\n{signal_icon} {sentiment_icon} [{company.ticker}] {company.company_name}\n"
                f"  事件：{event.event_title}\n"
                f"  摘要：{event.event_summary[:100]}...\n"
                f"  情緒: {impact.sentiment_label} (正: {pos:.2f} / 中: {neu:.2f} / 負: {neg:.2f})\n"
                f"  時間範圍: {impact.time_horizon} | 分類: {impact.classification}\n"
                f"  AI 分析筆記: {impact.analysis_notes}"
            )

        if not results:
            logger.info("目前沒有分析結果")

    finally:
        db.close()


def run_full_pipeline(use_demo: bool = False, skip_crawl: bool = False):
    """執行完整 Pipeline"""
    start_time = datetime.now()
    logger.info("🚀 Market Sentinel Pipeline 開始執行")
    logger.info(f"開始時間: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

    # 確保資料庫已初始化
    init_db()

    # 步驟 1: 取得新聞
    if use_demo:
        logger.info("使用 Demo 測試新聞")
        raw_news = DEMO_NEWS
        # 儲存 demo 新聞到 raw_news
        db = SessionLocal()
        try:
            for news in raw_news:
                exists = db.query(RawNews).filter(RawNews.url == news["url"]).first()
                if not exists:
                    db.add(RawNews(**news))
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"儲存 Demo 新聞失敗: {e}")
        finally:
            db.close()
    elif skip_crawl:
        logger.info("跳過爬蟲，使用資料庫中既有的原始新聞（支援斷點續跑）")
        db = SessionLocal()
        raw_news = [
            {
                "raw_id": r.raw_id,
                "source": r.source,
                "url": r.url,
                "title": r.title,
                "content": r.content,
                "published_at": r.published_at,
                "crawled_at": r.crawled_at
            }
            for r in db.query(RawNews).all()
        ]
        db.close()
    else:
        raw_news = step_crawl()

    if not raw_news:
        logger.warning("沒有新聞可分析，Pipeline 結束")
        return

    # 步驟 2: 清理
    clean_news = step_clean(raw_news)

    if not clean_news:
        logger.warning("清理後沒有有效新聞，Pipeline 結束")
        return

    # 步驟 3+4: 分析
    stats = step_analyze(clean_news)

    # 列印結果
    print_results()

    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    logger.info(f"\n✅ Pipeline 完成！耗時 {duration:.1f} 秒")
    logger.info(f"結束時間: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")


def main():
    parser = argparse.ArgumentParser(description="Market Sentinel — AI 財經新聞市場監控系統")
    parser.add_argument("--init", action="store_true", help="初始化資料庫 + 載入公司種子資料")
    parser.add_argument("--test", action="store_true", help="用測試新聞跑 Demo（不爬蟲）")
    parser.add_argument("--crawl-only", action="store_true", help="只爬蟲不分析")
    parser.add_argument("--skip-crawl", action="store_true", help="跳過爬蟲，直接分析資料庫既有新聞")
    parser.add_argument("--results", action="store_true", help="列印最新分析結果")
    parser.add_argument("--email", action="store_true", help="執行完畢後寄送分析報告")
    args = parser.parse_args()

    if args.init:
        step_init()
    elif args.test:
        # 自動清除舊資料庫，確保每次 Demo 都是最新資料
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "market_sentinel.db")
        if os.path.exists(db_path):
            os.remove(db_path)
            logger.info("已自動清除舊資料庫")
        step_init()
        run_full_pipeline(use_demo=True)
        logger.info("自動匯出最新分析結果至 CSV (供 Power BI 使用)...")
        db = SessionLocal()
        _auto_export_csv(db)
        _auto_export_html(db)
        db.close()
        logger.info("Market Sentinel 執行完畢！")
        if args.email:
            from core.email_service import send_daily_report
            logger.info("準備寄送分析報告...")
            csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "market_sentinel_export.csv")
            html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "dashboard.html")
            send_daily_report(csv_path=csv_path, html_path=html_path)
    elif args.crawl_only:
        init_db()
        step_crawl()
    elif args.results:
        init_db()
        print_results()
    else:
        run_full_pipeline(use_demo=False, skip_crawl=args.skip_crawl)
        # === 新增：自動匯出 CSV 供 Power BI 讀取 ===
        logger.info("自動匯出最新分析結果至 CSV (供 Power BI 使用)...")
        db = SessionLocal()
        _auto_export_csv(db)
        _auto_export_html(db)
        db.close()
        logger.info("Market Sentinel 執行完畢！")
        if args.email:
            from core.email_service import send_daily_report
            logger.info("準備寄送分析報告...")
            csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "market_sentinel_export.csv")
            html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "dashboard.html")
            send_daily_report(csv_path=csv_path, html_path=html_path)

def _auto_export_csv(db: Session):
    """將最新的資料匯出至 data/market_sentinel_export.csv"""
    import csv
    import os
    from models import ImpactAnalysis, Event, Company
    
    results = (
        db.query(ImpactAnalysis, Event, Company)
        .join(Event, ImpactAnalysis.event_id == Event.event_id)
        .join(Company, ImpactAnalysis.company_id == Company.company_id)
        .order_by(Event.first_reported_at.desc())
        .all()
    )
    
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
    os.makedirs(data_dir, exist_ok=True)
    fixed_csv_path = os.path.join(data_dir, "market_sentinel_export.csv")
    
    with open(fixed_csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=',', quoting=csv.QUOTE_MINIMAL)
        writer.writerow([
            "股票名稱", "新聞標題", "新聞摘要",
            "Sentiment", "Positive", "Neutral", "Negative",
            "Time Horizon", "Classification", "AI 分析筆記"
        ])
        for imp, event, comp in results:
            writer.writerow([
                comp.company_name, event.event_title, event.event_summary,
                imp.sentiment_label, imp.positive_score, imp.neutral_score, imp.negative_score,
                imp.time_horizon, imp.classification, imp.analysis_notes
            ])
def _auto_export_html(db: Session):
    """將最新的資料匯出至 data/dashboard.html"""
    import os
    from models import ImpactAnalysis, Event, Company
    
    results = (
        db.query(ImpactAnalysis, Event, Company)
        .join(Event, ImpactAnalysis.event_id == Event.event_id)
        .join(Company, ImpactAnalysis.company_id == Company.company_id)
        .order_by(Event.first_reported_at.desc())
        .limit(50)
        .all()
    )
    
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
    os.makedirs(data_dir, exist_ok=True)
    html_path = os.path.join(data_dir, "dashboard.html")
    
    html_content = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Market Sentinel - AI 分析儀表板</title>
    <style>
        body { font-family: Arial, sans-serif; background-color: #f4f7f6; margin: 0; padding: 20px; }
        .container { max-width: 1200px; margin: auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); }
        h1 { color: #333; text-align: center; }
        table { width: 100%; border-collapse: collapse; margin-top: 20px; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }
        th { background-color: #007bff; color: white; }
        tr:hover { background-color: #f1f1f1; }
        .badge { padding: 4px 8px; border-radius: 4px; font-size: 0.9em; font-weight: bold; color: white; }
        .bullish { background-color: #28a745; }
        .bearish { background-color: #dc3545; }
        .neutral { background-color: #6c757d; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Market Sentinel - 最新新聞 AI 影響分析</h1>
        <table>
            <thead>
                <tr>
                    <th>相關公司</th>
                    <th>事件標題</th>
                    <th>情緒標籤</th>
                    <th>情緒機率 (正/中/負)</th>
                    <th>時間範圍</th>
                    <th>分類</th>
                    <th>AI 分析筆記</th>
                </tr>
            </thead>
            <tbody>
"""
    for imp, event, comp in results:
        label = imp.sentiment_label or "Neutral"
        direction_class = "bullish" if label == "Positive" else ("bearish" if label == "Negative" else "neutral")
        pos = imp.positive_score if imp.positive_score is not None else 0.0
        neu = imp.neutral_score if imp.neutral_score is not None else 0.0
        neg = imp.negative_score if imp.negative_score is not None else 0.0
        html_content += f"""
                <tr>
                    <td>{comp.company_name}</td>
                    <td>{event.event_title}</td>
                    <td><span class="badge {direction_class}">{label}</span></td>
                    <td>{pos:.2f} / {neu:.2f} / {neg:.2f}</td>
                    <td>{imp.time_horizon}</td>
                    <td>{imp.classification}</td>
                    <td>{imp.analysis_notes}</td>
                </tr>
"""

    html_content += """
            </tbody>
        </table>
    </div>
</body>
</html>
"""

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    logger.info(f"成功產生儀表板: {html_path}")

if __name__ == "__main__":
    main()
