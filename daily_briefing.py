# FOR LOCAL TESTING VIA .ENV

from dotenv import load_dotenv
load_dotenv()

import os
import sys
import json
import html
import time
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timezone, timedelta

import requests
import anthropic
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

CALGARY_LAT = 51.0447
CALGARY_LON = -114.0719
MST = timezone(timedelta(hours=-7))

WMO_CODES = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
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
    71: "Slight snowfall",
    73: "Moderate snowfall",
    75: "Heavy snowfall",
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

WMO_EMOJI = {
    0: "\u2600\ufe0f",
    1: "\U0001f324\ufe0f", 2: "\u26c5",
    3: "\u2601\ufe0f",
    45: "\U0001f32b\ufe0f", 48: "\U0001f32b\ufe0f",
    51: "\U0001f327\ufe0f", 53: "\U0001f327\ufe0f", 55: "\U0001f327\ufe0f",
    56: "\U0001f327\ufe0f", 57: "\U0001f327\ufe0f",
    61: "\U0001f327\ufe0f", 63: "\U0001f327\ufe0f", 65: "\U0001f327\ufe0f",
    66: "\U0001f327\ufe0f", 67: "\U0001f327\ufe0f",
    71: "\U0001f328\ufe0f", 73: "\U0001f328\ufe0f", 75: "\U0001f328\ufe0f", 77: "\U0001f328\ufe0f",
    80: "\U0001f326\ufe0f", 81: "\U0001f326\ufe0f", 82: "\U0001f326\ufe0f",
    85: "\U0001f328\ufe0f", 86: "\U0001f328\ufe0f",
    95: "\u26c8\ufe0f", 96: "\u26c8\ufe0f", 99: "\u26c8\ufe0f",
}


def fetch_calendar_events():
    """Fetch today's and tomorrow's events from Google Calendar using OAuth refresh token."""
    try:
        creds = Credentials(
            token=None,
            refresh_token=os.environ["GOOGLE_REFRESH_TOKEN"], # TIME BASED TOKEN
            token_uri="https://oauth2.googleapis.com/token",
            client_id=os.environ["GOOGLE_CLIENT_ID"],
            client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
        )

        service = build("calendar", "v3", credentials=creds)

        now = datetime.now(MST)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_range = start_of_day + timedelta(days=2)

        events_result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=start_of_day.isoformat(),
                timeMax=end_of_range.isoformat(),
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )

        events = []
        for event in events_result.get("items", []):
            events.append(
                {
                    "summary": event.get("summary", "Untitled"),
                    "start": event["start"].get(
                        "dateTime", event["start"].get("date")
                    ),
                    "end": event["end"].get("dateTime", event["end"].get("date")),
                    "location": event.get("location", ""),
                    "description": event.get("description", "")[:200],
                }
            )

        return events
    except Exception as e:
        print(f"Error fetching calendar events: {e}", file=sys.stderr)
        return None


def fetch_weather():
    """Fetch today's weather forecast for Calgary from Open-Meteo."""
    try:
        resp = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": CALGARY_LAT,
                "longitude": CALGARY_LON,
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code,wind_speed_10m_max,sunrise,sunset",
                "hourly": "temperature_2m,weather_code",
                "timezone": "America/Edmonton",
                "forecast_days": 2,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        daily = data["daily"]
        hourly = data["hourly"]

        # Build hourly list sliced to 6AM today -> 5AM tomorrow (24 hours)
        hourly_data = []
        for i, t in enumerate(hourly["time"]):
            hourly_data.append({
                "time": t,
                "temp_c": hourly["temperature_2m"][i],
                "weather_code": hourly["weather_code"][i],
            })

        # Filter to 6AM today through 5AM tomorrow
        today_str = datetime.now(MST).strftime("%Y-%m-%d")
        start_hour = f"{today_str}T06:00"
        filtered_hourly = []
        started = False
        for entry in hourly_data:
            if entry["time"] == start_hour:
                started = True
            if started:
                filtered_hourly.append(entry)
            if started and len(filtered_hourly) == 24:
                break

        return {
            "high_c": daily["temperature_2m_max"][0],
            "low_c": daily["temperature_2m_min"][0],
            "precipitation_probability": daily["precipitation_probability_max"][0],
            "weather_code": daily["weather_code"][0],
            "weather_description": WMO_CODES.get(
                daily["weather_code"][0], "Unknown"
            ),
            "wind_speed_kmh": daily["wind_speed_10m_max"][0],
            "sunrise": daily["sunrise"][0],
            "sunset": daily["sunset"][0],
            "hourly": filtered_hourly,
        }
    except Exception as e:
        print(f"Error fetching weather: {e}", file=sys.stderr)
        return None


def fetch_pollen():
    """Fetch today's pollen data for Calgary from Open-Meteo Air Quality API."""
    try:
        resp = requests.get(
            "https://air-quality-api.open-meteo.com/v1/air-quality",
            params={
                "latitude": CALGARY_LAT,
                "longitude": CALGARY_LON,
                "hourly": "birch_pollen,grass_pollen,ragweed_pollen,alder_pollen,mugwort_pollen",
                "timezone": "America/Edmonton",
                "forecast_days": 1,
            },
            timeout=10,
        )
        resp.raise_for_status()
        hourly = resp.json()["hourly"]

        pollen_types = {
            "Birch": "birch_pollen",
            "Grass": "grass_pollen",
            "Ragweed": "ragweed_pollen",
            "Alder": "alder_pollen",
            "Mugwort": "mugwort_pollen",
        }

        peaks = {}
        for label, key in pollen_types.items():
            values = [v for v in hourly.get(key, []) if v is not None]
            peaks[label] = max(values) if values else 0

        dominant_type = max(peaks, key=peaks.get)
        dominant_count = peaks[dominant_type]

        if dominant_count == 0:
            return None

        if dominant_count < 20:
            severity = "Low"
        elif dominant_count < 50:
            severity = "Moderate"
        elif dominant_count < 150:
            severity = "High"
        else:
            severity = "Very High"

        return {
            **peaks,
            "dominant_type": dominant_type,
            "dominant_count": dominant_count,
            "severity": severity,
        }
    except Exception as e:
        print(f"Error fetching pollen: {e}", file=sys.stderr)
        return None


def fetch_apod():
    """Fetch NASA's Astronomy Picture of the Day with retries."""
    url = "http://api.nasa.gov/planetary/apod"
    params = {"api_key": os.environ["NASA_API_KEY"]}

    max_retries = 10 
    timeout = 10

    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(url, params=params, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()

            return {
                "title": data.get("title", ""),
                "explanation": data.get("explanation", ""),
                "url": data.get("url", ""),
                "hdurl": data.get("hdurl", ""),
                "media_type": data.get("media_type", "image"),
                "copyright": data.get("copyright", ""),
            }

        except Exception as e:
            print(f"Attempt {attempt} failed: {e}", file=sys.stderr)

            if attempt < max_retries:
                time.sleep(1)  # small delay before retry
            else:
                print("Error fetching APOD after 3 attempts.", file=sys.stderr)
                return None



def _format_time(iso_str):
    """Format an ISO datetime string to readable time (e.g., '6:30 AM')."""
    try:
        dt = datetime.fromisoformat(iso_str)
        hour = dt.hour % 12 or 12
        minute = dt.strftime("%M")
        ampm = "AM" if dt.hour < 12 else "PM"
        return f"{hour}:{minute} {ampm}"
    except (ValueError, AttributeError):
        return iso_str


def _format_day_header(iso_str):
    """Return 'Today' or 'Tomorrow' based on the event's date."""
    try:
        dt = datetime.fromisoformat(iso_str)
        today = datetime.now(MST).date()
        event_date = dt.date()
        delta = (event_date - today).days
        if delta == 0:
            return "Today"
        elif delta == 1:
            return "Tomorrow"
        else:
            return event_date.strftime("%A, %b %d")
    except (ValueError, AttributeError):
        return "Upcoming"


def calculate_moon_phase(date=None):
    """Calculate moon phase for a given date using the synodic month cycle."""
    if date is None:
        date = datetime.now(MST).date()
    reference_new_moon = datetime(2000, 1, 6).date()
    days_since = (date - reference_new_moon).days
    synodic_month = 29.53059
    phase_progress = (days_since % synodic_month) / synodic_month
    phases = [
        (0.0625, "New Moon", "\U0001f311"),
        (0.1875, "Waxing Crescent", "\U0001f312"),
        (0.3125, "First Quarter", "\U0001f313"),
        (0.4375, "Waxing Gibbous", "\U0001f314"),
        (0.5625, "Full Moon", "\U0001f315"),
        (0.6875, "Waning Gibbous", "\U0001f316"),
        (0.8125, "Last Quarter", "\U0001f317"),
        (0.9375, "Waning Crescent", "\U0001f318"),
    ]
    for threshold, name, emoji in phases:
        if phase_progress < threshold:
            return {"name": name, "emoji": emoji}
    return {"name": "New Moon", "emoji": "\U0001f311"}


def _build_widget(label, content_html, link=None):
    """Build a single Apple glass-style widget card."""
    inner = f"""<p style="margin:0 0 16px; font-size:11px; font-weight:600; color:#86868b; text-transform:uppercase; letter-spacing:1px;">{label}</p>
              {content_html}"""
    if link:
        inner = f'<a href="{link}" target="_blank" style="display:block; text-decoration:none; color:inherit;">{inner}</a>'
    return f"""
        <tr><td style="padding-bottom:12px;">
          <table width="100%" cellpadding="0" cellspacing="0" border="0" style="
            background-color:#ffffff;
            border:1px solid #e5e5ea;
            border-radius:16px;
            overflow:hidden;
            box-shadow:0 1px 4px rgba(0,0,0,0.04);
          ">
            <tr><td style="padding:24px 28px;">
              {inner}
            </td></tr>
          </table>
        </td></tr>"""


def _temp_bar_color(temp, min_temp, max_temp):
    """Return hex color for temperature bar, blue (cold) to orange (warm)."""
    if max_temp == min_temp:
        return "#5AC8FA"
    ratio = max(0, min(1, (temp - min_temp) / (max_temp - min_temp)))
    r = int(0x5A + ratio * (0xFF - 0x5A))
    g = int(0xC8 + ratio * (0x95 - 0xC8))
    b = int(0xFA + ratio * (0x00 - 0xFA))
    return f"#{r:02X}{g:02X}{b:02X}"


def _build_hourly_chart(hourly_data):
    """Build a scrollable HTML bar chart for hourly temperature data."""
    if not hourly_data:
        return ""

    temps = [h["temp_c"] for h in hourly_data]
    min_temp = min(temps)
    max_temp = max(temps)

    col_width = 45
    total_width = col_width * len(hourly_data)
    bar_max_height = 60

    # Build rows: emoji, temp, bar, time label
    emoji_cells = []
    temp_cells = []
    bar_cells = []
    time_cells = []

    for h in hourly_data:
        emoji = WMO_EMOJI.get(h["weather_code"], "\u2601\ufe0f")
        temp = h["temp_c"]
        color = _temp_bar_color(temp, min_temp, max_temp)

        if max_temp == min_temp:
            bar_height = bar_max_height // 2
        else:
            bar_height = int(20 + ((temp - min_temp) / (max_temp - min_temp)) * (bar_max_height - 20))

        # Parse hour label
        try:
            dt = datetime.fromisoformat(h["time"])
            hour = dt.hour
            if hour == 0:
                label = "12A"
            elif hour < 12:
                label = f"{hour}A"
            elif hour == 12:
                label = "12P"
            else:
                label = f"{hour - 12}P"
        except (ValueError, AttributeError):
            label = ""

        cell_style = f"text-align:center; width:{col_width}px; min-width:{col_width}px;"

        emoji_cells.append(f'<td style="{cell_style} font-size:16px; padding-bottom:2px;">{emoji}</td>')
        temp_cells.append(f'<td style="{cell_style} font-size:12px; font-weight:600; color:#1d1d1f; padding-bottom:4px;">{temp:.0f}\u00b0</td>')
        bar_cells.append(
            f'<td style="{cell_style} vertical-align:bottom; height:{bar_max_height + 8}px; padding:0 4px;">'
            f'<div style="width:20px; height:{bar_height}px; background:{color}; border-radius:4px; margin:0 auto;"></div>'
            f'</td>'
        )
        time_cells.append(f'<td style="{cell_style} font-size:10px; color:#86868b; padding-top:4px;">{label}</td>')

    chart_table = f"""<table cellpadding="0" cellspacing="0" border="0" style="width:{total_width}px;">
      <tr>{"".join(emoji_cells)}</tr>
      <tr>{"".join(temp_cells)}</tr>
      <tr>{"".join(bar_cells)}</tr>
      <tr>{"".join(time_cells)}</tr>
    </table>"""

    return f"""<div style="overflow-x:auto; -webkit-overflow-scrolling:touch; margin-top:16px; padding-bottom:4px;">
      {chart_table}
    </div>"""


def _build_weather_widget(weather, pollen=None, quip=""):
    """Build weather widget HTML from API data."""
    if weather is None:
        content = '<p style="margin:0; font-size:15px; color:#86868b;">Weather data unavailable.</p>'
        return _build_widget("\u2601\ufe0f Weather", content, link="https://weather.gc.ca/en/location/index.html?coords=51.046,-114.057")

    sunrise = _format_time(weather["sunrise"])
    sunset = _format_time(weather["sunset"])
    moon = calculate_moon_phase()

    quip_html = ""
    if quip:
        quip_html = f'<p style="margin:16px 0 0; font-size:14px; color:#6e6e73; font-style:italic;">\u201c{html.escape(quip)}\u201d</p>'

    # Hourly chart
    chart_html = _build_hourly_chart(weather.get("hourly", []))

    # Pollen row (conditional)
    pollen_html = ""
    if pollen:
        severity_colors = {"Low": "#34C759", "Moderate": "#FF9500", "High": "#FF3B30", "Very High": "#AF52DE"}
        sev_color = severity_colors.get(pollen["severity"], "#86868b")
        pollen_html = f"""
              <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:12px;">
                <tr>
                  <td style="padding:8px 0; font-size:11px; color:#86868b; text-transform:uppercase; letter-spacing:0.5px;">Pollen</td>
                </tr>
                <tr>
                  <td style="font-size:15px; font-weight:600; color:{sev_color};">
                    \U0001f927 {html.escape(pollen['severity'])} \u2014 {html.escape(pollen['dominant_type'])} ({pollen['dominant_count']:.0f} gr/m\u00b3)
                  </td>
                </tr>
              </table>"""

    content = f"""
              <table width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td style="width:50%;">
                    <p style="margin:0; font-size:11px; color:#86868b; text-transform:uppercase; letter-spacing:0.5px;">High</p>
                    <p style="margin:4px 0 0; font-size:28px; font-weight:700; color:#1d1d1f; letter-spacing:-1px;">{weather['high_c']:.0f}\u00b0C</p>
                  </td>
                  <td style="width:50%;">
                    <p style="margin:0; font-size:11px; color:#86868b; text-transform:uppercase; letter-spacing:0.5px;">Low</p>
                    <p style="margin:4px 0 0; font-size:28px; font-weight:700; color:#1d1d1f; letter-spacing:-1px;">{weather['low_c']:.0f}\u00b0C</p>
                  </td>
                </tr>
              </table>
              <p style="margin:12px 0 0; font-size:17px; color:#1d1d1f; font-weight:500;">{html.escape(weather['weather_description'])}</p>
              {chart_html}
              <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:16px;">
                <tr>
                  <td style="padding:8px 0; font-size:11px; color:#86868b; text-transform:uppercase; letter-spacing:0.5px; width:33%;">Precip</td>
                  <td style="padding:8px 0; font-size:11px; color:#86868b; text-transform:uppercase; letter-spacing:0.5px; width:33%;">Wind</td>
                  <td style="padding:8px 0; font-size:11px; color:#86868b; text-transform:uppercase; letter-spacing:0.5px; width:34%;">Moon</td>
                </tr>
                <tr>
                  <td style="font-size:17px; font-weight:600; color:#1d1d1f;">{weather['precipitation_probability']}%</td>
                  <td style="font-size:17px; font-weight:600; color:#1d1d1f;">{weather['wind_speed_kmh']:.0f} km/h</td>
                  <td style="font-size:15px; font-weight:600; color:#1d1d1f;">{moon['emoji']} {moon['name']}</td>
                </tr>
              </table>
              <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:12px;">
                <tr>
                  <td style="padding:8px 0; font-size:11px; color:#86868b; text-transform:uppercase; letter-spacing:0.5px; width:50%;">Sunrise</td>
                  <td style="padding:8px 0; font-size:11px; color:#86868b; text-transform:uppercase; letter-spacing:0.5px; width:50%;">Sunset</td>
                </tr>
                <tr>
                  <td style="font-size:17px; font-weight:600; color:#1d1d1f;">{sunrise}</td>
                  <td style="font-size:17px; font-weight:600; color:#1d1d1f;">{sunset}</td>
                </tr>
              </table>
              {pollen_html}
              {quip_html}"""

    return _build_widget("\u2601\ufe0f Weather", content, link="https://weather.gc.ca/en/location/index.html?coords=51.046,-114.057")


def _build_calendar_widget(events):
    """Build calendar widget HTML from events data, grouped by day."""
    if events is None:
        content = '<p style="margin:0; font-size:15px; color:#86868b;">Calendar data unavailable.</p>'
        return _build_widget("📅 Schedule", content, link="https://calendar.google.com/calendar/u/0/r")

    if not events:
        content = '<p style="margin:0; font-size:15px; color:#86868b;">Nothing scheduled \u2014 enjoy the open days!</p>'
        return _build_widget("📅 Schedule", content, link="https://calendar.google.com/calendar/u/0/r")

    from collections import OrderedDict
    days = OrderedDict()
    for e in events:
        date_key = e["start"][:10]
        days.setdefault(date_key, []).append(e)

    items_html = []
    is_first_day = True

    for date_key, day_events in days.items():
        day_label = _format_day_header(date_key)

        if not is_first_day:
            items_html.append(
                '<tr><td style="padding:14px 0 6px;"><div style="border-top:2px solid #e5e5ea; height:0;"></div></td></tr>'
            )

        items_html.append(f'''
              <tr><td style="padding:{'0' if is_first_day else '8px'} 0 10px;">
                <p style="margin:0; font-size:13px; font-weight:700; color:#1d1d1f; text-transform:uppercase; letter-spacing:0.5px;">{html.escape(day_label)}</p>
              </td></tr>''')

        is_first_day = False

        for j, e in enumerate(day_events):
            start, end = e["start"], e["end"]
            if "T" in start:
                time_str = f"{_format_time(start)} \u2013 {_format_time(end)}"
            else:
                time_str = "All Day"

            location_html = ""
            if e.get("location"):
                location_html = f'<p style="margin:4px 0 0; font-size:13px; color:#86868b;">📍 {html.escape(e["location"])}</p>'

            separator = ""
            if j > 0:
                separator = '<tr><td style="padding:10px 0;"><div style="border-top:1px solid #f2f2f7; height:0;"></div></td></tr>'

            items_html.append(f"""
              {separator}
              <tr><td>
                <p style="margin:0; font-size:13px; color:#86868b; font-weight:500;">{time_str}</p>
                <p style="margin:4px 0 0; font-size:17px; color:#1d1d1f; font-weight:600;">{html.escape(e['summary'])}</p>
                {location_html}
              </td></tr>""")

    content = f'<table width="100%" cellpadding="0" cellspacing="0" border="0">{"".join(items_html)}</table>'
    return _build_widget("📅 Schedule", content, link="https://calendar.google.com/calendar/u/0/r")


def _build_apod_widget(apod):
    """Build NASA APOD widget from API data."""
    if apod is None:
        content = '<p style="margin:0; font-size:15px; color:#86868b;">APOD data unavailable.</p>'
        return _build_widget("\U0001f52d Space", content)

    title = html.escape(apod["title"])
    explanation = html.escape(apod["explanation"])
    # Truncate long explanations
    if len(explanation) > 300:
        explanation = explanation[:297] + "..."

    image_html = ""
    if apod["media_type"] == "image" and apod["url"]:
        image_html = f'<img src="{html.escape(apod["url"])}" alt="{title}" style="width:100%; border-radius:10px; display:block; margin-bottom:16px;">'

    copyright_html = ""
    if apod["copyright"]:
        copyright_html = f'<p style="margin:12px 0 0; font-size:11px; color:#aeaeb2;">&copy; {html.escape(apod["copyright"])}</p>'

    content = f"""
              {image_html}
              <p style="margin:0; font-size:17px; font-weight:600; color:#1d1d1f;">{title}</p>
              <p style="margin:8px 0 0; font-size:14px; color:#6e6e73; line-height:1.5;">{explanation}</p>
              {copyright_html}"""

    apod_link = apod.get("hdurl") or apod.get("url") or None
    return _build_widget("\U0001f52d Space", content, link=apod_link)


def _build_digest_widget(digest_text):
    """Build daily digest widget from Claude-generated content."""
    content = f'<p style="margin:0; font-size:15px; color:#1d1d1f; line-height:1.6;">{html.escape(digest_text)}</p>'
    return _build_widget("\u2728 Daily Digest", content)


def _build_email(date_str, greeting, widgets_html, signoff):
    """Assemble the full email with Apple glass design."""
    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin:0; padding:0; background-color:#f2f2f7; font-family:-apple-system,BlinkMacSystemFont,'SF Pro Text','Segoe UI',system-ui,Helvetica,Arial,sans-serif; -webkit-font-smoothing:antialiased; -moz-osx-font-smoothing:grayscale;">
  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#f2f2f7;">
    <tr><td align="center" style="padding:48px 24px;">
      <table width="560" cellpadding="0" cellspacing="0" border="0" style="max-width:560px; width:100%;">

        <!-- Header -->
        <tr><td style="padding-bottom:32px; text-align:center;">
          <p style="margin:0; font-size:17px; color:#1d1d1f; line-height:1.5;">{html.escape(greeting)}</p>
          <p style="margin:8px 0 0; font-size:13px; color:#aeaeb2; font-weight:500; letter-spacing:0.3px;">{html.escape(date_str)} \u00b7 Calgary, AB</p>
        </td></tr>

        <!-- Widgets -->
        {widgets_html}

        <!-- Footer -->
        <tr><td style="padding-top:24px; text-align:center;">
          <p style="margin:0; font-size:15px; color:#6e6e73;">{html.escape(signoff)}</p>
        </td></tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _generate_dynamic_content(events, weather, pollen=None):
    """Use Claude to generate witty, dynamic content for the briefing."""
    client = anthropic.Anthropic()
    today = datetime.now(MST)
    today_str = today.strftime("%A, %B %d, %Y")

    context_parts = []
    if weather:
        context_parts.append(
            f"Weather: {weather['weather_description']}, "
            f"High {weather['high_c']}\u00b0C, Low {weather['low_c']}\u00b0C, "
            f"Precip {weather['precipitation_probability']}%"
        )
    if events:
        from collections import OrderedDict
        days = OrderedDict()
        for e in events:
            date_key = e["start"][:10]
            days.setdefault(date_key, []).append(e)
        calendar_lines = []
        for date_key, day_events in days.items():
            day_label = _format_day_header(date_key)
            summaries = ", ".join(ev["summary"] for ev in day_events)
            calendar_lines.append(f"{day_label}: {len(day_events)} event(s) \u2014 {summaries}")
        context_parts.append("Calendar:\n" + "\n".join(calendar_lines))
    elif events is not None:
        context_parts.append("Calendar: All clear for today and tomorrow!")
    if pollen and pollen.get("severity") not in (None, "Low"):
        context_parts.append(f"Pollen: {pollen['severity']} ({pollen['dominant_type']})")

    context = "\n".join(context_parts) if context_parts else "No data available."

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=512,
        system=(
            "You write content for a daily briefing email. Your tone is warm, witty, "
            "and comedic \u2014 like a funny, well-read friend who keeps things light. "
            "Keep everything brief and punchy.\n\n"
            "Return ONLY a JSON object with these exact keys:\n"
            '- "greeting": A fun morning greeting (1-2 sentences). '
            "Reference the day of week, weather, or something timely.\n"
            '- "weather_quip": A witty one-liner about today\'s weather (1 short sentence).\n'
            '- "digest": 2-3 sentences of entertaining commentary. Include a fun fact '
            "about today's date, something happening in the world, or comedic life advice. "
            "Keep it light and make the reader smile.\n"
            '- "signoff": A brief, funny sign-off (1 sentence).\n\n'
            "Return ONLY valid JSON. No markdown code fences or extra text."
        ),
        messages=[
            {
                "role": "user",
                "content": f"Date: {today_str}\nLocation: Calgary, AB\n\n{context}",
            }
        ],
    )

    try:
        text = message.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        return json.loads(text)
    except (json.JSONDecodeError, IndexError, KeyError):
        return {
            "greeting": f"Good morning! Happy {today.strftime('%A')}.",
            "weather_quip": "",
            "digest": "Stay curious, stay caffeinated.",
            "signoff": "Have a great day!",
        }


def compose_briefing(events, weather, apod, pollen=None):
    """Compose the full briefing email with Apple glass-style widgets."""
    today = datetime.now(MST).strftime("%A, %B %d, %Y")

    print("Generating dynamic content with Claude...")
    dynamic = _generate_dynamic_content(events, weather, pollen)

    weather_widget = _build_weather_widget(weather, pollen=pollen, quip=dynamic.get("weather_quip", ""))
    calendar_widget = _build_calendar_widget(events)
    apod_widget = _build_apod_widget(apod)
    digest_widget = _build_digest_widget(dynamic.get("digest", ""))

    widgets_html = weather_widget + calendar_widget + apod_widget + digest_widget

    return _build_email(
        today,
        dynamic.get("greeting", f"Good morning! Happy {datetime.now(MST).strftime('%A')}."),
        widgets_html,
        dynamic.get("signoff", "Have a great day!"),
    )


def send_email(subject, html_body):
        
    email = os.environ['GMAIL_ADDRESS']
    app_password = os.environ['GMAIL_APP_PASSWORD']
    to_email = os.environ['TO_EMAIL'] or email # DEFAULT TO EMAIL SELF IF NOT PROVIDED

    msg = MIMEText(html_body, "html")
    msg["Subject"] = subject
    msg["From"] = email
    msg["To"] = to_email

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(email, app_password)
        server.send_message(msg)

    print("✅ HTML email sent!")



def main():
    print("Fetching calendar events...")
    events = fetch_calendar_events()

    print("Fetching weather forecast...")
    weather = fetch_weather()

    print("Fetching pollen data...")
    pollen = fetch_pollen()

    print("Fetching NASA APOD...")
    apod = fetch_apod()

    print("Composing briefing with Claude...")
    briefing_html = compose_briefing(events, weather, apod, pollen)
    
    today = datetime.now(MST).strftime("%A, %B %d, %Y")
    subject = f"Daily Briefing - {today}"

    print("Sending email...")
    send_email(subject, briefing_html)

    print("Daily briefing sent successfully!")


if __name__ == "__main__":
    main()
