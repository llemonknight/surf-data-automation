# Surf Data Automation

這個專案會定時抓取 Stormglass 海況資料，並呼叫 Vertex AI 微調模型產生評語，再寫入 Google Sheet。設定 Vertex AI 時優先使用它，AI Rating 留空；未設定時保留原有 OpenAI 呼叫方式。

## 資料流程

1. GitHub Actions 依排程執行 `collect_data.py`。
2. `collect_data.py` 從 Stormglass API 抓明天及後天 Doublelion 指定時段的預報海況。
3. 腳本會把各筆 Doublelion 預報海況送給已設定的模型。
4. 腳本將原始海況、人工回報欄位、AI 預測欄位一起寫入 Google Sheet。

目前只抓 Doublelion，不再抓 Wushigang。未來兩天指台灣日期 n+1、n+2，不含今天；每次執行都抓兩天各 09:00、14:00，共四筆，不再依 SESSION_NAME 篩選。將缺少資料的日期合併成一次 Stormglass 區間請求，並依回傳時間精確選取資料。四筆都已存在時不呼叫 API；已有預報不會更新，因此某日期的預報可能保留兩天前抓取的版本。Vertex AI 有回傳評語才新增該筆資料；空白或失敗的回答不寫入，下次執行可重試。

## Google Sheet 欄位

每次收集結束後，Sheet 會依 Date、Time 升冪排序（同一天 09:00 在 14:00 前），標題列不動。排序會移動整列，保留人工評分、評語與額外欄位的對應關係；歷史 Wushigang 資料保留。若舊版 GitHub 排程仍在追加當天或 Wushigang 資料，需要同步更新或停用該舊排程。

腳本會維護第一列欄位：

```text
Date, Time, Wave Height (m), Wave Period (s), Wave Direction,
Wind Speed (m/s), Wind Direction, Sea Level (m),
My Rating, Comments, Spot, AI Rating, AI Comments, AI Model
```

`My Rating` 和 `Comments` 保留給使用者人工回報。

Vertex AI 會填入 `AI Comments` 與端點識別 `AI Model`；此模型只訓練評語，因此 `AI Rating` 留空。

## GitHub Secrets

必要：

```text
STORMGLASS_API_KEY
GOOGLE_CREDENTIALS
```

`GOOGLE_CREDENTIALS` 必須填入服務帳戶金鑰檔的完整 JSON 內容，不能填本機路徑。
該服務帳戶需有試算表編輯權限，及模型所在專案的 `aiplatform.endpoints.predict` 權限（例如 `roles/aiplatform.user`）。
不要將 `.env` 或私鑰 JSON 上傳到儲存庫。

目前 workflow 已設定下列 Vertex AI 端點，不需要 OpenAI API key：

```text
VERTEX_PROJECT_ID=pelagic-gist-455209-e6
VERTEX_LOCATION=us
VERTEX_ENDPOINT_ID=3548132818926174208
```

未設定 Vertex AI 時，程式仍保留 `OPENAI_API_KEY`、`OPENAI_MODEL`（或 `OPENAI_RATING_MODEL` / `OPENAI_COMMENT_MODEL`）的舊版替代流程。

## GitHub 更新與驗收

1. 更新 `collect_data.py`、`requirements.txt`、`.github/workflows/main.yml`，並一併提交 `tests/`、`scripts/`、`.gitignore`、`.env.example` 與 README。
2. 在 Settings → Secrets and variables → Actions 確認上述兩個 secrets。
3. 先在更新分支透過 Run workflow 手動驗收，再合併到預設分支；若 workflow 之前停用，需先啟用才能手動執行。啟用時舊預設分支的排程也會恢復，請避開排程時間或先合併再手動驗收。
4. 檢查 Actions 紀錄與 Sheet：未來兩天各 09:00、14:00，只新增 Doublelion，有 AI 評語，最後依日期時間排序。已存在的資料會跳過，不會強制重跑模型。

排程維持台灣時間 09:14、14:15，每次涵蓋完整四個時段。workflow 先跑離線測試，再執行收集；同一 workflow 的寫入會依序執行。GitHub 排程可能延遲，並非精準定時器。

## 本機測試

本機可在專案根目錄 `.env` 設定與 GitHub Actions 同名的環境變數。
請填入 `STORMGLASS_API_KEY`，Google 憑證路徑與已確認的 Vertex AI 端點已預填。
程式會自動載入 `.env`；目前 PowerShell 或 GitHub Actions 已有的環境變數優先，不會被覆蓋。
`.env` 已加入 `.gitignore`，不要提交實際金鑰。GitHub Actions 仍使用 repository secrets，不會自動同步本機設定。

安裝依賴後，Vertex AI 模擬資料測試可執行 `python scripts/test_vertex.py`，不必再指定專案。
`VERTEX_*` 設定也供每日收集程式使用。GitHub workflow 已設定已驗證的端點，GOOGLE_CREDENTIALS secret 必須是有該端點呼叫權限的服務帳戶。需將本機程式與 workflow 更新到 GitHub 才會影響線上排程。

先安裝依賴：

```powershell
pip install -r requirements.txt
```

Google service account 預設會讀取：

```text
D:\antigravity\surf-data-automation\secrets\google-key.json
```

如果 key 放在其他位置，可以設定：

```powershell
$env:GOOGLE_CREDENTIALS_FILE = "D:\path\to\google-key.json"
```

新環境可從範例建立設定檔，再填入真正的 Stormglass key 與本機 Google 憑證路徑：

```powershell
Copy-Item .env.example .env
```

已有 `.env` 時直接編輯，避免覆蓋現有設定。

每次執行涵蓋兩天早、下午；舊的 `-SessionName` 參數仍接受，但不再限制時段：

```powershell
.\scripts\run_local.ps1
```
