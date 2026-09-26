import re
import json

import pandas as pd
from sourcing import EU_COUNTRY_CODES


TIKTOK_CSV_TEMPLATE = """creator_name,handle,country,follower_count,average_views_30d,average_views_90d,video_count_30d,video_count_90d,engagement_rate_pct,content_niche,game_titles,public_contact_email,public_contact_url,source_url,data_provider,snapshot_date
Helsinki Hardware,@helsinkihardware,FI,18500,42000,38000,5,15,4.8,PC builds; Hardware and benchmarks,CS2,contact@helsinkihardware.fi,https://helsinkihardware.fi,https://tiktok.com/@helsinkihardware,Licensed provider,2026-09-26
Berlin Tech Setups,@berlin_setups,DE,34000,88000,82000,8,22,5.1,Gaming setups; Hardware and benchmarks,Valorant; Minecraft,collab@berlinsetups.de,https://berlinsetups.de/links,https://tiktok.com/@berlin_setups,Licensed provider,2026-09-26
Suomi Sim Racing,@suomisim,FI,8900,18500,21000,8,22,6.1,Gaming setups,Sim Racing,suomi@example.fi,https://suomisim.fi,https://tiktok.com/@suomisim,Licensed provider,2026-09-26
Klaus PC Builds,@klaus_builds,DE,24500,65000,58000,6,15,4.8,PC builds; Tech reviews,CS2,klaus@example.com,https://klausbuilds.de,https://tiktok.com/@klaus_builds,Licensed provider,2026-09-26
Paris Gamer Rigs,@parisgamerrigs,FR,14200,32000,29000,4,10,3.5,Tech reviews; PC builds,League of Legends,contact@parisgamerrigs.fr,https://parisgamerrigs.fr,https://tiktok.com/@parisgamerrigs,Licensed provider,2026-09-26
Warsaw Setups,@warsawsetups,PL,45000,110000,95000,12,30,5.2,Gaming setups; Gaming,Minecraft; Roblox,collab@warsawsetups.pl,https://warsawsetups.pl,https://tiktok.com/@warsawsetups,Licensed provider,2026-09-26
"""

INSTAGRAM_CSV_TEMPLATE = """creator_name,handle,country,follower_count,average_views_30d,average_views_90d,video_count_30d,video_count_90d,engagement_rate_pct,content_niche,game_titles,public_contact_email,public_contact_url,source_url,data_provider,snapshot_date
Munich PC Master,@munichpcmaster,DE,45000,120000,115000,8,24,4.2,PC builds; Hardware and benchmarks,Valorant,munich@example.de,https://munichpc.de,https://instagram.com/munichpcmaster,Licensed provider,2026-09-26
Helsinki Gamer Hub,@helsinkigamerhub,FI,22000,45000,42000,10,30,5.8,Gaming setups; Tech reviews,CS2,hello@helsinkigamerhub.fi,,https://instagram.com/helsinkigamerhub,Licensed provider,2026-09-26
Stockholm Rigs,@stockholmrigs,SE,67000,150000,140000,12,35,3.9,PC builds,Minecraft,collab@stockholmrigs.se,,https://instagram.com/stockholmrigs,Licensed provider,2026-09-26
Berlin Tech Labs,@berlintechlabs,DE,15500,38000,35000,5,15,4.5,Hardware and benchmarks,League of Legends,contact@berlintech.de,,https://instagram.com/berlintechlabs,Licensed provider,2026-09-26
Paris Setup Guru,@parissetupguru,FR,32000,85000,80000,7,20,5.1,Gaming setups,,hello@parisguru.fr,https://parisguru.fr,https://instagram.com/parissetupguru,Licensed provider,2026-09-26
Warsaw Hardware,@warsawhardware,PL,28000,62000,60000,9,26,4.7,Tech reviews; PC builds,CS2,collab@warsawhardware.pl,,https://instagram.com/warsawhardware,Licensed provider,2026-09-26
"""


def load_saved_youtube_dataset(dataset_path):
    """Load a previously extracted YouTube CSV into the app's creator profile shape."""
    frame = pd.read_csv(dataset_path)
    creators = []

    def text(value, default=""):
        return default if pd.isna(value) else str(value).strip()

    def optional_number(value):
        return None if pd.isna(value) else float(value)

    for _, row in frame.iterrows():
        declared_country = text(row.get("creator_country_declared"), "Not provided")
        if declared_country != "Not provided" and declared_country not in EU_COUNTRY_CODES:
            continue
        try:
            recent_videos = json.loads(text(row.get("recent_video_metrics_json"), "[]"))
        except (TypeError, json.JSONDecodeError):
            recent_videos = []
        categories = [item.strip() for item in text(row.get("content_niches")).split(";") if item.strip()]
        creators.append({
            "platform": "YouTube",
            "name": text(row.get("creator_name"), "Unknown creator"),
            "handle": text(row.get("channel_handle")),
            "url": text(row.get("channel_handle")),
            "declared_country": None if declared_country == "Not provided" else declared_country,
            "countries": [item.strip() for item in text(row.get("markets_discovered")).split(";") if item.strip()],
            "subscribers": optional_number(row.get("subscriber_count")),
            "subscriber_count_hidden": bool(row.get("subscriber_count_hidden", False)),
            "channel_total_views": optional_number(row.get("channel_total_views")),
            "channel_video_count": optional_number(row.get("channel_video_count")),
            "avg_recent_video_views": optional_number(row.get("average_video_views")),
            "median_recent_video_views": optional_number(row.get("median_video_views")),
            "view_window_days": optional_number(row.get("view_cohort_days")),
            "view_window_video_count": optional_number(row.get("view_cohort_video_count")),
            "avg_views_to_subscribers_pct": optional_number(row.get("average_views_to_subscribers_pct")),
            "avg_recent_video_likes": optional_number(row.get("average_likes")),
            "avg_recent_video_comments": optional_number(row.get("average_comments")),
            "recent_video_engagement_rate": optional_number(row.get("engagement_rate_pct")),
            "recent_30d_uploads": optional_number(row.get("uploads_last_30_days")),
            "recent_90d_uploads": optional_number(row.get("uploads_last_90_days")),
            "last_upload_days": optional_number(row.get("last_upload_age_days")),
            "pc_build_match": bool(row.get("pc_build_match", False)),
            "gaming_match": bool(row.get("gaming_match", False)),
            "content_categories": categories,
            "game_titles": [item.strip() for item in text(row.get("game_titles")).split(";") if item.strip()],
            "niche_match_ratio_pct": optional_number(row.get("niche_evidence_ratio_pct")),
            "risk_flags": [item.strip() for item in text(row.get("risk_review_flags")).split(";") if item.strip()],
            "trend_status": text(row.get("trend_status"), "No trend data"),
            "observed_monthly_view_growth": optional_number(row.get("observed_monthly_channel_view_growth")),
            "median_observed_monthly_video_view_growth": optional_number(row.get("observed_monthly_video_view_growth_median")),
            "observed_monthly_subscriber_growth": optional_number(row.get("observed_monthly_subscriber_growth")),
            "snapshot_interval_days": optional_number(row.get("snapshot_interval_days")),
            "estimated_monthly_views_from_snapshot": optional_number(row.get("estimated_monthly_views_run_rate")),
            "estimated_yearly_views_from_snapshot": optional_number(row.get("estimated_yearly_views_run_rate")),
            "public_contact_email": text(row.get("public_contact_email")) or None,
            "public_contact_url": text(row.get("public_contact_url")) or None,
            "description": text(row.get("channel_description")),
            "recent_videos": recent_videos,
            "data_provider": "Saved YouTube API extraction",
        })

    return creators


def _column_map(columns):
    normalized = {re.sub(r"[^a-z0-9]+", "_", str(column).strip().lower()).strip("_"): column for column in columns}
    aliases = {
        "creator_name": ("creator_name", "creator", "display_name", "name"),
        "handle": ("handle", "username", "user_name", "profile_handle"),
        "country": ("country", "country_code", "registered_country", "region_code"),
        "follower_count": ("follower_count", "followers", "followers_count"),
        "average_views_30d": ("average_views_30d", "avg_views_30d", "avg_video_views_30d"),
        "average_views_90d": ("average_views_90d", "avg_views_90d", "avg_video_views_90d"),
        "video_count_30d": ("video_count_30d", "videos_30d", "uploads_30d"),
        "video_count_90d": ("video_count_90d", "videos_90d", "uploads_90d"),
        "engagement_rate_pct": ("engagement_rate_pct", "engagement_rate", "engagement_pct"),
        "content_niche": ("content_niche", "niche", "content_categories"),
        "game_titles": ("game_titles", "games", "games_covered"),
        "public_contact_url": ("public_contact_url", "contact_url", "website"),
        "public_contact_email": ("public_contact_email", "contact_email", "business_email"),
        "source_url": ("source_url", "profile_url", "url"),
        "data_provider": ("data_provider", "provider", "source_name"),
        "snapshot_date": ("snapshot_date", "captured_at", "date_collected"),
    }
    result = {}
    for target, names in aliases.items():
        result[target] = next((normalized[name] for name in names if name in normalized), None)
    return result


def _normalize_niches(raw_niches, raw_games):
    text = f"{raw_niches}; {raw_games}".lower()
    categories = []
    if "pc" in text and any(term in text for term in ("build", "custom", "hardware")):
        categories.append("PC builds")
    if any(term in text for term in ("hardware", "benchmark", "gpu", "computer")):
        categories.append("Hardware and benchmarks")
    if any(term in text for term in ("review", "test", "unboxing")):
        categories.append("Tech reviews")
    if any(term in text for term in ("gaming", "gameplay", "game")) or raw_games.strip():
        categories.append("Gaming")
    if any(term in text for term in ("setup", "sim racing", "desk")):
        categories.append("Gaming setups")
    categories.extend(f"Game: {game.strip()}" for game in raw_games.split(";") if game.strip())
    return list(dict.fromkeys(categories))


def load_provider_csv(uploaded_file, platform_name="TikTok"):
    """Validate and normalize short-form rows exported by an authorized data provider."""
    frame = pd.read_csv(uploaded_file)
    columns = _column_map(frame.columns)
    required = ("creator_name", "handle", "country", "follower_count", "content_niche")
    missing = [name for name in required if columns[name] is None]
    if columns["average_views_30d"] is None and columns["average_views_90d"] is None:
        missing.append("average_views_30d or average_views_90d")
    if missing:
        raise ValueError("Missing required CSV columns: " + ", ".join(missing))

    creators = []
    issues = []
    for index, row in frame.iterrows():
        row_number = index + 2
        try:
            followers = int(row[columns["follower_count"]])
            views_30d = _optional_number(row, columns["average_views_30d"])
            views_90d = _optional_number(row, columns["average_views_90d"])
            if followers < 0 or (views_30d is not None and views_30d < 0) or (views_90d is not None and views_90d < 0):
                raise ValueError("counts cannot be negative")
        except (TypeError, ValueError) as error:
            issues.append(f"Row {row_number}: invalid follower/view counts ({error}).")
            continue

        def value(field, default=""):
            column = columns[field]
            if column is None or pd.isna(row[column]):
                return default
            return str(row[column]).strip()

        creator_name = value("creator_name")
        handle = value("handle")
        country = value("country").upper()
        if not creator_name or not handle or not country:
            issues.append(f"Row {row_number}: creator name, handle, and country are required.")
            continue
        if country not in EU_COUNTRY_CODES:
            issues.append(f"Row {row_number}: excluded non-EU creator country {country}.")
            continue

        selected_window = 30 if views_30d is not None else 90
        selected_views = views_30d if views_30d is not None else views_90d
        raw_niches = value("content_niche")
        raw_games = value("game_titles")
        niches = _normalize_niches(raw_niches, raw_games)
        games = [item.strip() for item in raw_games.split(";") if item.strip()]
        
        profile_url = value("source_url")
        if not profile_url:
            domain = "instagram.com" if platform_name == "Instagram" else "tiktok.com"
            profile_url = f"https://www.{domain}/{handle if handle.startswith('@') else '@' + handle}"
            
        creators.append({
            "platform": platform_name,
            "name": creator_name,
            "handle": handle,
            "url": profile_url,
            "declared_country": country,
            "countries": [country],
            "subscribers": followers,
            "follower_count": followers,
            "avg_recent_video_views": selected_views,
            "median_recent_video_views": None,
            "view_window_days": selected_window,
            "view_window_video_count": _optional_number(
                row,
                columns["video_count_30d"] if selected_window == 30 else columns["video_count_90d"],
            ),
            "avg_views_30d": views_30d,
            "avg_views_90d": views_90d,
            "recent_video_engagement_rate": _optional_number(row, columns["engagement_rate_pct"]),
            "content_categories": niches,
            "game_titles": games,
            "public_contact_url": value("public_contact_url") or None,
            "public_contact_email": value("public_contact_email") or None,
            "risk_flags": [],
            "trend_status": "Trend unavailable from a single provider snapshot",
            "provider_snapshot_date": value("snapshot_date") or None,
            "provider_source_url": profile_url,
            "data_provider": value("data_provider") or "Licensed provider CSV",
            "recent_videos": [],
            "description": "",
            "channel_total_views": None,
            "channel_video_count": None,
            "avg_views_to_subscribers_pct": round(100 * selected_views / followers, 2) if followers and selected_views is not None else None,
            "pc_build_match": any("pc" in niche.lower() or "hardware" in niche.lower() for niche in niches),
            "gaming_match": any("gaming" in niche.lower() or games for niche in niches),
        })

    return creators, issues


def _optional_number(row, column):
    if column is None or pd.isna(row[column]) or str(row[column]).strip() == "":
        return None
    return float(row[column])
