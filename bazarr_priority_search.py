#!/usr/bin/env python3
"""Queue priority subtitle searches in Bazarr: anime first, then movies."""
import urllib.request
import sqlite3
import json
import time

API_KEY = "d78b5c17cab81553d792838d64ff7235"
BASE = "http://127.0.0.1:6767/api"

def api_patch(endpoint, data):
    """Send PATCH to Bazarr API."""
    params = "&".join(f"{k}={v}" for k, v in data.items())
    url = f"{BASE}/{endpoint}?{params}"
    req = urllib.request.Request(url, method="PATCH", headers={"X-API-KEY": API_KEY})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status
    except Exception as e:
        return str(e)

c = sqlite3.connect("/config/db/bazarr.db")

# Phase 1: Anime episodes (highest priority)
anime_eps = c.execute("""
    SELECT sonarrSeriesId, sonarrEpisodeId
    FROM table_episodes
    WHERE path LIKE '/anime/%'
      AND missing_subtitles IS NOT NULL
      AND missing_subtitles != '[]'
    ORDER BY sonarrEpisodeId
""").fetchall()

print(f"Phase 1: Queuing {len(anime_eps)} anime episodes...")
queued = 0
errors = 0
for series_id, ep_id in anime_eps:
    status = api_patch("episodes/subtitles", {
        "seriesid": series_id,
        "episodeid": ep_id,
        "language": "en",
        "forced": "false",
        "hi": "false",
    })
    if status == 204:
        queued += 1
    else:
        errors += 1
    if queued % 50 == 0 and queued > 0:
        print(f"  ...queued {queued}/{len(anime_eps)} anime eps ({errors} errors)")
        time.sleep(1)  # Brief pause every 50 to avoid overwhelming

print(f"Phase 1 complete: {queued} anime eps queued, {errors} errors")

# Phase 2: Movies
movie_rows = c.execute("""
    SELECT radarrId
    FROM table_movies
    WHERE missing_subtitles IS NOT NULL
      AND missing_subtitles != '[]'
    ORDER BY radarrId
""").fetchall()

print(f"\nPhase 2: Queuing {len(movie_rows)} movies...")
m_queued = 0
m_errors = 0
for (radarr_id,) in movie_rows:
    params = "&".join([
        f"radarrid={radarr_id}",
        "language=en",
        "forced=false",
        "hi=false",
    ])
    url = f"{BASE}/movies/subtitles?{params}"
    req = urllib.request.Request(url, method="PATCH", headers={"X-API-KEY": API_KEY})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            if resp.status == 204:
                m_queued += 1
            else:
                m_errors += 1
    except Exception as e:
        m_errors += 1
    if m_queued % 25 == 0 and m_queued > 0:
        print(f"  ...queued {m_queued}/{len(movie_rows)} movies ({m_errors} errors)")
        time.sleep(1)

print(f"Phase 2 complete: {m_queued} movies queued, {m_errors} errors")
print(f"\nTotal: {queued + m_queued} items queued for priority search")
print("Bazarr's job queue will process these with 3 concurrent workers.")
print("The remaining TV/cartoon episodes will be handled by the next scheduled search cycle.")
