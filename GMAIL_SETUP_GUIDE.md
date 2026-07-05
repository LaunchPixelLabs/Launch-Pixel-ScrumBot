# Google Workspace (Gmail) Integration Setup Guide

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
