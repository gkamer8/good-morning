"""Weather data fetching tools - Open-Meteo API (free, no key required)."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import httpx


@dataclass
class WeatherCondition:
    """Current weather conditions."""

    location_name: str
    temperature_f: float
    temperature_c: float
    feels_like_f: float
    feels_like_c: float
    humidity: int
    wind_speed_mph: float
    wind_direction: str
    condition: str
    condition_code: int
    precipitation_probability: int
    uv_index: Optional[float] = None


@dataclass
class DailyForecast:
    """Daily weather forecast."""

    date: str
    high_f: float
    high_c: float
    low_f: float
    low_c: float
    condition: str
    precipitation_probability: int
    sunrise: str
    sunset: str


@dataclass
class WeatherForecast:
    """Complete weather forecast for a location."""

    location_name: str
    current: WeatherCondition
    daily: list[DailyForecast]
    alerts: list[str] = None

    def __post_init__(self):
        if self.alerts is None:
            self.alerts = []


# WMO Weather interpretation codes
WMO_CODES = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Foggy",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snow",
    73: "Moderate snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


def wind_direction_from_degrees(degrees: float) -> str:
    """Convert wind direction from degrees to cardinal direction."""
    directions = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                  "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    index = round(degrees / 22.5) % 16
    return directions[index]


def celsius_to_fahrenheit(c: float) -> float:
    """Convert Celsius to Fahrenheit."""
    return (c * 9/5) + 32


def kmh_to_mph(kmh: float) -> float:
    """Convert km/h to mph."""
    return kmh * 0.621371


async def fetch_weather(
    lat: float,
    lon: float,
    location_name: str,
) -> WeatherForecast:
    """Fetch weather data from Open-Meteo API."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Fetch current weather and forecast
        response = await client.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "current": [
                    "temperature_2m",
                    "apparent_temperature",
                    "relative_humidity_2m",
                    "weather_code",
                    "wind_speed_10m",
                    "wind_direction_10m",
                    "uv_index",
                ],
                "daily": [
                    "weather_code",
                    "temperature_2m_max",
                    "temperature_2m_min",
                    "precipitation_probability_max",
                    "sunrise",
                    "sunset",
                ],
                "temperature_unit": "celsius",
                "wind_speed_unit": "kmh",
                "precipitation_unit": "mm",
                "timezone": "auto",
                "forecast_days": 7,
            },
        )
        response.raise_for_status()
        data = response.json()

    current_data = data.get("current", {})
    daily_data = data.get("daily", {})

    # Build current conditions
    temp_c = current_data.get("temperature_2m", 0)
    feels_c = current_data.get("apparent_temperature", temp_c)
    wind_kmh = current_data.get("wind_speed_10m", 0)
    wind_deg = current_data.get("wind_direction_10m", 0)
    weather_code = current_data.get("weather_code", 0)

    current = WeatherCondition(
        location_name=location_name,
        temperature_c=temp_c,
        temperature_f=round(celsius_to_fahrenheit(temp_c), 1),
        feels_like_c=feels_c,
        feels_like_f=round(celsius_to_fahrenheit(feels_c), 1),
        humidity=current_data.get("relative_humidity_2m", 0),
        wind_speed_mph=round(kmh_to_mph(wind_kmh), 1),
        wind_direction=wind_direction_from_degrees(wind_deg),
        condition=WMO_CODES.get(weather_code, "Unknown"),
        condition_code=weather_code,
        precipitation_probability=daily_data.get("precipitation_probability_max", [0])[0],
        uv_index=current_data.get("uv_index"),
    )

    # Build daily forecasts
    daily_forecasts = []
    dates = daily_data.get("time", [])
    highs = daily_data.get("temperature_2m_max", [])
    lows = daily_data.get("temperature_2m_min", [])
    codes = daily_data.get("weather_code", [])
    precip_probs = daily_data.get("precipitation_probability_max", [])
    sunrises = daily_data.get("sunrise", [])
    sunsets = daily_data.get("sunset", [])

    for i, date in enumerate(dates):
        if i >= 7:  # Limit to 7 days
            break

        high_c = highs[i] if i < len(highs) else 0
        low_c = lows[i] if i < len(lows) else 0

        daily_forecasts.append(
            DailyForecast(
                date=date,
                high_c=high_c,
                high_f=round(celsius_to_fahrenheit(high_c), 1),
                low_c=low_c,
                low_f=round(celsius_to_fahrenheit(low_c), 1),
                condition=WMO_CODES.get(codes[i] if i < len(codes) else 0, "Unknown"),
                precipitation_probability=precip_probs[i] if i < len(precip_probs) else 0,
                sunrise=sunrises[i].split("T")[1] if i < len(sunrises) else "",
                sunset=sunsets[i].split("T")[1] if i < len(sunsets) else "",
            )
        )

    return WeatherForecast(
        location_name=location_name,
        current=current,
        daily=daily_forecasts,
        alerts=[],  # Open-Meteo free tier doesn't include alerts
    )


async def get_weather_for_locations(
    locations: list[dict],
) -> list[WeatherForecast]:
    """Fetch weather for multiple locations.

    Args:
        locations: List of dicts with 'name', 'lat', 'lon' keys

    Returns:
        List of WeatherForecast objects
    """
    forecasts = []

    for loc in locations:
        try:
            forecast = await fetch_weather(
                lat=loc["lat"],
                lon=loc["lon"],
                location_name=loc["name"],
            )
            forecasts.append(forecast)
        except Exception as e:
            print(f"Error fetching weather for {loc['name']}: {e}")

    return forecasts


def format_weather_for_agent(forecasts: list[WeatherForecast]) -> str:
    """Format weather data for the Claude agent."""
    if not forecasts:
        return "No weather data available."

    lines = ["# Weather Forecast\n"]

    for forecast in forecasts:
        current = forecast.current
        lines.append(f"## {forecast.location_name}\n")

        # Current conditions
        lines.append("### Current Conditions")
        lines.append(f"- **Temperature:** {current.temperature_f}°F ({current.temperature_c}°C)")
        lines.append(f"- **Feels Like:** {current.feels_like_f}°F ({current.feels_like_c}°C)")
        lines.append(f"- **Conditions:** {current.condition}")
        lines.append(f"- **Humidity:** {current.humidity}%")
        lines.append(f"- **Wind:** {current.wind_speed_mph} mph from the {current.wind_direction}")
        if current.uv_index is not None:
            lines.append(f"- **UV Index:** {current.uv_index}")
        lines.append("")

        # Today's forecast
        if forecast.daily:
            today = forecast.daily[0]
            lines.append("### Today's Forecast")
            lines.append(f"- **High:** {today.high_f}°F / **Low:** {today.low_f}°F")
            lines.append(f"- **Conditions:** {today.condition}")
            lines.append(f"- **Chance of Precipitation:** {today.precipitation_probability}%")
            lines.append(f"- **Sunrise:** {today.sunrise} / **Sunset:** {today.sunset}")
            lines.append("")

        # Extended forecast (next 3 days)
        if len(forecast.daily) > 1:
            lines.append("### Extended Forecast")
            for day in forecast.daily[1:4]:
                # Format date nicely
                try:
                    date_obj = datetime.strptime(day.date, "%Y-%m-%d")
                    day_name = date_obj.strftime("%A")
                except ValueError:
                    day_name = day.date

                lines.append(
                    f"- **{day_name}:** High {day.high_f}°F, Low {day.low_f}°F - "
                    f"{day.condition} ({day.precipitation_probability}% precip)"
                )
            lines.append("")

        # Alerts
        if forecast.alerts:
            lines.append("### ⚠️ Weather Alerts")
            for alert in forecast.alerts:
                lines.append(f"- {alert}")
            lines.append("")

        lines.append("---\n")

    return "\n".join(lines)
