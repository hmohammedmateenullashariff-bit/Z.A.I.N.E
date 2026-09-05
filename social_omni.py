"""
Z.A.I.N.E — Social Omni-Access & Opportunity Harvester Engine
Empowers Ultron and Zaine with direct deep-linking, searching, posting,
and live opportunity harvesting across all major social media & career platforms:
- Instagram
- Facebook
- X (formerly Twitter)
- LinkedIn
- Unstop (Hackathons, Competitions, Internships, Jobs)
- GitHub, Reddit, YouTube, Discord
"""

import urllib.parse
import webbrowser
import requests

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


def access_social_platform(
    platform: str,
    action: str = "open",
    query: str = "",
    username: str = "",
    text: str = "",
) -> str:
    """
    Directly accesses and navigates social media platforms in the user's browser.
    Platforms: 'instagram', 'facebook', 'x' (or 'twitter'), 'linkedin', 'unstop', 'github', 'reddit', 'youtube'.
    Actions: 'open', 'search', 'profile', 'post' (or 'compose'), 'hackathons', 'internships', 'jobs'.
    """
    p = platform.lower().strip()
    act = action.lower().strip()
    q_enc = urllib.parse.quote_plus(query.strip()) if query else ""
    user_clean = username.strip().lstrip("@")
    text_enc = urllib.parse.quote_plus(text.strip()) if text else ""

    target_url = ""
    summary_action = ""

    # 1. INSTAGRAM
    if p in ("instagram", "insta", "ig"):
        if act == "profile" and user_clean:
            target_url = f"https://www.instagram.com/{user_clean}/"
            summary_action = f"Opening Instagram profile for @{user_clean}"
        elif act == "search" and query:
            clean_tag = query.replace("#", "").strip()
            target_url = f"https://www.instagram.com/explore/tags/{clean_tag}/"
            summary_action = f"Searching Instagram tags for #{clean_tag}"
        elif act in ("messages", "dms", "inbox"):
            target_url = "https://www.instagram.com/direct/inbox/"
            summary_action = "Opening Instagram Direct Messages"
        else:
            target_url = "https://www.instagram.com/"
            summary_action = "Opening Instagram feed"

    # 2. FACEBOOK
    elif p in ("facebook", "fb"):
        if act == "profile" and user_clean:
            target_url = f"https://www.facebook.com/{user_clean}"
            summary_action = f"Opening Facebook profile for {user_clean}"
        elif act == "search" and query:
            target_url = f"https://www.facebook.com/search/top/?q={q_enc}"
            summary_action = f"Searching Facebook for '{query}'"
        elif act in ("groups", "group"):
            target_url = "https://www.facebook.com/groups/"
            summary_action = "Opening Facebook Groups"
        else:
            target_url = "https://www.facebook.com/"
            summary_action = "Opening Facebook feed"

    # 3. X (TWITTER)
    elif p in ("x", "twitter", "tweet"):
        if act in ("post", "tweet", "compose") and (text or query):
            content = text_enc or q_enc
            target_url = f"https://x.com/intent/tweet?text={content}"
            summary_action = "Opening X Tweet Composer with draft"
        elif act == "profile" and user_clean:
            target_url = f"https://x.com/{user_clean}"
            summary_action = f"Opening X profile for @{user_clean}"
        elif act == "search" and query:
            target_url = f"https://x.com/search?q={q_enc}&f=live"
            summary_action = f"Searching live posts on X for '{query}'"
        elif act in ("notifications", "mentions"):
            target_url = "https://x.com/notifications"
            summary_action = "Opening X Notifications"
        else:
            target_url = "https://x.com/"
            summary_action = "Opening X home feed"

    # 4. LINKEDIN
    elif p in ("linkedin", "li"):
        if act == "jobs" or "job" in query.lower():
            kw = q_enc or "software+engineer"
            target_url = f"https://www.linkedin.com/jobs/search/?keywords={kw}"
            summary_action = f"Searching LinkedIn Jobs for '{query or 'Software Engineering'}'"
        elif act in ("post", "share", "compose") and text:
            target_url = f"https://www.linkedin.com/feed/?shareActive=true&text={text_enc}"
            summary_action = "Opening LinkedIn Post Composer"
        elif act == "profile" and user_clean:
            target_url = f"https://www.linkedin.com/in/{user_clean}/"
            summary_action = f"Opening LinkedIn profile for {user_clean}"
        elif act == "search" and query:
            target_url = f"https://www.linkedin.com/search/results/all/?keywords={q_enc}"
            summary_action = f"Searching LinkedIn for '{query}'"
        elif act in ("messages", "messaging"):
            target_url = "https://www.linkedin.com/messaging/"
            summary_action = "Opening LinkedIn Messaging"
        else:
            target_url = "https://www.linkedin.com/feed/"
            summary_action = "Opening LinkedIn Feed"

    # 5. UNSTOP
    elif p in ("unstop", "d2c", "dare2compete"):
        category = "hackathons"
        if act in ("internships", "internship") or "intern" in query.lower():
            category = "internships"
        elif act in ("jobs", "job"):
            category = "jobs"
        elif act in ("competitions", "competition"):
            category = "competitions"
        elif act in ("quizzes", "quiz"):
            category = "quizzes"

        if query:
            target_url = f"https://unstop.com/{category}?searchTerm={q_enc}"
            summary_action = f"Searching Unstop {category.capitalize()} for '{query}'"
        else:
            target_url = f"https://unstop.com/{category}"
            summary_action = f"Opening Unstop {category.capitalize()} hub"

    # 6. GITHUB
    elif p in ("github", "gh"):
        if act == "search" and query:
            target_url = f"https://github.com/search?q={q_enc}"
            summary_action = f"Searching GitHub for '{query}'"
        elif act == "profile" and user_clean:
            target_url = f"https://github.com/{user_clean}"
            summary_action = f"Opening GitHub profile for {user_clean}"
        elif act in ("trending", "trend"):
            target_url = "https://github.com/trending"
            summary_action = "Opening GitHub Trending repositories"
        else:
            target_url = "https://github.com/"
            summary_action = "Opening GitHub"

    # 7. REDDIT
    elif p in ("reddit", "r"):
        if act == "search" and query:
            target_url = f"https://www.reddit.com/search/?q={q_enc}"
            summary_action = f"Searching Reddit for '{query}'"
        elif user_clean:
            sub = user_clean.replace("r/", "")
            target_url = f"https://www.reddit.com/r/{sub}/"
            summary_action = f"Opening Subreddit r/{sub}"
        else:
            target_url = "https://www.reddit.com/"
            summary_action = "Opening Reddit"

    # 8. YOUTUBE
    elif p in ("youtube", "yt"):
        if query:
            target_url = f"https://www.youtube.com/results?search_query={q_enc}"
            summary_action = f"Searching YouTube for '{query}'"
        else:
            target_url = "https://www.youtube.com/"
            summary_action = "Opening YouTube"

    # 9. DISCORD
    elif p in ("discord", "dc"):
        target_url = "https://discord.com/app"
        summary_action = "Opening Discord Web"

    else:
        # Generic platform fallback
        target_url = f"https://www.google.com/search?q={urllib.parse.quote_plus(f'{platform} {query}'.strip())}"
        summary_action = f"Searching the web for '{platform} {query}'"

    try:
        webbrowser.open(target_url)
        return f"⚡ [SOCIAL OMNI ACCESS]: {summary_action}.\nURL: {target_url}"
    except Exception as e:
        return f"Failed to open {platform}: {e}"


def search_unstop(category: str = "hackathons", query: str = "", limit: int = 6) -> str:
    """
    Queries live real-time opportunities directly from Unstop's public API.
    Categories: 'hackathons', 'competitions', 'internships', 'jobs', 'quizzes'.
    Returns structured details on active events, organizers, deadlines, and direct links.
    """
    cat = category.lower().strip()
    valid_cats = ["hackathons", "competitions", "internships", "jobs", "quizzes"]
    if cat not in valid_cats:
        cat = "hackathons"

    params = {
        "opportunity": cat,
        "per_page": limit,
    }
    if query and query.strip():
        params["searchTerm"] = query.strip()

    api_url = "https://unstop.com/api/public/opportunity/search-result"
    try:
        r = requests.get(api_url, headers=DEFAULT_HEADERS, params=params, timeout=12)
        if r.status_code != 200:
            return f"Unstop API responded with status {r.status_code}. Opening direct page in browser:\n{access_social_platform('unstop', action=cat, query=query)}"

        data = r.json()
        items = data.get("data", {}).get("data", [])
        if not items:
            return f"No active {cat} found on Unstop matching '{query}'. Opening search in browser:\n{access_social_platform('unstop', action=cat, query=query)}"

        lines = [f"🏆 UNSTOP LIVE INTEL — {len(items)} Active {cat.capitalize()} Found (Search: '{query or 'All'}'):\n"]
        for i, item in enumerate(items, 1):
            title = item.get("title", "Untitled Opportunity")
            org = item.get("organisation", {}).get("name", "Various Institutes")
            status = item.get("regnRequirements", {}).get("remain_days", "Open")
            views = item.get("viewsCount", 0)
            seo_url = item.get("seo_url") or item.get("public_url")
            full_url = f"https://unstop.com/{seo_url}" if seo_url and not seo_url.startswith("http") else seo_url or "https://unstop.com"

            lines.append(f"{i}. **{title}**")
            lines.append(f"   - Organizer: {org}")
            lines.append(f"   - Status: {status} | Impressions: {views}")
            lines.append(f"   - Direct URL: {full_url}\n")

        return "\n".join(lines).strip()
    except Exception as e:
        # Fallback to browser launch
        webbrowser.open(f"https://unstop.com/{cat}?searchTerm={urllib.parse.quote_plus(query)}")
        return f"Unable to fetch JSON stream directly ({e}). Launched Unstop in your default browser."
