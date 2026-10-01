from fastapi import HTTPException
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

from ..config import settings, TOKEN_DIR


SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]



class OAuthManager:

    def _client_config(self):
        if not settings.google_client_id or not settings.google_client_secret:
            raise HTTPException(
                500,
                "Google OAuth is not configured. Fill GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env."
            )

        return {
            "web": {
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [f"{settings.frontend_url.rstrip('/')}/auth/callback"],
            }
        }

    def flow(self, state=None):
        return Flow.from_client_config(
            self._client_config(),
            scopes=SCOPES,
            state=state,
            redirect_uri=f"{settings.frontend_url.rstrip('/')}/auth/callback",
            autogenerate_code_verifier=False,
        )

    def authorization_url(self):
        flow = self.flow()

        url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )

        return url, state

    def handle_callback(self, code: str, state: str | None, session_id: str):
        flow = self.flow(state=state)

        flow.fetch_token(code=code)

        TOKEN_DIR.mkdir(parents=True, exist_ok=True)

        token_file = TOKEN_DIR / f"{session_id}.json"
        token_file.write_text(
            flow.credentials.to_json(),
            encoding="utf-8"
        )

        try:
            token_file.chmod(0o600)
        except OSError:
            pass

    def credentials(self, session_id: str):
        token_file = TOKEN_DIR / f"{session_id}.json"
        if not token_file.exists():
            return None

        try:
            creds = Credentials.from_authorized_user_file(
                str(token_file),
                SCOPES
            )

            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())

                token_file.write_text(
                    creds.to_json(),
                    encoding="utf-8"
                )

            return creds if creds and creds.valid else None

        except Exception:
            return None


oauth = OAuthManager()