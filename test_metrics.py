import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import sourcing
from metrics_history import save_and_measure_snapshots


class YouTubeMetricsTests(unittest.TestCase):
    def test_keeps_core_size_channel_and_averages_recent_upload_cohort(self):
        now = datetime.now(timezone.utc)
        published_dates = [
            (now - timedelta(days=age)).isoformat()
            for age in (10, 20, 25)
        ]
        youtube = Mock()
        youtube.search.return_value.list.return_value.execute.return_value = {
                "items": [
                    {
                        "id": {"videoId": "video-1"},
                        "snippet": {
                            "channelId": "channel-1",
                            "title": "Gaming PC build",
                            "description": "RTX hardware test",
                            "publishedAt": published_dates[0],
                        },
                },
                    {
                        "id": {"videoId": "video-outside-eu"},
                        "snippet": {
                            "channelId": "channel-outside-eu",
                            "title": "Gaming PC build",
                            "description": "RTX hardware test",
                            "publishedAt": published_dates[0],
                        },
                    },
                ],
        }
        youtube.channels.return_value.list.return_value.execute.return_value = {
            "items": [
                {
                    "id": "channel-1",
                    "snippet": {"title": "Creator", "description": "Contact: creator@example.com https://creator.example", "customUrl": "@creator", "country": "DE"},
                    "contentDetails": {"relatedPlaylists": {"uploads": "uploads-1"}},
                    "statistics": {"subscriberCount": "120000", "viewCount": "500000", "videoCount": "150"},
                },
                {
                    "id": "channel-outside-eu",
                    "snippet": {"title": "Korea Creator", "description": "Gaming PCs", "country": "KR"},
                    "statistics": {"subscriberCount": "100000", "viewCount": "1000000", "videoCount": "100"},
                },
            ],
        }
        youtube.playlistItems.return_value.list.return_value.execute.return_value = {
            "items": [
                {
                    "snippet": {"title": title, "description": "RTX gaming PC build benchmark", "publishedAt": published_at},
                    "contentDetails": {"videoId": f"video-{index}", "videoPublishedAt": published_at},
                }
                for index, (title, published_at) in enumerate(zip(("RTX Valorant PC build", "Gaming PC benchmark", "Ryzen build"), published_dates), start=1)
            ],
        }
        youtube.videos.return_value.list.return_value.execute.return_value = {
            "items": [
                {
                    "id": f"video-{index}",
                    "snippet": {"publishedAt": published_at},
                    "statistics": {"viewCount": str(40000 + index * 10000), "likeCount": "800", "commentCount": "20"},
                }
                for index, published_at in enumerate(published_dates, start=1)
            ],
        }

        with patch.object(sourcing, "build", return_value=youtube):
            creators = sourcing.get_youtube_creators("not-a-real-key", "pc build", "DE", "de")

        self.assertEqual(len(creators), 1)
        creator = creators[0]

        self.assertEqual(creator["subscribers"], 120000)
        self.assertEqual(creator["declared_country"], "DE")
        self.assertEqual(creator["public_contact_email"], "creator@example.com")
        self.assertEqual(creator["public_contact_url"], "https://creator.example")
        self.assertEqual(creator["channel_total_views"], 500000)
        self.assertEqual(creator["channel_video_count"], 150)
        self.assertEqual(creator["view_window_days"], 30)
        self.assertEqual(creator["view_window_video_count"], 3)
        self.assertEqual(creator["avg_recent_video_views"], 60000)
        self.assertEqual(creator["median_recent_video_views"], 60000)
        self.assertGreater(creator["recent_video_engagement_rate"], 1)
        self.assertIn("PC builds", creator["content_categories"])
        self.assertIn("Game: Valorant", creator["content_categories"])
        youtube.search.return_value.list.assert_called_once()
        self.assertEqual(youtube.search.return_value.list.call_args.kwargs["order"], "date")

    def test_snapshot_growth_requires_prior_observation(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "metrics.sqlite3"
            creator = {
                "channel_id": "channel-1",
                "channel_total_views": 700,
                "subscribers": 70,
                "channel_video_count": 10,
                "recent_videos": [{"video_id": "video-1", "views": 200}],
            }

            save_and_measure_snapshots([creator], database_path)
            self.assertIsNone(creator["observed_monthly_view_growth"])

            old_capture = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
            with closing(sqlite3.connect(database_path)) as connection:
                with connection:
                    connection.execute(
                        """UPDATE channel_snapshots
                        SET captured_at = ?, channel_total_views = 700, subscriber_count = 70
                        WHERE channel_id = ?""",
                        (old_capture, "channel-1"),
                    )
                    connection.execute(
                        """INSERT INTO video_snapshots (video_id, channel_id, captured_at, view_count)
                        VALUES (?, ?, ?, ?)""",
                        ("video-1", "channel-1", old_capture, 100),
                    )

                creator.update(channel_total_views=1000, subscribers=100)
                creator["recent_videos"][0]["views"] = 400
            save_and_measure_snapshots([creator], database_path)

            self.assertAlmostEqual(creator["observed_monthly_view_growth"], 304, delta=3)
            self.assertAlmostEqual(creator["recent_videos"][0]["observed_monthly_view_growth"], 304, delta=3)
            self.assertAlmostEqual(creator["observed_monthly_subscriber_growth"], 30, delta=1)
            self.assertEqual(
                creator["estimated_yearly_views_from_snapshot"],
                creator["estimated_monthly_views_from_snapshot"] * 12,
            )

    def test_niche_classifier_uses_pc_evidence_and_localized_terms(self):
        lego_categories = sourcing._video_categories("Lego CITY Gaming PC Build")
        finnish_categories = sourcing._video_categories("Pelitietokoneen kasaus Ryzen 5")

        self.assertIn("Gaming", lego_categories)
        self.assertNotIn("PC builds", lego_categories)
        self.assertIn("PC builds", finnish_categories)


if __name__ == "__main__":
    unittest.main()
