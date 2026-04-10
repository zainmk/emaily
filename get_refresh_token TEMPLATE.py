"""
One-time utility to obtain a Google OAuth refresh token.

Usage:
    1. pip install google-auth-oauthlib
    2. Replace YOUR_CLIENT_ID and YOUR_CLIENT_SECRET below
    3. python get_refresh_token.py
    4. Sign in via the browser window and grant calendar access
    5. Copy the printed refresh token into your GitHub secret GOOGLE_REFRESH_TOKEN
"""

from google_auth_oauthlib.flow import InstalledAppFlow

CLIENT_ID = "YOUR_CLIENT_ID" # HERE
CLIENT_SECRET = "YOUR_CLIENT_SECRET" # HERE

flow = InstalledAppFlow.from_client_config(
    {
        "installed": {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "redirect_uris": ["http://localhost"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    },
    scopes=["https://www.googleapis.com/auth/calendar.readonly"],
)

creds = flow.run_local_server(port=8080, access_type="offline", prompt="consent")
print(f"\nRefresh token:\n{creds.refresh_token}")
print("\nSave this as the GOOGLE_REFRESH_TOKEN secret in your GitHub repository.")
