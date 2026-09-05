"""
事件分類與聚合模組 (Event Clustering) — 對應 §3.4
將多篇描述同一事件的新聞合併為一個「事件」，避免重複分析。
"""
import os
import json
import uuid
import logging
from datetime import datetime
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv

load_dotenv()

from core.llm_service import get_llm_json_response
from core.embedding_service import cosine_similarity, json_to_embedding

logger = logging.getLogger(__name__)

EVENT_SIMILARITY_THRESHOLD = float(os.getenv("EVENT_SIMILARITY_THRESHOLD", "0.85"))

# ===== System Prompt =====
EVENT_CONFIRMATION_PROMPT = """你是一位專業的新聞編輯。我會給你兩篇新聞，請判斷它們是否在報導「同一個特定事件」。

判斷原則：
1. 若只是「主題相近」（例如都在講台積電財報），但不屬於同一特定事件（例如一個是 Q1 財報，一個是 Q2 財報），請判斷為 False。
2. 若兩篇新聞描述的是同一件事的不同角度、或是不同媒體對同一事件的報導，請判斷為 True。

請嚴格以 JSON 格式回覆：
```json
{
  "is_same_event": true 或 false,
  "reasoning": "簡短理由"
}
```"""

EVENT_SUMMARIZATION_PROMPT = """你是一位專業的金融新聞編輯。請將以下多篇報導同一事件的新聞，整合成一個精煉的「事件摘要」。

請嚴格以 JSON 格式回覆：
```json
{
  "event_title": "事件標題（簡短有力，不超過20字）",
  "event_summary": "事件內容摘要（約100-150字，涵蓋核心事實與關鍵數據）"
}
```"""


def cluster_news_into_events(
    new_news: dict, 
    new_news_embedding: list[float], 
    relevance_results: list[dict],
    recent_events: list[dict],
    recent_news_records: dict
) -> tuple[dict, bool]:
    """
    將單篇新新聞聚合到既有事件中，或建立新事件。

    Args:
        new_news: 包含 'news_id', 'clean_title', 'clean_content', 'published_at' 的 dict
        new_news_embedding: 該新聞的 embedding 向量
        relevance_results: 該新聞相關的公司 (list of dict, 有 'company_id')
        recent_events: 近期事件列表 (list of dict, 需包含 'event_id', 'related_news_ids'(json), 'related_companies'(json))
        recent_news_records: dict {news_id: {"embedding": list[float], "title": str, "content": str}}
                             用於取得既有事件中代表性新聞的 embedding 來算相似度

    Returns:
        (event_dict, is_new_event)
        event_dict: 更新後的舊事件 或 建立的新事件
        is_new_event: True 表示新建了事件，需要進行 Impact Analysis；False 表示併入舊事件，不需重新分析。
    """
    new_company_ids = set(r["company_id"] for r in relevance_results)

    if not new_company_ids:
        return None, False

    candidate_event = None
    highest_sim = 0.0

    # 1. 尋找候選事件（條件：相似度高且涉及公司有交集）
    for event in recent_events:
        event_companies = set(json.loads(event.get("related_companies", "[]")))
        
        # 公司必須有交集才可能是同事件
        if not new_company_ids.intersection(event_companies):
            continue

        event_news_ids = json.loads(event.get("related_news_ids", "[]"))
        if not event_news_ids:
            continue
            
        # 取得該事件第一篇新聞的 embedding 當作代表
        rep_news_id = event_news_ids[0]
        rep_news = recent_news_records.get(rep_news_id)
        
        if not rep_news or not rep_news.get("embedding"):
            continue
            
        sim = cosine_similarity(new_news_embedding, rep_news["embedding"])
        
        if sim >= EVENT_SIMILARITY_THRESHOLD and sim > highest_sim:
            highest_sim = sim
            candidate_event = event
            rep_news_for_llm = rep_news

    # 2. 若有候選，交給 LLM 二次確認
    if candidate_event:
        logger.info(f"找到候選事件 (相似度 {highest_sim:.2f})，進行 LLM 確認...")
        
        user_prompt = f"""## 新聞 A（既有事件）
標題：{rep_news_for_llm.get('title', '')}
內文：{rep_news_for_llm.get('content', '')[:500]}

## 新聞 B（新進新聞）
標題：{new_news['clean_title']}
內文：{new_news['clean_content'][:500]}

請問這兩篇新聞是否在報導同一個事件？"""

        try:
            response = get_llm_json_response(user_prompt, EVENT_CONFIRMATION_PROMPT)
            is_same = response.get("is_same_event", False)
            logger.info(f"LLM 判斷是否同事件: {is_same} ({response.get('reasoning', '')})")
            
            if is_same:
                # 併入舊事件
                event_news_ids = json.loads(candidate_event["related_news_ids"])
                if new_news["news_id"] not in event_news_ids:
                    event_news_ids.append(new_news["news_id"])
                    candidate_event["related_news_ids"] = json.dumps(event_news_ids)
                
                # 合併相關公司
                event_companies = set(json.loads(candidate_event["related_companies"]))
                event_companies.update(new_company_ids)
                candidate_event["related_companies"] = json.dumps(list(event_companies))
                
                return candidate_event, False
        except Exception as e:
            logger.error(f"LLM 事件確認失敗: {e}")

    # 3. 建立新事件
    logger.info(f"建立新事件: {new_news['clean_title']}")
    
    # 用 LLM 生成事件標題與摘要
    user_prompt = f"""## 新聞報導
標題：{new_news['clean_title']}
內文：{new_news['clean_content']}

請幫這則新聞產生精煉的事件標題與摘要。"""

    try:
        response = get_llm_json_response(user_prompt, EVENT_SUMMARIZATION_PROMPT)
        event_title = response.get("event_title", new_news["clean_title"])
        event_summary = response.get("event_summary", new_news["clean_content"][:150] + "...")
    except Exception as e:
        logger.error(f"生成事件摘要失敗: {e}")
        event_title = new_news["clean_title"]
        event_summary = new_news["clean_content"][:150] + "..."

    new_event = {
        "event_id": str(uuid.uuid4()),
        "event_title": event_title,
        "related_news_ids": json.dumps([new_news["news_id"]]),
        "related_companies": json.dumps(list(new_company_ids)),
        "first_reported_at": new_news.get("published_at", datetime.now().isoformat()),
        "event_summary": event_summary
    }

    return new_event, True
