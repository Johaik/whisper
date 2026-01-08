"""One-time OAuth setup script for Google Contacts access.

Usage:
    python -m app.services.oauth_setup

This script will:
1. Open a browser for Google authentication
2. Get your authorization
3. Print the refresh token to add to your .env file

Prerequisites:
1. Create a Google Cloud project: https://console.cloud.google.com/
2. Enable the People API
3. Create OAuth 2.0 credentials (Desktop application)
4. Download the credentials JSON file
"""

import json
import os
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

# Scopes required for reading contacts
SCOPES = ['https://www.googleapis.com/auth/contacts.readonly']


def main():
    """Run the OAuth setup flow."""
    print("=" * 60)
    print("Google Contacts OAuth Setup")
    print("=" * 60)
    print()

    # Check for credentials file
    creds_file = os.environ.get('GOOGLE_CREDENTIALS_FILE', 'credentials.json')

    if not Path(creds_file).exists():
        print("ERROR: Credentials file not found!")
        print()
        print("Please follow these steps:")
        print()
        print("1. Go to https://console.cloud.google.com/")
        print("2. Create a new project (or select existing)")
        print("3. Enable the 'People API':")
        print("   - Go to APIs & Services > Library")
        print("   - Search for 'People API' and enable it")
        print("4. Create OAuth credentials:")
        print("   - Go to APIs & Services > Credentials")
        print("   - Click 'Create Credentials' > 'OAuth client ID'")
        print("   - Application type: 'Desktop app'")
        print("   - Download the JSON file")
        print(f"5. Save the file as '{creds_file}' in the project root")
        print()
        print("Then run this script again.")
        sys.exit(1)

    print(f"Found credentials file: {creds_file}")
    print()

    # Load client config
    with open(creds_file) as f:
        client_config = json.load(f)

    # Get client ID and secret
    if 'installed' in client_config:
        client_id = client_config['installed']['client_id']
        client_secret = client_config['installed']['client_secret']
    elif 'web' in client_config:
        client_id = client_config['web']['client_id']
        client_secret = client_config['web']['client_secret']
    else:
        print("ERROR: Invalid credentials file format")
        sys.exit(1)

    print("Starting OAuth flow...")
    print("A browser window will open for you to authorize access.")
    print()

    try:
        # Run the OAuth flow
        flow = InstalledAppFlow.from_client_secrets_file(creds_file, SCOPES)
        creds = flow.run_local_server(port=8090)

        print()
        print("=" * 60)
        print("SUCCESS! Authorization complete.")
        print("=" * 60)
        print()
        print("Add these to your .env file:")
        print()
        print(f"GOOGLE_CLIENT_ID={client_id}")
        print(f"GOOGLE_CLIENT_SECRET={client_secret}")
        print(f"GOOGLE_REFRESH_TOKEN={creds.refresh_token}")
        print()

        # Optionally write to .env
        env_path = Path('.env')
        if env_path.exists():
            print("Would you like to append these to .env? [y/N]: ", end='')
            response = input().strip().lower()
            if response == 'y':
                with open(env_path, 'a') as f:
                    f.write("\n# Google Contacts API\n")
                    f.write(f"GOOGLE_CLIENT_ID={client_id}\n")
                    f.write(f"GOOGLE_CLIENT_SECRET={client_secret}\n")
                    f.write(f"GOOGLE_REFRESH_TOKEN={creds.refresh_token}\n")
                print("Added to .env!")
        else:
            print("No .env file found. Create one and add the above settings.")

    except Exception as e:
        print(f"ERROR: OAuth flow failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

