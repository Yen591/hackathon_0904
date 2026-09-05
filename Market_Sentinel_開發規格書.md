# Market Sentinel — AI 財經新聞市場監控系統
## 開發規格書（供 AI / 工程團隊實作用）

版本：v1.0
文件目的：提供足夠明確的模組規格、資料結構與邏輯定義，使實作者（人類或 AI）能夠獨立完成開發，不需再回頭確認需求。

---

## 1. 系統概述

Market Sentinel 是一套「不需要預先設定關鍵字」的財經新聞監控系統。傳統做法是「關鍵字搜尋 → 找新聞 → 人工判斷」，本系統改為「AI 語意判斷 → 自動找出相關新聞 → 事件分析 → 自動產生市場報告」。

核心賣點：**From Keyword Search to AI Market Understanding**。系統能理解一則沒有直接提到公司名稱的新聞（例如「先進封裝產能吃緊」），並自動判斷其與特定公司（如台積電）的關聯性與市場影響。

---

## 2. 系統架構與資料流

```text
[資料來源：工商時報 / 經濟日報]
        ↓
   2.1 爬蟲模組 (Crawler)
        ↓
   2.2 新聞清理 / 去重模組 (Cleaning & Dedup)
        ↓
   2.3 AI 相關性判斷模組 (Relevance Engine)
        ↓
   2.4 事件分類與聚合模組 (Event Clustering)
        ↓
   2.5 金融影響分析模組 (Impact Analysis, 含 FinBERT)
        ↓
   2.6 資料儲存層 (Data Store)
        ↓
   2.7 Power BI 視覺化
        ↓
   2.8 JPG 報告產生
        ↓
   2.9 Email 自動寄送
```

每日排程觸發一次完整流程（詳見第 9 節）。

---

## 3. 模組規格

### 3.1 爬蟲模組 (Crawler)

**目的**：定時抓取工商時報、經濟日報等來源的財經新聞全文。

**輸入**：目標網站 URL 清單、抓取時間區間（例如「過去 24 小時」）。

**輸出**：原始新聞物件陣列，結構如下：

```json
{
  "raw_id": "string (uuid)",
  "source": "工商時報 | 經濟日報",
  "url": "string",
  "title": "string",
  "content": "string (全文)",
  "published_at": "ISO8601 datetime",
  "crawled_at": "ISO8601 datetime"
}
```

**邏輯要求**：
- 需處理分頁、動態載入內容（如有 JS 渲染需求，建議用 headless browser）。
- 需具備失敗重試機制（建議：3 次重試，指數退避）。
- 需記錄已抓取過的 URL，避免重複抓取（可用 URL hash 建立索引）。
- 需遵守目標網站的 robots.txt 與請求頻率限制，避免被封鎖。

**錯誤處理**：單一來源抓取失敗不應中斷整體流程，需記錄失敗清單並繼續下一來源。

---

### 3.2 新聞清理 / 去重模組 (Cleaning & Dedup)

**目的**：清除雜訊內容（廣告、版權宣告、記者署名格式），並排除重複或近似重複的新聞。

**輸入**：3.1 輸出的原始新聞陣列。

**輸出**：清理後的新聞物件，新增欄位：

```json
{
  "news_id": "string (uuid)",
  "raw_id": "string",
  "clean_title": "string",
  "clean_content": "string",
  "content_hash": "string (用於完全重複比對)",
  "embedding": "float[] (用於語意相似度比對，可選，供 3.4 事件聚合使用)"
}
```

**邏輯要求**：
- 完全重複：以 `content_hash`（正規化後全文的 hash，例如去除空白與標點後 SHA256）直接判斷。
- 近似重複（不同來源報導同一事件）：**不在此模組直接刪除**，而是保留給 3.4 事件聚合模組處理，避免誤刪不同角度的報導。
- 清理規則：移除固定樣板文字（記者 OOO／台北報導、版權聲明、廣告字串），可用正則表達式維護一份樣板清單。

---

### 3.3 AI 相關性判斷模組 (Relevance Engine) — 核心模組

**目的**：判斷一則新聞與哪些公司、哪些產業相關，不依賴關鍵字比對，而是語意理解。

**輸入**：3.2 輸出的清理後新聞、公司基本資料庫（見 3.3.3）。

**輸出**：

```json
{
  "news_id": "string",
  "relevance_results": [
    {
      "company_id": "string",
      "company_name": "string",
      "relation_type": "direct | indirect",
      "relevance_score": "number (0-100)",
      "reasoning": "string (AI 判斷理由，供人工複核與除錯用)"
    }
  ]
}
```

**判斷邏輯**：
1. 將新聞內容與候選公司清單（含公司名稱、產業別、主要業務描述、供應鏈關係）一併送入 LLM。
2. LLM 需回答：「此新聞與哪些公司直接相關？哪些間接相關（例如供應鏈上下游、同產業競爭者、原物料成本連動）？」
3. 每個相關公司需附上 0–100 的 `relevance_score` 與簡短理由。
4. 僅保留 `relevance_score >= 閾值`（建議預設 60，可設定）的結果進入下一階段。

**3.3.1 Prompt 設計要求（供實作者參考的規格，非最終文字）**：
- System prompt 需明確要求「不要僅依賴關鍵字比對，需理解產業鏈與間接影響」。
- 需提供公司清單作為 context（若清單過大，需先用 embedding 做粗篩，再用 LLM 精判，避免每則新聞都要跟全部公司比對造成成本過高）。
- 輸出需強制 JSON 格式，並定義 JSON schema 供 LLM 依循，方便程式解析。

**3.3.2 效能考量**：
- 建議先以 embedding 相似度（新聞 embedding vs 公司描述 embedding）做初篩，取 Top-N 候選公司，再交給 LLM 做精判與理由生成，降低 LLM 呼叫成本。

**3.3.3 公司基本資料庫（前置資料需求）**：

```json
{
  "company_id": "string",
  "company_name": "string",
  "ticker": "string",
  "industry": "string",
  "business_description": "string",
  "supply_chain_tags": "string[] (例如：先進封裝、AI伺服器、晶圓代工)",
  "embedding": "float[]"
}
```

此資料庫需由人工或另一套流程預先建立與維護，非本模組即時產生。

---

### 3.4 事件分類與聚合模組 (Event Clustering)

**目的**：將多篇描述同一事件的新聞合併為一個「事件」，確保每個事件只分析一次，避免重複計算與重複通知。

**輸入**：3.2 清理後新聞（含 embedding）、3.3 相關性判斷結果。

**輸出**：

```json
{
  "event_id": "string (uuid)",
  "event_title": "string (AI 生成的事件摘要標題)",
  "related_news_ids": "string[]",
  "related_companies": "string[] (company_id)",
  "first_reported_at": "ISO8601 datetime",
  "event_summary": "string (AI 生成的事件內容摘要)"
}
```

**聚合邏輯**：
1. 同一天內，`embedding` 語意相似度高於閾值（建議 cosine similarity ≥ 0.85，可調整）且涉及相同公司的新聞，視為同一事件候選。
2. 候選群組再交由 LLM 二次確認「是否為同一事件」，避免純向量相似度誤判（例如「台積電法說會」跟「台積電資本支出」語意相近但非同一事件）。
3. 確認為同一事件的新聞群組合併，由 LLM 生成統一的 `event_title` 與 `event_summary`。
4. 事件建立後即視為「已分析」，後續同事件新進新聞僅補充 `related_news_ids`，不重新觸發完整分析流程（除非內容有重大更新，例如原本為傳聞、後續轉為證實，此情況應標記為新事件並關聯原事件）。

---

### 3.5 金融影響分析模組 (Impact Analysis)

**目的**：對每個事件產生完整的金融影響分析結果，這是系統最終要交付給使用者的核心資料。

**輸入**：3.4 輸出的事件物件。

**輸出（每個事件一筆）**：

```json
{
  "event_id": "string",
  "company_id": "string",
  "sentiment_label": "Positive | Neutral | Negative",
  "market_direction": "Bullish | Bearish | Neutral",
  "impact_score": "number (0-100)",
  "surprise_score": "number (0-100)",
  "time_horizon": "Short-term | Long-term",
  "classification": "Signal | Noise",
  "confidence": "number (0-1)",
  "analysis_notes": "string"
}
```

**各欄位判斷邏輯**：

| 欄位 | 判斷方式 |
|---|---|
| `sentiment_label` | 使用 **FinBERT** 對事件摘要文字做金融情緒分類，輸出 Positive/Neutral/Negative |
| `market_direction` | 由 LLM 綜合 FinBERT 結果與事件內容判斷，並非單純等同 sentiment（例如「利空出盡」可能情緒偏負但方向偏多） |
| `impact_score` | LLM 根據事件對公司營收/獲利/產業地位的預期影響幅度評分，需在 prompt 中定義評分基準（例如：>80 分＝可能顯著影響股價；<30 分＝影響輕微） |
| `surprise_score` | 比較「事件內容」與「市場既有預期」的落差程度。若為預期內消息（如例行法說會數字符合預期），分數低；若為超乎預期的消息，分數高。可透過 LLM 判斷該類事件是否為「市場已普遍預期」 |
| `time_horizon` | Short-term：影響預期在數小時至數週內反映（如短期消息面波動）；Long-term：影響預期在數月至數年（如基本面結構性改變）。由 LLM 依事件性質分類 |
| `classification` | Signal：具備實質分析價值、可能影響投資判斷；Noise：市場雜訊、重複性消息、影響輕微。可用 `impact_score` 與 `surprise_score` 的組合設定規則門檻，並由 LLM 做最終判斷 |
| `confidence` | LLM 對自己這次判斷的信心程度（0–1），用於後續人工複核優先順序排序（confidence 低的優先人工檢視） |

**FinBERT 使用規格**：
- FinBERT 僅負責 `sentiment_label` 這一項的基礎情緒分數，作為 LLM 綜合判斷的輸入之一，不直接決定其他欄位。
- 輸入文字建議使用 `event_summary`（事件摘要）而非原始新聞全文，避免無關內容干擾情緒判斷。

---

### 3.6 資料儲存層 (Data Store)

建議採用關聯式資料庫（PostgreSQL）儲存結構化結果，並搭配向量資料庫（如 pgvector 或獨立向量 DB）儲存 embedding 供相似度查詢。

**核心資料表（簡要）**：
- `raw_news`：對應 3.1 輸出
- `clean_news`：對應 3.2 輸出
- `relevance_results`：對應 3.3 輸出
- `events`：對應 3.4 輸出
- `impact_analysis`：對應 3.5 輸出，`event_id` + `company_id` 為複合主鍵（一事件可能對多家公司有不同影響分析）
- `companies`：對應 3.3.3 公司資料庫

---

### 3.7 Power BI 整合模組

**目的**：將 `impact_analysis` 與 `events` 資料視覺化。

**資料串接方式**：Power BI 直接連接 3.6 資料庫（PostgreSQL），建議建立專屬的 view 或 materialized view 整合多表 join 結果，簡化 Power BI 端查詢。

**必要視覺化元件**：
- 今日事件數（卡片）
- Bullish / Bearish / Neutral 分布（圓餅圖或長條圖）
- Impact Score 分布（直方圖）
- Surprise Score 分布（直方圖）
- Short-term / Long-term 比例（長條圖）
- Signal / Noise 比例（長條圖）
- 公司別事件列表（表格，可篩選）
- 重大市場事件排行（依 `impact_score` 降冪排序的 Top N 列表）

**篩選器**：日期區間、公司、產業、Signal/Noise。

---

### 3.8 JPG 報告產生模組

**目的**：將 Power BI 報表匯出為靜態圖片，供 Email 附件使用。

**實作方式建議**：
- 使用 Power BI REST API 的 Export to File 功能，將指定報表頁匯出為 PNG/JPG。
- 需設定 Power BI Service Principal 或適當的 API 認證方式。
- 匯出時機：每日排程流程的最後一步，於資料更新完成、Power BI dataset refresh 完成後才觸發匯出（避免匯出到舊資料）。

---

### 3.9 Email 自動寄送模組

**目的**：將每日分析結果寄送給訂閱使用者。

**Email 內容規格**：
```text
主旨：Market Sentinel 每日市場情報 — {日期}

內文：
1. 今日重要事件摘要（依 impact_score 排序前 N 筆，含事件標題、公司、方向、分數）
2. JPG 報告（附件或內嵌圖片）
3. Power BI Dashboard 連結
```

**技術要求**：
- 支援 HTML 格式 Email。
- 收件人清單需可設定（建議獨立設定檔或資料表管理訂閱者）。
- 寄送失敗需記錄 log 並可重試。

---

## 4. 自動化排程

**每日執行流程（建議時間：台股開盤前或收盤後，依需求決定）**：

```text
1. Crawler 抓取新聞
2. Cleaning & Dedup
3. AI 相關性判斷
4. 事件聚合
5. 金融影響分析（FinBERT + LLM）
6. 寫入資料庫
7. 觸發 Power BI dataset refresh
8. 等待 refresh 完成，匯出 JPG
9. 寄送 Email
```

**要求**：
- 整條流程需可透過排程工具（如 Airflow、cron + script、或雲端排程服務）觸發，並具備每一步驟的執行紀錄與失敗通知機制。
- 任一步驟失敗時，需記錄失敗原因並通知維運人員，避免無聲失敗（silent failure）。

---

## 5. 非功能性需求

- **可設定性**：相關性閾值、事件聚合相似度閾值、Signal/Noise 判斷門檻，均應可透過設定檔調整，不需修改程式碼。
- **可追溯性**：每個分析結果需可回溯至原始新聞（`news_id` → `raw_id` → 原始 URL），供人工複核。
- **成本控制**：LLM 呼叫需注意批次處理與快取，避免對同一內容重複呼叫。
- **可擴充性**：新聞來源、公司清單需能以資料驅動方式擴充，不需改動核心邏輯。

---

## 6. 建議開發階段（MVP → 完整版）

| 階段 | 範圍 |
|---|---|
| MVP | 單一新聞來源爬蟲 + AI 相關性判斷 + 基本情緒分析，結果存 DB，人工查看 |
| Phase 2 | 加入事件聚合、完整金融影響分析（Impact/Surprise/Signal-Noise） |
| Phase 3 | Power BI 串接、JPG 匯出、Email 自動化 |
| Phase 4 | 排程自動化、錯誤處理與監控、多來源擴充 |

---

## 7. 驗收 / Demo 情境（對應原 SPEC 第 9 節）

**驗收情境**：輸入一則「未直接提及公司名稱」的新聞（例如「全球 AI 伺服器需求增加，先進封裝產能吃緊」），系統需能：
1. 在 3.3 模組判斷出與 TSMC 的高相關性分數（範例目標：約 90 分以上）並附理由。
2. 產出對應事件與完整 Impact Analysis（Bullish、Impact Score、Long-term、Signal 等欄位）。
3. 該事件出現在 Power BI dashboard 與當日 Email 摘要中。

此情境即為系統核心賣點的最小可驗證單位：「AI 能理解間接影響，而非僅依賴關鍵字」。

---

## 8. 統整分析（補充：非原 SPEC 內容，為新增評估）

以下是針對整份規格書的可行性與風險評估，供你評估開發優先順序與資源配置。

**1. 系統核心價值與風險集中在同一個模組**
整個系統的賣點完全建立在 3.3「AI 相關性判斷」模組能否穩定辨識間接關聯（如「先進封裝產能吃緊 → 台積電」）。這也是最難量化驗證正確率的一環，建議在開發初期就建立一組「人工標註的測試新聞集」（例如 50–100 則涵蓋直接/間接/無關案例），用來持續評估 Prompt 與模型調整後的準確率，而不是憑感覺調整。

**2. 兩階段判斷（Embedding 篩選 + LLM 精判）是必要的，不是可選項**
若公司清單達到數百家以上，每則新聞都用 LLM 跟全部公司逐一比對，成本與延遲會快速失控。3.3.2 提到的兩階段設計應視為 MVP 就要做的架構決策，而非後期優化項目。

**3. 事件聚合（3.4）比想像中更容易出錯**
純向量相似度容易把「主題相近但非同一事件」的新聞誤判為同一事件（如「台積電法說會」vs「台積電資本支出」）。規格中已加入 LLM 二次確認機制，這點務必保留，否則會直接影響「每個事件只分析一次」這個核心承諾的正確性。

**4. Surprise Score 與 Signal/Noise 是主觀性最高的兩個欄位，需要明確的評分基準文件**
Impact Score 還能參考財報數字等相對客觀指標，但 Surprise Score（是否超乎市場預期）與 Signal/Noise 分類高度依賴「市場既有預期」這種難以量化的東西。建議另外寫一份簡短的「評分基準說明」給實作 AI 參考，並在系統上線後持續用實際案例校正，否則這兩個分數容易變得不穩定或流於形式。

**5. Power BI + JPG 匯出屬於中後段整合工作，技術風險相對低但依賴外部服務設定**
這部分不涉及 AI 判斷邏輯，主要風險在 Power BI API 認證與 dataset refresh 完成時機的掌握（規格中第 9 節已要求「等 refresh 完成才匯出」，這點容易被忽略導致抓到舊資料，需特別留意）。

**6. 建議的優先順序（若資源有限，Hackathon 情境下）**
若時間有限，建議優先完成 MVP 階段（3.1–3.3 + 基本情緒分析）並準備好 Demo 情境（第 7 節），因為這已足以展示「From Keyword Search to AI Market Understanding」的核心賣點。Power BI、Email 自動化屬於「完整產品化」的加分項，但不是說服評審的關鍵，可視剩餘時間決定是否完整實作或用簡化版本（如直接輸出 HTML 報告取代 Power BI）替代展示。

**7. 資料一致性與可追溯性建議提早設計**
規格中第 5 節提到的「可追溯性」（分析結果需能回溯到原始新聞）在開發後期補上通常很痛苦，建議一開始建表時就把 `raw_id` → `news_id` → `event_id` → `analysis_id` 的關聯鏈設計好，這對之後除錯 AI 誤判也很有幫助。

