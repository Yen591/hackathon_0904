"""
爬蟲統一入口 — 整合所有新聞來源
"""
import logging
from crawler.udn_crawler import scrape_udn_news
from crawler.chinatimes_crawler import scrape_chinatimes_news

logger = logging.getLogger(__name__)


def crawl_all_sources(crawled_urls: set[str] = None) -> list[dict]:
    """
    爬取所有新聞來源，彙整回傳。
    單一來源失敗不中斷整體流程。

    Args:
        crawled_urls: 已抓取過的 URL 集合

    Returns:
        所有來源的原始新聞陣列
    """
    if crawled_urls is None:
        crawled_urls = set()

    all_news = []

    # 經濟日報
    try:
        udn_news = scrape_udn_news(crawled_urls)
        all_news.extend(udn_news)
        # 更新已抓取 URL
        crawled_urls.update(n["url"] for n in udn_news)
        logger.info(f"經濟日報：{len(udn_news)} 篇")
    except Exception as e:
        logger.error(f"經濟日報爬蟲失敗（不中斷流程）: {e}")

    # 工商時報
    try:
        ctee_news = scrape_chinatimes_news(crawled_urls)
        all_news.extend(ctee_news)
        crawled_urls.update(n["url"] for n in ctee_news)
        logger.info(f"工商時報：{len(ctee_news)} 篇")
    except Exception as e:
        logger.error(f"工商時報爬蟲失敗（不中斷流程）: {e}")

    logger.info(f"所有來源爬取完成，共 {len(all_news)} 篇新聞")
    return all_news
