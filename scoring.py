import json

GEMINI_MODEL = "gemini-3.8-flash"

def _local_analysis(creator_data, language):
    recent_videos = creator_data.get("recent_videos", [])
    content_categories = creator_data.get("content_categories", [])
    name = creator_data.get("name", "Unknown")
    subs = creator_data.get("subscribers") or 0
    
    # 1. Content Match (Max 40 points)
    weights = {
        "PC builds": 40,
        "Hardware and benchmarks": 35,
        "Tech reviews": 25,
        "Gaming setups": 20,
        "Gaming": 10,
        "Streaming": 5,
    }
    content_score = min(40, sum(weights.get(category, 0) for category in content_categories))
    
    # 2. View Performance (Max 30 points) - STRICTER REQUIREMENTS
    avg_views = creator_data.get("avg_recent_video_views") or 0
    if avg_views > 100000:
        view_score = 30
    elif avg_views > 50000:
        view_score = 22
    elif avg_views > 10000:
        view_score = 12
    elif avg_views > 5000:
        view_score = 5
    else:
        view_score = 0
        
    # 3. Consistency & Cadence (Max 15 points)
    uploads_30d = creator_data.get("recent_30d_uploads") or 0
    if uploads_30d >= 4:
        cadence_score = 15
    elif uploads_30d == 3:
        cadence_score = 10
    elif uploads_30d == 2:
        cadence_score = 5
    elif uploads_30d == 1:
        cadence_score = 2
    else:
        cadence_score = 0
        
    # 4. Engagement / View-to-Sub (Max 15 points)
    v2s = creator_data.get("avg_views_to_subscribers_pct") or 0
    if v2s >= 15:
        eng_score = 15
    elif v2s >= 8:
        eng_score = 10
    elif v2s >= 3:
        eng_score = 5
    else:
        eng_score = 0

    raw_score = content_score + view_score + cadence_score + eng_score
    
    # HARSH PENALTY for inactive channels (no recent uploads)
    if uploads_30d == 0:
        raw_score = int(raw_score * 0.2) # Slashes score by 80%

    # STRICT SUBSCRIBER TIER CAPS (Absolute maximums)
    if subs < 500:
        max_allowed = 9
    elif subs < 5000:
        max_allowed = 21
    elif subs < 50000:
        max_allowed = 48
    elif subs < 250000:
        max_allowed = 72
    else:
        max_allowed = 92
        
    score = min(raw_score, max_allowed)
    
    # ORGANIC JITTER: Add/subtract slightly to avoid round numbers (e.g. 42, 68, 89)
    jitter = (len(name) % 9) - 4
    score = score + jitter
    
    # Re-enforce absolute bounds after the jitter is applied
    if score > max_allowed: 
        score = max_allowed
    if score < 1: 
        score = 1

    video_topics = list(dict.fromkeys(
        category
        for video in recent_videos
        for category in video.get("content_categories", [])
    ))
    evidence = ", ".join(video_topics or content_categories) if video_topics or content_categories else "no clear PC/gaming topic evidence"
    
    reasoning = f"Strict Grade: {score}/92. Cap enforced: {max_allowed} (Subs: {subs:,}). Breakdown: Content ({content_score}), Views ({view_score}), Cadence ({cadence_score}), Eng ({eng_score})."

    # C2B / Trade-in angle in pitches
    pitches = {
        "de": f"Hallo {name},\n\nich verfolge eure Inhalte rund um {evidence} schon eine Weile und finde sie wirklich spannend. Ich melde mich im Namen von Prenew - wir sind eine europäische Plattform für generalüberholte Gaming-PCs mit Garantie, und wir kaufen auch gebrauchte Setups an.\n\nDa Hardware und Gaming genau euer Thema ist, wollten wir fragen, ob ihr offen für eine Zusammenarbeit wärt? Entweder um eines unserer Systeme zu testen, oder um eurer Community zu zeigen, wie einfach man sein altes Setup bei einem Upgrade zu Geld machen kann.\n\nBeste Grüße,\nDas Prenew-Team",
        "en": f"Hi {name},\n\nI've been following your recent content, especially around {evidence}, and wanted to reach out. I'm with Prenew—we're a European platform that buys used gaming PCs, refurbishes them, and sells them with a full warranty.\n\nWe’re looking for creators who really understand hardware and gaming to test our rigs or show their community how easy it is to trade in their old setups for cash. Would you be open to discussing a potential partnership?\n\nBest,\nThe Prenew Team",
        "fi": f"Hei {name},\n\nOlen seurannut sisältöänne ({evidence}) ja halusin olla yhteydessä. Edustan Prenewiä – eurooppalaista alustaa, joka ostaa käytettyjä pelitietokoneita, kunnostaa ne ja myy täydellä takuulla.\n\nEtsimme tekijöitä, jotka todella ymmärtävät laitteiston päälle, testaamaan koneitamme tai näyttämään yhteisölleen, kuinka helppoa vanhojen laitteiden vaihtaminen rahaksi on. Olisitteko avoimia keskustelemaan mahdollisesta yhteistyöstä?\n\nYstävällisin terveisin,\nPrenew-tiimi",
    }
    return {
        "brand_fit_score": round(score),
        "reasoning": reasoning,
        "outreach_pitch": pitches.get(language, pitches["en"]),
    }

def score_and_draft_pitch(gemini_api_key, creator_data, language="de"):
    """Score a creator and draft a localized pitch; fall back to local analysis."""
    fallback = _local_analysis(creator_data, language)
    if not gemini_api_key:
        return fallback

    language_names = {
        "bg": "Bulgarian", "fi": "Finnish", "en": "English", "de": "German", 
        "sv": "Swedish", "nl": "Dutch", "fr": "French", "pl": "Polish", "es": "Spanish"
    }
    
    requested_language = language_names.get(language, "English")
    recent_video_titles = [video.get("title", "") for video in creator_data.get("recent_videos", [])]
    
    prompt = f"""
    You are the strictly analytical Head of Marketing for Prenew, a European marketplace for refurbished gaming PCs. We buy used gaming PCs, refurbish them, and sell them cheaper than retail with a warranty.
    Evaluate this creator based on their public videos, channel metadata, and performance metrics. You are a ruthless data-driven marketing manager.
    
    Creator Name: {creator_data['name']}
    Subscribers: {creator_data.get('subscribers', '0')}
    Average Recent Views: {creator_data.get('avg_recent_video_views', '0')}
    Uploads (30d): {creator_data.get('recent_30d_uploads', '0')}
    Description: {creator_data.get('description', 'N/A')}
    Content categories detected: {creator_data.get('content_categories', [])}
    Recent video titles: {recent_video_titles}
    
    Task:
    1. Score this creator from 1 to 92 using a strict subscriber-tiered rubric. You MUST enforce these absolute maximum caps based on their subscriber count:
       - Under 500 subs: MAXIMUM score is 9.
       - 500 to 5,000 subs: MAXIMUM score is 21.
       - 5,000 to 50k subs: MAXIMUM score is 48.
       - 50k to 250k subs: MAXIMUM score is 72.
       - Over 250k subs: MAXIMUM score is 92 (Absolute limit, never 100).
       - INACTIVE channels (0 recent uploads) must have their score slashed by 80%.
       - Generate an organic, realistic number (e.g. 24, 37, 42, 68) rather than round multiples of 10.
    2. Provide a 2-3 sentence strict, analytical reasoning for your exact score breakdown. Do NOT infer viewer age. State the tier cap explicitly.
    3. Write a highly professional, authentic, and personalized outreach email in fluent {requested_language} proposing a partnership. Avoid marketing buzzwords. Use line breaks for paragraphs. MUST mention we both SELL refurbished PCs and BUY old PCs. Ask if they want to test a rig or show their audience how to sell their old setup. Sign off with "The Prenew Team" and include "prenew.com".
    
    Return ONLY a JSON object with keys: "brand_fit_score", "reasoning", "outreach_pitch".
    """
    
    try:
        from google import genai
        client = genai.Client(api_key=gemini_api_key)
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )
        text = response.text.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:].strip()
        result = json.loads(text)
        result["brand_fit_score"] = max(1, min(92, int(result["brand_fit_score"])))
        result.setdefault("reasoning", fallback["reasoning"])
        result.setdefault("outreach_pitch", fallback["outreach_pitch"])
        return result
    except Exception:
        fallback["reasoning"] += " (Gemini was unavailable, so the local estimate is shown.)"
        return fallback

def generate_gemini_recommendation(gemini_api_key, creator_data):
    """Generate one evidence-grounded collaboration recommendation for a selected creator."""
    recent_videos = [
        {
            "title": video.get("title"),
            "published_at": video.get("published_at"),
            "views": video.get("views"),
            "likes": video.get("likes"),
            "comments": video.get("comments"),
            "topics": video.get("content_categories", []),
        }
        for video in creator_data.get("recent_videos", [])[:12]
    ]
    prompt = f"""
You are Prenew's influencer research analyst. Recommend whether and how to approach this creator for a refurbished gaming-PC collaboration.
Use only the evidence below. Separate observed facts from hypotheses, do not infer audience age/demographics, and do not invent contacts or claim to have viewed unavailable analytics.

Creator evidence (JSON):
{json.dumps({**creator_data, 'recent_videos': recent_videos}, ensure_ascii=False, default=str)}

Return concise Markdown with these headings:
1. Recommendation: strong fit / test / low priority, with a one-sentence reason.
2. Evidence: niche, games, view cohort/window and sample size, views/follower ratio, engagement, upload cadence, and country provenance when present.
3. Suggested collaboration: one concrete test or content concept related to Prenew's buy-refurbish-sell model.
4. Risks and checks: list measured flags and missing data; label uncertainties explicitly.
5. Outreach angle: one short personalized hook, not a full message.
"""
    from google import genai
    client = genai.Client(api_key=gemini_api_key)
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
    )
    recommendation = (response.text or "").strip()
    if not recommendation:
        raise ValueError("Gemini returned an empty recommendation.")
    return recommendation