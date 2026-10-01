from fastapi import HTTPException
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

from ..config import settings, TOKEN_DIR
from ..database.db import SessionLocal, OAuthToken


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

    def _save_token(self, session_id: str, token_json: str):
        db = SessionLocal()
        try:
            row = db.get(OAuthToken, session_id)
            if row:
                row.token_json = token_json
            else:
                db.add(OAuthToken(session_id=session_id, token_json=token_json))
            db.commit()
        finally:
            db.close()

    def _load_token(self, session_id: str):
        db = SessionLocal()
        try:
            row = db.get(OAuthToken, session_id)
            return row.token_json if row else None
        finally:
            db.close()

    def handle_callback(self, code: str, state: str | None, session_id: str):
        flow = self.flow(state=state)
        flow.fetch_token(code=code)

        token_json = flow.credentials.to_json()
        self._save_token(session_id, token_json)

        # Keep the local file as a fallback for local development/backwards compatibility.
        TOKEN_DIR.mkdir(parents=True, exist_ok=True)
        token_file = TOKEN_DIR / f"{session_id}.json"
        token_file.write_text(token_json, encoding="utf-8")

        try:
            token_file.chmod(0o600)
        except OSError:
            pass

    def credentials(self, session_id: str):
        token_json = self._load_token(session_id)

        # Migrate an older file-based token into the database when one exists.
        if not token_json:
            token_file = TOKEN_DIR / f"{session_id}.json"
            if token_file.exists():
                try:
                    token_json = token_file.read_text(encoding="utf-8")
                    self._save_token(session_id, token_json)
                except Exception:
                    token_json = None

        if not token_json:
            return None

        try:
            creds = Credentials.from_authorized_user_info(
                __import__("json").loads(token_json),
                SCOPES
            )

            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                token_json = creds.to_json()
                self._save_token(session_id, token_json)

                # Keep local development fallback in sync.
                token_file = TOKEN_DIR / f"{session_id}.json"
                token_file.write_text(token_json, encoding="utf-8")

            return creds if creds and creds.valid else None

        except Exception:
            return None


oauth = OAuthManager()
