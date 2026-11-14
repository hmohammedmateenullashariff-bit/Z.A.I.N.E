"""Tests for YouTube post-upload last-3 published videos Telegram reporting."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _mock_response(status_code: int = 200, payload=None, headers=None, text: str = ""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = headers or {}
    resp.text = text or (json.dumps(payload) if payload is not None else "")
    resp.json.return_value = payload if payload is not None else {}
    return resp


def test_get_recent_published_videos_live_api_and_lag_merge(monkeypatch, tmp_path):
    from youtube_studio import analytics, uploader

    monkeypatch.setattr(uploader, "ARCHIVE_FILE", tmp_path / "archive.json")
    monkeypatch.setattr(uploader, "QUEUE_FILE", tmp_path / "queue.json")
    monkeypatch.setattr(uploader, "get_stored_token", lambda: {"access_token": "tok_123"})
    monkeypatch.setattr(uploader, "refresh_access_token", lambda td: "tok_123")

    def fake_get(url, headers=None, timeout=15):
        if "channels?" in url:
            return _mock_response(200, {
                "items": [{
                    "snippet": {"title": "Zaine Studio"},
                    "contentDetails": {"relatedPlaylists": {"uploads": "UU_TEST"}},
                }]
            })
        if "playlistItems?" in url:
            return _mock_response(200, {
                "items": [
                    {"contentDetails": {"videoId": "VID_3"}},
                    {"contentDetails": {"videoId": "VID_2"}},
                    {"contentDetails": {"videoId": "VID_1"}},
                    {"contentDetails": {"videoId": "VID_0"}},
                ]
            })
        if "videos?" in url:
            return _mock_response(200, {
                "items": [
                    {
                        "id": "VID_1",
                        "snippet": {"title": "First Short", "publishedAt": "2026-11-10T10:00:00Z"},
                        "statistics": {"viewCount": "100", "likeCount": "10", "commentCount": "1"},
                        "status": {"privacyStatus": "public"},
                        "contentDetails": {"duration": "PT35S"},
                    },
                    {
                        "id": "VID_3",
                        "snippet": {"title": "Third Video [60FPS]", "publishedAt": "2026-11-12T10:00:00Z"},
                        "statistics": {"viewCount": "950", "likeCount": "95", "commentCount": "12"},
                        "status": {"privacyStatus": "public"},
                        "contentDetails": {"duration": "PT1M15S"},
                    },
                    {
                        "id": "VID_2",
                        "snippet": {"title": "Second Short", "publishedAt": "2026-11-11T10:00:00Z"},
                        "statistics": {"viewCount": "420", "likeCount": "40", "commentCount": "4"},
                        "status": {"privacyStatus": "unlisted"},
                        "contentDetails": {"duration": "PT48S"},
                    },
                    {
                        "id": "VID_0",
                        "snippet": {"title": "Oldest Video", "publishedAt": "2026-11-01T10:00:00Z"},
                        "statistics": {"viewCount": "50", "likeCount": "2", "commentCount": "0"},
                        "status": {"privacyStatus": "public"},
                        "contentDetails": {"duration": "PT30S"},
                    },
                ]
            })
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(analytics.requests, "get", fake_get)

    # Case A: live API returns newest 3 sorted by publishedAt
    res = analytics.get_recent_published_videos(limit=3)
    assert res["connected"] is True
    assert res["channel_title"] == "Zaine Studio"
    assert [v["video_id"] for v in res["videos"]] == ["VID_3", "VID_2", "VID_1"]
    assert res["videos"][0]["video_url"] == "https://youtube.com/watch?v=VID_3"
    assert res["videos"][1]["video_url"] == "https://youtube.com/shorts/VID_2"
    assert res["videos"][0]["views"] == 950

    # Case B: newly uploaded video not yet returned by playlistItems/videos API appears #1 cleanly
    just_uploaded = {
        "video_id": "VID_NEW_99",
        "title": "Brand New Short #Shorts",
        "video_url": "https://youtube.com/shorts/VID_NEW_99",
        "published_at": "2026-11-13T12:00:00+00:00",
        "privacy_status": "public",
    }
    res_with_new = analytics.get_recent_published_videos(limit=3, extra_videos=[just_uploaded])
    assert [v["video_id"] for v in res_with_new["videos"]] == ["VID_NEW_99", "VID_3", "VID_2"]


def test_get_recent_published_videos_local_fallback_dedup_and_filter(monkeypatch, tmp_path):
    from youtube_studio import analytics, uploader

    archive_file = tmp_path / "youtube_queue_archive.json"
    queue_file = tmp_path / "youtube_queue.json"
    monkeypatch.setattr(uploader, "ARCHIVE_FILE", archive_file)
    monkeypatch.setattr(uploader, "QUEUE_FILE", queue_file)
    monkeypatch.setattr(uploader, "get_stored_token", lambda: None)
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)

    archive_file.write_text(json.dumps([
        {"video_id": "V1", "title": "Older", "status": "PUBLISHED", "published_at": "2026-11-01T08:00:00"},
        {"video_id": "V2", "title": "Mid", "status": "PUBLISHED", "published_at": "2026-11-05T08:00:00"},
    ]), encoding="utf-8")
    queue_file.write_text(json.dumps([
        {"video_id": "V2", "title": "Mid Duplicate", "status": "PUBLISHED", "published_at": "2026-11-05T08:00:00"},
        {"video_id": "V3", "title": "Newest Published", "status": "PUBLISHED", "published_at": "2026-11-10T09:00:00"},
        {"video_id": "V4", "title": "Still Queued", "status": "QUEUED", "published_at": "2026-11-12T10:00:00"},
    ]), encoding="utf-8")

    res = analytics.get_recent_published_videos(limit=3)
    assert res["connected"] is False
    assert res["source"] == "Local Studio Archive"
    assert [v["video_id"] for v in res["videos"]] == ["V3", "V2", "V1"]


def test_format_recent_videos_report_html_and_markdown_escaping():
    from youtube_studio import analytics

    report_data = {
        "connected": True,
        "channel_title": "Zaine <Studio> & Co",
        "source": "YouTube Data API (OAuth2)",
        "count": 2,
        "limit": 3,
        "videos": [
            {
                "video_id": "abc_123-XYZ",
                "title": "Luffy_Gear_5 [60FPS] & <Epic>*",
                "video_url": "https://youtube.com/shorts/abc_123-XYZ",
                "published_at": "2026-11-12T10:00:00Z",
                "privacy_status": "public",
                "duration_sec": 45,
                "views": 1200,
                "likes": 85,
                "comments": 9,
                "has_live_stats": True,
            },
            {
                "video_id": "def456",
                "title": "Local Clip",
                "video_url": "https://youtube.com/watch?v=def456",
                "published_at": "2026-11-11T10:00:00",
                "privacy_status": "unlisted",
                "duration_sec": 90,
                "has_live_stats": False,
            },
        ],
    }

    html_out = analytics.format_recent_videos_report(
        report_data, limit=3, just_uploaded_id="abc_123-XYZ", html_mode=True
    )
    assert "<b>🎬 Upload Complete — Last 3 Published YouTube Videos</b>" in html_out
    assert "Zaine &lt;Studio&gt; &amp; Co" in html_out
    assert "🆕 JUST PUBLISHED — Luffy_Gear_5 [60FPS] &amp; &lt;Epic&gt;*" in html_out
    assert '<a href="https://youtube.com/shorts/abc_123-XYZ">https://youtube.com/shorts/abc_123-XYZ</a>' in html_out
    assert "1,200 views" in html_out
    assert "⏱️ 1m 30s" in html_out

    md_out = analytics.format_recent_videos_report(
        report_data, limit=3, just_uploaded_id="abc_123-XYZ", html_mode=False
    )
    assert "**1. 🆕 JUST PUBLISHED — Luffy_Gear_5 [60FPS] & <Epic>***" in md_out
    assert "<b>" not in md_out


def test_upload_youtube_video_sends_telegram_report_and_archives(monkeypatch, tmp_path):
    from youtube_studio import analytics, uploader
    import telegram_bridge

    video_file = tmp_path / "new_short.mp4"
    video_file.write_bytes(b"fake_mp4_bytes")
    queue_file = tmp_path / "queue.json"
    archive_file = tmp_path / "archive.json"

    monkeypatch.setattr(uploader, "QUEUE_FILE", queue_file)
    monkeypatch.setattr(uploader, "ARCHIVE_FILE", archive_file)
    monkeypatch.setattr(uploader, "get_stored_token", lambda: {"access_token": "tok_abc"})
    monkeypatch.setattr(uploader, "refresh_access_token", lambda td: "tok_abc")

    def fake_post(url, headers=None, data=None, timeout=30):
        return _mock_response(200, headers={"Location": "https://upload.example/session_1"})

    def fake_put(url, headers=None, data=None, timeout=300):
        return _mock_response(200, payload={"id": "NEW_VID_123"})

    def fake_get(url, headers=None, timeout=15):
        if "channels?" in url:
            return _mock_response(200, {
                "items": [{
                    "snippet": {"title": "Mateen Channel"},
                    "contentDetails": {"relatedPlaylists": {"uploads": "UU_MATEEN"}},
                }]
            })
        if "playlistItems?" in url:
            return _mock_response(200, {
                "items": [
                    {"contentDetails": {"videoId": "NEW_VID_123"}},
                    {"contentDetails": {"videoId": "PREV_2"}},
                    {"contentDetails": {"videoId": "PREV_1"}},
                ]
            })
        if "videos?" in url:
            return _mock_response(200, {
                "items": [
                    {
                        "id": "NEW_VID_123",
                        "snippet": {"title": "Just Uploaded Short", "publishedAt": "2026-11-12T12:50:00Z"},
                        "statistics": {"viewCount": "0", "likeCount": "0", "commentCount": "0"},
                        "status": {"privacyStatus": "public"},
                        "contentDetails": {"duration": "PT40S"},
                    },
                    {
                        "id": "PREV_2",
                        "snippet": {"title": "Previous Video Two", "publishedAt": "2026-11-11T12:00:00Z"},
                        "statistics": {"viewCount": "540", "likeCount": "31", "commentCount": "3"},
                        "status": {"privacyStatus": "public"},
                        "contentDetails": {"duration": "PT52S"},
                    },
                    {
                        "id": "PREV_1",
                        "snippet": {"title": "Previous Video One", "publishedAt": "2026-11-10T12:00:00Z"},
                        "statistics": {"viewCount": "1200", "likeCount": "90", "commentCount": "7"},
                        "status": {"privacyStatus": "public"},
                        "contentDetails": {"duration": "PT1M20S"},
                    },
                ]
            })
        raise AssertionError(f"Unexpected GET {url}")

    monkeypatch.setattr(uploader.requests, "post", fake_post)
    monkeypatch.setattr(uploader.requests, "put", fake_put)
    monkeypatch.setattr(analytics.requests, "get", fake_get)

    sent_calls = []
    monkeypatch.setattr(
        telegram_bridge,
        "send_telegram_alert",
        lambda text, parse_mode="", reply_markup=None, *, force=False: (
            sent_calls.append({"text": text, "parse_mode": parse_mode, "force": force}),
            True,
        )[1],
    )

    res = uploader.upload_youtube_video(
        video_path=str(video_file),
        title="Just Uploaded Short",
        description="Test short",
        tags=["Shorts", "AI"],
    )

    assert res["status"] == "SUCCESS"
    assert res["video_id"] == "NEW_VID_123"
    assert res["telegram_report_sent"] is True
    assert len(sent_calls) == 1
    assert sent_calls[0]["parse_mode"] == "HTML"
    assert sent_calls[0]["force"] is False
    msg_text = sent_calls[0]["text"]
    assert "🆕 JUST PUBLISHED — Just Uploaded Short" in msg_text
    assert "Previous Video Two" in msg_text
    assert "Previous Video One" in msg_text

    # Verify archive recorded the unqueued direct upload and active queue stays clean
    archived = json.loads(archive_file.read_text(encoding="utf-8"))
    assert len(archived) == 1
    assert archived[0]["video_id"] == "NEW_VID_123"
    assert json.loads(queue_file.read_text(encoding="utf-8")) == []

    # Re-upload triggers ALREADY_PUBLISHED and does not re-send Telegram alert
    dup_res = uploader.upload_youtube_video(str(video_file), "Just Uploaded Short")
    assert dup_res["status"] == "ALREADY_PUBLISHED"
    assert len(sent_calls) == 1


def test_upload_failure_and_telegram_error_do_not_break_uploader(monkeypatch, tmp_path):
    from youtube_studio import analytics, uploader
    import telegram_bridge

    video_file = tmp_path / "short_err.mp4"
    video_file.write_bytes(b"mp4")
    monkeypatch.setattr(uploader, "QUEUE_FILE", tmp_path / "queue.json")
    monkeypatch.setattr(uploader, "ARCHIVE_FILE", tmp_path / "archive.json")
    monkeypatch.setattr(uploader, "get_stored_token", lambda: {"access_token": "tok"})
    monkeypatch.setattr(uploader, "refresh_access_token", lambda td: "tok")

    sent_calls = []
    monkeypatch.setattr(
        telegram_bridge,
        "send_telegram_alert",
        lambda *a, **kw: sent_calls.append(a) or True,
    )

    # 1. Failed upload chunk does not send Telegram report
    monkeypatch.setattr(uploader.requests, "post", lambda *a, **k: _mock_response(200, headers={"Location": "https://up/1"}))
    monkeypatch.setattr(uploader.requests, "put", lambda *a, **k: _mock_response(500, text="server error"))
    fail_res = uploader.upload_youtube_video(str(video_file), "Failed Video")
    assert fail_res["status"] == "FAILED"
    assert sent_calls == []

    # 2. Successful upload survives if Telegram dispatch throws
    monkeypatch.setattr(uploader.requests, "put", lambda *a, **k: _mock_response(200, payload={"id": "VID_OK"}))
    monkeypatch.setattr(analytics.requests, "get", lambda *a, **k: _mock_response(500))
    monkeypatch.setattr(telegram_bridge, "send_telegram_alert", MagicMock(side_effect=RuntimeError("tg down")))
    ok_res = uploader.upload_youtube_video(str(video_file), "Resilient Short")
    assert ok_res["status"] == "SUCCESS"
    assert ok_res["telegram_report_sent"] is False


def test_telegram_yt_approve_callback_and_ytreport_command(monkeypatch):
    import telegram_bridge
    from youtube_studio import analytics, uploader

    bridge = telegram_bridge.TelegramBridge(agent=None)
    bridge.answer_callback_query = MagicMock()
    bridge.edit_message_caption = MagicMock()
    bridge.send_message = MagicMock()
    bridge.send_chat_action = MagicMock()

    seen_approve_kwargs = []

    def fake_publish(pid, **kwargs):
        seen_approve_kwargs.append((pid, kwargs))
        return {
            "status": "SUCCESS",
            "title": "Approved Anime Short",
            "video_url": "https://youtube.com/shorts/APP123",
            "telegram_report_sent": True,
        }

    monkeypatch.setattr(uploader, "publish_approved_video", fake_publish)

    bridge.handle_callback_query({
        "id": "cb_1",
        "data": "yt_approve:YT-7788",
        "message": {"chat": {"id": 999}, "message_id": 55, "text": ""},
    })
    assert seen_approve_kwargs == [("YT-7788", {"notify_telegram": True, "force_telegram": True})]
    caption_arg = bridge.edit_message_caption.call_args[0][2]
    assert "APPROVED & PUBLISHED LIVE ON YOUTUBE" in caption_arg
    assert "Last 3 published YouTube videos report sent to Telegram." in caption_arg

    # Test /ytreport 2 slash command
    monkeypatch.setattr(
        analytics,
        "get_recent_published_videos",
        lambda limit=3: {
            "connected": False,
            "channel_title": "Test Studio",
            "limit": limit,
            "count": 1,
            "videos": [{
                "video_id": "V1",
                "title": "Test Clip",
                "video_url": "https://youtube.com/shorts/V1",
                "published_at": "2026-11-12T11:00:00",
                "privacy_status": "public",
                "has_live_stats": False,
            }],
        },
    )
    bridge.handle_text_message(999, "/ytreport 2")
    bridge.send_message.assert_called_once()
    args, kwargs = bridge.send_message.call_args
    assert args[0] == 999
    assert "Last 2 Published YouTube Videos" in args[1]
    assert kwargs["parse_mode"] == "HTML"


def test_tools_recent_youtube_report_and_upload_fix(monkeypatch, tmp_path):
    import tools
    from youtube_studio import analytics, uploader
    import telegram_bridge

    monkeypatch.setattr(uploader, "ARCHIVE_FILE", tmp_path / "archive.json")
    monkeypatch.setattr(uploader, "QUEUE_FILE", tmp_path / "queue.json")
    monkeypatch.setattr(uploader, "get_stored_token", lambda: None)
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)

    (tmp_path / "archive.json").write_text(json.dumps([
        {"video_id": "A1", "title": "First", "status": "PUBLISHED", "published_at": "2026-11-10T10:00:00"},
        {"video_id": "A2", "title": "Second", "status": "PUBLISHED", "published_at": "2026-11-11T10:00:00"},
        {"video_id": "A3", "title": "Third", "status": "PUBLISHED", "published_at": "2026-11-12T10:00:00"},
    ]), encoding="utf-8")

    monkeypatch.setattr(telegram_bridge, "send_telegram_alert", lambda *a, **kw: True)
    out = tools.report_recent_youtube_videos_tool(limit=3, send_telegram="true")
    assert "Third" in out and "Second" in out and "First" in out
    assert "Report delivered to Telegram." in out

    import youtube_studio
    monkeypatch.setattr(
        uploader,
        "upload_youtube_video",
        lambda *a, **kw: {
            "status": "SUCCESS",
            "video_id": "UP_99",
            "video_url": "https://youtube.com/shorts/UP_99",
            "telegram_report_sent": True,
        },
    )
    monkeypatch.setattr(
        youtube_studio,
        "upload_youtube_video",
        uploader.upload_youtube_video,
    )
    up_out = tools.upload_youtube_video_tool("video.mp4", "Title")
    assert "Upload Complete!" in up_out
    assert "https://youtube.com/shorts/UP_99" in up_out
    assert "Last 3 published videos report sent to Telegram." in up_out

