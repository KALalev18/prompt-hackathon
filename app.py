import streamlit as st
import pandas as pd
import os
import json
import tomllib
from pathlib import Path
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from sourcing import EU_MARKETS, get_youtube_creators, get_youtube_creators_across_eu, get_fallback_creators
from scoring import score_and_draft_pitch, generate_gemini_recommendation
from metrics_history import save_and_measure_snapshots
from platform_imports import TIKTOK_CSV_TEMPLATE, INSTAGRAM_CSV_TEMPLATE, load_provider_csv, load_saved_youtube_dataset

st.set_page_config(layout="wide", page_title="Prenew Micro-Scout")

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
    if is_csv_upload:
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
                            "Platform": platform,
                            "Creator": creator["name"],
                            "Handle": creator.get("handle", ""),
                            "Declared country": creator.get("declared_country") or "Not provided",
                            "Markets discovered": ", ".join(creator.get("countries", [])) or ("Demo" if use_demo_data else market),
                            "Subscribers / followers": subscribers,
                            "Size tier": size_tier,
                            "Core target match": is_core_youtube or (platform == "TikTok" and subscribers is not None and subscribers >= 4000),
                            # --- ADD THE NEW FIELDS HERE ---
                            "Commercial saturation": creator.get("commercial_saturation", "Unknown"),
                            "Verified Email": "✅ Yes" if creator.get("public_contact_email") else "❌ No",
                            "Channel total views": creator.get("channel_total_views"),
                            "Channel video count": creator.get("channel_video_count"),
                            "Avg video views": average_views,
                            "Median video views": creator.get("median_recent_video_views"),
                            "Views window (days)": creator.get("view_window_days"),
                            "Views sample size": creator.get("view_window_video_count"),
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
                            "Game titles": "; ".join(category.removeprefix("Game: ") for category in categories if category.startswith("Game: ")) or "; ".join(creator.get("game_titles", [])),
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
    filter_columns = st.columns(3)
    country_filter = filter_columns[0].selectbox("Country", ["All countries", *EU_MARKETS.keys()])
    size_filter = filter_columns[1].selectbox("Audience size", ["All sizes", "Core targets only", "Emerging YouTube (<50k)", "Large YouTube (>250k)"])
    view_filter = filter_columns[2].selectbox("Average views", ["Any", "20k-100k core range", "Below 20k", "Above 100k"])
    niche_filter = st.multiselect("Content niche", ["PC builds", "Gaming", "Hardware and benchmarks", "Tech reviews", "Gaming setups", "Streaming"])
    game_filter = st.text_input("Game title contains", "")
    contact_only = st.checkbox("Only profiles with a public contact route", value=False)
    review_flags_only = st.checkbox("Only profiles with review flags", value=False)
    sort_order = st.selectbox("Sort results", ["Country, then target fit", "Best target fit", "Highest average views"])

    if country_filter != "All countries":
        country_code = EU_MARKETS[country_filter][0]
        df = df[
            (df["Declared country"] == country_code)
            | df["Markets discovered"].str.contains(country_filter, case=False, regex=False)
        ]
    if size_filter == "Core targets only":
        df = df[df["Core target match"]]
    elif size_filter == "Emerging YouTube (<50k)":
        df = df[(df["Platform"] == "YouTube") & (df["Subscribers / followers"] < 50000)]
    elif size_filter == "Large YouTube (>250k)":
        df = df[(df["Platform"] == "YouTube") & (df["Subscribers / followers"] > 250000)]
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

    display_columns = [
        "Platform", "Creator", "Handle", "Declared country",
        "Subscribers / followers", "Avg video views", "PC build match", "Gaming match",
        "Content niche", "Game titles", "Commercial saturation", "Verified Email", 
        "Trend status", "Risk/review flags", "Channel",
    ]
    st.dataframe(
        df[display_columns],
        use_container_width=True,
        hide_index=True,
        column_config={"Channel": st.column_config.LinkColumn("Channel")},
    )

    selected_creator = st.selectbox("Review outreach for", df["Creator"].tolist())
    selected = df[df["Creator"] == selected_creator].iloc[0]
    st.subheader(f"Outreach draft: {selected_creator}")
    st.metric("Brand fit estimate", f"{selected['Fit score']}/100")
    st.write(f"**Creator-declared country:** {selected['Declared country']}")
    st.write(f"**Markets where discovered:** {selected['Markets discovered']}")
    st.write(f"**Content niche:** {selected['Content niche']}")
    if selected["Game titles"]:
        st.write(f"**Games identified:** {selected['Game titles']}")
    st.write(selected["Why it fits"])
    if gemini_api_key:
        recommendation_key = f"gemini_recommendation_{selected_creator}"
        if st.button("Generate Collaboration Strategy", key=f"generate_{selected_creator}"):
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
    with st.expander("Outreach and contact fields"):
        st.write("The outreach draft is an editable suggestion only; this app never sends it. Public contact email/URL fields are included only when present in the source data. Data source and provider snapshot date show where and when imported metrics came from.")
    with st.expander("YouTube performance metrics"):
        st.caption("Average and median views use the 30-day upload cohort when at least three uploads exist, otherwise the 90-day cohort. These are current lifetime views of videos published in that period. Observed view growth compares saved public counters, and requires a later snapshot at least seven days apart.")
        metric_columns = st.columns(4)
        metric_columns[0].metric("Channel lifetime views", f"{selected['Channel total views']:,}" if pd.notna(selected["Channel total views"]) else "N/A")
        metric_columns[1].metric("Channel videos", f"{selected['Channel video count']:,}" if pd.notna(selected["Channel video count"]) else "N/A")
        metric_columns[2].metric("Avg video views", f"{selected['Avg video views']:,.0f}" if pd.notna(selected["Avg video views"]) else "N/A")
        metric_columns[3].metric("Recent engagement", f"{selected['Recent engagement %']:.2f}%" if pd.notna(selected["Recent engagement %"]) else "N/A")
        st.write(f"Median views: {selected['Median video views'] if pd.notna(selected['Median video views']) else 'N/A'}")
        st.write(f"Observed monthly video-view growth: {selected['Observed monthly video view growth'] if pd.notna(selected['Observed monthly video view growth']) else 'Needs another video snapshot'}")
        st.write(f"Estimated yearly channel views at current run rate: {selected['Estimated yearly views (snapshot)'] if pd.notna(selected['Estimated yearly views (snapshot)']) else 'Needs another channel snapshot'}")
        st.write(f"**Public contact:** {selected['Public contact email'] or selected['Public contact URL'] or 'Not provided in public profile description'}")
        if selected["Risk/review flags"]:
            st.warning(selected["Risk/review flags"])
        for video in selected["Recent videos"]:
            growth = video.get("observed_monthly_view_growth")
            growth_text = f" | observed monthly growth: {growth:+,}" if growth is not None else ""
            st.write(f"[{video['title']}]({video['url']}) | {video.get('views', 0):,} views | {video.get('likes', 0):,} likes | {video.get('comments', 0):,} comments | published {video.get('published_at', 'date unknown')}{growth_text}")
    st.text_area(f"Draft for human review ({market})", selected["Outreach draft"], height=150)
    with st.expander("Recent videos used for niche detection"):
        if selected["Recent videos"]:
            for video in selected["Recent videos"]:
                st.write(f"[{video['title']}]({video['url']})")
        else:
            st.caption("No recent video data in this sample profile.")
    
    st.caption("No message is sent. Verify the channel and contact method, personalize the draft, and get approval before outreach.")

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