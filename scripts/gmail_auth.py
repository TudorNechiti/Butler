"""One-time Gmail login. Prints a refresh token to paste into .env as GMAIL_REFRESH_TOKEN.

Run locally, never in CI:  uv run python -m scripts.gmail_auth

A browser opens on Google's consent screen. Because the app is unverified, Google shows
"Google hasn't verified this app": choose Advanced -> Go to Butler. The token is printed to
this terminal only and never written to disk.
"""

from __future__ import annotations

from google_auth_oauthlib.flow import InstalledAppFlow
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from agents.email_labeler.gmail import SCOPES, TOKEN_URI


class _ClientSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    gmail_client_id: str
    gmail_client_secret: SecretStr


def main() -> None:
    settings = _ClientSettings()  # type: ignore[call-arg]
    client_config = {
        "installed": {
            "client_id": settings.gmail_client_id,
            "client_secret": settings.gmail_client_secret.get_secret_value(),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": TOKEN_URI,
            "redirect_uris": ["http://localhost"],
        }
    }
    flow = InstalledAppFlow.from_client_config(client_config, scopes=list(SCOPES))
    # offline + consent: guarantees Google returns a refresh token, even on a repeat login.
    credentials = flow.run_local_server(port=0, access_type="offline", prompt="consent")

    granted = set(credentials.granted_scopes or [])
    if granted != set(SCOPES):
        raise SystemExit(f"Unexpected scopes granted: {sorted(granted)}. Expected {SCOPES}.")
    if not credentials.refresh_token:
        raise SystemExit("Google returned no refresh token. Revoke Butler's access and retry.")

    print("\nAdd this line to .env (and keep it out of chats and commits):\n")
    print(f"GMAIL_REFRESH_TOKEN={credentials.refresh_token}\n")


if __name__ == "__main__":
    main()
