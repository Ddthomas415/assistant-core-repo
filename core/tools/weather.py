"""
Weather tool using Open-Meteo (https://open-meteo.com/).

No API key required. Uses IP-based geolocation as default location,
or accepts explicit lat/lon or a city name (resolved via geocoding API).
"""
from __future__ import annotations

from typing import Any


_GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
_WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
_IP_GEO_URL  = "https://ipapi.co/json/"

_WMO_CODES: dict[int, str] = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Rime fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
    80: "Slight showers", 81: "Moderate showers", 82: "Heavy showers",
    95: "Thunderstorm", 96: "Thunderstorm w/ hail", 99: "Thunderstorm w/ heavy hail",
}


def get_weather(location: str | None = None) -> dict[str, Any]:
    """
    Fetch current weather for a location string or current IP location.

    Returns:
        {
            "location":     str,
            "temperature_c": float,
            "feels_like_c":  float,
            "humidity":     int,
            "wind_kph":     float,
            "condition":    str,
            "error":        str | None,
        }
    """
    import requests  # noqa: PLC0415

    try:
        lat, lon, place = _resolve_location(location, requests)
    except Exception as exc:
        return _error(str(exc))

    try:
        params = {
            "latitude":  lat,
            "longitude": lon,
            "current":   "temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,weather_code",
            "wind_speed_unit": "kmh",
            "timezone":  "auto",
        }
        r = requests.get(_WEATHER_URL, params=params, timeout=8)
        r.raise_for_status()
        d = r.json()
        c = d["current"]

        condition = _WMO_CODES.get(c.get("weather_code", 0), "Unknown")

        return {
            "location":      place,
            "temperature_c": round(c["temperature_2m"], 1),
            "feels_like_c":  round(c["apparent_temperature"], 1),
            "humidity":      int(c["relative_humidity_2m"]),
            "wind_kph":      round(c["wind_speed_10m"], 1),
            "condition":     condition,
            "error":         None,
        }
    except Exception as exc:
        return _error(str(exc))


def format_result(data: dict[str, Any]) -> str:
    """Format weather result for the assistant message."""
    if data.get("error"):
        return f"Weather unavailable: {data['error']}"
    return (
        f"Weather in {data['location']}:\n"
        f"  {data['condition']}\n"
        f"  Temperature: {data['temperature_c']}°C (feels like {data['feels_like_c']}°C)\n"
        f"  Humidity: {data['humidity']}%\n"
        f"  Wind: {data['wind_kph']} km/h"
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_location(
    location: str | None,
    requests: Any,
) -> tuple[float, float, str]:
    """Return (lat, lon, display_name)."""
    if not location:
        return _ip_location(requests)

    r = requests.get(
        _GEOCODE_URL,
        params={"name": location, "count": 1, "language": "en", "format": "json"},
        timeout=8,
    )
    r.raise_for_status()
    results = r.json().get("results", [])
    if not results:
        raise ValueError(f"Location not found: {location}")
    hit = results[0]
    name = hit.get("name", location)
    country = hit.get("country", "")
    return hit["latitude"], hit["longitude"], f"{name}, {country}".rstrip(", ")


def _ip_location(requests: Any) -> tuple[float, float, str]:
    r = requests.get(_IP_GEO_URL, timeout=6)
    r.raise_for_status()
    d = r.json()
    lat = float(d.get("latitude", 0))
    lon = float(d.get("longitude", 0))
    city = d.get("city", "Unknown")
    country = d.get("country_name", "")
    return lat, lon, f"{city}, {country}".rstrip(", ")


def _error(msg: str) -> dict[str, Any]:
    return {
        "location": "", "temperature_c": 0.0, "feels_like_c": 0.0,
        "humidity": 0, "wind_kph": 0.0, "condition": "", "error": msg,
    }
