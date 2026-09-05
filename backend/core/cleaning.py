"""
新聞清理 / 去重模組 — 對應 §3.2
清除雜訊內容（廣告、版權宣告、記者署名格式），並排除完全重複的新聞
"""
import re
import hashlib
import uuid
import logging

logger = logging.getLogger(__name__)

# ===== 清理規則：要移除的樣板文字 =====
BOILERPLATE_PATTERNS = [
    # 記者署名格式
    r"記者\s*\S{2,4}\s*[／/]\s*\S{2,6}報導",
    r"【記者\s*\S{2,4}\s*[／/]\s*\S{2,6}報導】",
    r"（記者\s*\S{2,4}\s*[／/]\s*\S{2,6}報導）",
    # 版權聲明
    r"※\s*歡迎用「轉貼」或「分享」的方式轉傳.*",
    r"版權所有.*轉載必究.*",
    r"本文.*授權.*轉載.*",
    r"©.*版權所有.*",
    # 廣告與推廣
    r"延伸閱讀[：:].*",
    r"※\s*免責聲明.*",
    r"想了解更多.*",
    r"立即訂閱.*",
    # 經濟日報特有
    r"經濟日報.*關注",
    r"本文轉自.*",
]

# 編譯正則表達式
_COMPILED_PATTERNS = [re.compile(p, re.DOTALL) for p in BOILERPLATE_PATTERNS]


def clean_text(text: str) -> str:
    """
    清理新聞文字內容：移除樣板文字、多餘空白

    Args:
        text: 原始新聞全文

    Returns:
        清理後的文字
    """
    cleaned = text
    for pattern in _COMPILED_PATTERNS:
        cleaned = pattern.sub("", cleaned)

    # 清理多餘空行和空白
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = cleaned.strip()

    return cleaned


def compute_content_hash(text: str) -> str:
    """
    計算正規化後全文的 SHA256 hash，用於完全重複比對。
    正規化：去除所有空白與標點後計算。

    Args:
        text: 清理後的新聞全文

    Returns:
        SHA256 hash 字串
    """
    # 正規化：去除所有空白字元和中英文標點
    normalized = re.sub(r"[\s\u3000]+", "", text)  # 空白與全形空格
    normalized = re.sub(r"[，。、；：「」『』（）【】！？…—～\"\"''·《》〈〉,.;:!?\-\"'()\[\]{}]", "", normalized)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def process_raw_news(raw_news_list: list[dict], existing_hashes: set[str] = None) -> list[dict]:
    """
    批次處理原始新聞：清理 + 去重

    Args:
        raw_news_list: 原始新聞 dict 陣列（來自爬蟲模組）
        existing_hashes: 資料庫中已存在的 content_hash 集合（避免跨批次重複）

    Returns:
        清理後的新聞 dict 陣列（新增 news_id, clean_title, clean_content, content_hash）
    """
    if existing_hashes is None:
        existing_hashes = set()

    seen_hashes = set(existing_hashes)
    clean_news_list = []

    for raw in raw_news_list:
        # 清理標題和內文
        clean_title = clean_text(raw.get("title", ""))
        clean_content = clean_text(raw.get("content", ""))

        # 跳過內文太短的新聞（可能是爬取失敗）
        if len(clean_content) < 50:
            logger.warning(f"新聞內文太短，跳過: {raw.get('title', 'N/A')[:30]}...")
            continue

        # 計算 hash 做完全重複比對
        content_hash = compute_content_hash(clean_content)

        if content_hash in seen_hashes:
            logger.info(f"完全重複，跳過: {clean_title[:30]}...")
            continue

        seen_hashes.add(content_hash)

        clean_news = {
            "news_id": str(uuid.uuid4()),
            "raw_id": raw["raw_id"],
            "clean_title": clean_title,
            "clean_content": clean_content,
            "content_hash": content_hash,
        }
        clean_news_list.append(clean_news)

    logger.info(f"清理完成：{len(raw_news_list)} 篇原始 → {len(clean_news_list)} 篇有效新聞")
    return clean_news_list
