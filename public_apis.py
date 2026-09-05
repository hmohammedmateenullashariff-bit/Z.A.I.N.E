"""
Z.A.I.N.E — Public APIs Integration Layer
Curated zero-authentication, open-access public APIs from https://github.com/public-apis/public-apis:
- Weather & Meteorology: Open-Meteo & Open-Meteo Geocoding
- Cryptocurrencies & Market Prices: CoinGecko Public API
- Real-time Currency Conversion: Frankfurter Exchange Rates
- Dictionary & Vocabulary: Free Dictionary API
- Humor & Inspiration: Official Joke API & ZenQuotes
- Generic Public API Query Tool: Safe dynamic GET client for any public-apis endpoint
"""

import requests
import urllib.parse
from typing import Dict, Any, Optional

DEFAULT_TIMEOUT = 10
HEADERS = {
    "User-Agent": "ZAINE-Jarvis-Assistant/1.0 (Personal AI Assistant)"
}

# WMO Weather interpretation codes (WW)
WMO_CODE_MAP = {
    0: "Clear sky ☀️",
    1: "Mainly clear 🌤️",
    2: "Partly cloudy ⛅",
    3: "Overcast ☁️",
    45: "Fog 🌫️",
    48: "Depositing rime fog 🌫️",
    51: "Light drizzle 🌦️",
    53: "Moderate drizzle 🌦️",
    55: "Dense drizzle 🌧️",
    61: "Slight rain 🌧️",
    63: "Moderate rain 🌧️",
    65: "Heavy rain 🌧️",
    71: "Slight snow fall 🌨️",
    73: "Moderate snow fall 🌨️",
    75: "Heavy snow fall ❄️",
    80: "Slight rain showers 🌦️",
    81: "Moderate rain showers 🌧️",
    82: "Violent rain showers ⛈️",
    95: "Thunderstorm ⛈️",
    96: "Thunderstorm with slight hail ⛈️",
    99: "Thunderstorm with heavy hail ⛈️",
}


def get_weather(city: str = "") -> str:
    """
    Fetches real-time weather and temperature for any city using Open-Meteo public API (zero key required).
    If city is omitted, defaults to geolocation or Bengaluru.
    """
    target_city = city.strip() if city and city.strip() else "Bengaluru"

    try:
        # 1. Geocode city name to lat/lon
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={urllib.parse.quote(target_city)}&count=1&language=en&format=json"
        geo_resp = requests.get(geo_url, headers=HEADERS, timeout=DEFAULT_TIMEOUT)
        geo_data = geo_resp.json()

        results = geo_data.get("results")
        if not results:
            return f"Could not find coordinates for city '{target_city}', Sir."

        top = results[0]
        lat = top.get("latitude")
        lon = top.get("longitude")
        name = top.get("name")
        country = top.get("country", "")
        admin1 = top.get("admin1", "")

        # 2. Fetch current weather from Open-Meteo
        weather_url = (
            f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
            f"&current=temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m"
            f"&timezone=auto"
        )
        w_resp = requests.get(weather_url, headers=HEADERS, timeout=DEFAULT_TIMEOUT)
        w_data = w_resp.json()
        curr = w_data.get("current", {})

        temp = curr.get("temperature_2m", "N/A")
        feels_like = curr.get("apparent_temperature", "N/A")
        humidity = curr.get("relative_humidity_2m", "N/A")
        wind = curr.get("wind_speed_10m", "N/A")
        w_code = curr.get("weather_code", 0)
        condition = WMO_CODE_MAP.get(w_code, "Fair")

        loc_str = f"{name}, {admin1}, {country}".replace(", ,", ",").strip(", ")
        return (
            f"Weather Report for {loc_str}:\n"
            f"• Condition: {condition}\n"
            f"• Temperature: {temp}°C (Feels like {feels_like}°C)\n"
            f"• Humidity: {humidity}%\n"
            f"• Wind Speed: {wind} km/h"
        )
    except Exception as e:
        return f"Error retrieving weather for '{target_city}': {e}"


def get_crypto_price(coin: str = "bitcoin") -> str:
    """
    Fetches real-time price and 24h market change for any cryptocurrency (bitcoin, ethereum, solana, etc.)
    using CoinGecko Public API (zero key required).
    """
    clean_coin = coin.lower().strip().replace(" ", "-")
    coin_aliases = {
        "btc": "bitcoin",
        "eth": "ethereum",
        "sol": "solana",
        "doge": "dogecoin",
        "ada": "cardano",
        "xrp": "ripple",
    }
    coin_id = coin_aliases.get(clean_coin, clean_coin)

    url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd,inr&include_24hr_change=true"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=DEFAULT_TIMEOUT)
        data = resp.json()
        if not data or coin_id not in data:
            return f"Could not find cryptocurrency '{coin}'. Please try full name like 'bitcoin' or 'ethereum'."

        coin_data = data[coin_id]
        usd = coin_data.get("usd", 0)
        inr = coin_data.get("inr", 0)
        change_24h = coin_data.get("usd_24h_change", 0.0)
        trend = "📈" if change_24h >= 0 else "📉"

        return (
            f"Cryptocurrency Market Update ({coin_id.upper()}):\n"
            f"• USD: ${usd:,.2f}\n"
            f"• INR: ₹{inr:,.2f}\n"
            f"• 24h Change: {trend} {change_24h:+.2f}%"
        )
    except Exception as e:
        return f"Error fetching crypto price for '{coin}': {e}"


def convert_currency(amount: float, from_curr: str = "USD", to_curr: str = "INR") -> str:
    """
    Converts currency using real-time European Central Bank rates via Frankfurter Public API (zero key required).
    Example: convert_currency(100, 'USD', 'INR')
    """
    f_c = from_curr.upper().strip()
    t_c = to_curr.upper().strip()

    if f_c == t_c:
        return f"{amount} {f_c} = {amount} {t_c}"

    url = f"https://api.frankfurter.dev/v1/latest?amount={amount}&from={f_c}&to={t_c}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=DEFAULT_TIMEOUT)
        data = resp.json()
        rates = data.get("rates", {})
        if t_c not in rates:
            return f"Could not convert from {f_c} to {t_c}. Unsupported currency code."

        converted = rates[t_c]
        date_str = data.get("date", "latest")
        return f"Currency Exchange ({date_str}):\n{amount:,.2f} {f_c} = {converted:,.2f} {t_c} (Rate: 1 {f_c} = {converted/amount:,.4f} {t_c})"
    except Exception as e:
        return f"Error converting currency: {e}"


def get_word_definition(word: str) -> str:
    """
    Fetches meanings, phonetic transcription, part of speech, and usage examples for any English word
    using Free Dictionary API (zero key required).
    """
    clean_word = word.strip().lower()
    url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{clean_word}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=DEFAULT_TIMEOUT)
        if resp.status_code == 404:
            return f"No dictionary entry found for '{word}', Sir."
        data = resp.json()
        if not data or not isinstance(data, list):
            return f"No dictionary entry found for '{word}'."

        entry = data[0]
        phonetic = entry.get("phonetic", "")
        meanings = entry.get("meanings", [])

        lines = [f"Dictionary Entry for '{clean_word.capitalize()}' {phonetic}:"]
        for m in meanings[:3]:
            pos = m.get("partOfSpeech", "")
            defs = m.get("definitions", [])
            if defs:
                top_def = defs[0].get("definition", "")
                example = defs[0].get("example", "")
                ex_str = f' (e.g. "{example}")' if example else ""
                lines.append(f"• [{pos}] {top_def}{ex_str}")

        return "\n".join(lines)
    except Exception as e:
        return f"Error fetching definition for '{word}': {e}"


def get_random_joke() -> str:
    """Fetches a random programming or general joke from Official Joke API."""
    url = "https://official-joke-api.appspot.com/random_joke"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=DEFAULT_TIMEOUT)
        data = resp.json()
        setup = data.get("setup", "")
        punchline = data.get("punchline", "")
        return f"{setup}\n... {punchline} 😄"
    except Exception as e:
        return f"Error fetching joke: {e}"


def get_inspirational_quote() -> str:
    """Fetches an inspirational quote from ZenQuotes API."""
    url = "https://zenquotes.io/api/random"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=DEFAULT_TIMEOUT)
        data = resp.json()
        if data and isinstance(data, list):
            q = data[0].get("q", "")
            a = data[0].get("a", "Unknown")
            return f'"{q}" — {a}'
        return "Stay focused and build great things."
    except Exception as e:
        return f"Error fetching quote: {e}"


def query_public_api(endpoint_url: str, params: Optional[Dict[str, Any]] = None) -> str:
    """
    Safely queries any public REST API endpoint from https://github.com/public-apis/public-apis
    and returns formatted text/JSON (up to 1000 characters).
    """
    clean_url = endpoint_url.strip()
    if not clean_url.startswith("http://") and not clean_url.startswith("https://"):
        clean_url = "https://" + clean_url

    try:
        resp = requests.get(clean_url, params=params, headers=HEADERS, timeout=12)
        content_type = resp.headers.get("Content-Type", "")
        if "application/json" in content_type:
            data = resp.json()
            import json
            formatted = json.dumps(data, indent=2)
            if len(formatted) > 1200:
                formatted = formatted[:1200] + "\n... [truncated]"
            return f"API Response ({resp.status_code}):\n{formatted}"
        else:
            text = resp.text.strip()
            if len(text) > 1000:
                text = text[:1000] + "\n... [truncated]"
            return f"API Response ({resp.status_code}):\n{text}"
    except Exception as e:
        return f"Error querying public API at {clean_url}: {e}"
