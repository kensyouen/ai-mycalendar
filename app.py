import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
from streamlit_calendar import calendar
import json
import uuid
import os
from datetime import datetime
import pytz

# --- iOS風デザイン設定 ---
st.set_page_config(page_title="AI Calendar", page_icon="📅", layout="centered")
st.markdown("""
<style>
    .stApp { background-color: #F2F2F7; }
    html, body, [class*="css"] { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
    header { visibility: hidden; }
    footer { visibility: hidden; }
    .stTabs [data-baseweb="tab-list"] { gap: 6px; background-color: #E3E3E8; border-radius: 12px; padding: 4px; margin-bottom: 20px; }
    .stTabs [data-baseweb="tab"] { border-radius: 9px; padding: 8px 16px; background-color: transparent; border: none; color: #8E8E93; font-weight: 600; }
    .stTabs [aria-selected="true"] { background-color: #FFFFFF !important; color: #000000 !important; box-shadow: 0 3px 6px rgba(0,0,0,0.08); }
    .stButton > button { border-radius: 14px; font-weight: 600; height: 48px; border: none; width: 100%; transition: 0.2s; }
    .stButton > button[data-testid="baseButton-primary"] { background-color: #007AFF; color: white; }
    div[data-baseweb="input"] > div, div[data-baseweb="textarea"] > textarea, div[data-baseweb="select"] > div { border-radius: 12px !important; border: 1px solid #E5E5EA !important; background-color: #FFFFFF !important; }
    div[data-testid="stDialog"] > div { border-radius: 20px; }
</style>
""", unsafe_allow_html=True)

# --- 初期設定 ---
JST = pytz.timezone('Asia/Tokyo')
now_jst = datetime.now(JST)

SPREADSHEET_URL = os.environ.get("SPREADSHEET_URL")
GCP_SA_JSON = os.environ.get("GCP_SA_JSON")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-3.6-flash') 

@st.cache_resource
def init_gspread():
    credentials = Credentials.from_service_account_info(
        json.loads(GCP_SA_JSON),
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    client = gspread.authorize(credentials)
    return client.open_by_url(SPREADSHEET_URL).worksheet("Events")

sheet = init_gspread()

# --- 日時を見やすくする関数 ---
def format_datetime_str(dt_str):
    if not dt_str: return ""
    try:
        dt_str = dt_str.replace("T", " ")
        dt_obj = datetime.strptime(dt_str[:16], "%Y-%m-%d %H:%M")
        wd = ["月", "火", "水", "木", "金", "土", "日"][dt_obj.weekday()]
        return f"{dt_obj.month}月{dt_obj.day}日({wd}) {dt_obj.hour:02d}:{dt_obj.minute:02d}"
    except Exception:
        return dt_str

# --- AI解析関数 (新規追加) ---
def extract_schedule_from_memo(memo_text, notification_text):
    prompt = f"""
    AI秘書として、以下のメモからスケジュールと通知設定を抽出しJSONで出力してください。
    【現在時刻】: {now_jst.strftime('%Y年%m月%d日 %H:%M')}
    【予定の入力】: {memo_text}
    【AIに通知を登録してもらう】: {notification_text}
    
    【出力JSON】
    {{
        "title": "予定タイトル",
        "start_time": "YYYY-MM-DD HH:MM:00",
        "end_time": "YYYY-MM-DD HH:MM:00",
        "memo": "通知で送ってほしい内容や詳細",
        "notify_minutes_before": 60
    }}
    ※notify_minutes_beforeは通知タイミングを分単位の整数で（例:2時間前なら120。指定がなければ60）。JSON以外のテキストは含めないで。
    """
    response = model.generate_content(prompt)
    try:
        clean_text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_text)
    except Exception:
        return None

# --- AI解析関数 (編集用) ---
def edit_schedule_with_ai(record, edit_instruction):
    prompt = f"""
    AI秘書として、現在の予定にユーザーの「変更指示」を適用し、更新後の予定をJSONで出力してください。
    【現在の予定】タイトル: {record['title']}, 開始: {record['start_time']}, 終了: {record['end_time']}, メモ: {record['memo']}, 通知: {record['notify_minutes_before']}分前
    【変更指示】: {edit_instruction}
    【出力JSON】
    {{ "title": "変更後タイトル", "start_time": "YYYY-MM-DD HH:MM:00", "end_time": "YYYY-MM-DD HH:MM:00", "memo": "変更後メモ", "notify_minutes_before": 60 }}
    ※JSON以外含めないで。
    """
    response = model.generate_content(prompt)
    try:
        clean_text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_text)
    except Exception:
        return None

# --- 詳細ポップアップ ---
@st.dialog("🗓️ 予定の詳細")
def show_event_details(event):
    st.markdown(f"### {event['title']}")
    
    start_str = format_datetime_str(event.get('start', ''))
    end_str = format_datetime_str(event.get('end', ''))
    
    if start_str and end_str:
        start_date = start_str.split(" ")[0]
        end_date = end_str.split(" ")[0]
        if start_date == end_date: # 同じ日なら終了日は時間だけ表示
            st.write(f"**⏰ 日時:** {start_str} 〜 {end_str.split(' ')[1]}")
        else:
            st.write(f"**⏰ 日時:** {start_str} 〜 {end_str}")
            
    props = event.get('extendedProps', {})
    if props.get('memo'):
        st.write(f"**📝 メモ:**\n{props.get('memo')}")
    st.info(f"🔔 通知: {props.get('notify', 0)}分前")

# --- 編集ポップアップ ---
@st.dialog("✏️ 予定の編集")
def edit_event_dialog(record):
    st.markdown("**✨ AIにお任せ編集**")
    ai_edit_memo = st.text_input("例：「時間を16時に変更して通知を2時間前に」", key=f"ai_input_{record['id']}")
    if st.button("✨ AIで変更内容を適用", key=f"ai_btn_{record['id']}", type="primary"):
        if ai_edit_memo:
            with st.spinner("AIが修正中..."):
                updated = edit_schedule_with_ai(record, ai_edit_memo)
                if updated:
                    record.update(updated)
                    st.success("✅ 内容を書き換えました！下の保存ボタンを押してください。")
    st.divider()
    st.markdown("**✍️ 手動編集・保存**")
    new_title = st.text_input("タイトル", value=record['title'], key=f"t_{record['id']}")
    new_start = st.text_input("開始日時", value=record['start_time'], key=f"s_{record['id']}")
    new_end = st.text_input("終了日時", value=record['end_time'], key=f"e_{record['id']}")
    new_memo = st.text_area("詳細・通知用メモ", value=record['memo'], key=f"m_{record['id']}")
    new_notify = st.number_input("通知(分前)", value=int(record['notify_minutes_before']), step=15, key=f"n_{record['id']}")
    if st.button("💾 この内容で更新を保存", key=f"save_{record['id']}"):
        cell = sheet.find(record['id'])
        if cell:
            sheet.update(f"B{cell.row}:G{cell.row}", [[new_title, new_start, new_end, new_memo, new_notify, record['is_notified']]])
            st.rerun()

# --- UI構築 ---
st.title("📅 My AI Calendar")
tab1, tab2, tab3 = st.tabs(["✍️ 追加", "🗓️ カレンダー", "📋 予定一覧"])

with tab1:
    st.write("**① AIに予定を登録してもらう**")
    memo_input = st.text_area("予定の入力 (日時と内容)", placeholder="例：明日の15時にトヨペットで納車", height=80)
    
    st.write("**② AIに通知を登録してもらう（任意）**")
    notification_memo = st.text_area("通知の設定やメモ", placeholder="例：2時間前に、印鑑を忘れないように通知して！", height=80)
    
    notify_options = {"🤖 AIにおまかせ (上記から自動判断)": "auto", "🔕 通知しない": 0, "⏳ 15分前": 15, "⏳ 1時間前": 60, "📅 前日": 1440}
    selected_notify = st.selectbox("通知タイミング (手動上書き用)", list(notify_options.keys()))
    
    if st.button("✨ カレンダーに追加", type="primary"):
        if memo_input:
            with st.spinner("AIが登録中..."):
                schedule_data = extract_schedule_from_memo(memo_input, notification_memo)
                if schedule_data:
                    notify_val = notify_options[selected_notify]
                    final_notify = schedule_data.get("notify_minutes_before", 60) if notify_val == "auto" else notify_val
                    new_id = str(uuid.uuid4())
                    sheet.append_row([new_id, schedule_data.get("title", "名称未設定"), schedule_data.get("start_time", ""), schedule_data.get("end_time", ""), schedule_data.get("memo", ""), final_notify, "FALSE"])
                    st.success("✅ 追加しました！")
                    st.balloons()
        else:
            st.warning("予定を入力してください。")

with tab2:
    records = sheet.get_all_records()
    events = [{"title": r["title"], "start": r["start_time"], "end": r["end_time"], "extendedProps": {"memo": r["memo"], "notify": r["notify_minutes_before"]}} for r in records]
    cal_options = {"locale": "ja", "contentHeight": "auto", "headerToolbar": {"left": "prev,next", "center": "title", "right": "dayGridMonth,timeGridWeek"}, "initialView": "dayGridMonth", "buttonText": {"today": "今日", "month": "月", "week": "週"}}
    cal = calendar(events=events, options=cal_options, callbacks=['eventClick'])
    if cal.get("eventClick"): show_event_details(cal["eventClick"]["event"])

with tab3:
    if not records: st.info("予定はまだありません。")
    else:
        for r in sorted(records, key=lambda x: x['start_time']):
            with st.expander(f"📌 {r['title']} ({format_datetime_str(r['start_time'])})"):
                st.write(f"**時間**: {format_datetime_str(r['start_time'])} 〜 {format_datetime_str(r['end_time'])}")
                st.write(f"**通知**: {r['notify_minutes_before']}分前\n**メモ**: {r['memo']}")
                st.markdown("👇 **テキストをコピー**")
                st.code(f"【{r['title']}】\n日時: {format_datetime_str(r['start_time'])} 〜 {format_datetime_str(r['end_time'])}\nメモ: {r['memo']}", language="text")
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("✏️ 編集", key=f"edit_{r['id']}", use_container_width=True): edit_event_dialog(r)
                with col2:
                    if st.button("🗑️ 削除", key=f"del_{r['id']}", use_container_width=True):
                        if cell := sheet.find(r['id']):
                            sheet.delete_rows(cell.row)
                            st.rerun()
