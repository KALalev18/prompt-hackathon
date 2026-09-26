import json

GEMINI_MODEL = "gemini-3.8-flash"

def _local_analysis(creator_data, language):
    recent_videos = creator_data.get("recent_videos", [])
    content_categories = creator_data.get("content_categories", [])
    weights = {
        "PC builds": 35,
        "Hardware and benchmarks": 28,
        "Tech reviews": 18,
        "Gaming": 12,
        "Gaming setups": 10,
        "Streaming": 5,
    }
    score = min(100, 20 + sum(weights.get(category, 0) for category in content_categories))
    if creator_data.get("avg_views_to_subscribers_pct") is not None:
        score = min(100, score + min(10, max(0, creator_data["avg_views_to_subscribers_pct"] / 10)))

    video_topics = list(dict.fromkeys(
        category
        for video in recent_videos
        for category in video.get("content_categories", [])
    ))
    evidence = ", ".join(video_topics or content_categories) if video_topics or content_categories else "no clear PC/gaming topic evidence"
    name = creator_data.get("name", "")
    
    # C2B / Trade-in angle in pitches
    pitches = {
        "de": f"Hallo liebes Team von {name}, eure Inhalte zu {evidence} passen gut zu Prenew. Wir verkaufen gepruefte, refurbished Gaming-PCs mit Garantie und kaufen auch gebrauchte Setups an. Haettet ihr Interesse, einen PC zu testen oder eurer Community zu zeigen, wie einfach sie ihr altes Setup an uns verkaufen koennen?",
        "en": f"Hello {name} team, your content about {evidence} looks highly relevant to Prenew. We sell quality-checked refurbished gaming PCs and also buy used rigs for cash. Would you be interested in testing a PC, or showing your audience how easily they can sell their old setups to us when upgrading?",
        "fi": f"Hei {name} tiimi, sisältönne aiheesta {evidence} sopii hyvin Prenewille. Myymme tarkistettuja kunnostettuja pelitietokoneita ja ostamme myös käytettyjä koneita. Kiinnostaisiko teitä testata tietokonetta tai esitellä yleisöllenne, kuinka helposti he voivat myydä vanhan koneensa meille?",
    }
    return {
        "brand_fit_score": round(score),
        "reasoning": f"Evidence from recent public uploads: {evidence}. This estimates content fit, not audience age or demographics.",
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
    You are the Head of Marketing for Prenew, a European marketplace that operates like Swappie but for gaming PCs. We buy used gaming PCs from consumers for cash, refurbish them, and sell them cheaper than retail with a warranty.
    Evaluate this creator based on their public videos and available channel metadata. Do not infer viewer age or purchasing power from a game's title.
    
    Creator Name: {creator_data['name']}
    Subscribers: {creator_data['subscribers']}
    Description: {creator_data['description']}
    Content categories detected from public recent videos: {creator_data.get('content_categories', [])}
    Recent video titles: {recent_video_titles}
    
    Task:
    1. Score content fit from 1-100 using explicit PC builds, hardware, reviews, and gaming evidence. Discuss game titles as topics, not as evidence of audience age.
    2. Write a 3-sentence casual outreach message in fluent {requested_language} proposing a partnership. You MUST mention that we both SELL refurbished PCs and BUY old PCs for cash. Ask if they want to test a PC or show their audience how to sell their old rig for an upgrade.
    
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
        result["brand_fit_score"] = max(1, min(100, int(result["brand_fit_score"])))
        result.setdefault("reasoning", fallback["reasoning"])
        result.setdefault("outreach_pitch", fallback["outreach_pitch"])
        return result
    except Exception:
        fallback["reasoning"] += " Gemini was unavailable, so the local estimate is shown."
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