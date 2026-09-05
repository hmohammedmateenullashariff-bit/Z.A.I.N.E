"""
Z.A.I.N.E — Viral Trend & Meme Tracker
Harvests real-time viral trends, memes, and spikes across:
- Anime (character battles, power escalations, seasonal hype)
- Gaming (boss secrets, GTA 6 leaks, Elden Ring lore, mechanics)
- Memes & Pop Culture (trending meme formats, viral humor)
- Mind-Blowing Facts (astronomy, psychology, science curiosities)
- Tech & AI (frontier models, GPU breakthroughs, distributed systems)
"""

import json
import time
import urllib.request
import xml.etree.ElementTree as ET
from typing import List, Dict, Any

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

# Curated high-velocity seed trends per genre (graceful offline fallback)
SEED_TRENDS = {
    "anime": [
        {"topic": "Naruto vs Sasuke Final Valley Full Power", "score": 98, "title": "Who ACTUALLY Won at Final Valley: Naruto or Sasuke? #Shorts #Anime"},
        {"topic": "Luffy Gear 5 vs Imu Ancient Powers", "score": 96, "title": "Luffy Gear 5 vs Imu: The Void Century Final War #Shorts #Anime #OnePiece"},
        {"topic": "Goku Ultra Instinct vs Vegeta Ultra Ego", "score": 94, "title": "Ultra Instinct vs Ultra Ego: Who Survives? #Shorts #DragonBall"},
        {"topic": "Gojo vs Sukuna Domain Clash Explained", "score": 92, "title": "The Secret Reason Sukuna Won Against Gojo #Shorts #JujutsuKaisen"},
        {"topic": "Solo Leveling Sung Jinwoo Shadow Monarch Scale", "score": 90, "title": "How Sung Jinwoo Broke the Scaling in Solo Leveling #Shorts #Anime"},
    ],
    "gaming": [
        {"topic": "Elden Ring Godskin Apostle Dark Secret", "score": 97, "title": "The Darkest Detail in Elden Ring Lore #Shorts #Gaming #EldenRing"},
        {"topic": "GTA 6 Real Time Water and Crash Physics", "score": 95, "title": "Why GTA 6 Physics Will Ruin All Other Games #Shorts #Gaming #GTA6"},
        {"topic": "Minecraft Deep Dark Warden Origin Lore", "score": 89, "title": "The Terrifying Truth About the Minecraft Warden #Shorts #Minecraft"},
        {"topic": "Black Myth Wukong Secret Boss Locations", "score": 88, "title": "The Secret Boss Nobody Found in Wukong #Shorts #Gaming"},
    ],
    "facts": [
        {"topic": "The Bootes Void 300 Million Light Year Mystery", "score": 95, "title": "The Scariest Void in the Known Universe #Shorts #Space #Facts"},
        {"topic": "The Gruen Effect Retail Manipulation", "score": 93, "title": "The Psychological Trick Stores Use to Steal Your Money #Shorts #Facts"},
        {"topic": "Time Dilation at Black Hole Event Horizon", "score": 91, "title": "What Happens If You Fall Into a Black Hole? #Shorts #Science"},
        {"topic": "The Mariana Trench Challenger Deep Sound", "score": 88, "title": "What Scientists Recorded at the Bottom of the Ocean #Shorts #Mystery"},
    ],
    "cat": [
        {"topic": "The 3 AM Feline Zoomies Dimensional Rabbit Hole", "score": 94, "title": "Why Your Cat Sprints Like a Demon at 3 AM #Shorts #Cats #Memes"},
        {"topic": "Orange Cat Single Braincell Phenomenon", "score": 92, "title": "Proof That All Orange Cats Share One Braincell #Shorts #CatMemes"},
        {"topic": "The Feline Belly Rub Trap Protocol", "score": 89, "title": "What Your Cat Is Thinking During Belly Rubs #Shorts #FunnyCats"},
    ],
    "tech": [
        {"topic": "Claude 3.7 Sonnet Hybrid Reasoning Engine", "score": 98, "title": "Why Claude 3.7 Sonnet Changes Autonomous AI Coding #Shorts #AI"},
        {"topic": "Why Redis Single Thread Beats Multithreading", "score": 91, "title": "The Single-Threaded Secret Behind Redis #Shorts #Tech #SystemDesign"},
        {"topic": "Quantum Computing Quantum Supremacy 2026", "score": 87, "title": "Did Quantum Computers Just Break Encryption? #Shorts #Tech"},
    ],
}


def fetch_google_trends_rss(geo: str = "US", max_results: int = 15) -> List[Dict[str, Any]]:
    """Fetches real-time search trends via Google Trends daily RSS."""
    url = f"https://trends.google.com/trends/trendingsearches/daily/rss?geo={geo}"
    trends = []
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=6) as response:
            xml_data = response.read()
            root = ET.fromstring(xml_data)
            channel = root.find("channel")
            if channel is not None:
                for item in channel.findall("item")[:max_results]:
                    title_elem = item.find("title")
                    approx_traffic = item.find("{https://trends.google.com/trends/trendingsearches/daily}approx_traffic")
                    traffic_str = approx_traffic.text if approx_traffic is not None else "100K+"
                    if title_elem is not None and title_elem.text:
                        trends.append({
                            "title": title_elem.text.strip(),
                            "traffic": traffic_str,
                            "source": "google_trends",
                        })
    except Exception:
        pass
    return trends


def fetch_reddit_viral_memes(subreddit: str = "memes", limit: int = 10) -> List[Dict[str, Any]]:
    """Fetches top viral topics from reddit communities without auth."""
    url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit={limit}"
    posts = []
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ZaineViralTracker/2.0"})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
            children = data.get("data", {}).get("children", [])
            for child in children:
                p_data = child.get("data", {})
                title = p_data.get("title", "").strip()
                score = p_data.get("score", 0)
                # Filter stickied / generic posts
                if not p_data.get("stickied") and title and len(title) > 10:
                    posts.append({
                        "title": title,
                        "score": score,
                        "source": f"r/{subreddit}",
                    })
    except Exception:
        pass
    return posts


def get_trending_topics(genre: str = "auto", limit: int = 5) -> List[Dict[str, Any]]:
    """
    Returns ranked high-velocity trending topics for the requested genre:
    - 'anime', 'gaming', 'facts', 'cat', 'kids', 'tech', or 'auto'
    """
    genre_key = genre.lower().strip()
    if genre_key not in SEED_TRENDS and genre_key != "auto":
        genre_key = "anime"

    results = []

    # 1. Harvest live web feeds if applicable
    if genre_key in ("cat", "kids", "auto"):
        reddit_memes = fetch_reddit_viral_memes("memes", limit=5)
        for p in reddit_memes:
            results.append({
                "topic": p["title"],
                "genre": "cat" if any(w in p["title"].lower() for w in ("cat", "dog", "pet")) else "kids" if "kid" in p["title"].lower() else "meme",
                "score": min(99, 80 + int(p.get("score", 0) / 1000)),
                "title": f"{p['title'][:70]} #Shorts #Memes",
                "source": p["source"],
            })

    if genre_key in ("gaming", "auto"):
        reddit_gaming = fetch_reddit_viral_memes("gaming", limit=5)
        for p in reddit_gaming:
            results.append({
                "topic": p["title"],
                "genre": "gaming",
                "score": min(99, 85 + int(p.get("score", 0) / 1000)),
                "title": f"{p['title'][:70]} #Shorts #Gaming",
                "source": p["source"],
            })

    if genre_key in ("anime", "auto"):
        reddit_anime = fetch_reddit_viral_memes("animemes", limit=5)
        for p in reddit_anime:
            results.append({
                "topic": p["title"],
                "genre": "anime",
                "score": min(99, 85 + int(p.get("score", 0) / 1000)),
                "title": f"{p['title'][:70]} #Shorts #Anime",
                "source": p["source"],
            })

    # 2. Blend with high-authority seed trends
    if genre_key == "auto":
        for g, items in SEED_TRENDS.items():
            for item in items:
                results.append({
                    "topic": item["topic"],
                    "genre": g,
                    "score": item["score"],
                    "title": item["title"],
                    "source": "curated_viral_vault",
                })
    else:
        seed_pool = SEED_TRENDS.get(genre_key, SEED_TRENDS["anime"])
        for item in seed_pool:
            results.append({
                "topic": item["topic"],
                "genre": genre_key,
                "score": item["score"],
                "title": item["title"],
                "source": "curated_viral_vault",
            })

    # Sort descending by viral velocity score
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]


def format_trending_dossier() -> str:
    """Returns a formatted Markdown dossier of top trending topics across all niches."""
    lines = [
        "### 🔥 Zaine Studio Viral Intelligence: Real-Time Trending Topics",
        f"*Synchronized at: {time.strftime('%Y-%m-%d %H:%M:%S')}*\n",
    ]

    for g in ["anime", "gaming", "facts", "cat", "tech"]:
        items = get_trending_topics(genre=g, limit=2)
        emoji = {"anime": "⚔️", "gaming": "🎮", "facts": "🧠", "cat": "🐾", "tech": "⚡"}.get(g, "🎬")
        lines.append(f"**{emoji} {g.upper()} TRENDS:**")
        for idx, it in enumerate(items, 1):
            lines.append(f"  {idx}. **{it['topic']}** (Velocity: `{it['score']}/100`, Source: `{it['source']}`)")
            lines.append(f"     Suggested: *\"{it['title']}\"*")
        lines.append("")

    return "\n".join(lines)
