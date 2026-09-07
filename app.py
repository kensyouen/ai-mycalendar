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

# --- iOS風の超スタイリッシュなデザイン設定 (カスタムCSS) ---
st.set_page_config(page_title="AI Calendar", page_icon="📅", layout="centered")
st.markdown("""
<style>
    /* 全体の背景をiOSのシステムグレー風に */
    .stApp { background-color: #F2F2F7; }
    html, body, [class*="css"] { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
    /* ヘッダーとフッターを隠してネイティブアプリっぽく */
    header { visibility: hidden; }
    footer { visibility: hidden; }
    
    /* タブをiOSのセグメントコントロール風に */
    .stTabs [data-baseweb="tab-list"] {
        gap: 6px; background-color: #E3E3E8; border-radius: 12px; padding: 4px; margin-bottom: 20px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 9px; padding: 8px 16px; background-color: transparent; border: none; color: #8E8E93; font-weight: 600;
    }
    .stTabs [aria-selected="true"] {
        background-color: #FFFFFF !important; color: #000000 !important; box-shadow: 0 3px 6px rgba(0,0,0,0.08);
    }
    /* ボタンを丸くスタイリッシュに */
    .stButton > button {
        border-radius: 14px; font-weight: 600; height: 48px; border: none; width: 100%; transition: 0.2s;
    }
    .stButton > button[data-testid="baseButton-primary"] {
        background-color: #007AFF; color: white;
    }
    .stButton > button[data-testid="baseButton-secondary"] {
        background-color: #FFFFFF; color: #007AFF; box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
    /* 入力フォームの角丸化 */
    div[data-baseweb="input"] > div, div[data-baseweb="textarea"] > textarea, div[data-baseweb="select"] > div {
        border-radius: 12px !important; border: 1px solid #E5E5EA !important; background-color: #FFFFFF !important;
    }
    /* 展開メニュー（Expander）のデザイン */
    .streamlit-expanderHeader { font-weight: bold; color: #1C1C1E; }
</style>
""", unsafe_allow_html=True)

# --- 初期設定とAPI連携 ---
JST = pytz.timezone('Asia/Tokyo')
now_jst = datetime.now(JST)

SPREADSHEET_URL = os.environ.get("SPREADSHEET_URL")
GCP_SA_JSON = os.environ.get("GCP_SA_JSON")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-3.6-flash') # AIモデル

@st.cache_resource
def init_gspread():
    credentials = Credentials.from_service_account_info(
        json.loads(GCP_SA_JSON),
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    client = gspread.authorize(credentials)
    sheet = client.open_by_url(SPREADSHEET_URL).worksheet("Events")
    return sheet

sheet = init_gspread()

# --- 機能: AI解析 ---
def extract_schedule_from_memo(memo_text):
    prompt = f"""
    あなたは優秀なAI秘書です。以下のユーザーの予定メモから、スケジュール情報を抽出し、必ず指定されたJSONフォーマットのみで出力してください。
    【現在の日本時間】: {now_jst.strftime('%Y年%m月%d日 %H:%M')}
    【ユーザーのメモ】: {memo_text}
    【出力JSONフォーマット】
    {{
        "title": "予定のタイトル",
        "start_time": "YYYY-MM-DD HH:MM:00",
        "end_time": "YYYY-MM-DD HH:MM:00",
        "memo": "詳細",
        "notify_minutes_before": 60 
    }}
    ※notify_minutes_beforeは通知タイミングを分単位の整数で出力。指定がなければ60。
    """
    response = model.generate_content(prompt)
    try:
        clean_text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_text)
    except Exception as e:
        st.error(f"解析エラー: もう少し具体的に書いてみてください。")
        return None

# --- ポップアップ（ダイアログ）機能 ---
@st.dialog("🗓️ 予定の詳細")
def show_event_details(event):
    st.markdown(f"### {event['title']}")
    st.write(f"**⏰ 日時:** {event['start']} 〜 {event['end']}")
    props = event.get('extendedProps', {})
    st.write(f"**📝 メモ:** {props.get('memo', '')}")
    st.info(f"🔔 通知: {props.get('notify', 0)}分前")

@st.dialog("✏️ 予定の編集")
def edit_event_dialog(record):
    st.markdown("内容を書き換えて保存してください。")
    new_title = st.text_input("タイトル", value=record['title'])
    new_start = st.text_input("開始日時 (YYYY-MM-DD HH:MM:SS)", value=record['start_time'])
    new_end = st.text_input("終了日時 (YYYY-MM-DD HH:MM:SS)", value=record['end_time'])
    new_memo = st.text_area("詳細メモ", value=record['memo'])
    new_notify = st.number_input("通知(分前)", value=int(record['notify_minutes_before']), step=15)
    
    if st.button("💾 更新を保存", type="primary"):
        cell = sheet.find(record['id'])
        if cell:
            # gspreadのupdate機能で該当行を丸ごと書き換え
            sheet.update(f"B{cell.row}:G{cell.row}", [[new_title, new_start, new_end, new_memo, new_notify, record['is_notified']]])
            st.success("更新しました！")
            st.rerun()

# --- UI構築 ---
st.title("📅 My AI Calendar")

tab1, tab2, tab3 = st.tabs(["✍️ 追加", "🗓️ カレンダー", "📋 予定一覧"])

# 【タブ1: 予定の追加】
with tab1:
    st.write("予定の内容を入力してください。")
    memo_input = st.text_area("予定メモ", placeholder="例：明日の15時にトヨペットで納車予定", height=120)
    
    # 通知設定を別枠で作成
    notify_options = {
        "🤖 AIにおまかせ (メモから自動判断)": "auto",
        "🔕 通知しない": 0,
        "⏳ 15分前": 15,
        "⏳ 1時間前": 60,
        "⏳ 2時間前": 120,
        "📅 前日 (24時間前)": 1440
    }
    selected_notify = st.selectbox("通知のタイミング", list(notify_options.keys()))
    
    if st.button("✨ AIでカレンダーに追加", type="primary"):
        if memo_input:
            with st.spinner("AIがカレンダーに登録中..."):
                schedule_data = extract_schedule_from_memo(memo_input)
                if schedule_data:
                    # UIで選んだ通知設定を反映 ("auto"以外の場合)
                    notify_val = notify_options[selected_notify]
                    if notify_val != "auto":
                        schedule_data["notify_minutes_before"] = notify_val
                    
                    new_id = str(uuid.uuid4())
                    row = [
                        new_id,
                        schedule_data.get("title", "名称未設定"),
                        schedule_data.get("start_time", ""),
                        schedule_data.get("end_time", ""),
                        schedule_data.get("memo", memo_input),
                        schedule_data.get("notify_minutes_before", 60),
                        "FALSE"
                    ]
                    sheet.append_row(row)
                    st.success(f"✅ カレンダーに追加しました！")
                    st.balloons()
        else:
            st.warning("予定メモを入力してください。")

# 【タブ2: カレンダー表示】
with tab2:
    records = sheet.get_all_records()
    events = []
    for r in records:
        events.append({
            "title": r["title"],
            "start": r["start_time"],
            "end": r["end_time"],
            # 詳細表示用の隠しデータ
            "extendedProps": {
                "memo": r["memo"],
                "notify": r["notify_minutes_before"]
            }
        })
    
    calendar_options = {
        "headerToolbar": {"left": "prev,next", "center": "title", "right": "dayGridMonth,timeGridWeek"},
        "initialView": "dayGridMonth",
        "buttonText": {"month": "月", "week": "週"}
    }
    
    # callbacks=['eventClick'] をつけることでタップに反応させる
    cal = calendar(events=events, options=calendar_options, callbacks=['eventClick'])
    if cal.get("eventClick"):
        # タップされたら詳細ダイアログを表示
        show_event_details(cal["eventClick"]["event"])

# 【タブ3: 予定一覧・編集・コピー】
with tab3:
    if not records:
        st.info("予定はまだありません。")
    else:
        for r in reversed(records):
            copy_text = f"【{r['title']}】\n日時: {r['start_time']} 〜 {r['end_time']}\n詳細: {r['memo']}"
            
            with st.expander(f"📌 {r['title']} ({r['start_time'][:10]})"):
                st.write(f"**時間**: {r['start_time']} 〜 {r['end_time']}")
                st.write(f"**通知**: {r['notify_minutes_before']}分前")
                st.write(f"**詳細**: {r['memo']}")
                
                st.markdown("👇 **テキストをコピー**")
                st.code(copy_text, language="text")
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("✏️ 編集", key=f"edit_{r['id']}", use_container_width=True):
                        edit_event_dialog(r)
                with col2:
                    if st.button("🗑️ 削除", key=f"del_{r['id']}", use_container_width=True):
                        cell = sheet.find(r['id'])
                        if cell:
                            sheet.delete_rows(cell.row)
                            st.rerun()
