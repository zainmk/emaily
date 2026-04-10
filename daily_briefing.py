import os
import sys
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
            refresh_token=os.environ["GOOGLE_REFRESH_TOKEN"],
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


def compose_briefing(events, weather):
    """Use Claude to compose a formatted daily briefing email."""
    client = anthropic.Anthropic()

    today = datetime.now(MST).strftime("%A, %B %d, %Y")

    if events is None:
        events_text = "Calendar data was unavailable due to an error."
    elif len(events) == 0:
        events_text = "No events scheduled for today."
    else:
        lines = []
        for e in events:
            line = f"- {e['start']} to {e['end']}: {e['summary']}"
            if e.get("location"):
                line += f" (Location: {e['location']})"
            lines.append(line)
        events_text = "\n".join(lines)

    if weather is None:
        weather_text = "Weather data was unavailable due to an error."
    else:
        weather_text = (
            f"Conditions: {weather['weather_description']}\n"
            f"High: {weather['high_c']}\u00b0C / Low: {weather['low_c']}\u00b0C\n"
            f"Precipitation probability: {weather['precipitation_probability']}%\n"
            f"Wind: {weather['wind_speed_kmh']} km/h\n"
            f"Sunrise: {weather['sunrise']} / Sunset: {weather['sunset']}"
        )

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        system=(
            "You are a personal assistant composing a daily briefing email. "
            "Write in a warm, professional tone. Format the email in HTML with "
            "clean styling. Include a greeting, a weather summary section, "
            "a calendar/schedule section, and a brief sign-off. "
            "Use inline CSS for styling (background colors, padding, etc.) "
            "since this will be viewed in an email client. "
            "Keep it concise but informative."
        ),
        messages=[
            {
                "role": "user",
                "content": (
                    f"Please compose my daily briefing email for {today} "
                    f"in Calgary, AB.\n\n"
                    f"WEATHER FORECAST:\n{weather_text}\n\n"
                    f"TODAY'S CALENDAR:\n{events_text}"
                ),
            }
        ],
    )

    return message.content[0].text


def send_email(subject, html_body):
    """Send an HTML email via Gmail SMTP."""
    gmail_address = os.environ["GMAIL_ADDRESS"]
    gmail_password = os.environ["GMAIL_APP_PASSWORD"]
    recipient = os.environ["RECIPIENT_EMAIL"]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = gmail_address
    msg["To"] = recipient
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(gmail_address, gmail_password)
        server.sendmail(gmail_address, recipient, msg.as_string())


def main():
    print("Fetching calendar events...")
    events = fetch_calendar_events()

    print("Fetching weather forecast...")
    weather = fetch_weather()

    print("Composing briefing with Claude...")
    briefing_html = compose_briefing(events, weather)

    today = datetime.now(MST).strftime("%A, %B %d, %Y")
    subject = f"Daily Briefing - {today}"

    print("Sending email...")
    send_email(subject, briefing_html)

    print("Daily briefing sent successfully!")


if __name__ == "__main__":
    main()
