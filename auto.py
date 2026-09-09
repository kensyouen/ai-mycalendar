import os
import json
import requests
from datetime import datetime, timedelta
import pytz
import gspread
from google.oauth2.service_account import Credentials

# --- 初期設定 ---
JST = pytz.timezone('Asia/Tokyo')
now_jst = datetime.now(JST)

SPREADSHEET_URL = os.environ.get("SPREADSHEET_URL")
GCP_SA_JSON = os.environ.get("GCP_SA_JSON")
LINE_USER_ID = os.environ.get("LINE_USER_ID")
LINE_ACCESS_TOKEN = os.environ.get("LINE_ACCESS_TOKEN")

def send_line_message(text):
    headers = {
        "Authorization": f"Bearer {LINE_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {
        "to": LINE_USER_ID,
        "messages": [{"type": "text", "text": text}]
    }
    requests.post("https://api.line.me/v2/bot/message/push", headers=headers, json=data)

def format_datetime_str(dt_str):
    try:
        dt_obj = datetime.strptime(dt_str[:16], "%Y-%m-%d %H:%M")
        wd = ["月", "火", "水", "木", "金", "土", "日"][dt_obj.weekday()]
        return f"{dt_obj.month}月{dt_obj.day}日({wd}) {dt_obj.hour:02d}:{dt_obj.minute:02d}"
    except Exception:
        return dt_str

def main():
    # スプレッドシートに接続
    credentials = Credentials.from_service_account_info(
        json.loads(GCP_SA_JSON), scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    client = gspread.authorize(credentials)
    sheet = client.open_by_url(SPREADSHEET_URL).worksheet("Events")
    records = sheet.get_all_records()
    
    for i, record in enumerate(records):
        # 既に通知済みのものはスキップ
        if str(record.get('is_notified')).upper() == 'TRUE':
            continue
            
        start_str = str(record.get('start_time')).replace("T", " ")
        try:
            start_time = JST.localize(datetime.strptime(start_str[:16], "%Y-%m-%d %H:%M"))
        except Exception:
            continue
            
        # 通知すべき時間を計算
        notify_minutes = int(record.get('notify_minutes_before', 60))
        notify_time = start_time - timedelta(minutes=notify_minutes)
        
        # 現在時刻が「通知すべき時間」を過ぎていて、かつ「予定開始時刻」より前なら通知
        if notify_time <= now_jst <= start_time:
            title = record.get('title', '予定')
            memo = record.get('memo', '')
            time_str = format_datetime_str(start_str)
            
            message = f"🔔 まもなく予定の時間です！\n\n【{title}】\n⏰ 日時: {time_str}"
            if memo:
                message += f"\n📝 メモ: {memo}"
                
            send_line_message(message)
            
            # スプレッドシートの「通知済みフラグ(G列)」を TRUE に書き換える (ヘッダー行があるので行番号は i + 2)
            sheet.update_cell(i + 2, 7, 'TRUE')

if __name__ == "__main__":
    main()
