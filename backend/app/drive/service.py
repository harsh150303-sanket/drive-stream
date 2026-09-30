import requests

from googleapiclient.discovery import build

from ..auth.oauth import oauth


VIDEO_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".webm",
    ".m4v",
    ".avi",
    ".mkv",
    ".mpeg",
    ".mpg",
}

FOLDER_MIME = "application/vnd.google-apps.folder"


class DriveService:

    def creds(self):
        return oauth.credentials()

    def api(self):
        c = self.creds()

        if not c:
            return None

        return build(
            "drive",
            "v3",
            credentials=c,
            cache_discovery=False
        )

    def list_root(self):
        svc = self.api()

        if not svc:
            raise PermissionError(
                "Google Drive is not connected."
            )

        q = "'root' in parents and trashed = false"

        items = []
        token = None

        while True:
            res = svc.files().list(
                q=q,
                pageSize=1000,
                pageToken=token,
                fields=(
                    "nextPageToken,"
                    "files("
                    "id,name,mimeType,size,createdTime,"
                    "modifiedTime,parents,thumbnailLink,"
                    "webContentLink,capabilities/canDownload"
                    ")"
                ),
                orderBy="folder,name_natural"
            ).execute()

            items.extend(res.get("files", []))

            token = res.get("nextPageToken")

            if not token:
                break

        return items

    def list_children(self, folder_id: str):
        svc = self.api()

        if not svc:
            raise PermissionError(
                "Google Drive is not connected."
            )

        q = f"'{folder_id}' in parents and trashed = false"

        items = []
        token = None

        while True:
            res = svc.files().list(
                q=q,
                pageSize=1000,
                pageToken=token,
                fields=(
                    "nextPageToken,"
                    "files("
                    "id,name,mimeType,size,createdTime,"
                    "modifiedTime,parents,thumbnailLink,"
                    "webContentLink,capabilities/canDownload"
                    ")"
                ),
                orderBy="folder,name_natural"
            ).execute()

            items.extend(res.get("files", []))

            token = res.get("nextPageToken")

            if not token:
                break

        return items

    def get_file(self, file_id: str):
        svc = self.api()

        if not svc:
            raise PermissionError(
                "Google Drive is not connected."
            )

        return svc.files().get(
            fileId=file_id,
            fields=(
                "id,name,mimeType,size,createdTime,"
                "modifiedTime,parents,thumbnailLink,"
                "capabilities/canDownload"
            )
        ).execute()

    def search(self, root_id: str, qtext: str):
        svc = self.api()

        if not svc:
            raise PermissionError(
                "Google Drive is not connected."
            )

        escaped = qtext.replace("'", "\\'")

        q = (
            "trashed = false "
            f"and name contains '{escaped}'"
        )

        res = svc.files().list(
            q=q,
            pageSize=100,
            fields=(
                "files("
                "id,name,mimeType,size,createdTime,"
                "modifiedTime,parents,thumbnailLink"
                ")"
            )
        ).execute()

        return res.get("files", [])

    def stream_request(
        self,
        file_id: str,
        byte_range: str | None = None
    ):
        creds = self.creds()

        if not creds:
            raise PermissionError(
                "Google Drive is not connected."
            )

        url = (
            "https://www.googleapis.com/drive/v3/files/"
            f"{file_id}?alt=media"
        )

        headers = {
            "Authorization": f"Bearer {creds.token}"
        }

        if byte_range:
            headers["Range"] = byte_range

        return requests.get(
            url,
            headers=headers,
            stream=True,
            timeout=60
        )

    def thumbnail(self, file_id: str):
        f = self.get_file(file_id)

        return f.get("thumbnailLink")


drive = DriveService()


def is_video(f):
    if f.get("mimeType", "").startswith("video/"):
        return True

    name = f.get("name", "").lower()

    return any(
        name.endswith(x)
        for x in VIDEO_EXTENSIONS
    )