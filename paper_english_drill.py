import streamlit as st
import random
import pandas as pd
import os

st.set_page_config(page_title="Paper English Drill", page_icon="🎓")

st.title("論文英語フレーズ・ドリル")
st.write("JCM/JAC投稿に向けた英語の「型」を反復学習します。")

# ==========================================
# 常に最新のCSVを読み込む関数
# ==========================================
def load_latest_data():
    if os.path.exists('phrases.csv'):
        try:
            df = pd.read_csv('phrases.csv')
            return df.to_dict('records')
        except Exception as e:
            st.error(f"CSVの読み込みエラー: {e}")
            return []
    else:
        st.error("同じフォルダに phrases.csv が見つかりません。")
        return []

qa_data = load_latest_data()

if not qa_data:
    st.warning("問題データがありません。抽出アプリから追加してください。")
    st.stop()

st.info(f"💡 現在、データベースに **{len(qa_data)}問** の型が登録されています。")

# ==========================================
# セッション状態（クイズの進行）の管理
# ==========================================
if getattr(st.session_state, 'current_q', None) is None:
    st.session_state.current_q = random.choice(qa_data)
if getattr(st.session_state, 'answered', None) is None:
    st.session_state.answered = False
if getattr(st.session_state, 'shuffled_choices', None) is None:
    choices = [st.session_state.current_q['correct'], st.session_state.current_q['wrong1'], st.session_state.current_q['wrong2']]
    st.session_state.shuffled_choices = random.sample(choices, len(choices))

# ==========================================
# 問題の表示
# ==========================================
q = st.session_state.current_q
st.subheader("【ミッション】空欄に入る適切な表現を選べ")
st.success(f"和訳: {q['question']}")
st.markdown(f"### {q['blank_sentence']}")

with st.form(key='quiz_form'):
    user_choice = st.radio("選択肢:", st.session_state.shuffled_choices)
    submit = st.form_submit_button("解答する")

if submit:
    st.session_state.answered = True
    if user_choice == q['correct']:
        st.success("正解！この「型」をしっかり記憶しましょう。")
    else:
        st.error(f"不正解...。正解は「{q['correct']}」です。")
    
    # --------------------------------------------------
    # 【新機能】引用元コンテキストの表示
    # --------------------------------------------------
    original = str(q.get('original_context', ''))
    translation = str(q.get('context_translation', ''))
    
    # 以前のデータ（nan）を弾きつつ、テキストが存在する場合のみ表示
    if original and original.lower() != 'nan':
        st.markdown("---")
        st.markdown("#### 📖 実際の論文での使用例（引用元）")
        st.info(f"**【英文】**\n\n{original}")
        if translation and translation.lower() != 'nan':
            st.info(f"**【和訳】**\n\n{translation}")
    else:
        st.caption("※この問題には引用元のコンテキストデータがありません。")

if st.session_state.answered:
    if st.button("次の問題へ"):
        st.session_state.current_q = random.choice(qa_data)
        st.session_state.answered = False
        st.session_state.shuffled_choices = None 
        st.rerun()