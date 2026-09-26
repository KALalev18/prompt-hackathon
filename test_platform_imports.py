import io
import json
import unittest

import pandas as pd
from platform_imports import load_saved_youtube_dataset, load_tiktok_provider_csv


class TikTokProviderImportTests(unittest.TestCase):
    def test_normalizes_provider_profile_and_core_metrics(self):
        csv_data = io.StringIO(
            "creator_name,handle,country,follower_count,average_views_30d,average_views_90d,video_count_30d,engagement_rate_pct,content_niche,game_titles,public_contact_email,public_contact_url,source_url,data_provider,snapshot_date\n"
            "Example Creator,@example,DE,12000,45000,,4,5.2,PC builds; gaming,Valorant,business@example.com,https://example.com/contact,https://example.com/profile,Test Vendor,2026-09-26\n"
        )
        creators, issues = load_tiktok_provider_csv(csv_data)

        self.assertEqual(issues, [])
        self.assertEqual(len(creators), 1)
        creator = creators[0]
        self.assertEqual(creator["platform"], "TikTok")
        self.assertEqual(creator["declared_country"], "DE")
        self.assertEqual(creator["follower_count"], 12000)
        self.assertEqual(creator["avg_recent_video_views"], 45000)
        self.assertEqual(creator["view_window_days"], 30)
        self.assertIn("PC builds", creator["content_categories"])
        self.assertIn("Game: Valorant", creator["content_categories"])
        self.assertEqual(creator["public_contact_url"], "https://example.com/contact")
        self.assertEqual(creator["public_contact_email"], "business@example.com")
        self.assertEqual(creator["data_provider"], "Test Vendor")

    def test_rejects_csv_without_required_metrics(self):
        csv_data = io.StringIO("creator_name,handle,country\nExample,@example,DE\n")
        with self.assertRaisesRegex(ValueError, "follower_count"):
            load_tiktok_provider_csv(csv_data)

    def test_excludes_non_eu_country_from_saved_youtube_extract(self):
        csv_data = io.StringIO(
            "creator_country_declared,markets_discovered,creator_name,channel_handle\n"
            "DE,Germany,EU Creator,https://youtube.com/@eucreator\n"
            "KR,Germany,Foreign Creator,https://youtube.com/@foreigncreator\n"
        )
        creators = load_saved_youtube_dataset(csv_data)
        self.assertEqual([creator["name"] for creator in creators], ["EU Creator"])

    def test_excludes_non_eu_country_from_tiktok_provider_csv(self):
        csv_data = io.StringIO(
            "creator_name,handle,country,follower_count,average_views_30d,content_niche\n"
            "EU Creator,@eucreator,DE,5000,10000,gaming\n"
            "Foreign Creator,@foreigncreator,KR,8000,20000,gaming\n"
        )
        creators, issues = load_tiktok_provider_csv(csv_data)
        self.assertEqual([creator["name"] for creator in creators], ["EU Creator"])
        self.assertTrue(any("non-EU creator country KR" in issue for issue in issues))

    def test_loads_saved_youtube_extract_into_filterable_creator_profile(self):
        csv_data = io.StringIO()
        pd.DataFrame([{
            "creator_country_declared": "DE",
            "markets_discovered": "Austria; Germany",
            "creator_name": "Sample Creator",
            "channel_handle": "https://youtube.com/@sample",
            "subscriber_count": 120000,
            "channel_total_views": 500000,
            "channel_video_count": 150,
            "average_video_views": 60000,
            "median_video_views": 55000,
            "view_cohort_days": 30,
            "view_cohort_video_count": 3,
            "average_views_to_subscribers_pct": 50,
            "average_likes": 800,
            "average_comments": 20,
            "engagement_rate_pct": 1.36,
            "uploads_last_30_days": 3,
            "uploads_last_90_days": 8,
            "last_upload_age_days": 4,
            "pc_build_match": True,
            "gaming_match": True,
            "content_niches": "PC builds; Gaming; Game: Valorant",
            "game_titles": "Valorant",
            "niche_evidence_ratio_pct": 80,
            "risk_review_flags": "",
            "trend_status": "Awaiting repeat snapshots",
            "public_contact_email": "creator@example.com",
            "public_contact_url": "https://creator.example",
            "channel_description": "PC builds",
            "recent_video_metrics_json": json.dumps([{
                "title": "Recent PC build",
                "url": "https://youtube.com/watch?v=abc",
                "views": 60000,
                "likes": 800,
                "comments": 20,
            }]),
        }]).to_csv(csv_data, index=False)
        csv_data.seek(0)
        creators = load_saved_youtube_dataset(csv_data)

        self.assertEqual(len(creators), 1)
        self.assertEqual(creators[0]["platform"], "YouTube")
        self.assertEqual(creators[0]["declared_country"], "DE")
        self.assertEqual(creators[0]["countries"], ["Austria", "Germany"])
        self.assertEqual(creators[0]["view_window_days"], 30)
        self.assertEqual(creators[0]["public_contact_email"], "creator@example.com")
        self.assertEqual(creators[0]["recent_videos"][0]["views"], 60000)


if __name__ == "__main__":
    unittest.main()
