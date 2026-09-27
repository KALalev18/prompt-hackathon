import re
from datetime import datetime, timezone
from statistics import median
from googleapiclient.discovery import build

EU_MARKETS = {
    "Austria": ("AT", "de", "Gaming PC bauen PC Build"),
    "Belgium": ("BE", "nl", "gaming pc bouwen pc build"),
    "Bulgaria": ("BG", "bg", "геймърски компютър сглобяване"),
    "Croatia": ("HR", "hr", "gaming PC slaganje"),
    "Cyprus": ("CY", "el", "gaming PC συναρμολόγηση"),
    "Czechia": ("CZ", "cs", "herní PC sestava gaming"),
    "Denmark": ("DK", "da", "gaming PC byg computer"),
    "Estonia": ("EE", "et", "gaming PC ehitamine"),
    "Finland": ("FI", "fi", "pelitietokoneen kasaus"),
    "France": ("FR", "fr", "montage PC gamer"),
    "Germany": ("DE", "de", "Gaming PC bauen"),
    "Greece": ("GR", "el", "gaming PC συναρμολόγηση"),
    "Hungary": ("HU", "hu", "gaming PC építés"),
    "Ireland": ("IE", "en", "gaming PC build"),
    "Italy": ("IT", "it", "assemblare PC gaming"),
    "Latvia": ("LV", "lv", "gaming PC dators"),
    "Lithuania": ("LT", "lt", "žaidimų kompiuteris gaming PC"),
    "Luxembourg": ("LU", "fr", "montage PC gamer"),
    "Malta": ("MT", "en", "gaming PC build"),
    "Netherlands": ("NL", "nl", "gaming PC bouwen"),
    "Poland": ("PL", "pl", "składanie PC gamingowego"),
    "Portugal": ("PT", "pt", "montagem PC gaming"),
    "Romania": ("RO", "ro", "asamblare PC gaming"),
    "Slovakia": ("SK", "sk", "zostava herného PC"),
    "Slovenia": ("SI", "sl", "gaming PC sestava"),
    "Spain": ("ES", "es", "montaje PC gaming"),
    "Sweden": ("SE", "sv", "bygga gaming PC"),
}
EU_COUNTRY_CODES = {market[0] for market in EU_MARKETS.values()}

NICHE_KEYWORDS = {
    "Hardware and benchmarks": ("hardware", "benchmark", "gpu", "graphics card", "grafikkarte", "rtx", "radeon", "cpu", "processor", "prozessor", "motherboard", "mainboard", "ram", "ssd", "placa gráfica", "scheda grafica", "karta graficzna", "grafická karta", "gráfica"),
    "Gaming setups": ("gaming setup", "setup tour", "desk setup", "gaming room", "sim racing", "simracing", "spielzimmer", "setup gaming", "escritorio gamer", "setup gamer"),
    "Tech reviews": ("review", "reviews", "test", "unboxing", "kaufberatung", "vergleich", "recensione", "recensioni", "avis", "reseña", "reseñas", "análisis", "análise", "anmeldelse", "recenzja", "recenzje", "testbericht", "laitetesti"),
    "Streaming": ("streaming", "streamer", "twitch", "obs studio"),
}

GAME_KEYWORDS = {
    "Apex Legends": ("apex legends",),
    "Brawl Stars": ("brawl stars",),
    "Call of Duty": ("call of duty", "warzone"),
    "Counter-Strike 2": ("counter-strike 2", "counter strike 2", "cs2"),
    "Dota 2": ("dota 2",),
    "Fortnite": ("fortnite",),
    "GTA V": ("gta v", "gta 5", "grand theft auto"),
    "League of Legends": ("league of legends", "lol gameplay"),
    "Minecraft": ("minecraft",),
    "Overwatch 2": ("overwatch 2",),
    "PUBG": ("pubg", "playerunknown's battlegrounds"),
    "Roblox": ("roblox",),
    "Rocket League": ("rocket league",),
    "The Sims 4": ("the sims 4", "sims 4"),
    "Valorant": ("valorant",),
}

PC_BUILD_TERMS = (
    "pc build", "pc-build", "build a pc", "building a pc", "pc bauen",
    "pc zusammenbau", "computer build", "gaming pc build", "gaming pc bauen",
    "montage pc", "montage pc gamer", "montagem pc", "assemblare pc", "składanie pc",
    "składanie pc gamingowego", "pc kasaus", "pelitietokoneen kasaus", "gaming pc ehitamine",
    "herní pc sestava", "herny pc sestava", "zostava herného pc", "zostava herneho pc",
    "gaming pc építés", "asamblare pc gaming", "asamblare calculator", "gaming pc slaganje",
    "геймърски компютър", "сглобяване на компютър", "gaming pc bouwen", "bygge gaming pc",
    "gaming pc sestava", "montagem de pc gamer", "montaje pc gaming", "ensamblaje pc gaming",
    "bygg gaming pc", "gaming computer bouwen", "komputer gamingowy",
)
PC_HARDWARE_TERMS = (
    "pc", "desktop", "computer", "gpu", "graphics card", "grafikkarte", "rtx",
    "radeon", "cpu", "ryzen", "intel core", "motherboard", "mainboard", "ram", "ssd",
)
TOY_OR_BRICK_TERMS = ("lego", "duplo", "brickfilm", "toy", "spielzeug")


def _video_categories(title, description=""):
    text = f"{title} {description}".lower()
    categories = [
        category
        for category, keywords in NICHE_KEYWORDS.items()
        if any(keyword in text for keyword in keywords)
    ]
    game_names = [
        game
        for game, keywords in GAME_KEYWORDS.items()
        if any(keyword in text for keyword in keywords)
    ]
    has_pc_hardware = any(term in text for term in PC_HARDWARE_TERMS)
    has_build_phrase = any(term in text for term in PC_BUILD_TERMS)
    toy_context = any(term in text for term in TOY_OR_BRICK_TERMS)
    has_pc_parts = any(term in text for term in ("rtx", "radeon", "ryzen", "cpu", "gpu", "motherboard", "mainboard", "ram", "ssd"))

    if has_build_phrase and has_pc_hardware and (not toy_context or has_pc_parts):
        categories.append("PC builds")
    gaming_terms = (
        "gaming", "gameplay", "gamer", "videojuego", "videojuegos", "videogioco",
        "videogiochi", "jogo", "jogos", "jeux vidéo", "jeux video", "videospiel",
        "videospiele", "herní", "hry", "игри", "геймър", "pelaaminen", "pelitietokone",
        "spel", "spil", "žaidimų", "žaidimas", "žaidimai", "gry komputerowe", "jocuri",
    )
    if any(term in text for term in gaming_terms) or game_names or (has_pc_hardware and has_build_phrase):
        categories.append("Gaming")
    categories.extend(f"Game: {game}" for game in game_names)
    return list(dict.fromkeys(categories))


def _extract_public_contact(description):
    email_matches = re.findall(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", description, flags=re.IGNORECASE)
    url_matches = re.findall(r"https?://[^\s<>\])]+", description, flags=re.IGNORECASE)
    return {
        "public_contact_email": email_matches[0].rstrip(".,;") if email_matches else None,
        "public_contact_url": url_matches[0].rstrip(".,;") if url_matches else None,
    }


def _refresh_video_metrics(creator):
    videos = creator.get("recent_videos", [])
    now = datetime.now(timezone.utc)
    dated_videos = []
    for video in videos:
        published_at = video.get("published_at")
        if not published_at:
            continue
        try:
            published_date = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        except ValueError:
            continue
        video["age_days"] = max(0, (now - published_date).total_seconds() / 86400)
        video["content_categories"] = _video_categories(video.get("title", ""), video.get("description", ""))
        dated_videos.append(video)

    uploads_30d = [video for video in dated_videos if video["age_days"] <= 30]
    uploads_90d = [video for video in dated_videos if video["age_days"] <= 90]
    uploads_91_180d = [video for video in dated_videos if 90 < video["age_days"] <= 180]
    uploads_181_270d = [video for video in dated_videos if 180 < video["age_days"] <= 270]
    
    window_days = 30 if len(uploads_30d) >= 3 else 90
    cohort = uploads_30d if window_days == 30 else uploads_90d
    measured_videos = [video for video in cohort if video.get("views", 0) >= 0]
    total_views = sum(video["views"] for video in measured_videos)
    cohort_views = [video["views"] for video in measured_videos]
    creator["view_window_days"] = window_days
    creator["view_window_video_count"] = len(measured_videos)
    creator["avg_recent_video_views"] = round(total_views / len(measured_videos), 1) if measured_videos else None
    creator["median_recent_video_views"] = median(cohort_views) if cohort_views else None
    creator["avg_recent_video_likes"] = round(
        sum(video.get("likes", 0) for video in measured_videos) / len(measured_videos), 1
    ) if measured_videos else None
    creator["avg_recent_video_comments"] = round(
        sum(video.get("comments", 0) for video in measured_videos) / len(measured_videos), 1
    ) if measured_videos else None
    creator["recent_video_engagement_rate"] = round(
        100 * sum(video.get("likes", 0) + video.get("comments", 0) for video in measured_videos) / total_views,
        2,
    ) if total_views else None

    # Historical 3, 6, 9-month stats
    def _avg(vids):
        measured = [v for v in vids if v.get("views", 0) >= 0]
        return round(sum(v["views"] for v in measured) / len(measured), 1) if measured else 0

    creator["uploads_3m"] = len(uploads_90d)
    creator["uploads_6m"] = len(uploads_91_180d)
    creator["uploads_9m"] = len(uploads_181_270d)
    creator["avg_views_3m"] = _avg(uploads_90d)
    creator["avg_views_6m"] = _avg(uploads_91_180d)
    creator["avg_views_9m"] = _avg(uploads_181_270d)

    # Commercial saturation and gambling detection
    sponsor_terms = ("sponsor", "sponsored", "ad ", "advertisement", "werbung", "anzeige", "promo code", "discount code")
    gambling_terms = ("cs2 cases", "case opening", "betting", "csgo roll", "csgoroll", "casino", "gamble", "lootbox")
    
    sponsored_count = 0
    has_gambling = False
    
    for video in measured_videos:
        text = f"{video.get('title', '')} {video.get('description', '')}".lower()
        if any(term in text for term in sponsor_terms):
            sponsored_count += 1
        if any(term in text for term in gambling_terms):
            has_gambling = True
            
    creator["commercial_saturation"] = f"{sponsored_count} in {len(measured_videos)} sponsored" if measured_videos else "Unknown"

    subscriber_count = creator.get("subscribers")
    creator["avg_views_to_subscribers_pct"] = round(100 * creator["avg_recent_video_views"] / subscriber_count, 2) if creator["avg_recent_video_views"] is not None and subscriber_count else None
    creator["recent_30d_uploads"] = len(uploads_30d)
    creator["recent_90d_uploads"] = len(uploads_90d)
    creator["upload_frequency_per_month_90d"] = round(len(uploads_90d) / 3, 2)
    creator["last_upload_days"] = min((video["age_days"] for video in dated_videos), default=None)

    category_counts = {}
    for video in dated_videos:
        for category in video.get("content_categories", []):
            category_counts[category] = category_counts.get(category, 0) + 1
    creator["content_categories"] = [
        category for category, _ in sorted(category_counts.items(), key=lambda item: (-item[1], item[0]))
    ]
    creator["niche_match_ratio_pct"] = round(
        100 * sum(bool(video.get("content_categories")) for video in dated_videos) / len(dated_videos), 1
    ) if dated_videos else 0
    creator["view_concentration_top_video_pct"] = round(
        100 * max((video.get("views", 0) for video in measured_videos), default=0) / total_views, 1
    ) if total_views else None

    risk_flags = []
    if has_gambling:
        risk_flags.append("High-risk: Gambling or CS2 case opening promotions detected")
    if creator["last_upload_days"] is not None and creator["last_upload_days"] > 90:
        risk_flags.append("No public upload in the last 90 days")
    if len(dated_videos) >= 5 and creator["niche_match_ratio_pct"] < 20:
        risk_flags.append("Few recent uploads show a clear PC/gaming niche")
    if creator["view_concentration_top_video_pct"] is not None and creator["view_concentration_top_video_pct"] >= 70:
        risk_flags.append("Recent views are concentrated in one video")
    creator["risk_flags"] = risk_flags
    creator["trend_status"] = "Awaiting repeat snapshots"


def _discover_youtube_creators(youtube, keyword, region_code, language, country_name=None):
    search_response = youtube.search().list(
        q=keyword,
        type="video",
        part="id,snippet",
        maxResults=35,
        regionCode=region_code,
        relevanceLanguage=language,
        order="date",
    ).execute()

    videos_by_channel = {}
    for item in search_response.get("items", []):
        snippet = item.get("snippet", {})
        channel_id = snippet.get("channelId")
        video_id = item.get("id", {}).get("videoId")
        if not channel_id or not video_id:
            continue
        videos_by_channel.setdefault(channel_id, []).append({
            "video_id": video_id,
            "title": snippet.get("title", "Untitled video"),
            "description": snippet.get("description", ""),
            "published_at": snippet.get("publishedAt"),
            "url": f"https://www.youtube.com/watch?v={video_id}",
        })

    channel_ids = list(videos_by_channel)
    if not channel_ids:
        return []

    channels_response = youtube.channels().list(
        part="statistics,snippet,contentDetails",
        id=",".join(channel_ids),
    ).execute()

    candidates = []
    for channel in channels_response.get("items", []):
        snippet = channel.get("snippet", {})
        declared_country = snippet.get("country")
        if declared_country and declared_country not in EU_COUNTRY_CODES:
            continue
        statistics = channel.get("statistics", {})
        subscriber_count = int(statistics.get("subscriberCount", 0)) if statistics.get("subscriberCount") else None
        custom_url = snippet.get("customUrl")
        channel_url = f"https://www.youtube.com/{custom_url}" if custom_url else f"https://youtube.com/channel/{channel['id']}"
        public_contact = _extract_public_contact(snippet.get("description", ""))
        seed_videos = videos_by_channel.get(channel["id"], [])
        
        candidates.append({
            "channel_id": channel["id"],
            "name": snippet.get("title", "Unknown channel"),
            "description": snippet.get("description", ""),
            "profile_image_url": snippet.get("thumbnails", {}).get("default", {}).get("url"),
            "subscribers": subscriber_count,
            "subscriber_count_hidden": bool(statistics.get("hiddenSubscriberCount", False)),
            "channel_total_views": int(statistics.get("viewCount", 0)),
            "channel_video_count": int(statistics.get("videoCount", 0)),
            "declared_country": declared_country,
            "uploads_playlist_id": channel.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads"),
            "public_contact_email": public_contact["public_contact_email"],
            "public_contact_url": public_contact["public_contact_url"],
            "url": channel_url,
            "recent_videos": [],
            "search_evidence_videos": seed_videos,
            "content_categories": [],
            "countries": [country_name] if country_name else [],
            "search_terms": [keyword],
        })

    return candidates


def _enrich_from_uploads(youtube, creators, progress_callback=None):
    all_video_ids = set()
    total_creators = max(1, len(creators))
    for index, creator in enumerate(creators, start=1):
        uploads_playlist_id = creator.get("uploads_playlist_id")
        videos = []
        
        if uploads_playlist_id:
            try:
                response = youtube.playlistItems().list(
                    part="snippet,contentDetails",
                    playlistId=uploads_playlist_id,
                    maxResults=200,
                ).execute()
                for item in response.get("items", []):
                    snippet = item.get("snippet", {})
                    video_id = item.get("contentDetails", {}).get("videoId")
                    if not video_id:
                        continue
                    videos.append({
                        "video_id": video_id,
                        "title": snippet.get("title", "Untitled video"),
                        "description": snippet.get("description", ""),
                        "published_at": item.get("contentDetails", {}).get("videoPublishedAt") or snippet.get("publishedAt"),
                        "url": f"https://www.youtube.com/watch?v={video_id}",
                    })
            except Exception:
                videos = []
        if not videos:
            videos = creator.pop("search_evidence_videos", [])
        else:
            creator.pop("search_evidence_videos", None)
        creator["recent_videos"] = videos
        all_video_ids.update(video["video_id"] for video in videos)
        if progress_callback and (index % 10 == 0 or index == len(creators)):
            progress_callback(index, total_creators, "Enriching creators")

    video_details = {}
    video_ids = list(all_video_ids)
    for start in range(0, len(video_ids), 50):
        response = youtube.videos().list(
            part="statistics,snippet",
            id=",".join(video_ids[start:start + 50]),
        ).execute()
        video_details.update({video["id"]: video for video in response.get("items", [])})

    now = datetime.now(timezone.utc)
    for creator in creators:
        videos = []
        for item in creator.get("recent_videos", []):
            detail = video_details.get(item["video_id"], {})
            statistics = detail.get("statistics", {})
            published_at = detail.get("snippet", {}).get("publishedAt") or item.get("published_at")
            age_months = None
            if published_at:
                try:
                    published_date = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
                    age_months = max(1 / 30, (now - published_date).total_seconds() / (86400 * 30.4375))
                except ValueError:
                    pass
            videos.append({
                **item,
                "published_at": published_at,
                "views": int(statistics.get("viewCount", 0)),
                "likes": int(statistics.get("likeCount", 0)),
                "comments": int(statistics.get("commentCount", 0)),
                "lifetime_views_per_month": round(int(statistics.get("viewCount", 0)) / age_months, 1) if age_months else None,
            })
        creator["recent_videos"] = videos
        creator["search_evidence_videos"] = None
        _refresh_video_metrics(creator)
    return creators


def get_youtube_creators(api_key, keyword="gaming pc setup", region_code="DE", language="de", country_name=None):
    """Find relevant YouTube channels in one market."""
    youtube = build("youtube", "v3", developerKey=api_key)
    creators = _discover_youtube_creators(youtube, keyword, region_code, language, country_name)
    return _enrich_from_uploads(youtube, creators)


def get_youtube_creators_across_eu(api_key, progress_callback=None, markets=None, additional_keyword=""):
    """Search EU markets and merge duplicate channels, keeping their source markets."""
    youtube = build("youtube", "v3", developerKey=api_key)
    markets = markets or EU_MARKETS
    merged = {}
    errors = []

    for index, (country, (region_code, language, keyword)) in enumerate(markets.items(), start=1):
        try:
            creators = _discover_youtube_creators(
                youtube,
                f"{keyword} {additional_keyword}".strip(),
                region_code,
                language,
                country_name=country,
            )
        except Exception as error:
            status = getattr(getattr(error, "resp", None), "status", None)
            errors.append(f"{country}: HTTP {status}" if status else f"{country}: {type(error).__name__}")
            if status in (401, 403, 429):
                break
            creators = []

        for creator in creators:
            channel_id = creator["channel_id"]
            if channel_id not in merged:
                merged[channel_id] = creator
                continue

            existing = merged[channel_id]
            existing["countries"] = list(dict.fromkeys(existing["countries"] + creator["countries"]))
            existing["search_terms"] = list(dict.fromkeys(existing["search_terms"] + creator["search_terms"]))
            existing["content_categories"] = list(dict.fromkeys(
                existing["content_categories"] + creator["content_categories"]
            ))
            known_video_urls = {video["url"] for video in existing["recent_videos"]}
            existing["recent_videos"].extend(
                video for video in creator["recent_videos"]
                if video["url"] not in known_video_urls
            )
            existing["recent_videos"] = existing["recent_videos"][:5]

        if progress_callback:
            progress_callback(index, len(markets), country)

        if errors and errors[-1].startswith(country + ":") and errors[-1].endswith(("HTTP 401", "HTTP 403", "HTTP 429")):
            break

    if progress_callback:
        progress_callback(len(markets), len(markets), "Loading recent uploads and metrics")
    creators = _enrich_from_uploads(youtube, list(merged.values()), progress_callback=progress_callback)
    return creators, errors


def get_fallback_creators():
    """Return clearly labeled sample data for a no-credentials demo."""
    return [
        {
            "name": "Demo: BerlinerTechZocker",
            "description": "PC Builds, Benchmarks und Hardware Reviews. Valorant & CS:GO.",
            "profile_image_url": "https://www.gravatar.com/avatar/00000000000000000000000000000000?d=mp&f=y",
            "subscribers": 12500,
            "channel_total_views": None,
            "channel_video_count": None,
            "avg_recent_video_views": None,
            "avg_recent_video_likes": None,
            "avg_recent_video_comments": None,
            "recent_video_engagement_rate": None,
            "recent_30d_uploads": None,
            "upload_frequency_per_month_90d": None,
            "observed_monthly_view_growth": None,
            "uploads_3m": 12,
            "uploads_6m": 8,
            "uploads_9m": 15,
            "avg_views_3m": 25000,
            "avg_views_6m": 22000,
            "avg_views_9m": 18000,
            "url": "https://youtube.com/",
            "content_categories": ["PC builds", "Hardware and benchmarks", "Gaming"],
            "recent_videos": [],
        },
        {
            "name": "Demo: SimRacing DE",
            "description": "Alles rund um Sim Racing und Setup-Optimierung.",
            "profile_image_url": "https://www.gravatar.com/avatar/00000000000000000000000000000000?d=mp&f=y",
            "subscribers": 34000,
            "channel_total_views": None,
            "channel_video_count": None,
            "avg_recent_video_views": None,
            "avg_recent_video_likes": None,
            "avg_recent_video_comments": None,
            "recent_video_engagement_rate": None,
            "recent_30d_uploads": None,
            "upload_frequency_per_month_90d": None,
            "observed_monthly_view_growth": None,
            "uploads_3m": 5,
            "uploads_6m": 6,
            "uploads_9m": 4,
            "avg_views_3m": 15000,
            "avg_views_6m": 18000,
            "avg_views_9m": 12000,
            "url": "https://youtube.com/",
            "content_categories": ["Gaming setups", "Gaming"],
            "recent_videos": [],
        },
    ]