# -*- coding: utf-8 -*-
"""
スマホ最適化CSS & ダークモードスタイル定義
"""

def get_custom_css() -> str:
    """アプリ全体に適用するカスタムCSSを返す"""
    return """
    <style>
    /* ===== グローバルリセット ===== */
    .main .block-container {
        padding-top: 1rem;
        padding-bottom: 1rem;
        max-width: 100%;
    }

    /* ===== メトリクスカード ===== */
    .metric-card {
        background: linear-gradient(135deg, #1A1F2E 0%, #252B3B 100%);
        border: 1px solid rgba(76, 155, 232, 0.2);
        border-radius: 12px;
        padding: 1.2rem;
        margin-bottom: 0.8rem;
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    .metric-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 20px rgba(76, 155, 232, 0.15);
    }
    .metric-card .metric-label {
        color: #8899AA;
        font-size: 0.85rem;
        margin-bottom: 0.3rem;
        display: flex;
        align-items: center;
        gap: 0.4rem;
    }
    .metric-card .metric-value {
        color: #FAFAFA;
        font-size: 1.8rem;
        font-weight: 700;
        line-height: 1.2;
    }
    .metric-card .metric-delta {
        font-size: 0.8rem;
        margin-top: 0.2rem;
    }
    .metric-delta.positive { color: #00D26A; }
    .metric-delta.negative { color: #FF4B4B; }

    /* ===== 銘柄カード（スマホ向け） ===== */
    .stock-card {
        background: #1A1F2E;
        border: 1px solid #2D3748;
        border-radius: 10px;
        padding: 1rem;
        margin-bottom: 0.6rem;
        display: flex;
        flex-wrap: wrap;
        gap: 0.5rem;
    }
    .stock-card .stock-ticker {
        font-weight: 700;
        color: #4C9BE8;
        font-size: 1rem;
    }
    .stock-card .stock-name {
        color: #BBBBBB;
        font-size: 0.85rem;
        flex-basis: 100%;
    }
    .stock-card .stock-stat {
        background: #252B3B;
        border-radius: 6px;
        padding: 0.3rem 0.6rem;
        font-size: 0.78rem;
        color: #CCCCCC;
    }
    .stock-card .stock-stat strong {
        color: #FAFAFA;
    }

    /* ===== AIインサイトカード ===== */
    .ai-insight-card {
        background: linear-gradient(135deg, #1A2332 0%, #1F2B3D 100%);
        border: 1px solid rgba(76, 155, 232, 0.3);
        border-radius: 14px;
        padding: 1.5rem;
        margin: 1rem 0;
        position: relative;
        overflow: hidden;
    }
    .ai-insight-card::before {
        content: "";
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 3px;
        background: linear-gradient(90deg, #4C9BE8, #7B61FF, #4C9BE8);
    }
    .ai-insight-card h4 {
        color: #4C9BE8;
        margin-bottom: 0.8rem;
    }

    /* ===== ニュースカード ===== */
    .news-card {
        background: #1A1F2E;
        border-left: 3px solid #4C9BE8;
        border-radius: 0 8px 8px 0;
        padding: 0.8rem 1rem;
        margin-bottom: 0.5rem;
    }
    .news-card .news-title {
        color: #E0E0E0;
        font-size: 0.9rem;
        font-weight: 600;
        text-decoration: none;
    }
    .news-card .news-title:hover {
        color: #4C9BE8;
    }
    .news-card .news-date {
        color: #777;
        font-size: 0.75rem;
        margin-top: 0.2rem;
    }

    /* ===== セクションヘッダー ===== */
    .section-header {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        margin: 1.5rem 0 0.8rem 0;
        padding-bottom: 0.5rem;
        border-bottom: 2px solid rgba(76, 155, 232, 0.3);
    }
    .section-header h3 {
        margin: 0;
        color: #FAFAFA;
        font-size: 1.1rem;
    }

    /* ===== データ更新ボタン ===== */
    .stButton > button {
        border-radius: 8px;
        font-weight: 600;
        transition: all 0.2s ease;
    }

    /* ===== Plotlyチャート背景透過 ===== */
    .js-plotly-plot .plotly .main-svg {
        background: transparent !important;
    }

    /* ===== スマホ対応メディアクエリ ===== */
    @media (max-width: 768px) {
        .main .block-container {
            padding-left: 0.5rem;
            padding-right: 0.5rem;
            padding-top: 0.5rem;
        }
        .metric-card .metric-value {
            font-size: 1.4rem;
        }
        .metric-card {
            padding: 0.8rem;
        }
        /* サイドバーを狭くする */
        section[data-testid="stSidebar"] {
            width: 240px !important;
        }
        /* テーブルの横スクロール */
        .stDataFrame {
            overflow-x: auto;
        }
    }

    /* ===== プログレスバーカスタマイズ ===== */
    .stProgress > div > div {
        background: linear-gradient(90deg, #4C9BE8, #7B61FF);
    }

    /* ===== タブスタイル ===== */
    .stTabs [data-baseweb="tab-list"] {
        gap: 4px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px 8px 0 0;
        padding: 8px 16px;
    }

    /* ===== 空状態メッセージ ===== */
    .empty-state {
        text-align: center;
        padding: 3rem;
        color: #8899AA;
    }
    .empty-state .icon {
        font-size: 3rem;
        margin-bottom: 1rem;
    }
    .empty-state h3 {
        color: #CCCCCC;
        margin-bottom: 0.5rem;
    }
    </style>
    """


def metric_card(label: str, value: str, icon: str = "📊", delta: str = "", delta_positive: bool = True) -> str:
    """メトリクスカードHTMLを生成する"""
    delta_html = ""
    if delta:
        cls = "positive" if delta_positive else "negative"
        delta_html = f'<div class="metric-delta {cls}">{delta}</div>'
    return f"""
    <div class="metric-card">
        <div class="metric-label">{icon} {label}</div>
        <div class="metric-value">{value}</div>
        {delta_html}
    </div>
    """


def stock_card(ticker: str, name: str, sector: str, close: float, volume: int,
               rsi: float = None, volume_ratio: float = None) -> str:
    """銘柄情報カードHTMLを生成する（スマホフレンドリー）"""
    stats = [f'<span class="stock-stat">セクター: <strong>{sector}</strong></span>']
    stats.append(f'<span class="stock-stat">終値: <strong>¥{close:,.0f}</strong></span>')
    stats.append(f'<span class="stock-stat">出来高: <strong>{volume:,.0f}</strong></span>')
    if rsi is not None:
        rsi_color = "#FF4B4B" if rsi < 30 else ("#00D26A" if rsi > 70 else "#FAFAFA")
        stats.append(f'<span class="stock-stat">RSI: <strong style="color:{rsi_color}">{rsi:.1f}</strong></span>')
    if volume_ratio is not None:
        vr_color = "#00D26A" if volume_ratio > 2.0 else "#FAFAFA"
        stats.append(f'<span class="stock-stat">出来高倍率: <strong style="color:{vr_color}">{volume_ratio:.2f}x</strong></span>')

    return f"""
    <div class="stock-card">
        <span class="stock-ticker">{ticker}</span>
        <span class="stock-name">{name}</span>
        {"".join(stats)}
    </div>
    """


def news_card(title: str, link: str, pub_date: str) -> str:
    """ニュースカードHTMLを生成する"""
    return f"""
    <div class="news-card">
        <a href="{link}" target="_blank" class="news-title">{title}</a>
        <div class="news-date">{pub_date}</div>
    </div>
    """


def section_header(title: str, icon: str = "📈") -> str:
    """セクションヘッダーHTMLを生成する"""
    return f"""
    <div class="section-header">
        <h3>{icon} {title}</h3>
    </div>
    """


def empty_state(message: str, icon: str = "📭") -> str:
    """データ未取得時の空状態メッセージHTMLを生成する"""
    return f"""
    <div class="empty-state">
        <div class="icon">{icon}</div>
        <h3>データがありません</h3>
        <p>{message}</p>
    </div>
    """
