import os
import requests
import arrow
import gspread
import json
import re
from pathlib import Path
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from google.auth.transport.requests import AuthorizedSession

load_dotenv(Path(__file__).resolve().parent / ".env", override=False)

# ================= 設定區 =================
STORMGLASS_API_KEY = os.environ.get("STORMGLASS_API_KEY")
SHEET_NAME = os.environ.get("SHEET_NAME", "Surf_AI_Dataset")
GOOGLE_CREDENTIALS = os.environ.get("GOOGLE_CREDENTIALS") # JSON string
GOOGLE_CREDENTIALS_FILE = os.environ.get(
    "GOOGLE_CREDENTIALS_FILE",
    r"D:\antigravity\surf-data-automation\secrets\google-key.json",
)
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL")
OPENAI_RATING_MODEL = os.environ.get("OPENAI_RATING_MODEL", OPENAI_MODEL)
OPENAI_COMMENT_MODEL = os.environ.get("OPENAI_COMMENT_MODEL", OPENAI_MODEL)
VERTEX_PROJECT_ID = os.environ.get("VERTEX_PROJECT_ID")
VERTEX_LOCATION = os.environ.get("VERTEX_LOCATION", "us")
VERTEX_ENDPOINT_ID = os.environ.get("VERTEX_ENDPOINT_ID")

SPOTS = {
    "Doublelion": {'lat': 24.8887033, 'lng': 121.8499292},
}

SESSION_HOURS = {
    "Morning": 9,
    "Afternoon": 14
}

SHEET_HEADERS = [
    "Date",
    "Time",
    "Wave Height (m)",
    "Wave Period (s)",
    "Wave Direction",
    "Wind Speed (m/s)",
    "Wind Direction",
    "Sea Level (m)",
    "My Rating",
    "Comments",
    "Spot",
    "AI Rating",
    "AI Comments",
    "AI Model",
]
# =========================================

def is_ascii(value):
    if not value:
        return True

    try:
        value.encode("ascii")
        return True
    except UnicodeEncodeError:
        return False

def load_google_credentials():
    if GOOGLE_CREDENTIALS:
        return json.loads(GOOGLE_CREDENTIALS)

    if GOOGLE_CREDENTIALS_FILE and os.path.exists(GOOGLE_CREDENTIALS_FILE):
        with open(GOOGLE_CREDENTIALS_FILE, "r", encoding="utf-8") as file:
            return json.load(file)

    return None

def ensure_headers(worksheet):
    existing_headers = worksheet.row_values(1)
    if existing_headers[:len(SHEET_HEADERS)] == SHEET_HEADERS:
        return

    if not existing_headers:
        worksheet.append_row(SHEET_HEADERS)
        return

    worksheet.update(values=[SHEET_HEADERS], range_name="A1:N1")

def sort_forecast_rows(worksheet):
    rows = worksheet.get_all_values()[1:]
    # Displayed dates/times can represent either text or native Sheets numbers.
    def key(index):
        row = rows[index]
        if not row or not row[0]:
            return ('9999-12-31', 24, 0)
        hour, minute = map(int, row[1].split(':'))
        return (arrow.get(row[0]).format('YYYY-MM-DD'), hour, minute)

    current = list(range(len(rows)))
    ordered = sorted(current, key=key)
    moves = []
    for position, identity in enumerate(ordered):
        source = current.index(identity)
        if source == position:
            continue
        # Native row moves preserve extra columns, formatting and user reports.
        moves.append({'moveDimension': {
            'source': {'sheetId': worksheet.id, 'dimension': 'ROWS', 'startIndex': source + 1, 'endIndex': source + 2},
            'destinationIndex': position + 1,
        }})
        current.insert(position, current.pop(source))
    if moves:
        worksheet.spreadsheet.batch_update({'requests': moves})

def format_surf_context(row_data, title):
    return (
        f"{title}\n"
        f"Date: {row_data[0]}\n"
        f"Time: {row_data[1]}\n"
        f"Spot: {row_data[10]}\n"
        f"Wave Height (m): {row_data[2]}\n"
        f"Wave Period (s): {row_data[3]}\n"
        f"Wave Direction: {row_data[4]}\n"
        f"Wind Speed (m/s): {row_data[5]}\n"
        f"Wind Direction: {row_data[6]}\n"
        f"Sea Level (m): {row_data[7]}"
    )

def build_surf_prompt(row_data, task):
    return f"請根據以下預報海況{task}：\n\n{format_surf_context(row_data, '預報海況')}"

def extract_response_text(data):
    if data.get("output_text"):
        return data["output_text"].strip()

    output_parts = []
    for item in data.get("output", []):
        for content in item.get("content", []):
            text = content.get("text")
            if text:
                output_parts.append(text)
    return "\n".join(output_parts).strip()

def ask_openai_model(model, system_prompt, user_prompt):
    if not OPENAI_API_KEY or not model:
        return ""

    try:
        response = requests.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "input": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.2,
            },
            timeout=30,
        )
        if response.status_code != 200:
            print(f"⚠️ OpenAI API 請求失敗: {response.text}")
            return ""

        return extract_response_text(response.json())
    except Exception as e:
        print(f"❌ OpenAI API 發生錯誤: {e}")
        return ""

def predict_vertex_fields(row_data):
    endpoint = f"projects/{VERTEX_PROJECT_ID}/locations/{VERTEX_LOCATION}/endpoints/{VERTEX_ENDPOINT_ID}"
    host = f"aiplatform.{VERTEX_LOCATION}.rep.googleapis.com" if VERTEX_LOCATION in ("us", "eu") else f"{VERTEX_LOCATION}-aiplatform.googleapis.com"
    prompt = "請根據以下海況生成一段簡短評語：\n" + "\n".join(
        f"{label}: {value}" for label, value in zip(SHEET_HEADERS[2:8], row_data[2:8])
    ) + f"\nTime: {row_data[1]}\nSpot: {row_data[10]}"
    try:
        creds = Credentials.from_service_account_info(load_google_credentials(), scopes=['https://www.googleapis.com/auth/cloud-platform'])
        with AuthorizedSession(creds) as session:
            response = session.post(
                f"https://{host}/v1beta1/{endpoint}:generateContent",
                json={
                    "systemInstruction": {"parts": [{"text": "你是一個衝浪海況分析助手，根據海況數值生成簡短、自然的浪人回饋。"}]},
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                },
                timeout=120,
            )
        response.raise_for_status()
        comment = "\n".join(
            part['text'] for candidate in response.json().get('candidates', [])
            for part in candidate.get('content', {}).get('parts', [])
            if part.get('text') and not part.get('thought')
        ).strip()
        return ['', comment, endpoint if comment else '']
    except Exception as e:
        print(f"Vertex AI 請求失敗: {e}")
        return ['', '', '']


def predict_ai_fields(row_data):
    if VERTEX_PROJECT_ID and VERTEX_ENDPOINT_ID:
        return predict_vertex_fields(row_data)
    rating = ask_openai_model(
        OPENAI_RATING_MODEL,
        "你是一個衝浪海況分析助手，根據海況數值輸出浪人評分。只輸出 1 到 5 的分數。",
        build_surf_prompt(row_data, "預測浪人評分"),
    )
    rating_match = re.search(r"\b[1-5](?:\.\d+)?\b", rating)
    rating = rating_match.group(0) if rating_match else rating.strip()

    comment = ask_openai_model(
        OPENAI_COMMENT_MODEL,
        "你是一個衝浪海況分析助手，根據海況數值生成簡短、自然的浪人回饋。",
        build_surf_prompt(row_data, "生成一段簡短評語"),
    )

    model_names = []
    if OPENAI_RATING_MODEL:
        model_names.append(f"rating={OPENAI_RATING_MODEL}")
    if OPENAI_COMMENT_MODEL and OPENAI_COMMENT_MODEL != OPENAI_RATING_MODEL:
        model_names.append(f"comment={OPENAI_COMMENT_MODEL}")

    return [rating, comment, "; ".join(model_names)]

def get_surf_data(lat, lng, spot_name, target_hours, dates):
    url = "https://api.stormglass.io/v2/weather/point"

    target_times = [
        arrow.get(date).replace(tzinfo='Asia/Taipei').replace(hour=target_hour, minute=0, second=0, microsecond=0)
        for date in dates
        for target_hour in target_hours
    ]
    if not target_times:
        return []

    params = {
        'lat': lat,
        'lng': lng,
        'params': ','.join(['waveHeight', 'wavePeriod', 'waveDirection', 'windSpeed', 'windDirection', 'seaLevel']),
        'start': min(target_times).to('UTC').timestamp(),
        'end': max(target_times).to('UTC').timestamp(),
        'source': 'sg'
    }
    headers = {'Authorization': STORMGLASS_API_KEY}

    try:
        response = requests.get(url, params=params, headers=headers, timeout=30)
        if response.status_code != 200:
            print(f"⚠️ {spot_name} API 請求失敗: {response.text}")
            return []

        data = response.json()
        if 'hours' not in data or len(data['hours']) == 0:
            print(f"⚠️ {spot_name} 查無資料")
            return []

        hours = {arrow.get(item['time']).timestamp(): item for item in data['hours']}
        rows = []
        for target_time in target_times:
            item = hours.get(target_time.timestamp())
            if item is None:
                print(f"⚠️ {spot_name} {target_time.isoformat()} 查無對應時段資料")
                continue
            sea_level = item.get('seaLevel', {}).get('sg', 0.0)
            rows.append([
                target_time.format('YYYY-MM-DD'),
                target_time.format('HH:mm'),
                item['waveHeight']['sg'],
                item['wavePeriod']['sg'],
                item['waveDirection']['sg'],
                item['windSpeed']['sg'],
                item['windDirection']['sg'],
                sea_level,
                "", # My Rating
                "", # Comments
                spot_name
            ])
        return rows
    except Exception as e:
        print(f"❌ {spot_name} 發生錯誤: {e}")
        return []

def main():
    creds_dict = load_google_credentials()
    missing_config = []
    if not STORMGLASS_API_KEY:
        missing_config.append("STORMGLASS_API_KEY")
    if not creds_dict:
        missing_config.append("Google credentials")

    if missing_config:
        print(f"❌ 錯誤：缺少 {', '.join(missing_config)}")
        print(f"   Google key 路徑: {GOOGLE_CREDENTIALS_FILE}")
        return
    if not is_ascii(STORMGLASS_API_KEY):
        print("❌ 錯誤：STORMGLASS_API_KEY 含有非英數字元，請確認你貼的是 Stormglass 真正的 API key。")
        return
    vertex_enabled = bool(VERTEX_PROJECT_ID and VERTEX_ENDPOINT_ID)
    if vertex_enabled:
        print("使用 Vertex AI 產生評語，AI Rating 留空。")
    elif not OPENAI_API_KEY or not (OPENAI_RATING_MODEL or OPENAI_COMMENT_MODEL):
        print("⚠️ 未設定 OpenAI 模型環境變數，本次只寫入海況數據，不產生 AI 預測。")
    elif not is_ascii(OPENAI_API_KEY):
        print("❌ 錯誤：OPENAI_API_KEY 含有非英數字元，請確認你貼的是 OpenAI 真正的 API key。")
        return

    # 驗證 Google Service Account
    try:
        scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        gc = gspread.authorize(creds)
        sh = gc.open(SHEET_NAME)
        worksheet = sh.sheet1
        ensure_headers(worksheet)
        print(f"✅ 成功連結到試算表: {SHEET_NAME}")
    except Exception as e:
        print(f"❌ 無法存取試算表: {e}")
        return

    # 每次涵蓋未來兩天的上午與下午。
    now_taipei = arrow.now('Asia/Taipei')
    forecast_dates = [now_taipei.shift(days=days).format('YYYY-MM-DD') for days in (1, 2)]

    print(f"🌊 自動任務GOGO：抓取 {', '.join(forecast_dates)} 的 09:00、14:00 預報數據...")

    existing_data = worksheet.get_all_values()
    existing_keys = set()
    for row in existing_data[1:]:
        if len(row) >= 11:
            existing_keys.add(f"{row[0]}_{row[1]}_{row[10]}")

    for name, coords in SPOTS.items():
        pending_dates = []
        for forecast_date in forecast_dates:
            if any(f"{forecast_date}_{hour:02d}:00_{name}" not in existing_keys for hour in SESSION_HOURS.values()):
                pending_dates.append(forecast_date)

        for row_data in get_surf_data(coords['lat'], coords['lng'], name, SESSION_HOURS.values(), dates=pending_dates):
            if f"{row_data[0]}_{row_data[1]}_{name}" in existing_keys:
                continue
            row_data.extend(predict_ai_fields(row_data))
            if vertex_enabled and not row_data[12]:
                print(f"AI 評語為空，暫不寫入 {row_data[0]} {row_data[1]}，下次可重試。")
                continue
            worksheet.append_row(row_data, value_input_option='RAW')
            print(f"✅ 已寫入 {name} {row_data[0]} {row_data[1]} - AI 評語: {row_data[12] or 'N/A'}")

    sort_forecast_rows(worksheet)

if __name__ == "__main__":
    main()
