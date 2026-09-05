"""
金融影響分析模組 (Impact Analysis) — §3.5
MVP 階段使用 LLM 做情緒/方向/影響分析
Phase 2 可整合 FinBERT 做 sentiment 基礎判斷
"""
import logging
from core.llm_service import get_llm_json_response

logger = logging.getLogger(__name__)

IMPACT_SYSTEM_PROMPT = """你是一位資深金融分析師，負責分析新聞事件對特定公司的金融市場影響。

## 分析維度
你需要針對每一組「新聞 + 公司」提供以下分析：

1. **sentiment_label** (Positive / Neutral / Negative)：新聞對該公司的情緒傾向
2. **positive_score** (0-1)：正面情緒的機率分數
3. **neutral_score** (0-1)：中性情緒的機率分數
4. **negative_score** (0-1)：負面情緒的機率分數
   - 以上三者之和必須等於 1.0
5. **market_direction** (Bullish / Bearish / Neutral)：
   - 注意：不一定等同 sentiment（例如「利空出盡」sentiment 偏負但 direction 可能偏多）
6. **impact_score** (0-100)：
   - >80：可能顯著影響股價
   - 50-80：中度影響
   - <30：影響輕微
7. **surprise_score** (0-100)：
   - 此消息是否超乎市場預期？
   - 高分 = 出乎意料（如突發重大訂單、意外虧損）
   - 低分 = 市場已普遍預期（如例行法說會符合預期）
8. **time_horizon** (Short-term / Long-term)：
   - Short-term：影響在數小時至數週反映
   - Long-term：影響在數月至數年（結構性改變）
9. **classification** (Signal / Noise)：
   - Signal：具備實質分析價值，可能影響投資判斷
   - Noise：市場雜訊、重複性消息、影響輕微
10. **confidence** (0-1)：你對這次判斷的信心程度
11. **analysis_notes**：簡短的分析說明（2-3句話）

## 輸出格式
嚴格以 JSON 格式回覆：
```json
{
  "impact_results": [
    {
      "company_id": "公司ID",
      "sentiment_label": "Positive/Neutral/Negative",
      "positive_score": 0.0-1.0,
      "neutral_score": 0.0-1.0,
      "negative_score": 0.0-1.0,
      "market_direction": "Bullish/Bearish/Neutral",
      "impact_score": 0-100,
      "surprise_score": 0-100,
      "time_horizon": "Short-term/Long-term",
      "classification": "Signal/Noise",
      "confidence": 0.0-1.0,
      "analysis_notes": "分析說明"
    }
  ]
}
```"""


def analyze_impact(
    news_title: str,
    news_content: str,
    relevant_companies: list[dict],
    news_id: str = None,
    event_id: str = None,
) -> list[dict]:
    """
    對一則新聞/事件的相關公司進行金融影響分析

    Args:
        news_title: 新聞標題
        news_content: 新聞內文（或事件摘要）
        relevant_companies: 相關公司清單 list[dict]，每個含 company_id, company_name, 
                           relevance_score, reasoning
        news_id: 新聞 ID（MVP 階段以新聞為單位分析）
        event_id: 事件 ID（Phase 2 以事件為單位分析）

    Returns:
        list[dict] — 每個公司的影響分析結果
    """
    if not relevant_companies:
        return []

    # 組裝相關公司資訊
    companies_info = "\n".join(
        f"- {c['company_name']} (ID: {c['company_id']}, "
        f"相關性: {c.get('relevance_score', 'N/A')}分, "
        f"類型: {c.get('relation_type', 'N/A')}, "
        f"原因: {c.get('reasoning', 'N/A')})"
        for c in relevant_companies
    )

    from core.finbert_service import FinbertService
    finbert = FinbertService()
    finbert_result = finbert.analyze(news_title + " " + news_content)
    finbert_context = f"FinBERT 預測情緒: {finbert_result['label']} (信心度: {finbert_result['score']:.2f})"

    user_prompt = f"""## 新聞標題
{news_title}

## 新聞全文
{news_content}

## AI 量化情緒指標
{finbert_context}
(請在判斷各公司影響時，將此整體新聞情緒做為基礎參考)

## 相關公司（已由相關性分析模組判定）
{companies_info}

請對每家相關公司進行金融影響分析，嚴格按照 JSON 格式回覆。"""

    try:
        response = get_llm_json_response(user_prompt, IMPACT_SYSTEM_PROMPT)
        results = response.get("impact_results", [])

        # 補上 news_id / event_id
        for r in results:
            if news_id:
                r["news_id"] = news_id
            if event_id:
                r["event_id"] = event_id

        logger.info(f"影響分析完成：{len(results)} 筆結果")
        return results

    except Exception as e:
        logger.error(f"影響分析失敗: {e}")
        return []
