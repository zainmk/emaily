# emaily
##### a routine claude-ai generated email summarizing relevant authenticated info.

# purpose
instead of navigating and organizing informational 'widgets', a routinely generated email that targets specific API's and uses claude to summarize the information and email this summary on a routine basis (all the info. you need for the day sent in an email in the morning).

# stack
F | -

B | Python

I | GitHub Actions

D | - 


# ai
- claude code

# tools
- google for email smtp ; easiest to use to via 'app passwords' w.out constant token refresh logic and user-prompted auth required. (for full cron automation)

# setup
the following github secrets must be added for the workflow file to function and proper authentication...

GOOGLE_CLIENT_ID: registered application generated client id (must register a google application first)
GOOGLE_CLIENT_SECRET: registered application generated secret (must register a google application first)
GOOGLE_REFRESH_TOKEN: collected via running the 'get_refresh_token.py' file

ANTHROPIC_API_KEY: Private API Key for anthropic-claude 'call'

GMAIL_ADDRESS: Gmail Account Username
GMAIL_APP_PASSWORD: 'App Password' of the referenced GMAIL_ADDRESS; will need to be created via Google account. 
TO_EMAIL: email address of whre the 'dashboard' is emailed to.


# ex.
<img width="523" height="952" alt="emaily-1" src="https://github.com/user-attachments/assets/1c71ac30-93e6-460a-af40-604c984fe80d" />
<img width="523" height="952" alt="image" src="https://github.com/user-attachments/assets/8e4af422-0ae5-4d68-9180-d2a5bf04a4e5" />
