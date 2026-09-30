# DriveStream

DriveStream is a private/local Windows web app for browsing and watching video files stored in Google Drive. Videos remain in Drive; the local FastAPI backend proxies byte ranges to the Drive API.

## Requirements
- Windows 10/11
- Python 3.10+
- A Google Cloud project with Google Drive API enabled
- A Google OAuth 2.0 Web application client

## 1. Google Cloud setup
1. Open Google Cloud Console.
2. Create/select a project.
3. Enable **Google Drive API**.
4. Configure the OAuth consent screen.
5. Create an OAuth client ID of type **Web application**.
6. Add this authorized redirect URI exactly:
   `http://localhost:8000/auth/callback`
7. Copy the client ID and client secret.

For a personal/local app, keep the OAuth app in testing mode and add your own Google account as a test user if Google asks for it.

## 2. Configure DriveStream
Copy `.env.example` to `.env`.
Set:
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`

Do not commit `.env` or `tokens/`.

## 3. Run on Windows
Double-click `run.bat`.
It creates `.venv`, installs Python dependencies, starts FastAPI on `127.0.0.1:8000`, and opens the browser.

## 4. Connect Google Drive
Click **Connect Google Drive**, sign in, and approve read-only Drive access. The backend stores OAuth credentials locally under `tokens/`; they are never sent to the browser.

## 5. Select the root folder
Open Settings and paste the Google Drive folder ID. For a URL like:
`https://drive.google.com/drive/folders/ABC123`
use `ABC123`.

The selected folder is saved locally and becomes the library root on future launches.

## 6. Streaming behavior
The browser requests `/api/videos/{file_id}/stream` with HTTP `Range` headers. DriveStream validates the range and sends the same range to Google Drive's `files.get?alt=media` endpoint. The response is streamed to the browser without intentionally creating a permanent local copy.

Google documents that Drive blob downloads support partial downloads using the HTTP `Range` header. See: https://developers.google.com/workspace/drive/api/guides/manage-downloads

### Limitation
This is a local proxy, not a CDN. Google Drive/network latency and API behavior still affect startup and seeking. DriveStream refuses to silently turn a requested partial response into a full response if the upstream does not honor the range. Browser codec support also varies; the app does not transcode files.

## 7. Features
- Google OAuth 2.0 read-only Drive access
- Root folder selection
- Folder navigation and breadcrumbs
- Video thumbnails when Drive supplies them
- MP4/MOV/WEBM/M4V/AVI/MKV/MPEG/MPG discovery
- Search with debounce
- Sorting by name/date/size in the UI
- HTML5 player with native seeking, volume, fullscreen and playback speed
- Local watch history and resume position
- Local favorites
- Library refresh/cache
- Responsive dark interface

## 8. Troubleshooting
### `redirect_uri_mismatch`
Make sure the Google OAuth client contains exactly:
`http://localhost:8000/auth/callback`

### `Access blocked: This app's request is invalid`
Check the OAuth consent screen and ensure your Google account is a test user while the app is in testing mode.

### Drive folder cannot be opened
Confirm the account used for OAuth can access the folder and that the folder ID is correct.

### Video will not play
The browser may not support the video's codec/container. DriveStream does not automatically convert videos.

### Port 8000 is already in use
Stop the process using port 8000, or change `PORT` and the OAuth redirect URI together.

## Security
The server binds to `127.0.0.1` by default and is not intended to be publicly exposed. OAuth tokens and the SQLite database are local application data and excluded from git.
