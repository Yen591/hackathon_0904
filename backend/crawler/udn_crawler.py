"""
經濟日報爬蟲 (money.udn.com) — §3.1
強化版：加入重試機制、logging、已抓取 URL 檢查
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
RETRY_DELAY = 2  # 初始重試延遲秒數（指數退避）
REQUEST_INTERVAL = 1.5  # 每次請求間隔秒數

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def _request_with_retry(url: str, timeout: int = 10) -> requests.Response | None:
    """帶重試機制的 HTTP 請求（3 次重試，指數退避）"""
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


def scrape_udn_news(crawled_urls: set[str] = None) -> list[dict]:
    """
    爬取經濟日報財經新聞

    Args:
        crawled_urls: 已抓取過的 URL 集合，用於避免重複抓取

    Returns:
        原始新聞物件陣列
    """
    if crawled_urls is None:
        crawled_urls = set()

    base_url = "https://money.udn.com/money/index"
    logger.info(f"開始爬取經濟日報: {base_url}")

    response = _request_with_retry(base_url)
    if not response:
        logger.error("無法取得經濟日報首頁")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    links = soup.find_all("a")
    story_urls = set()

    for link in links:
        href = link.get("href")
        if href:
            full_url = urljoin(base_url, href)
            if full_url.startswith("https://money.udn.com/money/story"):
                if full_url not in crawled_urls:
                    story_urls.add(full_url)

    logger.info(f"找到 {len(story_urls)} 篇待爬新聞（已排除已抓取 URL）")

    news_data = []
    failed_urls = []

    for i, story_url in enumerate(story_urls):
        # 請求頻率控制
        if i > 0:
            time.sleep(REQUEST_INTERVAL)

        story_response = _request_with_retry(story_url)
        if not story_response:
            failed_urls.append(story_url)
            continue

        try:
            story_soup = BeautifulSoup(story_response.text, "html.parser")

            # 爬取標題
            title_tag = story_soup.find("h1", class_="article-head__title")
            title = title_tag.get_text(strip=True) if title_tag else "N/A"

            # 爬取發布時間
            time_tag = story_soup.find("time", class_="article-body__time")
            publish_time_str = time_tag.get_text(strip=True) if time_tag else ""

            iso_time = datetime.now().isoformat()
            if publish_time_str:
                try:
                    if len(publish_time_str) > 10:
                        parsed_time = datetime.strptime(publish_time_str, "%Y-%m-%d %H:%M")
                        iso_time = parsed_time.isoformat()
                except ValueError:
                    pass

            # 爬取內文
            content_tag = story_soup.find("section", class_="article-body__editor")
            paragraphs = content_tag.find_all("p") if content_tag else []
            content = "\n".join(p.get_text(strip=True) for p in paragraphs)

            # 確保有爬到內文與標題才加入
            if title != "N/A" and content:
                news_item = {
                    "raw_id": str(uuid.uuid4()),
                    "source": "經濟日報",
                    "url": story_url,
                    "title": title,
                    "content": content,
                    "published_at": iso_time,
                    "crawled_at": datetime.now().isoformat(),
                }
                news_data.append(news_item)
                logger.debug(f"成功爬取: {title[:40]}...")

        except Exception as e:
            logger.error(f"解析失敗: {story_url} — {e}")
            failed_urls.append(story_url)
            continue

    if failed_urls:
        logger.warning(f"失敗清單 ({len(failed_urls)} 篇): {failed_urls}")

    logger.info(f"經濟日報爬取完成：成功 {len(news_data)} 篇，失敗 {len(failed_urls)} 篇")
    return news_data


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    news = scrape_udn_news()
    print(f"共抓取 {len(news)} 篇新聞。")
    if news:
        print("第一筆範例：")
        print(news[0])
