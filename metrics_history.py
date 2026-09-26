import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median


DATABASE_PATH = Path(__file__).with_name("creator_metrics.sqlite3")
MINIMUM_GROWTH_INTERVAL_DAYS = 7


def save_and_measure_snapshots(creators, database_path=DATABASE_PATH):
    """Persist channel and video counters, deriving growth only from prior observations."""
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    results = {}

    with closing(sqlite3.connect(database_path)) as connection:
        with connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS channel_snapshots (
                    channel_id TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    channel_total_views INTEGER NOT NULL,
                    subscriber_count INTEGER NOT NULL,
                    channel_video_count INTEGER NOT NULL,
                    PRIMARY KEY (channel_id, captured_at)
                )
                """,
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS video_snapshots (
                    video_id TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    view_count INTEGER NOT NULL,
                    PRIMARY KEY (video_id, captured_at)
                )
                """
            )

            for creator in creators:
                channel_id = creator.get("channel_id")
                if not channel_id:
                    continue

                total_views = creator.get("channel_total_views")
                subscriber_count = creator.get("subscribers")
                video_count = creator.get("channel_video_count")
                if total_views is None or video_count is None:
                    continue
                stored_subscriber_count = subscriber_count if subscriber_count is not None else -1

                previous = connection.execute(
                    """
                    SELECT captured_at, channel_total_views, subscriber_count
                    FROM channel_snapshots
                    WHERE channel_id = ?
                        AND captured_at <= ?
                    ORDER BY captured_at DESC
                    LIMIT 1
                    """,
                    (channel_id, (now - timedelta(days=MINIMUM_GROWTH_INTERVAL_DAYS)).isoformat()),
                ).fetchone()

                metrics = {
                    "snapshot_captured_at": now_iso,
                    "snapshot_interval_days": None,
                    "observed_monthly_view_growth": None,
                    "observed_monthly_subscriber_growth": None,
                    "estimated_monthly_views_from_snapshot": None,
                    "estimated_yearly_views_from_snapshot": None,
                }
                if previous:
                    previous_date = datetime.fromisoformat(previous[0])
                    interval_days = (now - previous_date).total_seconds() / 86400
                    if interval_days > 0:
                        monthly_factor = 30.4375 / interval_days
                        view_delta = total_views - previous[1]
                        subscriber_delta = (
                            subscriber_count - previous[2]
                            if subscriber_count is not None and previous[2] >= 0
                            else None
                        )
                        monthly_view_growth = round(view_delta * monthly_factor)
                        metrics.update({
                            "snapshot_interval_days": round(interval_days, 2),
                            "observed_monthly_view_growth": monthly_view_growth,
                            "observed_monthly_subscriber_growth": round(subscriber_delta * monthly_factor) if subscriber_delta is not None else None,
                            "estimated_monthly_views_from_snapshot": max(0, monthly_view_growth),
                            "estimated_yearly_views_from_snapshot": max(0, round(monthly_view_growth * 12)),
                        })

                connection.execute(
                    """
                    INSERT INTO channel_snapshots (
                        channel_id, captured_at, channel_total_views,
                        subscriber_count, channel_video_count
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (channel_id, now_iso, total_views, stored_subscriber_count, video_count),
                )
                results[channel_id] = metrics

                observed_video_growth = []
                for video in creator.get("recent_videos", []):
                    video_id = video.get("video_id")
                    view_count = video.get("views")
                    if not video_id or view_count is None:
                        continue
                    previous_video = connection.execute(
                        """
                        SELECT captured_at, view_count
                        FROM video_snapshots
                        WHERE video_id = ? AND captured_at <= ?
                        ORDER BY captured_at DESC
                        LIMIT 1
                        """,
                        (video_id, (now - timedelta(days=MINIMUM_GROWTH_INTERVAL_DAYS)).isoformat()),
                    ).fetchone()
                    video["observed_monthly_view_growth"] = None
                    video["snapshot_interval_days"] = None
                    if previous_video:
                        previous_video_date = datetime.fromisoformat(previous_video[0])
                        interval_days = (now - previous_video_date).total_seconds() / 86400
                        if interval_days > 0:
                            growth = round((view_count - previous_video[1]) * 30.4375 / interval_days)
                            video["observed_monthly_view_growth"] = growth
                            video["snapshot_interval_days"] = round(interval_days, 2)
                            observed_video_growth.append(growth)
                    connection.execute(
                        """
                        INSERT INTO video_snapshots (video_id, channel_id, captured_at, view_count)
                        VALUES (?, ?, ?, ?)
                        """,
                        (video_id, channel_id, now_iso, view_count),
                    )

                creator["median_observed_monthly_video_view_growth"] = (
                    round(median(observed_video_growth))
                    if observed_video_growth else None
                )
                if observed_video_growth:
                    creator["trend_status"] = (
                        "Views accelerating" if creator["median_observed_monthly_video_view_growth"] > 0
                        else "Views declining" if creator["median_observed_monthly_video_view_growth"] < 0
                        else "Views stable"
                    )
                else:
                    creator["trend_status"] = "Awaiting repeat video snapshots"
                if creator["trend_status"] == "Views declining":
                    creator.setdefault("risk_flags", []).append("Tracked recent videos have declining views")

    for creator in creators:
        snapshot_metrics = results.get(creator.get("channel_id"))
        if snapshot_metrics:
            creator.update(snapshot_metrics)

    return creators
