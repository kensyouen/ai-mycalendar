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

# --- iOS風のスタイリッシュなデザイン設定 (カスタムCSS) ---
st.set_page_config(page_title="AI Calendar", page_icon="📅", layout="centered")
st.markdown("""
<style>
    /* 全体のフォントをiOS風(San Francisco)に */
    html, body, [class*="css"] {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }
    /* カード風のUI */
    .css-1r6slb0, .css-18e3th9 {
        background-color: #ffffff;
        border-radius: 15px;
        padding: 20px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
    }
    /* ボタンをiOSっぽく角丸に */
    .stButton > button {
        border-radius: 12px;
        font-weight: 600;
    }
    /* コピー機能のコードブロック背景をクリーンに */
    .stCodeBlock {
        border-radius: 10px;
    }
</style>
""", unsafe_allow_html=True)

# --- 初期設定とAPI連携 ---
JST = pytz.timezone('Asia/Tokyo')
now_jst = datetime.now(JST)

# Secretsから環境変数を取得
SPREADSHEET_URL = os.environ.get("SPREADSHEET_URL")
GCP_SA_JSON = os.environ.get("GCP_SA_JSON")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash') # 最新の高速モデルを使用

# スプレッドシート接続関数
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

# --- 機能1: AIによるメモからの予定抽出 ---
def extract_schedule_from_memo(memo_text):
    prompt = f"""
    あなたは優秀なAI秘書です。以下のユーザーのメモから、スケジュール情報を抽出し、必ず指定されたJSONフォーマットのみで出力してください。
    
    【現在の日本時間】: {now_jst.strftime('%Y年%m月%d日 %H:%M')}
    ※「明日」「来週」などの表現は、この現在時間を基準に具体的な日時に変換してください。
    
    【ユーザーのメモ】: {memo_text}
    
    【出力JSONフォーマット】
    {{
        "title": "予定のタイトル",
        "start_time": "YYYY-MM-DD HH:MM:00",
        "end_time": "YYYY-MM-DD HH:MM:00",
        "memo": "場所や詳細など",
        "notify_minutes_before": 60 
    }}
    ※notify_minutes_beforeは通知タイミングを分単位の整数で出力（例: 1時間前なら60、前日なら1440、指定がなければデフォルトで60）。
    ※終了時間が不明な場合は開始時間の1時間後を設定。
    ※JSON以外のテキスト（マークダウンの```など）は一切含めないでください。
    """
    response = model.generate_content(prompt)
    try:
        # Markdownの ```json や ``` が付いている場合を考慮して除去
        clean_text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_text)
    except Exception as e:
        st.error(f"AI解析エラー: もう少し具体的に書いてみてください。\n{e}")
        return None

# --- UI構築 ---
st.title("📅 My AI Calendar")

tab1, tab2, tab3 = st.tabs(["✍️ 予定の追加", "🗓️ カレンダー", "📋 予定一覧・コピー"])

# 【タブ1: 予定の追加 (AIメモ入力)】
with tab1:
    st.subheader("メモ書きで予定を追加")
    memo_input = st.text_area("例：「明日の15時から渋谷で会議。2時間前に通知して」", height=100)
    
    if st.button("✨ AIで自動入力", type="primary"):
        if memo_input:
            with st.spinner("AIが予定を解析中..."):
                schedule_data = extract_schedule_from_memo(memo_input)
                
                if schedule_data:
                    # スプレッドシートに保存
                    new_id = str(uuid.uuid4())
                    row = [
                        new_id,
                        schedule_data.get("title", "名称未設定"),
                        schedule_data.get("start_time", ""),
                        schedule_data.get("end_time", ""),
                        schedule_data.get("memo", memo_input),
                        schedule_data.get("notify_minutes_before", 60),
                        "FALSE" # 通知済みフラグ
                    ]
                    sheet.append_row(row)
                    st.success(f"✅ 追加しました: {schedule_data.get('title')} ({schedule_data.get('start_time')})")
        else:
            st.warning("メモを入力してください。")

# 【タブ2: カレンダー表示】
with tab2:
    records = sheet.get_all_records()
    events = []
    for r in records:
        events.append({
            "title": r["title"],
            "start": r["start_time"],
            "end": r["end_time"],
        })
    
    # カレンダーのオプション設定 (月/週切り替え可能)
    calendar_options = {
        "headerToolbar": {
            "left": "prev,next today",
            "center": "title",
            "right": "dayGridMonth,timeGridWeek" # 月と週の切り替えボタン
        },
        "initialView": "dayGridMonth",
        "buttonText": {
            "today": "今日",
            "month": "月",
            "week": "週"
        }
    }
    
    st.markdown("カレンダー上で月と週の表示を切り替えられます。")
    calendar(events=events, options=calendar_options)

# 【タブ3: 予定一覧とワンタッチコピー】
with tab3:
    st.subheader("今後の予定一覧")
    if not records:
        st.info("予定はまだありません。")
    else:
        for r in reversed(records): # 最新のものを上に
            # コピー用のテキストを作成
            copy_text = f"【{r['title']}】\n日時: {r['start_time']} 〜 {r['end_time']}\n詳細: {r['memo']}"
            
            with st.expander(f"📌 {r['title']} ({r['start_time'][:10]})"):
                st.write(f"**時間**: {r['start_time']} 〜 {r['end_time']}")
                st.write(f"**通知**: {r['notify_minutes_before']}分前")
                st.write(f"**詳細**: {r['memo']}")
                
                # Streamlitの機能を利用したワンタッチコピー用ブロック
                st.markdown("👇 **右上のアイコンからテキストをコピー**")
                st.code(copy_text, language="text")
                
                # 削除機能 (IDで検索して行を削除)
                if st.button("🗑️ この予定を削除", key=f"del_{r['id']}"):
                    cell = sheet.find(r['id'])
                    if cell:
                        sheet.delete_rows(cell.row)
                        st.rerun()
