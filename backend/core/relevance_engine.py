"""
AI 相關性判斷模組 (Relevance Engine) — §3.3 核心模組
兩階段判斷：Embedding 粗篩 → LLM 精判
"""
import os
import json
import logging
from dotenv import load_dotenv

load_dotenv()

from core.llm_service import get_llm_json_response
from core.embedding_service import get_embedding, cosine_similarity, json_to_embedding

logger = logging.getLogger(__name__)

RELEVANCE_THRESHOLD = int(os.getenv("RELEVANCE_THRESHOLD", "60"))
EMBEDDING_TOP_N = int(os.getenv("EMBEDDING_TOP_N", "8"))

# ===== System Prompt =====
RELEVANCE_SYSTEM_PROMPT = """你是一位專業的金融分析師，負責判斷新聞與上市公司的相關性。

## 核心原則
1. **不要僅依賴關鍵字比對**，你需要深入理解產業鏈上下游關係、供應鏈連動效應、原物料成本傳導等間接影響。
2. 一則新聞即使完全沒有提到某公司的名字，只要內容涉及該公司的業務領域、供應鏈或競爭格局，就應判斷為相關。
3. 區分「直接相關」(direct) 和「間接相關」(indirect)：
   - direct：新聞直接提及該公司、或直接涉及該公司的核心業務
   - indirect：新聞涉及該公司的上下游供應鏈、同產業競爭者、原物料成本連動等

## 輸出格式
你必須嚴格以 JSON 格式回覆，不要加任何額外文字，格式如下：
```json
{
  "relevance_results": [
    {
      "company_id": "公司ID",
      "company_name": "公司名稱",
      "relation_type": "direct 或 indirect",
      "relevance_score": 0到100的整數,
      "reasoning": "簡短說明判斷理由（一到兩句話）"
    }
  ]
}
```

## 評分基準
- 90-100：新聞直接討論該公司的重大事件（如財報、法說會、重大訂單）
- 70-89：新聞直接涉及該公司的核心業務領域（如台積電的先進製程相關新聞）
- 60-69：新聞間接影響該公司（如上游原物料價格變動、同產業政策變化）
- 60以下：相關性低，不需列出

只列出 relevance_score >= 60 的公司。若沒有任何公司相關，回傳 {"relevance_results": []}。"""


def analyze_relevance(
    news_content: str,
    news_title: str,
    companies: list[dict],
) -> tuple[list[dict], list[float] | None]:
    """
    分析一則新聞與公司的相關性（兩階段判斷）

    Args:
        news_content: 清理後的新聞全文
        news_title: 新聞標題
        companies: 公司資料 list[dict]，每個 dict 需包含
                   company_id, company_name, business_description, 
                   supply_chain_tags, embedding(JSON str)

    Returns:
        (relevance_results, news_embedding) tuple
        - relevance_results: list[dict] 每個 dict 含 company_id, company_name,
          relation_type, relevance_score, reasoning
        - news_embedding: list[float] 或 None
    """
    # Stage 1: Embedding 粗篩
    candidate_companies, news_embedding = _embedding_prefilter(
        news_content, news_title, companies
    )

    if not candidate_companies:
        logger.info("Embedding 粗篩後無候選公司")
        return [], news_embedding

    logger.info(
        f"Embedding 粗篩結果：{len(candidate_companies)} 家候選公司 — "
        + ", ".join(c["company_name"] for c in candidate_companies)
    )

    # Stage 2: LLM 精判
    results = _llm_relevance_judge(news_content, news_title, candidate_companies)

    # 過濾低於閾值的結果
    filtered = [r for r in results if r.get("relevance_score", 0) >= RELEVANCE_THRESHOLD]

    logger.info(
        f"LLM 精判結果：{len(filtered)} 家相關公司 (閾值={RELEVANCE_THRESHOLD})"
    )

    return filtered, news_embedding


def _embedding_prefilter(
    news_content: str,
    news_title: str,
    companies: list[dict],
) -> tuple[list[dict], list[float] | None]:
    """
    Stage 1: 用 Embedding 相似度做粗篩，取 Top-N 候選公司
    """
    news_embedding = None
    try:
        embed_text = f"{news_title}\n{news_content[:500]}"
        news_embedding = get_embedding(embed_text)
    except Exception as e:
        logger.warning(f"生成新聞 embedding 失敗: {e}，將使用全部公司進行 LLM 判斷")
        return companies[:EMBEDDING_TOP_N], None

    # 計算與每家公司的相似度
    scored = []
    for comp in companies:
        comp_embedding = json_to_embedding(comp.get("embedding", ""))
        if not comp_embedding:
            scored.append((comp, 0.5))  # 沒有 embedding 的公司給預設分
            continue
        sim = cosine_similarity(news_embedding, comp_embedding)
        scored.append((comp, sim))

    scored.sort(key=lambda x: x[1], reverse=True)
    top_n = scored[:EMBEDDING_TOP_N]

    logger.debug(
        "Embedding 相似度排名: "
        + ", ".join(f"{c['company_name']}={s:.3f}" for c, s in top_n)
    )

    return [comp for comp, _ in top_n], news_embedding


def _llm_relevance_judge(
    news_content: str,
    news_title: str,
    candidate_companies: list[dict],
) -> list[dict]:
    """
    Stage 2: 用 LLM 對候選公司做精確相關性判斷
    """
    companies_context = "\n\n".join(
        f"【{c['company_name']}】(ID: {c['company_id']})\n"
        f"  產業：{c.get('industry', 'N/A')}\n"
        f"  業務：{c.get('business_description', 'N/A')}\n"
        f"  供應鏈標籤：{c.get('supply_chain_tags', '[]')}"
        for c in candidate_companies
    )

    user_prompt = f"""## 新聞標題
{news_title}

## 新聞全文
{news_content}

## 候選公司清單
{companies_context}

請分析此新聞與上述候選公司的相關性，嚴格按照 JSON 格式回覆。"""

    try:
        response = get_llm_json_response(user_prompt, RELEVANCE_SYSTEM_PROMPT)
        results = response.get("relevance_results", [])
        return results
    except Exception as e:
        logger.error(f"LLM 相關性判斷失敗: {e}")
        return []
