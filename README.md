# Prenew Creator Scout

A Streamlit creator-discovery prototype for YouTube and TikTok provider exports. It ranks creators by content fit and Prenew's collaboration ranges and exports CRM-ready CSV. Outreach remains optional and human-reviewed.

## Run locally

In PowerShell, from this folder:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install streamlit pandas google-api-python-client google-genai
streamlit run app.py
```

When the saved EU snapshot CSV is present, it is the default source, so the extracted creator list opens without another API call. Choose **YouTube API discovery** to refresh one market or **All EU markets (27)**; turn off **Use demo data** and enter a YouTube Data API key in its password field. Discovery does not hard-filter subscriber counts: all sizes remain available, while YouTube creators in the 50k–250k subscriber / 20k–100k average-view target are ranked first. Audience-size controls can show core, emerging, or large creators.

YouTube profiles are enriched from each channel's uploads playlist (up to 50 recent public uploads). The app uses a 30-day upload cohort when there are at least three uploads in that period; otherwise it uses 90 days. It reports average and median current views of videos published in the cohort, sample size, engagement, upload frequency/recency, identified games, and video evidence. These are current lifetime views for videos published in the window, not views gained during the window.

Creators with a declared country outside the EU-27 are excluded. Creator-declared country is shown separately from the EU markets where search surfaced the channel; when the country is unavailable, the profile is retained based on EU-market discovery. Public email/contact URLs are extracted only when present in the channel description. Niche confidence and risk flags are based on observed upload patterns; the app does not infer viewer age or demographics.

For TikTok, select **TikTok licensed-provider CSV** and upload an export from a commercial data source authorized for marketing use. The app provides a CSV template. TikTok's Research API is restricted to approved non-commercial research, while Display API requires creator authorization and is not general discovery. The import requires creator name, handle, country, follower count, niche, and a 30- or 90-day average-view field. Game titles, engagement, post count, public contact email/URL, provider name, source URL, and snapshot date are optional.

Gemini is optional; local fit scoring uses observed topics and views-to-followers ratio.

## Metric semantics

The app stores YouTube channel and per-video public counters in `creator_metrics.sqlite3`. Observed monthly growth appears only after another snapshot at least seven days later. Yearly views are a run-rate estimate, not a forecast; first-run historical growth is unavailable. Do not compare snapshots across YouTube's August 24, 2026 view-count definition change.

YouTube API public counts do not include competitors' channel Analytics or audience demographics. A channel's optional country is self-associated and is not proof of residence or viewer geography. TikTok discovery requires a licensed provider or creator-authorized data flow; the app does not call TikTok's Research API.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s . -p "test_*.py" -v
```
