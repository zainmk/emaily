# FOR LOCAL TESTING VIA .ENV

# from dotenv import load_dotenv
# load_dotenv()

import os
import sys
import json
import html
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


def fetch_calendar_events():
    """Fetch today's events from Google Calendar using OAuth refresh token."""
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
        end_of_day = start_of_day + timedelta(days=1)

        events_result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=start_of_day.isoformat(),
                timeMax=end_of_day.isoformat(),
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
                "timezone": "America/Edmonton",
                "forecast_days": 1,
            },
            timeout=10,
        )
        resp.raise_for_status()
        daily = resp.json()["daily"]

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
        }
    except Exception as e:
        print(f"Error fetching weather: {e}", file=sys.stderr)
        return None


def fetch_apod():
    """Fetch NASA's Astronomy Picture of the Day."""
    try:
        resp = requests.get(
            "http://api.nasa.gov/planetary/apod",
            params={"api_key": os.environ["NASA_API_KEY"]},
            timeout=10,
        )
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
        print(f"Error fetching APOD: {e}", file=sys.stderr)
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


def _build_widget(label, content_html):
    """Build a single Apple glass-style widget card."""
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
              <p style="margin:0 0 16px; font-size:11px; font-weight:600; color:#86868b; text-transform:uppercase; letter-spacing:1px;">{label}</p>
              {content_html}
            </td></tr>
          </table>
        </td></tr>"""


def _build_weather_widget(weather, quip=""):
    """Build weather widget HTML from API data."""
    if weather is None:
        content = '<p style="margin:0; font-size:15px; color:#86868b;">Weather data unavailable.</p>'
        return _build_widget("\u2601\ufe0f Weather", content)

    sunrise = _format_time(weather["sunrise"])
    sunset = _format_time(weather["sunset"])

    quip_html = ""
    if quip:
        quip_html = f'<p style="margin:16px 0 0; font-size:14px; color:#6e6e73; font-style:italic;">\u201c{html.escape(quip)}\u201d</p>'

    content = f"""
              <p style="margin:0; font-size:48px; font-weight:700; color:#1d1d1f; letter-spacing:-2px; line-height:1;">{weather['high_c']:.0f}\u00b0</p>
              <p style="margin:4px 0 0; font-size:17px; color:#1d1d1f; font-weight:500;">{html.escape(weather['weather_description'])}</p>
              <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:20px;">
                <tr>
                  <td style="padding:8px 0; font-size:11px; color:#86868b; text-transform:uppercase; letter-spacing:0.5px; width:33%;">Low</td>
                  <td style="padding:8px 0; font-size:11px; color:#86868b; text-transform:uppercase; letter-spacing:0.5px; width:33%;">Precip</td>
                  <td style="padding:8px 0; font-size:11px; color:#86868b; text-transform:uppercase; letter-spacing:0.5px; width:34%;">Wind</td>
                </tr>
                <tr>
                  <td style="font-size:17px; font-weight:600; color:#1d1d1f;">{weather['low_c']:.0f}\u00b0C</td>
                  <td style="font-size:17px; font-weight:600; color:#1d1d1f;">{weather['precipitation_probability']}%</td>
                  <td style="font-size:17px; font-weight:600; color:#1d1d1f;">{weather['wind_speed_kmh']:.0f} km/h</td>
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
              {quip_html}"""

    return _build_widget("\u2601\ufe0f Weather", content)


def _build_calendar_widget(events):
    """Build calendar widget HTML from events data."""
    if events is None:
        content = '<p style="margin:0; font-size:15px; color:#86868b;">Calendar data unavailable.</p>'
        return _build_widget("📅 Schedule", content)

    if not events:
        content = '<p style="margin:0; font-size:15px; color:#86868b;">Nothing scheduled \u2014 enjoy the open day!</p>'
        return _build_widget("📅 Schedule", content)

    items_html = []
    for i, e in enumerate(events):
        start, end = e["start"], e["end"]
        if "T" in start:
            time_str = f"{_format_time(start)} \u2013 {_format_time(end)}"
        else:
            time_str = "All Day"

        location_html = ""
        if e.get("location"):
            location_html = f'<p style="margin:4px 0 0; font-size:13px; color:#86868b;">📍 {html.escape(e["location"])}</p>'

        separator = ""
        if i > 0:
            separator = '<tr><td style="padding:10px 0;"><div style="border-top:1px solid #f2f2f7; height:0;"></div></td></tr>'

        items_html.append(f"""
              {separator}
              <tr><td>
                <p style="margin:0; font-size:13px; color:#86868b; font-weight:500;">{time_str}</p>
                <p style="margin:4px 0 0; font-size:17px; color:#1d1d1f; font-weight:600;">{html.escape(e['summary'])}</p>
                {location_html}
              </td></tr>""")

    content = f'<table width="100%" cellpadding="0" cellspacing="0" border="0">{"".join(items_html)}</table>'
    return _build_widget("📅 Schedule", content)


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

    return _build_widget("\U0001f52d Space", content)


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


def _generate_dynamic_content(events, weather):
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
        event_summaries = [e["summary"] for e in events]
        context_parts.append(
            f"Calendar: {len(events)} events \u2014 {', '.join(event_summaries)}"
        )
    elif events is not None:
        context_parts.append("Calendar: Free day, no events!")

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


def compose_briefing(events, weather, apod):
    """Compose the full briefing email with Apple glass-style widgets."""
    today = datetime.now(MST).strftime("%A, %B %d, %Y")

    print("Generating dynamic content with Claude...")
    dynamic = _generate_dynamic_content(events, weather)

    weather_widget = _build_weather_widget(weather, dynamic.get("weather_quip", ""))
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

    print("Fetching NASA APOD...")
    apod = fetch_apod()

    print("Composing briefing with Claude...")
    briefing_html = compose_briefing(events, weather, apod)
    
    today = datetime.now(MST).strftime("%A, %B %d, %Y")
    subject = f"Daily Briefing - {today}"

    print("Sending email...")
    send_email(subject, briefing_html)

    print("Daily briefing sent successfully!")


if __name__ == "__main__":
    main()
