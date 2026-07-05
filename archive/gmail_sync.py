import os
import pickle
import base64
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# If modifying these scopes, delete the file token.pickle.
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

class GmailSync:
    def __init__(self, credentials_path='credentials.json', token_path='token.pickle'):
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.service = None
        self.is_configured = False
        self.initialize_gmail()

    def initialize_gmail(self):
        """Initializes the Gmail API service. Safe-fails if credentials are not provided."""
        if not os.path.exists(self.credentials_path) and not os.path.exists(self.token_path):
            print("⚠️ [Gmail Sync] 'credentials.json' not found. Please place your Google Cloud OAuth Client ID file in the project folder to enable Gmail Sync.")
            self.create_instructions_file()
            return

        creds = None
        # The file token.pickle stores the user's access and refresh tokens
        if os.path.exists(self.token_path):
            try:
                with open(self.token_path, 'rb') as token:
                    creds = pickle.load(token)
            except Exception as e:
                print(f"⚠️ [Gmail Sync] Failed to load token.pickle: {e}")

        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    print(f"⚠️ [Gmail Sync] Failed to refresh Gmail credentials: {e}")
                    creds = None
            
            if not creds:
                if not os.path.exists(self.credentials_path):
                    print("⚠️ [Gmail Sync] Cannot authenticate: 'credentials.json' is missing.")
                    return
                try:
                    # Note: This flow requires a browser. For server deployments, using service accounts is recommended,
                    # but for local use/testing, InstalledAppFlow works perfectly.
                    flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, SCOPES)
                    # We run a local server to capture redirect
                    creds = flow.run_local_server(port=0)
                except Exception as e:
                    print(f"⚠️ [Gmail Sync] Failed to run auth flow: {e}")
                    return

            # Save the credentials for the next run
            try:
                with open(self.token_path, 'wb') as token:
                    pickle.dump(creds, token)
            except Exception as e:
                print(f"⚠️ [Gmail Sync] Failed to save token.pickle: {e}")

        try:
            self.service = build('gmail', 'v1', credentials=creds)
            self.is_configured = True
            print("📨 [Gmail Sync] Gmail API successfully initialized and connected!")
        except Exception as e:
            print(f"⚠️ [Gmail Sync] Failed to build Gmail service: {e}")

    def fetch_latest_emails(self, max_results=5):
        """Fetches the latest unread emails from the inbox."""
        if not self.is_configured or not self.service:
            return []

        try:
            # Query for unread messages in the INBOX
            results = self.service.users().messages().list(
                userId='me',
                q='is:unread category:primary',
                maxResults=max_results
            ).execute()
            
            messages = results.get('messages', [])
            email_list = []

            for msg in messages:
                msg_id = msg['id']
                # Fetch full email details
                email_data = self.service.users().messages().get(userId='me', id=msg_id).execute()
                
                # Parse headers
                headers = email_data.get('payload', {}).get('headers', [])
                subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), 'No Subject')
                sender = next((h['value'] for h in headers if h['name'].lower() == 'from'), 'Unknown Sender')
                date = next((h['value'] for h in headers if h['name'].lower() == 'date'), '')

                # Parse body
                body = ""
                parts = email_data.get('payload', {}).get('parts', [])
                if not parts:
                    # Simple body
                    data = email_data.get('payload', {}).get('body', {}).get('data', '')
                    if data:
                        body = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
                else:
                    # Multipart body
                    for part in parts:
                        if part.get('mimeType') == 'text/plain':
                            data = part.get('body', {}).get('data', '')
                            if data:
                                body = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
                                break
                        elif part.get('mimeType') == 'text/html':
                            data = part.get('body', {}).get('data', '')
                            if data:
                                body = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
                                # We keep it plain text for AI reading

                # Mark as read so we don't fetch it again next time
                self.service.users().messages().batchModify(
                    userId='me',
                    body={
                        'ids': [msg_id],
                        'removeLabelIds': ['UNREAD']
                    }
                ).execute()

                email_list.append({
                    "id": msg_id,
                    "sender": sender,
                    "subject": subject,
                    "date": date,
                    "body": body[:2000]  # Cap length for Gemini parsing
                })

            return email_list
        except Exception as e:
            print(f"⚠️ [Gmail Sync] Error fetching emails: {e}")
            return []

    def create_instructions_file(self):
        """Creates a markdown guide on how the user can generate credentials.json."""
        instr_path = 'GMAIL_SETUP_GUIDE.md'
        if os.path.exists(instr_path):
            return
            
        guide_content = """# Google Workspace (Gmail) Integration Setup Guide

To enable your `LP_Bot` to scan client emails and post AI Scrum summaries, follow these steps to obtain a Google Cloud `credentials.json` file.

## 1. Create a Google Cloud Project
1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Click on the project dropdown in the top-left and select **New Project**.
3. Name it `Launch Pixel Assistant` and click **Create**.

## 2. Enable Gmail API
1. In the sidebar, go to **APIs & Services** > **Library**.
2. Search for `Gmail API` and click on it.
3. Click **Enable**.

## 3. Configure OAuth Consent Screen
1. Go to **APIs & Services** > **OAuth consent screen**.
2. Choose **External** user type and click **Create**.
3. Fill out the App information:
   - **App name**: `LP Scrum Bot`
   - **User support email**: *Your email*
   - **Developer contact information**: *Your email*
4. Click **Save and Continue** through the scopes section.
5. In the **Test users** section, click **Add Users** and enter your workspace Gmail address. This is critical since the app is in testing mode!
6. Click **Save and Continue**.

## 4. Generate OAuth Credentials
1. Go to **APIs & Services** > **Credentials**.
2. Click **+ Create Credentials** at the top and select **OAuth client ID**.
3. Set the Application type to **Desktop app**.
4. Set the name to `LP Desktop Bot` and click **Create**.
5. A modal will pop up. Click **Download JSON** to download your client secret file.
6. Rename this downloaded file to `credentials.json` and place it in the same directory as `bot.py` (`/Users/viveksharma/Documents/GitHub/test/ai-scrum-master/`).

## 5. Run the Bot
- When the bot runs, it will open your default browser asking you to authorize the app.
- Once authenticated, it will generate a `token.pickle` file, and you won't need to sign in again!
"""
        try:
            with open(instr_path, 'w') as f:
                f.write(guide_content)
        except Exception:
            pass
