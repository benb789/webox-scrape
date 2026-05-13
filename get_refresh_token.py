"""
One-time script to generate a Google OAuth refresh token.
Run this locally, log in when the browser opens, then copy the printed refresh token.
"""
import json
import sys

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    print("Run: pip install google-auth-oauthlib")
    sys.exit(1)

CLIENT_SECRET_FILE = r"C:\Users\benlb\Downloads\client_secret_35034834617-1s3q4agb4ta3oluf8417lggu9ajq0lvh.apps.googleusercontent.com.json"
SCOPES = ["https://www.googleapis.com/auth/drive"]

flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
creds = flow.run_local_server(port=0)

print("\n=== Copy these three values into GitHub Secrets ===")
print(f"GOOGLE_CLIENT_ID:     {creds.client_id}")
print(f"GOOGLE_CLIENT_SECRET: {creds.client_secret}")
print(f"GOOGLE_REFRESH_TOKEN: {creds.refresh_token}")
