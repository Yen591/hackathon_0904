"""
工商時報爬蟲 (ctee.com.tw) — §3.1
爬取工商時報財經新聞
"""
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import uuid
import time
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAY = 2
REQUEST_INTERVAL = 1.5

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# 工商時報財經新聞分類頁面
CTEE_SECTIONS = [
    "https://ctee.com.tw/news/stocks",      # 證券
    "https://ctee.com.tw/news/tech",         # 科技
    "https://ctee.com.tw/news/industry",     # 產業
    "https://ctee.com.tw/news/finance",      # 金融
]


def _request_with_retry(url: str, timeout: int = 10) -> requests.Response | None:
    """帶重試機制的 HTTP 請求"""
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(url, headers=HEADERS, timeout=timeout)
            response.encoding = "utf-8"
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            delay = RETRY_DELAY * (2 ** attempt)
            if attempt < MAX_RETRIES - 1:
                logger.warning(f"請求失敗 (第{attempt+1}次)，{delay}秒後重試: {url} — {e}")
                time.sleep(delay)
            else:
                logger.error(f"請求失敗 (已達最大重試次數): {url} — {e}")
                return None


def scrape_chinatimes_news(crawled_urls: set[str] = None) -> list[dict]:
    """
    爬取工商時報財經新聞

    Args:
        crawled_urls: 已抓取過的 URL 集合

    Returns:
        原始新聞物件陣列
    """
    if crawled_urls is None:
        crawled_urls = set()

    logger.info("開始爬取工商時報")

    # 從各分類頁面收集文章 URL
    article_urls = set()

    for section_url in CTEE_SECTIONS:
        response = _request_with_retry(section_url)
        if not response:
            logger.warning(f"無法取得工商時報分類頁: {section_url}")
            continue

        soup = BeautifulSoup(response.text, "html.parser")

        # 工商時報的文章連結格式
        for link in soup.find_all("a", href=True):
            href = link["href"]
            full_url = urljoin(section_url, href)
            # 工商時報文章 URL 通常格式：https://ctee.com.tw/news/xxxxx/xxxxxx.html
            if (
                full_url.startswith("https://ctee.com.tw/news/")
                and full_url.endswith(".html")
                and full_url not in crawled_urls
            ):
                article_urls.add(full_url)

        time.sleep(REQUEST_INTERVAL)

    logger.info(f"找到 {len(article_urls)} 篇待爬新聞")

    news_data = []
    failed_urls = []

    for i, article_url in enumerate(article_urls):
        if i > 0:
            time.sleep(REQUEST_INTERVAL)

        response = _request_with_retry(article_url)
        if not response:
            failed_urls.append(article_url)
            continue

        try:
            soup = BeautifulSoup(response.text, "html.parser")

            # 標題
            title_tag = soup.find("h1", class_="entry-title")
            if not title_tag:
                title_tag = soup.find("h1")
            title = title_tag.get_text(strip=True) if title_tag else "N/A"

            # 發布時間
            time_tag = soup.find("time", class_="entry-date")
            if not time_tag:
                time_tag = soup.find("time")
            
            iso_time = datetime.now().isoformat()
            if time_tag:
                datetime_attr = time_tag.get("datetime", "")
                if datetime_attr:
                    try:
                        parsed = datetime.fromisoformat(datetime_attr.replace("Z", "+00:00"))
                        iso_time = parsed.isoformat()
                    except ValueError:
                        pass

            # 內文
            content_div = soup.find("div", class_="entry-content")
            if not content_div:
                content_div = soup.find("article")
            
            paragraphs = content_div.find_all("p") if content_div else []
            content = "\n".join(
                p.get_text(strip=True)
                for p in paragraphs
                if p.get_text(strip=True) and len(p.get_text(strip=True)) > 5
            )

            if title != "N/A" and content and len(content) > 30:
                news_item = {
                    "raw_id": str(uuid.uuid4()),
                    "source": "工商時報",
                    "url": article_url,
                    "title": title,
                    "content": content,
                    "published_at": iso_time,
                    "crawled_at": datetime.now().isoformat(),
                }
                news_data.append(news_item)
                logger.debug(f"成功爬取: {title[:40]}...")

        except Exception as e:
            logger.error(f"解析失敗: {article_url} — {e}")
            failed_urls.append(article_url)
            continue

    if failed_urls:
        logger.warning(f"失敗清單 ({len(failed_urls)} 篇): {failed_urls}")

    logger.info(f"工商時報爬取完成：成功 {len(news_data)} 篇，失敗 {len(failed_urls)} 篇")
    return news_data


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    news = scrape_chinatimes_news()
    print(f"共抓取 {len(news)} 篇新聞。")
    if news:
        print("第一筆範例：")
        print(news[0])
