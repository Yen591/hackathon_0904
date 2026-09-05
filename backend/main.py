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
        "raw_id": "demo-001",
        "source": "測試",
        "url": "https://example.com/demo-001",
        "title": "全球 AI 伺服器需求增加，先進封裝產能吃緊",
        "content": (
            "隨著生成式 AI 應用快速普及，全球 AI 伺服器需求持續攀升。"
            "業界指出，由於 NVIDIA 新一代 GPU 採用先進封裝技術 CoWoS，"
            "導致封裝產能嚴重吃緊，交期已拉長至六個月以上。"
            "供應鏈消息透露，主要晶圓代工廠已全面擴充先進封裝產能，"
            "但短期內仍難以滿足市場需求。分析師預估，"
            "AI 伺服器相關供應鏈將持續受惠，相關零組件廠商訂單能見度已達明年。"
            "此外，伺服器代工廠的產能利用率也已接近滿載，"
            "電源供應器、散熱模組等關鍵零組件需求同步增長。"
        ),
        "published_at": datetime.now().isoformat(),
        "crawled_at": datetime.now().isoformat(),
    },
    {
        "raw_id": "demo-002",
        "source": "測試",
        "url": "https://example.com/demo-002",
        "title": "國際油價大幅波動，石化業者面臨成本壓力",
        "content": (
            "受中東地緣政治緊張影響，國際原油價格近期大幅波動，"
            "布蘭特原油價格單週漲幅超過 8%。石化業者表示，"
            "原油價格上漲將直接推升塑膠原料成本，包括 PVC、PE、PP 等產品價格可能調漲。"
            "不過分析師指出，若價格能順利轉嫁下游，對石化廠商的影響有限。"
            "同時，部分金融機構也關注油價波動對整體通膨的影響，"
            "可能影響央行貨幣政策走向。"
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
        logger.info(f"清理新聞儲存完成：{len(clean_news)} 篇")
    except Exception as e:
        db.rollback()
        logger.error(f"儲存清理新聞失敗: {e}")
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

    for i, news in enumerate(clean_news):
        logger.info(f"\n--- 分析第 {i+1}/{len(clean_news)} 篇: {news['clean_title'][:40]}... ---")

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
                db.add(ImpactAnalysis(
                    event_id=event_dict["event_id"],
                    company_id=imp.get("company_id", ""),
                    sentiment_label=imp.get("sentiment_label", ""),
                    market_direction=imp.get("market_direction", ""),
                    impact_score=imp.get("impact_score", 0),
                    surprise_score=imp.get("surprise_score", 0),
                    time_horizon=imp.get("time_horizon", ""),
                    classification=imp.get("classification", ""),
                    confidence=imp.get("confidence", 0),
                    analysis_notes=imp.get("analysis_notes", ""),
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
            .order_by(ImpactAnalysis.impact_score.desc())
            .limit(20)
            .all()
        )

        for impact, event, company in results:
            signal_icon = "🔴" if impact.classification == "Signal" else "⚪"
            direction_icon = {"Bullish": "📈", "Bearish": "📉", "Neutral": "➡️"}.get(
                impact.market_direction, "❓"
            )

            logger.info(
                f"\n{signal_icon} {direction_icon} [{company.ticker}] {company.company_name}\n"
                f"  事件：{event.event_title}\n"
                f"  摘要：{event.event_summary[:100]}...\n"
                f"  情緒: {impact.sentiment_label} | 方向: {impact.market_direction}\n"
                f"  Impact: {impact.impact_score} | Surprise: {impact.surprise_score} | 信心: {impact.confidence}\n"
                f"  時間範圍: {impact.time_horizon} | 分類: {impact.classification}\n"
                f"  分析: {impact.analysis_notes}"
            )

        if not results:
            logger.info("目前沒有分析結果")

    finally:
        db.close()


def run_full_pipeline(use_demo: bool = False):
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
    parser.add_argument("--results", action="store_true", help="列印最新分析結果")
    args = parser.parse_args()

    if args.init:
        step_init()
    elif args.test:
        run_full_pipeline(use_demo=True)
    elif args.crawl_only:
        init_db()
        step_crawl()
    elif args.results:
        init_db()
        print_results()
    else:
        run_full_pipeline(use_demo=False)


if __name__ == "__main__":
    main()
