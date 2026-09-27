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

st.set_page_config(layout="wide", page_title="Prenew Micro-Scout")

st.markdown("""
<style>
    /* Main background */
    .stApp {
        background-color: #13603d; 
        color: #ffffff;
    }
    
    /* 1. White background with dark text for ALL inputs, dropdowns, uploaders */
    .stTextInput input, 
    .stTextArea textarea, 
    .stSelectbox div[data-baseweb="select"] > div,
    .stMultiSelect div[data-baseweb="select"] > div,
    [data-testid="stFileUploaderDropzone"] {
        background-color: #ffffff !important;
        border: 1px solid #ffffff !important;
        color: #000000 !important; 
        border-radius: 8px !important;
    }

    /* Force text inside the drag-and-drop uploader to be dark */
    [data-testid="stFileUploaderDropzone"] div,
    [data-testid="stFileUploaderDropzone"] span,
    [data-testid="stFileUploaderDropzone"] small {
        color: #000000 !important;
    }

    /* --- OVERRIDE: White Checkboxes (Ticks) --- */
    div[data-baseweb="checkbox"] div[role="checkbox"] {
        background-color: #ffffff !important; 
        border: 2px solid #ffffff !important;
    }
    /* The actual tick mark inside the box */
    div[data-baseweb="checkbox"] div[role="checkbox"] svg {
        color: #000000 !important; /* Black tick */
        fill: #000000 !important;
    }
    
    /* --- OVERRIDE: White Data Tables with Black Text --- */
    [data-testid="stDataFrame"] > div > div > div > div {
        background-color: #ffffff !important;
    }
    
    /* Table Headers */
    [data-testid="stDataFrame"] th {
        background-color: #f8f9fa !important; /* Slightly off-white for headers */
        color: #000000 !important; /* Black text */
        border-bottom: 1px solid #dee2e6 !important;
    }
    
    /* Table Cells (Rows) */
    [data-testid="stDataFrame"] td {
        background-color: #ffffff !important; /* Pure white */
        color: #000000 !important; /* Black text */
        border-bottom: 1px solid #f1f3f5 !important;
    }
    
    /* 2. Fix the dark buttons: Standard, Download, and Browse Files buttons */
    .stButton > button,
    .stDownloadButton > button,
    [data-testid="stFileUploaderDropzone"] button {
        background-color: #ffffff !important;
        border: 1px solid #ffffff !important;
        color: #000000 !important;
        border-radius: 8px !important;
    }
    .stButton > button p, 
    .stDownloadButton > button p {
        color: #000000 !important;
    }
    
    /* Primary action buttons get the solid fill ("Buy a PC" style) */
    .stButton > button[kind="primary"] {
        background-color: #a4ffa2 !important; 
        color: #13603d !important;
        border: none !important;
        font-weight: 700 !important;
    }
    .stButton > button[kind="primary"] p {
        color: #13603d !important;
    }
    
    /* 3. Make the success message box RED */
    [data-testid="stAlert"] {
        background-color: #d93838 !important; /* Vibrant Red */
        color: #ffffff !important;
        border: none !important;
        border-radius: 8px !important;
    }
    [data-testid="stAlert"] div, [data-testid="stAlert"] span, [data-testid="stAlert"] p {
        color: #ffffff !important;
    }

    /* Fix Radio Buttons from being dark holes */
    div[role="radio"] {
        background-color: #ffffff !important;
    }

    /* Make placeholder text dark grey to contrast with the white background */
    .stTextInput input::placeholder, 
    .stTextArea textarea::placeholder,
    .stSelectbox div[class*="placeholder"], 
    .stMultiSelect div[class*="placeholder"] {
        color: #666666 !important;
    }
    
    /* Ensure dropdown text and icons remain dark */
    .stSelectbox span, .stMultiSelect span {
        color: #000000 !important;
    }
    
    /* Containers and Expanders get a matching subtle white frame */
    [data-testid="stExpander"], [data-testid="stVerticalBlockBorderWrapper"] {
        background-color: transparent !important;
        border: 1px solid rgba(255, 255, 255, 0.4) !important;
        border-radius: 8px !important;
    }

    /* Make the Dataframe/Table White with Black Text */
    [data-testid="stDataFrame"] > div > div > div > div {
        background-color: #ffffff !important;
        color: #000000 !important;
    }
    
    /* Ensure table headers are also white/black */
    [data-testid="stDataFrame"] th {
        background-color: #f8f9fa !important;
        color: #000000 !important;
        border-bottom: 1px solid #dee2e6 !important;
    }
    
    /* Ensure table cells (rows) have dark text and subtle borders */
    [data-testid="stDataFrame"] td {
        background-color: #ffffff !important;
        color: #000000 !important;
        border-bottom: 1px solid #f1f3f5 !important;
    } 
    
    /* Fix alignment to push content left and use full width */
    .block-container {
        padding-left: 2rem !important;
        padding-right: 2rem !important;
        max-width: 100% !important;
    }
</style>
""", unsafe_allow_html=True)

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

st.title("Prenew Creator Scout")
st.write("Find relevant creators, understand their content fit, and prepare outreach.")
saved_datasets = sorted(Path(__file__).parent.glob("youtube_creator_data_eu27_*.csv"))
saved_dataset_path = saved_datasets[-1] if saved_datasets else None

st.divider()

top_col1, top_col2 = st.columns([1, 1], gap="large")

with top_col1:
    youtube_source_label = "YouTube API discovery" if saved_dataset_path else "Demo data"
    source_options = [youtube_source_label, "TikTok licensed-provider CSV", "Instagram licensed-provider CSV"]
    source_mode = st.radio("Select Discovery Source", source_options, horizontal=True)
    niche_query = st.text_input("Filter by niche, game, or creator name", "")

with top_col2:
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
    
    # Only draw the upload UI if a CSV mode is actually selected
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
            )

if st.session_state.get("active_source_mode") != source_mode:
    st.session_state.pop("creator_results", None)
    st.session_state["active_source_mode"] = source_mode

load_saved_on_open = from_saved and not st.session_state.get("creator_results")

if st.button("Load / refresh dataset", type="primary") or load_saved_on_open:
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
                    for creator in candidates:
                        results = []
                    candidates = creators
                    now_utc = datetime.now(timezone.utc)
                    
                    for creator in candidates:
                        # Convert the saved CSV text string back into a usable list
                        if "recent_videos" not in creator and "recent_video_metrics_json" in creator:
                            try:
                                raw_json = creator["recent_video_metrics_json"]
                                creator["recent_videos"] = json.loads(raw_json) if isinstance(raw_json, str) else []
                            except Exception:
                                creator["recent_videos"] = []
                                
                        # Compute historical cohorts on the fly from recent videos
                        recent_vids = creator.get("recent_videos", [])
                        u3m, u6m, u9m = [], [], []
                        for vid in recent_vids:
                            pub = vid.get("published_at")
                            if not pub:
                                continue
                            try:
                                dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                                age_days = max(0, (now_utc - dt).total_seconds() / 86400)
                            except Exception:
                                continue
                            v_views = vid.get("views", 0) or 0
                            if age_days <= 90:
                                u3m.append(v_views)
                            elif 90 < age_days <= 180:
                                u6m.append(v_views)
                            elif 180 < age_days <= 270:
                                u9m.append(v_views)

                        uploads_3m = len(u3m) if recent_vids else creator.get("uploads_3m", 0)
                        uploads_6m = len(u6m) if recent_vids else creator.get("uploads_6m", 0)
                        uploads_9m = len(u9m) if recent_vids else creator.get("uploads_9m", 0)
                        avg_views_3m = round(sum(u3m) / len(u3m), 1) if u3m else creator.get("avg_views_3m", 0)
                        avg_views_6m = round(sum(u6m) / len(u6m), 1) if u6m else creator.get("avg_views_6m", 0)
                        avg_views_9m = round(sum(u9m) / len(u9m), 1) if u9m else creator.get("avg_views_9m", 0)
                        
                        platform = creator.get("platform", "YouTube")
                        analysis = score_and_draft_pitch(
                            "",
                            creator,
                            language,
                        )
                        categories = creator.get("content_categories", [])
                        subscribers = creator.get("subscribers")
                        average_views = creator.get("avg_recent_video_views")
                        is_core_youtube = bool(
                            platform == "YouTube"
                            and subscribers is not None
                            and average_views is not None
                            and 50000 <= subscribers <= 250000
                            and 20000 <= average_views <= 100000
                        )
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
                            
                            # Added Historical Metrics (using correct local variables)
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
            if status == 403:
                detail = "Check that YouTube Data API v3 is enabled, the key is valid, and its restrictions allow this app."
            elif status == 400:
                detail = "Check the market, language, and search phrase."
            elif status == 429:
                detail = "YouTube API quota or rate limit reached."
            else:
                detail = "Check the key and YouTube Data API project settings."
            st.error(f"YouTube API request failed (HTTP {status}). {detail}")
        except Exception as error:
            st.error(f"Discovery failed ({type(error).__name__}). Check your API key and network connection.")

results = st.session_state.get("creator_results", [])
if results:
    source_label = st.session_state.get("creator_source_label", "creator dataset")
    st.success(f"Prepared {len(results)} profiles from {source_label}. Country searched and creator-declared country are separate fields.")
    st.caption("Creators with a declared country outside the EU-27 are excluded. If country is not provided, EU-market discovery is retained and shown separately.")
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
        country_filter = f_col1.selectbox("Country", ["All countries", *EU_MARKETS.keys()])
        size_filter = f_col2.selectbox("Audience size", ["All sizes", "Micro-creators (< 10k)", "Emerging (10k - 50k)", "Established (50k - 250k)", "Large (> 250k)"])
        view_filter = f_col3.selectbox("Average views", ["Any", "20k-100k core range", "Below 20k", "Above 100k"])
        
        f_col4, f_col5 = st.columns(2)
        niche_filter = f_col4.multiselect("Content niche", ["PC builds", "Gaming", "Hardware and benchmarks", "Tech reviews", "Gaming setups", "Streaming"])
        game_filter = f_col5.text_input("Game title contains", "")
        
        f_col6, f_col7, f_col8 = st.columns([1, 1, 1.5])
        with f_col6:
            st.write("") # Spacing alignment
            contact_only = st.checkbox("Has public contact route", value=False)
        with f_col7:
            st.write("") # Spacing alignment
            review_flags_only = st.checkbox("Has review flags", value=False)
        with f_col8:
            sort_order = st.selectbox("Sort results", ["Country, then target fit", "Best target fit", "Highest average views"])
    if country_filter != "All countries":
        country_code = EU_MARKETS[country_filter][0]
        df = df[
            (df["Declared country"] == country_code)
            | df["Markets discovered"].str.contains(country_filter, case=False, regex=False)
        ]
    if size_filter == "Core targets only":
        df = df[df["Core target match"]]
    if size_filter == "Micro-creators (< 10k)":
        df = df[df["Subscribers / followers"] < 10000]
    elif size_filter == "Emerging (10k - 50k)":
        df = df[df["Subscribers / followers"].between(10000, 49999)]
    elif size_filter == "Established (50k - 250k)":
        df = df[df["Subscribers / followers"].between(50000, 250000)]
    elif size_filter == "Large (> 250k)":
        df = df[df["Subscribers / followers"] > 250000]
    if view_filter == "20k-100k core range":
        df = df[df["Avg video views"].between(20000, 100000)]
    elif view_filter == "Below 20k":
        df = df[df["Avg video views"] < 20000]
    elif view_filter == "Above 100k":
        df = df[df["Avg video views"] > 100000]
    if niche_filter:
        for niche in niche_filter:
            if niche == "PC builds":
                df = df[df["PC build match"]]
            elif niche == "Gaming":
                df = df[df["Gaming match"]]
            else:
                df = df[df["Content niche"].str.contains(niche, case=False, regex=False)]
    if game_filter.strip():
        df = df[df["Game titles"].str.contains(game_filter.strip(), case=False, regex=False)]
    if contact_only:
        df = df[df["Public contact email"].notna() | df["Public contact URL"].notna()]
    if review_flags_only:
        df = df[df["Risk/review flags"].fillna("").str.len() > 0]

    if df.empty:
        st.info("No creators match these filters. Clear a filter or search term to see more profiles.")
        st.stop()

    discovered_country = df["Markets discovered"].fillna("").str.split(", ").str[0]
    df["_Country sort"] = discovered_country.where(
        discovered_country.ne(""), df["Declared country"].fillna("Unknown")
    )
    if sort_order == "Country, then target fit":
        df = df.sort_values(
            ["_Country sort", "Core target match", "PC build match", "Gaming match", "Fit score"],
            ascending=[True, False, False, False, False], na_position="last",
        )
    elif sort_order == "Best target fit":
        df = df.sort_values(
            ["Core target match", "PC build match", "Gaming match", "Fit score", "Avg video views"],
            ascending=[False, False, False, False, False], na_position="last",
        )
    else:
        df = df.sort_values("Avg video views", ascending=False, na_position="last")

    st.divider()
    st.markdown("### Database Overview")
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    kpi1.metric("Total Creators Displayed", len(df))
    kpi2.metric("Core Target Fits", len(df[df["Core target match"]]))
    kpi3.metric("Verified Emails Found", len(df[df["Verified Email"] == "Yes"]))
    kpi4.metric("PC Build Channels", len(df[df["PC build match"]]))
    
    st.write("")
    
    # Define essential columns shown by default
    core_columns = [
        "Platform", "Creator", "Declared country",
        "Subscribers / followers", "Avg video views", "Content niche", "Verified Email"
    ]
    
    # Define optional columns that are hidden by default
    optional_columns = [
        "Handle", "PC build match", "Gaming match", "Game titles", 
        "Commercial saturation", "Trend status", "Risk/review flags", "Channel"
    ]
    
    # Render checkboxes in a compact 4-column grid
    st.markdown("**Add columns to table**")
    selected_extras = []
    chk_cols = st.columns(4)
    for i, col_name in enumerate(optional_columns):
        if chk_cols[i % 4].checkbox(col_name):
            selected_extras.append(col_name)
    
    # Combine core columns with the user's selections
    display_columns = core_columns + selected_extras

    st.dataframe(
        df[display_columns],
        use_container_width=True,
        hide_index=True,
        column_config={
            "Channel": st.column_config.LinkColumn("Channel")
        },
    )
    st.divider()
    
    # Create a formatted label for the dropdown that includes the subscriber count
    df["_Dropdown_Label"] = df.apply(
        lambda r: f"{r['Creator']} ({int(r['Subscribers / followers']):,} subs)" 
        if pd.notna(r['Subscribers / followers']) else r['Creator'], 
        axis=1
    )
    
    selected_label = st.selectbox("Select a creator to review and prepare outreach", df["_Dropdown_Label"].tolist())
    selected = df[df["_Dropdown_Label"] == selected_label].iloc[0]
    selected_creator = selected["Creator"]
    
    # Make the profile header a clickable hyperlink pointing to their channel
    st.markdown(f"### Profile: [{selected_creator}]({selected['Channel']})")
    
    # Split into a clean 2-column dashboard layout
    detail_left, detail_right = st.columns([1, 1.2], gap="large")
    
    with detail_left:
        st.metric("Brand fit estimate", f"{selected['Fit score']}/100")
        st.write(f"**Declared country:** {selected['Declared country']}")
        st.write(f"**Discovered in:** {selected['Markets discovered']}")
        st.write(f"**Content niche:** {selected['Content niche']}")
        if selected["Game titles"]:
            st.write(f"**Games identified:** {selected['Game titles']}")
            
        st.markdown("**Why it fits:**")
        st.write(selected["Why it fits"])
        
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
        # Append the website URL to the draft text dynamically
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
                                "name": selected["Creator"],
                                "platform": selected["Platform"],
                                "declared_country": selected["Declared country"],
                                "markets_discovered": selected["Markets discovered"],
                                "followers": selected["Subscribers / followers"],
                                "uploads_last_3m": selected.get("Uploads (Last 3m)", 0),
                                "uploads_3m_to_6m": selected.get("Uploads (3m-6m)", 0),
                                "uploads_6m_to_9m": selected.get("Uploads (6m-9m)", 0),
                                "avg_views_last_3m": selected.get("Avg Views (Last 3m)", 0),
                                "avg_views_3m_to_6m": selected.get("Avg Views (3m-6m)", 0),
                                "avg_views_6m_to_9m": selected.get("Avg Views (6m-9m)", 0),
                                "average_video_views": selected["Avg video views"],
                                "median_video_views": selected["Median video views"],
                                "view_window_days": selected["Views window (days)"],
                                "view_window_video_count": selected["Views sample size"],
                                "engagement_rate_pct": selected["Recent engagement %"],
                                "content_niches": selected["Content niche"],
                                "game_titles": selected["Game titles"],
                                "risk_flags": selected["Risk/review flags"],
                                "recent_videos": selected["Recent videos"],
                                "description": selected.get("Channel description", ""),
                                "fit_reasoning": selected["Why it fits"],
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
            
            if selected["Risk/review flags"]:
                st.warning(selected["Risk/review flags"])

        with st.expander("Recent Evidence Videos"):
            if selected["Recent videos"]:
                for video in selected["Recent videos"]:
                    st.write(f"[{video['title']}]({video.get('url', '#')}) | {video.get('views', 0):,} views")
            else:
                st.caption("No recent video data in this sample profile.")

    st.divider()
    
    export_columns = [
        "Platform", "Creator", "Handle", "Declared country", "Markets discovered",
        "Subscribers / followers", "Size tier", "Core target match", "Channel total views",
        "Channel video count", "Avg video views", "Median video views", "Views window (days)",
        "Views sample size", "Avg views / followers %", "Avg recent video likes",
        "Avg recent video comments", "Recent engagement %", "Uploads last 30d", "Uploads last 90d",
        "Last upload age (days)", "Observed monthly channel view growth",
        "Observed monthly video view growth", "Trend status", "Observed monthly subscriber growth",
        "Snapshot interval days", "Estimated monthly views (snapshot)", "Estimated yearly views (snapshot)",
        "PC build match", "Gaming match", "Niche confidence (% recent uploads matched)",
        "Content niche", "Game titles", "Risk/review flags", "Public contact email",
        "Public contact URL", "Data source", "Provider snapshot date", "Fit score",
        "Why it fits", "Outreach draft", "Recent video metrics JSON", "Channel",
    ]
    export_df = df[export_columns].copy()
    st.download_button(
        "Download shortlist as CSV (CRM Ready)",
        data=export_df.to_csv(index=False).encode("utf-8-sig"),
        file_name="prenew_creator_shortlist.csv",
        mime="text/csv",
    )