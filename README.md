# Market Sentinel - AI 財經新聞市場監控系統

問題：交易室工作者、證券研究者每天需要研究產業新聞，並花費時間分析或整理成報告，消耗許多時間，排擠交易策略、跨部門溝通、對齊商業目標等核心工作。

使用者：金融產業的交易室工作者或證券研究者。

核心功能：透過爬蟲從經濟日報抓取首頁新聞，針對台積電這檔股票進行相關分類，留下可能影響股價的新聞並進行分析。使用
FinBERT 模型判斷情緒溫度，LLM 判斷影響時間長短、分類及簡短說明。串接
Power BI 進行資料視覺化，最後自動寄信到使用者信箱。

作品範圍：自動抓取、分析並寄送報告的系統。

未來擴充可能：擴充至更多股票及更多新聞來源。

## Pipeline

1.  **新聞爬蟲**：自動從「經濟日報」等來源抓取即時新聞。
2.  **AI 相關性過濾**：利用 **Gemini Embedding**
    計算新聞內容與關注的「種子公司」之間的向量相似度，過濾無關新聞。
3.  **情緒與影響力分析**：
    -   透過 **FinBERT** 判斷財經文本的 3 種情緒機率 (Positive / Neutral
        / Negative)。
    -   透過 **OpenAI** 判斷新聞影響的時間長短 (Time
        Horizon)、是否為有效訊號 (Classification)，並產生 2-3 句簡短分析
        (Analysis Notes)。
4.  **自動化輸出**：產出 `CSV` (適配 Power BI) 與 `HTML` 預覽圖表。
5.  **寄送報告**：可選的自動寄信功能，將最新結果寄給管理層。

------------------------------------------------------------------------

## 從零開始操作指南 (Getting Started)

### 1. 系統環境準備

-   **Python**：確認電腦已安裝 Python 3.10 或以上版本。
-   **套件管理**：本專案使用 [`uv`](https://github.com/astral-sh/uv)
    進行套件管理，也可以使用標準的 `pip`。

### 2. 環境變數設定 (.env)

進入 `backend` 資料夾，找到 `.env` 檔案（若無請自行建立），填寫 API
金鑰與相關設定：

``` env
# OpenAI API 金鑰 (用於 GPT 分析)
OPENAI_API_KEY=sk-xxxxxxx

# Google Gemini API 金鑰 (用於 Embedding 計算相似度)
GEMINI_API_KEY=AIzaSyxxxxx

# 指定 LLM 的供應商 (請保持 openai)
LLM_PROVIDER=openai

# (選填) 自動寄信功能
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=您的Gmail信箱@gmail.com
# 必須使用 Gmail 的「應用程式密碼 (App Password)」，不可填寫原密碼
SMTP_PASSWORD=您的Gmail應用程式密碼
RECEIVER_EMAIL=收件人信箱@example.com
SENDER_EMAIL=您的Gmail信箱@gmail.com
```

### 3. 安裝依賴套件

開啟終端機 (Terminal / PowerShell) 並進入 `backend` 目錄：

``` bash
cd backend

# 使用 uv 安裝
uv pip install -r requirements.txt

# 或使用傳統 pip 安裝
pip install -r requirements.txt
```

### 4. 系統初始化（建立資料庫與種子資料）

第一次執行前，或更換 Embedding
模型時，必須重置資料庫並載入公司種子資料。

請確保在 `backend` 目錄下執行：

``` bash
uv run python main.py --init
```

> 如果之前執行過且想重新建立資料庫，可以手動刪除
> `data/market_sentinel.db`，再執行上方指令。

### 5. 執行完整分析流程

執行以下指令後，系統會自動抓取新聞、進行分析並儲存結果：

``` bash
uv run python main.py
```

-   **寄信給主管**

    加上 `--email` 參數即可，前提是 `.env` 已正確設定 SMTP：

    ``` bash
    uv run python main.py --email
    ```

-   **快速 Demo，不執行爬蟲**

    加上 `--test` 參數，系統會清除舊資料並載入一組模擬新聞資料：

    ``` bash
    uv run python main.py --test
    ```

------------------------------------------------------------------------

## 如何與 Power BI 整合

`main.py` 執行完畢後，會在專案根目錄的 `data` 資料夾中產生
`market_sentinel_export.csv`。

1.  打開地端 **Power BI Desktop**。
2.  點選「取得資料 (Get Data)」\>「文字/CSV (Text/CSV)」。
3.  選擇 `data/market_sentinel_export.csv`。
4.  匯入後，可以使用 `Sentiment`, `Positive`, `Time Horizon`,
    `Classification` 等欄位建立視覺化圖表與儀表板。
5.  未來只要排程執行 `python main.py`，Power BI
    按下「重新整理」即可取得最新分析數據。

## 專案架構說明

``` text
hackathon_0904/
├── backend/
│   ├── .env                    # 環境變數與 API 密鑰設定
│   ├── main.py                 # 系統主程式入口 (CLI)
│   ├── api.py                  # FastAPI 伺服器 (若有需要可架設 API)
│   ├── models.py               # 資料庫 Schema
│   ├── crawler/                # 各大財經新聞爬蟲 (目前內建經濟日報)
│   └── core/                   # 核心邏輯 (LLM, Embedding, FinBERT, Email)
├── frontend/                   # 網頁端展示介面 (可選)
├── data/                       # 存放產出的 CSV、HTML 以及 SQLite 資料庫
└── README.md                   # 本份操作手冊
```
