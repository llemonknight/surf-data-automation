import os
import requests
import arrow
import gspread
import json
from google.oauth2.service_account import Credentials

# ================= 設定區 =================
STORMGLASS_API_KEY = os.environ.get("STORMGLASS_API_KEY")
SHEET_NAME = os.environ.get("SHEET_NAME", "Surf_AI_Dataset")
GOOGLE_CREDENTIALS = os.environ.get("GOOGLE_CREDENTIALS") # JSON string

SPOTS = {
    "Wushigang": {'lat': 24.8706, 'lng': 121.8416},
    "Doublelion": {'lat': 24.8887033, 'lng': 121.8499292},
}

SESSION_HOURS = {
    "Morning": 9,
    "Afternoon": 14
}
# =========================================

def get_surf_data(lat, lng, spot_name, target_hour, date=None):
    url = "https://api.stormglass.io/v2/weather/point"

    if date:
        target_time = arrow.get(date).replace(tzinfo='Asia/Taipei').replace(hour=target_hour, minute=0, second=0, microsecond=0)
    else:
        target_time = arrow.now('Asia/Taipei').replace(hour=target_hour, minute=0, second=0, microsecond=0)

    params = {
        'lat': lat,
        'lng': lng,
        'params': ','.join(['waveHeight', 'wavePeriod', 'waveDirection', 'windSpeed', 'windDirection', 'seaLevel']),
        'start': target_time.to('UTC').timestamp(),
        'end': target_time.to('UTC').timestamp(),
        'source': 'sg'
    }
    headers = {'Authorization': STORMGLASS_API_KEY}

    try:
        response = requests.get(url, params=params, headers=headers)
        if response.status_code != 200:
            print(f"⚠️ {spot_name} API 請求失敗: {response.text}")
            return None

        data = response.json()
        if 'hours' not in data or len(data['hours']) == 0:
            print(f"⚠️ {spot_name} 查無資料")
            return None

        item = data['hours'][0]
        sea_level = item.get('seaLevel', {}).get('sg', 0.0)

        return [
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
        ]
    except Exception as e:
        print(f"❌ {spot_name} 發生錯誤: {e}")
        return None

def main():
    if not STORMGLASS_API_KEY or not GOOGLE_CREDENTIALS:
        print("❌ 錯誤：缺少的環境變數 (STORMGLASS_API_KEY 或 GOOGLE_CREDENTIALS)")
        return

    # 驗證 Google Service Account
    try:
        creds_dict = json.loads(GOOGLE_CREDENTIALS)
        scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        gc = gspread.authorize(creds)
        sh = gc.open(SHEET_NAME)
        worksheet = sh.sheet1
        print(f"✅ 成功連結到試算表: {SHEET_NAME}")
    except Exception as e:
        print(f"❌ 無法存取試算表: {e}")
        return

    # 判斷現在應該抓哪個時段 (根據目前台灣時間)
    now_taipei = arrow.now('Asia/Taipei')
    current_hour = now_taipei.hour
    
    # 自動判定邏輯：如果是上午 8-11 點跑，抓 Morning；如果是下午 13-16 點跑，抓 Afternoon
    # 如果是手動跑或排程，可以由參數決定，這裡先簡單判斷
    if 8 <= current_hour <= 12:
        session_name = "Morning"
    else:
        session_name = "Afternoon"

    target_hour = SESSION_HOURS[session_name]
    today_str = now_taipei.format('YYYY-MM-DD')
    
    print(f"🌊 自動任務開始：抓取 {today_str} 的 {session_name} 時段數據...")

    existing_data = worksheet.get_all_values()
    existing_keys = set()
    for row in existing_data[1:]:
        if len(row) >= 11:
            existing_keys.add(f"{row[0]}_{row[1]}_{row[10]}")

    for name, coords in SPOTS.items():
        target_time_str = f"{target_hour:02d}:00"
        check_key = f"{today_str}_{target_time_str}_{name}"

        if check_key in existing_keys:
            print(f"⏭️ 跳過：{name} {session_name} 的資料已存在。")
            continue

        row_data = get_surf_data(coords['lat'], coords['lng'], name, target_hour, date=today_str)
        if row_data:
            worksheet.append_row(row_data)
            print(f"✅ 已寫入 {name} ({session_name}) - 潮高: {row_data[7]}m")


if __name__ == "__main__":
    main()
