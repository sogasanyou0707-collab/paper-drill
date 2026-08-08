import streamlit as st
import os
import requests
import xml.etree.ElementTree as ET
import google.generativeai as genai
from dotenv import load_dotenv
import time
import json  # ←追加
import csv   # ←追加

# ==========================================
# 1. 初期設定とAPIキー読み込み
# ==========================================
st.set_page_config(page_title="Paper Phrase Extractor", page_icon="🔍")

load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    st.error("⚠️ `.env` ファイルが見つからないか、`GEMINI_API_KEY` が設定されていません。")
    st.stop()

genai.configure(api_key=API_KEY)
# 最新の 3.6 Flash を指定
model = genai.GenerativeModel("gemini-3.6-flash")

# ==========================================
# 2. PubMed / PMC 検索・取得関数
# ==========================================
def fetch_articles(keyword, journal, max_results, search_type, offset=0):
    # search_type: 'abstract' (PubMed) or 'fulltext' (PMC)
    db = "pubmed" if search_type == "アブストラクトのみ" else "pmc"
    
    # 検索クエリの構築
    query = f'"{keyword}"[All Fields] AND "{journal}"[Journal]'
    
    st.write(f"🔍 {db.upper()} データベースで検索中... (クエリ: {query} / {offset}件目からスキップして取得)")
    
    # ESearch API (retstartを追加して取得開始位置をズラす)
    search_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db={db}&term={query}&retmode=json&retmax={max_results}&retstart={offset}"
    
    # 【復元】ここが抜けていました！URLに対して実際にリクエストを送ります
    response = requests.get(search_url)
    
    if response.status_code != 200:
        st.error("APIへの接続に失敗しました。")
        return []

    id_list = response.json().get('esearchresult', {}).get('idlist', [])
    
    if not id_list:
        st.warning("条件に一致する論文が見つかりませんでした。")
        return []

    st.write(f"📄 {len(id_list)} 件の論文IDを取得しました。テキストをダウンロード中...")
    
    # EFetch API
    ids = ",".join(id_list)
    fetch_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db={db}&id={ids}&retmode=xml"
    fetch_response = requests.get(fetch_url)
    
    articles_text = []
    root = ET.fromstring(fetch_response.content)
    
    if db == "pubmed":
        # PubMedの場合はアブストラクトを抽出
        for article in root.findall('.//PubmedArticle'):
            abstract_texts = article.findall('.//AbstractText')
            if abstract_texts:
                abstract = " ".join([elem.text for elem in abstract_texts if elem.text])
                articles_text.append(abstract)
    else:
        # PMCの場合は全文（bodyタグ内）を抽出
        for article in root.findall('.//article'):
            bodies = article.findall('.//body')
            for body in bodies:
                # itertext() でXMLタグを除去したプレーンテキストを取得
                full_text = " ".join(body.itertext())
                articles_text.append(full_text)
                
    st.success(f"✅ {len(articles_text)} 件のテキスト抽出に成功しました。")
    return articles_text

# ==========================================
# 3. Gemini による複数論文「横断」フレーズ抽出関数（絶対崩れないプロ仕様）
# ==========================================
def extract_and_save_phrases(articles_text, output_csv="phrases.csv"):
    # 【修正】JSONの見本の波括弧 {} を {{ }} にしてPythonの誤作動を防ぎました
    prompt_template = """
    あなたはネイティブの医学論文査読者です。以下の【複数の医学論文】のテキスト全文を横断的に分析し、
    これらの論文間で共通して頻出する、学術英語の論文執筆で非常に使い回しやすい「汎用的なフレーズ（型）」を 合計15個 抽出し、JSON形式で出力してください。
    
    【厳守する出力フォーマット】
    必ず以下のキーを持つJSONの「配列（リスト）」形式で出力すること。
    [
      {{
        "question": "短い日本語訳",
        "correct": "正解の英単語/熟語",
        "wrong1": "ダミー選択肢1",
        "wrong2": "ダミー選択肢2",
        "blank_sentence": "correctを[   ]にした短い英文",
        "original_context": "抽出元の実際の1〜2文（フレーズが実際に使われていた文脈がわかる原文）",
        "context_translation": "original_contextの自然な日本語訳"
      }}
    ]
    
    【複数の対象テキスト】
    {combined_text}
    """

    st.write("🧠 取得したすべての論文を統合し、Gemini に横断分析させています...")
    combined_articles = "\n\n=================================\n\n".join(articles_text)

    try:
        prompt = prompt_template.format(combined_text=combined_articles)
        
        response = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json"
            )
        )
        
        data = json.loads(response.text)
        
        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, list):
                    data = value
                    break
            else:
                data = [data]
                
        clean_data = []
        for item in data:
            clean_item = {str(k).strip().replace('"', ''): str(v).strip() for k, v in item.items()}
            clean_data.append(clean_item)

        file_exists = os.path.isfile(output_csv) and os.path.getsize(output_csv) > 0
        
        with open(output_csv, mode="a", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "question", "correct", "wrong1", "wrong2", 
                "blank_sentence", "original_context", "context_translation"
            ], extrasaction='ignore')
            
            if not file_exists:
                writer.writeheader()
            for row in clean_data:
                writer.writerow(row)
                
        st.success(f"🎉 完了しました！文脈付きのリッチな頻出フレーズが {output_csv} に追加されました。")
        
    except Exception as e:
        st.error(f"抽出・保存処理中にエラーが発生しました: {e}")
        with st.expander("AIからの生の出力を確認する（デバッグ用）"):
            st.write(response.text if 'response' in locals() else "出力なし")

# ==========================================
# 4. Streamlit UI構築
# ==========================================
st.title("論文フレーズ自動抽出システム 🤖")
st.write("PubMed/PMCから論文を検索し、Gemini 3.6 Flashが直接 `phrases.csv` に学習問題を追加します。")

with st.form("search_form"):
    st.subheader("検索条件の設定")
    
    # 【修正】ここでcol1とcol2を定義しています
    col1, col2 = st.columns(2)
    
    with col1:
        keyword = st.text_input("検索キーワード", value="sputum image analysis")
        journal = st.text_input("対象ジャーナル", value="Journal of clinical microbiology")
    with col2:
        search_type = st.radio("検索範囲", ["アブストラクトのみ", "全文（PubMed Central）"])
        max_results = st.number_input("取得する論文数", min_value=1, max_value=10, value=5)
        # スキップ件数の設定を追加
        offset = st.number_input("検索開始位置 (スキップ件数)", min_value=0, value=0, step=5, help="同じキーワードで再度検索する場合は、ここの数字を増やして重複を避けます。")
        
    submit_btn = st.form_submit_button("検索＆フレーズ抽出を開始")

if submit_btn:
    with st.spinner("PubMed/PMCからデータを取得しています..."):
        # offsetを関数に渡す
        articles = fetch_articles(keyword, journal, max_results, search_type, offset)
        
    if articles:
        with st.spinner("Gemini 3.6 Flash がフレーズを抽出し、CSVに書き込んでいます..."):
            extract_and_save_phrases(articles, output_csv="phrases.csv")