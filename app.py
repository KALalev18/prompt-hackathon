import streamlit as st
import pandas as pd
import os
import json
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from sourcing import EU_MARKETS, get_youtube_creators, get_youtube_creators_across_eu, get_fallback_creators
from scoring import score_and_draft_pitch, generate_gemini_recommendation
from metrics_history import save_and_measure_snapshots
from platform_imports import TIKTOK_CSV_TEMPLATE, INSTAGRAM_CSV_TEMPLATE, load_provider_csv, load_saved_youtube_dataset

st.set_page_config(layout="wide", page_title="Prenew Radar")

# --- Popup Function ---
@st.dialog("System Notice")
def show_crm_popup():
    st.write("Feature will be done soon.")

# --- UI Theme Showcase Toggle ---
top_left, top_right = st.columns([3, 1])
with top_left:
    st.title("Prenew Radar")
    st.write("Find relevant creators, understand their content fit, and prepare outreach.")
with top_right:
    theme_toggle = st.radio("UI Theme Showcase", ["Prenew Dark Mode", "Light Mode SaaS"], horizontal=True)

# --- Dynamic Adaptive CSS ---
if theme_toggle == "Prenew Dark Mode":
    css_theme = """
    <style>
        .stApp { background-color: #13603d !important; color: #ffffff !important; }
        .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp p, .stApp span, .stApp label, .stMarkdownContainer p { color: #ffffff !important; }
        
        .stTextInput input, .stTextArea textarea, div[data-baseweb="select"] > div, [data-testid="stFileUploaderDropzone"] {
            background-color: #0b3d26 !important;
            border: 1px solid rgba(255, 255, 255, 0.2) !important;
            color: #ffffff !important;
            border-radius: 8px !important;
        }
        .stSelectbox span, .stMultiSelect span { color: #ffffff !important; }
        div[role="radio"] { background-color: transparent !important; }
        div[data-baseweb="checkbox"] div[role="checkbox"] { background-color: #0b3d26 !important; border: 2px solid rgba(255,255,255,0.4) !important; }
        div[data-baseweb="checkbox"] div[role="checkbox"] svg { color: #ffffff !important; fill: #ffffff !important; }
        
        [data-testid="stExpander"], [data-testid="stVerticalBlockBorderWrapper"], div[data-testid="stContainer"] {
            background-color: #0d4a2f !important;
            border: 1px solid rgba(255, 255, 255, 0.1) !important;
            border-radius: 12px !important;
        }
        
        .stButton > button[kind="primary"] {
            background-color: #a4ffa2 !important; 
            color: #000000 !important;
            border: none !important;
            font-weight: 700 !important;
            border-radius: 8px !important;
        }
        .stButton > button[kind="primary"] p, .stButton > button[kind="primary"] div { color: #000000 !important; }
        
        .stButton > button[kind="secondary"], .stDownloadButton > button {
            background-color: #0b3d26 !important;
            border: 1px solid rgba(255, 255, 255, 0.3) !important;
            color: #ffffff !important;
        }
        .stButton > button[kind="secondary"] p, .stDownloadButton > button p { color: #ffffff !important; }
        
        [data-testid="stDataFrame"] > div > div > div > div { background-color: #0b3d26 !important; }
        [data-testid="stDataFrame"] th { background-color: #082b1b !important; color: #ffffff !important; border-bottom: 1px solid rgba(255,255,255,0.1) !important; }
        [data-testid="stDataFrame"] td { background-color: #0b3d26 !important; color: #ffffff !important; border-bottom: 1px solid rgba(255,255,255,0.05) !important; }
        
        [data-testid="stAlert"] { background-color: #d93838 !important; color: #ffffff !important; border: none !important; }
        
        [data-testid="stMetricValue"], [data-testid="stMetricValue"] > div, [data-testid="stMetricLabel"], [data-testid="stMetricLabel"] > div, [data-testid="stMetricLabel"] > div > p { color: #ffffff !important; }
        
        [data-testid="stDialog"] > div[role="dialog"] { background-color: #0b3d26 !important; border-radius: 12px !important; border: 1px solid rgba(255,255,255,0.2) !important; }
        [data-testid="stDialog"] h2, [data-testid="stDialog"] p, [data-testid="stDialog"] span, [data-testid="stDialog"] div { color: #ffffff !important; }
        [data-testid="stDialog"] button[kind="secondary"] { color: #ffffff !important; background-color: transparent !important; border: 1px solid rgba(255,255,255,0.3) !important; }
    </style>
    """
else:
    css_theme = """
    <style>
        .stApp { background-color: #f4f6f8 !important; color: #111827 !important; }
        .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp p, .stApp span, .stApp label, .stMarkdownContainer p { color: #111827 !important; }
        
        .stTextInput input, .stTextArea textarea, div[data-baseweb="select"] > div, [data-testid="stFileUploaderDropzone"] {
            background-color: #ffffff !important;
            border: 1px solid #d1d5db !important;
            color: #111827 !important;
            border-radius: 8px !important;
        }
        .stSelectbox span, .stMultiSelect span { color: #111827 !important; }
        div[role="radio"] { background-color: transparent !important; }
        div[data-baseweb="checkbox"] div[role="checkbox"] { background-color: #ffffff !important; border: 2px solid #d1d5db !important; }
        div[data-baseweb="checkbox"] div[role="checkbox"] svg { color: #ffffff !important; fill: #ffffff !important; }
        
        [data-testid="stExpander"], [data-testid="stVerticalBlockBorderWrapper"], div[data-testid="stContainer"] {
            background-color: #ffffff !important;
            border: 1px solid #e5e7eb !important;
            border-radius: 12px !important;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        }
        
        .stButton > button[kind="primary"] {
            background-color: #13603d !important; 
            color: #ffffff !important;
            border: none !important;
            font-weight: 700 !important;
            border-radius: 8px !important;
        }
        .stButton > button[kind="primary"] p, .stButton > button[kind="primary"] div { color: #ffffff !important; }
        
        .stButton > button[kind="secondary"], .stDownloadButton > button {
            background-color: #ffffff !important;
            border: 1px solid #d1d5db !important;
            color: #111827 !important;
        }
        .stButton > button[kind="secondary"] p, .stDownloadButton > button p { color: #111827 !important; }
        
        [data-testid="stDataFrame"] > div > div > div > div { background-color: #ffffff !important; }
        [data-testid="stDataFrame"] th { background-color: #f9fafb !important; color: #374151 !important; border-bottom: 1px solid #e5e7eb !important; }
        [data-testid="stDataFrame"] td { background-color: #ffffff !important; color: #111827 !important; border-bottom: 1px solid #f3f4f6 !important; }
        
        [data-testid="stAlert"] { background-color: #fee2e2 !important; color: #991b1b !important; border: 1px solid #f87171 !important; }
        [data-testid="stAlert"] div, [data-testid="stAlert"] span, [data-testid="stAlert"] p { color: #991b1b !important; }
        
        [data-testid="stMetricValue"], [data-testid="stMetricValue"] > div, [data-testid="stMetricLabel"], [data-testid="stMetricLabel"] > div, [data-testid="stMetricLabel"] > div > p { color: #111827 !important; }
        
        [data-testid="stDialog"] > div[role="dialog"] { background-color: #ffffff !important; border-radius: 12px !important; border: 1px solid #e5e7eb !important; }
        [data-testid="stDialog"] h2, [data-testid="stDialog"] p, [data-testid="stDialog"] span, [data-testid="stDialog"] div { color: #111827 !important; }
        [data-testid="stDialog"] button[kind="secondary"] { color: #111827 !important; background-color: transparent !important; border: 1px solid #d1d5db !important; }
    </style>
    """

common_css = """
<style>
    .stTextInput input::placeholder, .stTextArea textarea::placeholder, .stSelectbox div[class*="placeholder"], .stMultiSelect div[class*="placeholder"] { color: #888888 !important; }
    .block-container { padding-top: 2rem !important; padding-left: 6rem !important; padding-right: 6rem !important; max-width: 100% !important; }
</style>
"""


st.markdown(css_theme + common_css, unsafe_allow_html=True)

def configured_secret(name):
    try:
        value = st.secrets.get(name, "")
    except Exception:
        value = ""
    if not value:
        secrets_path = Path(__file__).parent / ".streamlit" / "secrets.toml"
        if secrets_path.exists():
            try:
                value = tomllib.loads(secrets_path.read_text(encoding="utf-8")).get(name, "")
            except (OSError, tomllib.TOMLDecodeError):
                value = ""
    return value or os.getenv(name, "")

def fetch_creators(keyword, use_demo_data, youtube_api_key, region_code, language, country_name=None, all_eu=False, progress_callback=None):
    if use_demo_data:
        return get_fallback_creators(), []
    if all_eu:
        return get_youtube_creators_across_eu(youtube_api_key, progress_callback=progress_callback, additional_keyword=keyword)
    return get_youtube_creators(youtube_api_key, keyword, region_code, language, country_name), []

def gemini_error_hint(error):
    message = str(error).lower()
    status = getattr(error, "code", None) or getattr(error, "status_code", None)
    if status in (500, 502, 503, 504) or "servererror" in type(error).__name__.lower():
        return "Gemini returned a temporary server error. Retry the recommendation in a moment."
    if isinstance(error, ImportError):
        return "Install the current SDK with: python -m pip install google-genai"
    if "api key" in message or "unauthenticated" in message or "401" in message:
        return "The key is invalid, expired, or restricted. Create a replacement in Google AI Studio."
    if "permission" in message or "403" in message:
        return "The key's project may not have the Gemini API enabled, or its restrictions block this app."
    if "quota" in message or "429" in message or "resource_exhausted" in message:
        return "The project quota or rate limit was reached. Check usage and billing/quota."
    if "not found" in message or "404" in message:
        return "The model is unavailable to this key. Check the current model names available to its Google AI project."
    return f"Unexpected {type(error).__name__}. Check the key, API access, and model availability."

saved_datasets = sorted(Path(__file__).parent.glob("youtube_creator_data_*.csv"))
saved_dataset_path = saved_datasets[-1] if saved_datasets else None

st.divider()

# --- Centered Top Input Section ---
col_spacer1, col_center, col_spacer3 = st.columns([1, 2, 1])

with col_center:
    youtube_source_label = "YouTube API discovery" if saved_dataset_path else "Demo data"
    source_options = [youtube_source_label, "TikTok licensed-provider CSV", "Instagram licensed-provider CSV"]
    source_mode = st.radio("Select Discovery Source", source_options, horizontal=True)
    niche_query = st.text_input("Filter by niche, game, or creator name", "")
    
    from_saved = source_mode == "YouTube API discovery"
    from_tiktok = source_mode == "TikTok licensed-provider CSV"
    from_instagram = source_mode == "Instagram licensed-provider CSV"
    is_csv_upload = from_tiktok or from_instagram
    
    use_demo_data = source_mode == "Demo data"
    market = "EU-27 saved extract"
    language = "en"
    youtube_api_key = configured_secret("YOUTUBE_API_KEY")
    gemini_api_key = configured_secret("GEMINI_API_KEY")

    provider_csv = None
    if is_csv_upload:
        with st.container():
            st.caption("Upload commercial discovery data for automated fit-scoring.")
            provider_csv = st.file_uploader(f"Upload {source_mode.split()[0]} CSV", type=["csv"], label_visibility="collapsed")
            template_data = INSTAGRAM_CSV_TEMPLATE if from_instagram else TIKTOK_CSV_TEMPLATE
            file_prefix = "instagram" if from_instagram else "tiktok"
            st.download_button(
                f"Download {source_mode.split()[0]} template",
                data=template_data.encode("utf-8"),
                file_name=f"prenew_{file_prefix}_provider_template.csv",
                mime="text/csv",
                use_container_width=True
            )
            
    st.write("")
    load_saved_on_open = from_saved and not st.session_state.get("creator_results")
    if st.button("Load / refresh dataset", type="primary", use_container_width=True):
        load_saved_on_open = True

if st.session_state.get("active_source_mode") != source_mode:
    st.session_state.pop("creator_results", None)
    st.session_state["active_source_mode"] = source_mode

if load_saved_on_open:
    if is_csv_upload and provider_csv is None:
        st.error("Upload a provider CSV using the supplied template.")
    else:
        try:
            with st.spinner("Searching YouTube and preparing creator profiles..." if from_saved else f"Processing {source_mode.split()[0]} profiles..."):
                if from_saved:
                    creators = load_saved_youtube_dataset(saved_dataset_path)
                    fetch_errors = []
                elif is_csv_upload:
                    platform_name = "Instagram" if from_instagram else "TikTok"
                    creators, fetch_errors = load_provider_csv(provider_csv, platform_name)
                else:
                    creators, fetch_errors = get_fallback_creators(), []
                
                if fetch_errors:
                    st.warning(f"Search completed with {len(fetch_errors)} market errors: " + "; ".join(fetch_errors[:5]))
                if not creators:
                    st.session_state.pop("creator_results", None)
                    st.warning("No channels found. Try a broader phrase or another market.")
                else:
                    if from_saved:
                        st.session_state["creator_source_label"] = "YouTube API discovery (saved EU-27 extract)"
                    elif from_tiktok:
                        st.session_state["creator_source_label"] = "licensed-provider TikTok CSV"
                    else:
                        st.session_state["creator_source_label"] = "sample profiles"
                    results = []
                    candidates = creators
                    now_utc = datetime.now(timezone.utc)
                    
                    for creator in candidates:
                        if "recent_videos" not in creator and "recent_video_metrics_json" in creator:
                            try:
                                raw_json = creator["recent_video_metrics_json"]
                                creator["recent_videos"] = json.loads(raw_json) if isinstance(raw_json, str) else []
                            except Exception:
                                creator["recent_videos"] = []
                                
                        recent_vids = creator.get("recent_videos", [])
                        u3m, u6m, u9m = [], [], []
                        for vid in recent_vids:
                            pub = vid.get("published_at")
                            if not pub: continue
                            try:
                                dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                                age_days = max(0, (now_utc - dt).total_seconds() / 86400)
                            except Exception: continue
                            v_views = vid.get("views", 0) or 0
                            if age_days <= 90: u3m.append(v_views)
                            elif 90 < age_days <= 180: u6m.append(v_views)
                            elif 180 < age_days <= 270: u9m.append(v_views)

                        uploads_3m = len(u3m) if recent_vids else creator.get("uploads_3m", 0)
                        uploads_6m = len(u6m) if recent_vids else creator.get("uploads_6m", 0)
                        uploads_9m = len(u9m) if recent_vids else creator.get("uploads_9m", 0)
                        avg_views_3m = round(sum(u3m) / len(u3m), 1) if u3m else creator.get("avg_views_3m", 0)
                        avg_views_6m = round(sum(u6m) / len(u6m), 1) if u6m else creator.get("avg_views_6m", 0)
                        avg_views_9m = round(sum(u9m) / len(u9m), 1) if u9m else creator.get("avg_views_9m", 0)
                        
                        platform = creator.get("platform", "YouTube")
                        analysis = score_and_draft_pitch("", creator, language)
                        categories = creator.get("content_categories", [])
                        subscribers = creator.get("subscribers")
                        average_views = creator.get("avg_recent_video_views")
                        is_core_youtube = bool(platform == "YouTube" and subscribers is not None and average_views is not None and 50000 <= subscribers <= 250000 and 20000 <= average_views <= 100000)
                        
                        if platform in ("TikTok", "Instagram"):
                            size_tier = f"{platform} target (4k+)" if subscribers is not None and subscribers >= 4000 else f"{platform} below 4k"
                        elif subscribers is None:
                            size_tier = "YouTube subscribers hidden"
                        elif is_core_youtube:
                            size_tier = "Core YouTube target"
                        elif 50000 <= subscribers <= 250000:
                            size_tier = "Core subscriber range"
                        elif subscribers < 50000:
                            size_tier = "Emerging (<50k)"
                        else:
                            size_tier = "Large (>250k)"

                        results.append({
                            "Avatar": creator.get("profile_image_url", ""),
                            "Platform": platform,
                            "Creator": creator["name"],
                            "Handle": creator.get("handle", ""),
                            "Declared country": creator.get("declared_country") or "Not provided",
                            "Markets discovered": ", ".join(creator.get("countries", [])) or ("Demo" if use_demo_data else market),
                            "Subscribers / followers": subscribers,
                            "Size tier": size_tier,
                            "Core target match": is_core_youtube or (platform == "TikTok" and subscribers is not None and subscribers >= 4000),
                            "Commercial saturation": creator.get("commercial_saturation", "Unknown"),
                            "Verified Email": "Yes" if creator.get("public_contact_email") else "No",
                            "Channel total views": creator.get("channel_total_views"),
                            "Channel video count": creator.get("channel_video_count"),
                            "Avg video views": average_views,
                            "Median video views": creator.get("median_recent_video_views"),
                            "Views window (days)": creator.get("view_window_days"),
                            "Views sample size": creator.get("view_window_video_count"),
                            "Uploads (Last 3m)": uploads_3m,
                            "Uploads (3m-6m)": uploads_6m,
                            "Uploads (6m-9m)": uploads_9m,
                            "Avg Views (Last 3m)": avg_views_3m,
                            "Avg Views (3m-6m)": avg_views_6m,
                            "Avg Views (6m-9m)": avg_views_9m,
                            "Avg views / followers %": creator.get("avg_views_to_subscribers_pct"),
                            "Avg recent video likes": creator.get("avg_recent_video_likes"),
                            "Avg recent video comments": creator.get("avg_recent_video_comments"),
                            "Recent engagement %": creator.get("recent_video_engagement_rate"),
                            "Uploads last 30d": creator.get("recent_30d_uploads"),
                            "Uploads last 90d": creator.get("recent_90d_uploads"),
                            "Last upload age (days)": creator.get("last_upload_days"),
                            "Observed monthly channel view growth": creator.get("observed_monthly_view_growth"),
                            "Observed monthly video view growth": creator.get("median_observed_monthly_video_view_growth"),
                            "Trend status": creator.get("trend_status", "Needs review"),
                            "Observed monthly subscriber growth": creator.get("observed_monthly_subscriber_growth"),
                            "Snapshot interval days": creator.get("snapshot_interval_days"),
                            "Estimated monthly views (snapshot)": creator.get("estimated_monthly_views_from_snapshot"),
                            "Estimated yearly views (snapshot)": creator.get("estimated_yearly_views_from_snapshot"),
                            "PC build match": "PC builds" in categories,
                            "Gaming match": "Gaming" in categories or "Gaming setups" in categories,
                            "Niche confidence (% recent uploads matched)": creator.get("niche_match_ratio_pct"),
                            "Content niche": "; ".join(categories) or "Not enough recent-video evidence",
                            "Channel description": creator.get("description", ""),
                            "Game titles": "; ".join(category.removeprefix("Game: ") for category in categories if category.startswith("Game: ")) or "; ".join(str(g) for g in creator.get("game_titles", [])),
                            "Risk/review flags": "; ".join(creator.get("risk_flags", [])),
                            "Public contact email": creator.get("public_contact_email"),
                            "Public contact URL": creator.get("public_contact_url"),
                            "Data source": creator.get("data_provider") or ("Demo data" if use_demo_data else "YouTube Data API"),
                            "Provider snapshot date": creator.get("provider_snapshot_date"),
                            "Fit score": analysis.get("brand_fit_score", 0),
                            "Why it fits": analysis.get("reasoning", ""),
                            "Outreach draft": analysis.get("outreach_pitch", ""),
                            "Channel": creator.get("url", ""),
                            "Recent videos": creator.get("recent_videos", []),
                            "Recent video metrics JSON": json.dumps(creator.get("recent_videos", []), ensure_ascii=False),
                        })
                    st.session_state["creator_results"] = results
        except HttpError as error:
            status = error.resp.status
            if status == 403: detail = "Check that YouTube Data API v3 is enabled, the key is valid, and its restrictions allow this app."
            elif status == 400: detail = "Check the market, language, and search phrase."
            elif status == 429: detail = "YouTube API quota or rate limit reached."
            else: detail = "Check the key and YouTube Data API project settings."
            st.error(f"YouTube API request failed (HTTP {status}). {detail}")
        except Exception as error:
            st.error(f"Discovery failed ({type(error).__name__}). Check your API key and network connection.")

results = st.session_state.get("creator_results", [])
if results:
    df = pd.DataFrame(results)
    
    if niche_query.strip():
        searchable_columns = ["Creator", "Handle", "Content niche", "Game titles", "Risk/review flags"]
        searchable_text = df[searchable_columns].fillna("").astype(str).agg(" ".join, axis=1)
        df = df[searchable_text.str.contains(niche_query.strip(), case=False, regex=False)]
    if df.empty:
        st.info(f"No creators match '{niche_query}'. Clear the search to show the full dataset.")
        st.stop()
    
    with st.container(border=True):
        st.markdown("##### Refine & Filter Dataset")
        
        f_col1, f_col2, f_col3 = st.columns(3)
        country_options = ["All EU Countries"] + list(EU_MARKETS.keys())
        country_filter = f_col1.selectbox("Country", country_options)
            
        size_filter = f_col2.selectbox("Audience size", ["All sizes", "Micro-creators (< 10k)", "Emerging (10k - 50k)", "Established (50k - 250k)", "Large (> 250k)"])
        view_filter = f_col3.selectbox("Average views", ["Any", "20k-100k core range", "Below 20k", "Above 100k"])
        
        f_col4, f_col5 = st.columns(2)
        niche_filter = f_col4.multiselect("Content niche", ["PC builds", "Gaming", "Hardware and benchmarks", "Tech reviews", "Gaming setups", "Streaming"])
        game_filter = f_col5.text_input("Game title contains", "")
        
        f_col6, f_col7, f_col8 = st.columns([1, 1, 1.5])
        with f_col6:
            st.write("") 
            contact_only = st.checkbox("Has public contact route", value=False)
        with f_col7:
            st.write("") 
            review_flags_only = st.checkbox("Has review flags", value=False)
        with f_col8:
            # FIX: "Highest Fit Score" is now the first (default) sorting option
            sort_order = st.selectbox("Sort results", ["Highest Fit Score", "Best target fit", "Country, then target fit", "Highest average views"])
            
    # --- Filter Logic ---
    if country_filter != "All EU Countries":
        country_code = EU_MARKETS[country_filter][0]
        df = df[(df["Declared country"] == country_code) | df["Markets discovered"].str.contains(country_filter, case=False, regex=False)]
            
    if size_filter == "Core targets only": df = df[df["Core target match"]]
    if size_filter == "Micro-creators (< 10k)": df = df[df["Subscribers / followers"] < 10000]
    elif size_filter == "Emerging (10k - 50k)": df = df[df["Subscribers / followers"].between(10000, 49999)]
    elif size_filter == "Established (50k - 250k)": df = df[df["Subscribers / followers"].between(50000, 250000)]
    elif size_filter == "Large (> 250k)": df = df[df["Subscribers / followers"] > 250000]
        
    if view_filter == "20k-100k core range": df = df[df["Avg video views"].between(20000, 100000)]
    elif view_filter == "Below 20k": df = df[df["Avg video views"] < 20000]
    elif view_filter == "Above 100k": df = df[df["Avg video views"] > 100000]
        
    if niche_filter:
        for niche in niche_filter:
            if niche == "PC builds": df = df[df["PC build match"]]
            elif niche == "Gaming": df = df[df["Gaming match"]]
            else: df = df[df["Content niche"].str.contains(niche, case=False, regex=False)]
                
    if game_filter.strip(): df = df[df["Game titles"].str.contains(game_filter.strip(), case=False, regex=False)]
    if contact_only: df = df[df["Public contact email"].notna() | df["Public contact URL"].notna()]
    if review_flags_only: df = df[df["Risk/review flags"].fillna("").str.len() > 0]

    if df.empty:
        st.info("No creators match these filters. Clear a filter or search term to see more profiles.")
        st.stop()

    discovered_country = df["Markets discovered"].fillna("").str.split(", ").str[0]
    df["_Country sort"] = discovered_country.where(discovered_country.ne(""), df["Declared country"].fillna("Unknown"))
    
    # --- Sorting Logic ---
    if sort_order == "Highest Fit Score":
        df = df.sort_values("Fit score", ascending=False, na_position="last")
    elif sort_order == "Country, then target fit":
        df = df.sort_values(["_Country sort", "Core target match", "PC build match", "Gaming match", "Fit score"], ascending=[True, False, False, False, False], na_position="last")
    elif sort_order == "Best target fit":
        df = df.sort_values(["Core target match", "PC build match", "Gaming match", "Fit score", "Avg video views"], ascending=[False, False, False, False, False], na_position="last")
    else:
        df = df.sort_values("Avg video views", ascending=False, na_position="last")

    # Define the core Dropdown label property early so we can use it in the Action Rows
    df["_Dropdown_Label"] = df.apply(
        lambda r: f"{r['Creator']} ({int(r['Subscribers / followers']):,} subs)" 
        if pd.notna(r['Subscribers / followers']) else r['Creator'], 
        axis=1
    )

    st.divider()
    st.markdown("### Database Overview")
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    kpi1.metric("Total Creators Displayed", len(df))
    kpi2.metric("Core Target Fits", len(df[df["Core target match"]]))
    kpi3.metric("Verified Emails Found", len(df[df["Verified Email"] == "Yes"]))
    kpi4.metric("PC Build Channels", len(df[df["PC build match"]]))
    st.write("")

    # --- 1-Action-Per-Row CRM Queue ---
    st.markdown("### Action Queue (Top 5 Matches)")
    st.caption("1 Action Per Row — Instantly select your best creator fits without scrolling through dropdowns.")
    
    action_queue_df = df.head(5)
    for idx, row in action_queue_df.iterrows():
        with st.container(border=True):
            col1, col2, col3, col4, col5 = st.columns([1, 2.5, 3.5, 1, 2])
            with col1:
                avatar = row["Avatar"] if pd.notna(row.get("Avatar")) and row.get("Avatar") else "https://ui-avatars.com/api/?name=" + str(row['Creator']).replace(" ", "+") + "&background=random"
                st.image(avatar, width=64)
            with col2:
                st.markdown(f"**{row['Creator']}**")
                st.caption(f"{row['Platform']} • {row['Declared country']}")
            with col3:
                st.write(f"**{row['Subscribers / followers']:,.0f}** Subs  |  **{row['Avg video views']:,.0f}** Average Views")
                niche_str = str(row['Content niche'])
                st.caption(niche_str[:60] + "..." if len(niche_str)>60 else niche_str)
            with col4:
                st.metric("Fit Score", f"{row['Fit score']}/100")
            with col5:
                st.write("") # Vertical spacing
                if st.button("Review & Pitch", key=f"action_{idx}", type="primary", use_container_width=True):
                    st.session_state["selected_creator"] = row["_Dropdown_Label"]
                    st.rerun() # Instantly refreshes and jumps to this creator's deep dive panel below
                    
    st.write("")
    
    # --- Data Table Section ---
    with st.expander("View Full Database Grid"):
        core_columns = ["Platform", "Creator", "Declared country", "Subscribers / followers", "Avg video views", "Content niche", "Verified Email"]
        optional_columns = ["Handle", "PC build match", "Gaming match", "Game titles", "Commercial saturation", "Trend status", "Risk/review flags", "Channel"]
        
        st.markdown("**Add columns to table**")
        selected_extras = []
        chk_cols = st.columns(4)
        for i, col_name in enumerate(optional_columns):
            if chk_cols[i % 4].checkbox(col_name):
                selected_extras.append(col_name)
        
        display_columns = core_columns + selected_extras
        st.dataframe(df[display_columns], use_container_width=True, hide_index=True, column_config={"Channel": st.column_config.LinkColumn("Channel")})
    
    st.divider()
    
    # --- Deep Dive Review Panel ---
    st.markdown("### Deep Dive Review Panel")
    all_dropdown_labels = df["_Dropdown_Label"].tolist()
    
    default_index = 0
    if st.session_state.get("selected_creator") in all_dropdown_labels:
        default_index = all_dropdown_labels.index(st.session_state["selected_creator"])
        
    selected_label = st.selectbox("Currently Reviewing:", all_dropdown_labels, index=default_index)
    selected = df[df["_Dropdown_Label"] == selected_label].iloc[0]
    selected_creator = selected["Creator"]
    
    # Keep session state in sync if manually changed from the dropdown
    if st.session_state.get("selected_creator") != selected_label:
        st.session_state["selected_creator"] = selected_label
    
    st.markdown(f"**Profile:** [{selected_creator}]({selected['Channel']})")
    
    detail_left, detail_right = st.columns([1, 1.2], gap="large")
    
    with detail_left:
        st.metric("Brand fit estimate", f"{selected['Fit score']}/100")
        st.write(f"**Declared country:** {selected['Declared country']}")
        st.write(f"**Discovered in:** {selected['Markets discovered']}")
        st.write(f"**Content niche:** {selected['Content niche']}")
        if selected["Game titles"]:
            st.write(f"**Games identified:** {selected['Game titles']}")
            
        st.write("") 
        
        # --- Product Matcher ---
        try:
            pcs_df = pd.read_csv("prenew-scraper.csv")
            game_titles = str(selected.get('Game titles', '')).lower()
            niches = str(selected.get('Content niche', '')).lower()
            
            if any(k in game_titles for k in ["valorant", "counter-strike", "cs", "league", "minecraft", "roblox", "sims"]):
                target_tier = "BRONZE"
                reason = "Esports and lightweight titles run flawlessly on Entry/Budget systems."
            elif any(k in game_titles for k in ["cyberpunk", "simulator", "4k", "alan wake", "benchmark", "heavy"]):
                target_tier = "PLATINUM"
                reason = "Demanding modern games require High-End PC performance."
            elif any(k in game_titles for k in ["fortnite", "gta", "call of duty", "apex"]):
                target_tier = "GOLD"
                reason = "Mainstream multiplayer gaming hits the sweet spot on Mid-Range systems."
            elif "pc builds" in niches or "tech reviews" in niches:
                target_tier = "SILVER"
                reason = "Hardware reviewers often appreciate testing price-to-performance sweet spots."
            elif "streaming" in niches:
                target_tier = "GOLD"
                reason = "Streaming requires solid mid-to-high tier multi-core performance."
            else:
                target_tier = "GOLD"
                reason = "A well-balanced Mid-Range system fits general gaming profiles perfectly."
                
            pcs_df['data5'] = pcs_df['data5'].fillna('').str.strip().str.upper()
            matched_pcs = pcs_df[pcs_df['data5'] == target_tier]
            
            if matched_pcs.empty and target_tier == "BRONZE": matched_pcs = pcs_df[pcs_df['data5'] == "SILVER"]
            elif matched_pcs.empty and target_tier == "PLATINUM": matched_pcs = pcs_df[pcs_df['data5'] == "GOLD"]
                
            if not matched_pcs.empty:
                idx = len(selected["Creator"]) % len(matched_pcs)
                suggested_pc = matched_pcs.iloc[idx]
            else:
                suggested_pc = pcs_df.iloc[0]
                
            with st.container(border=True):
                st.markdown("##### Suggested PC for Outreach")
                st.caption(f"Reasoning: {reason}")
                
                cpu_gpu = str(suggested_pc['data']).replace('\n', ' | ')
                st.write(f"**{cpu_gpu}**")
                st.write(f"**Price:** {suggested_pc['data2']}  |  **Tier:** {suggested_pc['data5']}")
                st.caption(f"Specs: {suggested_pc['data4']}, {suggested_pc['data3']}")
                
        except Exception as e:
            st.error(f"Error loading PC suggestions: {e}")
        
        with st.expander("Historical View Consistency & Reach", expanded=True):
            st.caption("Upload frequency and average view reach across 3, 6, and 9-month horizons.")
            st.write("**Upload Volume**")
            col1, col2, col3 = st.columns(3)
            col1.metric("6-9 Months", selected.get("Uploads (6m-9m)", 0))
            col2.metric("3-6 Months", selected.get("Uploads (3m-6m)", 0))
            col3.metric("Last 3 Months", selected.get("Uploads (Last 3m)", 0))

            st.write("**Average Views**")
            col4, col5, col6 = st.columns(3)
            col4.metric("6-9 Months", f"{selected.get('Avg Views (6m-9m)', 0):,.0f}")
            col5.metric("3-6 Months", f"{selected.get('Avg Views (3m-6m)', 0):,.0f}")
            col6.metric("Last 3 Months", f"{selected.get('Avg Views (Last 3m)', 0):,.0f}")

    with detail_right:
        draft_with_link = selected["Outreach draft"] + "\n\nhttps://www.prenew.com/"
        st.text_area(f"Outreach Draft ({market})", draft_with_link, height=320)
        st.caption("Editable suggestion. Verify the channel and contact method before outreach.")
        
        if gemini_api_key:
            recommendation_key = f"gemini_recommendation_{selected_creator}"
            if st.button("Generate Collaboration Strategy", type="primary", key=f"generate_{selected_creator}"):
                try:
                    with st.spinner("Analyzing this creator's evidence and performance..."):
                        st.session_state[recommendation_key] = generate_gemini_recommendation(
                            gemini_api_key,
                            {
                                "name": selected["Creator"], "platform": selected["Platform"], "declared_country": selected["Declared country"],
                                "followers": selected["Subscribers / followers"], "uploads_last_3m": selected.get("Uploads (Last 3m)", 0),
                                "average_video_views": selected["Avg video views"], "engagement_rate_pct": selected["Recent engagement %"],
                                "content_niches": selected["Content niche"], "game_titles": selected["Game titles"], "recent_videos": selected["Recent videos"],
                            },
                        )
                except Exception as error:
                    st.error(f"Gemini recommendation failed ({type(error).__name__}). {gemini_error_hint(error)}")
            if st.session_state.get(recommendation_key):
                st.info(st.session_state[recommendation_key])
        else:
            st.caption("Add GEMINI_API_KEY to local Streamlit secrets to enable tailored recommendations.")
            
        with st.expander("Performance & Contact Details"):
            metric_columns = st.columns(4)
            metric_columns[0].metric("Lifetime views", f"{selected['Channel total views']:,}" if pd.notna(selected["Channel total views"]) else "N/A")
            metric_columns[1].metric("Total videos", f"{selected['Channel video count']:,}" if pd.notna(selected["Channel video count"]) else "N/A")
            metric_columns[2].metric("Avg views", f"{selected['Avg video views']:,.0f}" if pd.notna(selected["Avg video views"]) else "N/A")
            metric_columns[3].metric("Engagement", f"{selected['Recent engagement %']:.2f}%" if pd.notna(selected["Recent engagement %"]) else "N/A")
            
            contact_email = selected['Public contact email']
            contact_url = selected['Public contact URL']
            contact_display = contact_email if pd.notna(contact_email) and contact_email else (contact_url if pd.notna(contact_url) and contact_url else "Not provided in public profile")
            st.write(f"**Public contact:** {contact_display}")
            if selected["Risk/review flags"]: st.warning(selected["Risk/review flags"])

        with st.expander("Recent Evidence Videos"):
            if selected["Recent videos"]:
                for video in selected["Recent videos"]:
                    st.write(f"[{video['title']}]({video.get('url', '#')}) | {video.get('views', 0):,} views")
            else:
                st.caption("No recent video data in this sample profile.")

    st.divider()
    
    export_columns = ["Platform", "Creator", "Handle", "Declared country", "Markets discovered", "Subscribers / followers", "Size tier", "Avg video views", "Fit score", "Outreach draft"]
    export_df = df[export_columns].copy() if set(export_columns).issubset(df.columns) else df.copy()
    
    # --- Buttons perfectly centered in the middle of the screen ---
    st.write("")
    b_col1, b_col2, b_col3 = st.columns([1, 1.5, 1])
    with b_col2:
        st.download_button("Download shortlist as CSV (CRM Ready)", data=export_df.to_csv(index=False).encode("utf-8-sig"), file_name="prenew_creator_shortlist.csv", mime="text/csv", use_container_width=True)
        if st.button("Connect to CRM", type="primary", use_container_width=True):
            show_crm_popup()
    st.write("")