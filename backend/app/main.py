from pathlib import Path
import secrets
import hmac
from datetime import datetime, timezone
from urllib.parse import quote
from fastapi import FastAPI, Depends, Request, Response, HTTPException
from fastapi.responses import RedirectResponse, StreamingResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import select, delete
from .config import settings, FRONTEND_DIR
from .database.db import init_db, get_db, FileCache, WatchHistory, Favorite, Setting
from .auth.oauth import oauth
from .drive.service import drive, is_video, FOLDER_MIME
from .streaming.range import parse_range, RangeError

app = FastAPI(title="DriveStream", version="1.0.0")
app.add_middleware(SessionMiddleware, secret_key=settings.session_secret, https_only=True, same_site="lax")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:8000", "http://127.0.0.1:8000", settings.frontend_url], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
def startup(): init_db()

def session_id(request: Request):
    sid = request.session.get("session_id")
    if not sid:
        sid = secrets.token_urlsafe(32)
        request.session["session_id"] = sid
    return sid

def scoped_id(sid, value):
    return f"{sid}:{value}"

def unscoped_id(sid, value):
    prefix = f"{sid}:"
    return value[len(prefix):] if value.startswith(prefix) else value

def setting(db, key, sid=None):
    key = scoped_id(sid, key) if sid else key
    row = db.get(Setting, key); return row.value if row else None

def set_setting(db, key, value, sid=None):
    key = scoped_id(sid, key) if sid else key
    row = db.get(Setting, key)
    if not row: row = Setting(key=key); db.add(row)
    row.value = value; db.commit()

def public_file(f, fav=False):
    return {"id":f.get("id"),"name":f.get("name"),"mimeType":f.get("mimeType"),"size":int(f["size"]) if f.get("size") else None,"modifiedTime":f.get("modifiedTime"),"createdTime":f.get("createdTime"),"parents":f.get("parents",[]),"thumbnail":f.get("thumbnailLink"),"isFolder":f.get("mimeType")==FOLDER_MIME,"favorite":fav}

@app.get("/api/auth/status")
def auth_status(request: Request, db: Session = Depends(get_db)):
    sid = session_id(request)
    return {"authenticated": oauth.credentials(sid) is not None, "rootFolderId": setting(db, "root_folder_id", sid)}

@app.get("/api/auth/login")
def auth_login(request: Request):
    session_id(request)
    url, state = oauth.authorization_url()
    request.session["oauth_state"] = state
    return {"url": url, "state": state}

@app.get("/auth/callback")
def auth_callback(request: Request, code: str | None=None, state: str | None=None, error: str | None=None):
    if error: return RedirectResponse(f"{settings.frontend_url}/?auth_error={quote(error)}")
    if not code: return RedirectResponse(f"{settings.frontend_url}/?auth_error=missing_code")
    sid = session_id(request)
    expected_state = request.session.pop("oauth_state", None)
    if not state or not expected_state or not hmac.compare_digest(state, expected_state):
        return RedirectResponse(f"{settings.frontend_url}/?auth_error=invalid_state")
    try: oauth.handle_callback(code, state, sid)
    except Exception as e: return RedirectResponse(f"{settings.frontend_url}/?auth_error={quote(str(e)[:180])}")
    return RedirectResponse(f"{settings.frontend_url}/?connected=1")

@app.get("/api/root")
def get_root(db: Session = Depends(get_db)):
    root = setting(db,"root_folder_id") or settings.root_folder_id
    if not root: return {"selected":False,"folders":[]}
    try: f=drive.get_file(root); return {"selected":True,"folder":public_file(f)}
    except Exception as e: raise HTTPException(502, "Unable to read the selected Drive folder.")

@app.post("/api/root/{folder_id}")
def set_root(folder_id: str, db: Session = Depends(get_db)):
    try:
        f=drive.get_file(folder_id)
        if f.get("mimeType") != FOLDER_MIME: raise HTTPException(400,"That Drive item is not a folder.")
    except HTTPException: raise
    except Exception: raise HTTPException(502,"Could not access that Drive folder.")
    set_setting(db,"root_folder_id",folder_id)
    return {"ok":True,"folder":public_file(f)}

@app.get("/api/drive/root")
def drive_root(db: Session = Depends(get_db)):
    try:
        items = drive.list_root()
    except PermissionError as e:
        raise HTTPException(401, str(e))
    except Exception:
        raise HTTPException(502, "Google Drive could not be read.")

    favs = {x.google_drive_id for x in db.scalars(select(Favorite)).all()}

    return {
        "items": [
            public_file(x, x.get("id") in favs)
            for x in items
            if x.get("mimeType") == FOLDER_MIME or is_video(x)
        ]
    }

@app.get("/api/folders/{folder_id}")
def folder(folder_id: str, db: Session = Depends(get_db)):
    try: items=drive.list_children(folder_id)
    except PermissionError as e: raise HTTPException(401,str(e))
    except Exception: raise HTTPException(502,"Google Drive could not be read.")
    favs={x.google_drive_id for x in db.scalars(select(Favorite)).all()}
    return {"items":[public_file(x, x.get("id") in favs) for x in items if x.get("mimeType")==FOLDER_MIME or is_video(x)]}

@app.get("/api/videos/{file_id}")
def video(file_id: str, db: Session=Depends(get_db)):
    try: f=drive.get_file(file_id)
    except Exception: raise HTTPException(404,"Video not found or no longer accessible.")
    if not is_video(f): raise HTTPException(400,"This file is not a supported video.")
    fav=db.scalar(select(Favorite).where(Favorite.google_drive_id==file_id)) is not None
    return public_file(f,fav)

@app.get("/api/videos/{file_id}/thumbnail")
def thumbnail(file_id: str):
    try: url=drive.thumbnail(file_id)
    except Exception: raise HTTPException(404,"Thumbnail unavailable.")
    if not url: raise HTTPException(404,"Thumbnail unavailable.")
    return RedirectResponse(url)

@app.get("/api/videos/{file_id}/stream")
def stream(file_id: str, request: Request):
    try: meta=drive.get_file(file_id)
    except Exception: raise HTTPException(404,"Video not found or no longer accessible.")
    if not is_video(meta): raise HTTPException(400,"Unsupported video type.")
    size=meta.get("size")
    if size is None: raise HTTPException(400,"Drive did not provide a streamable file size.")
    try: br=parse_range(request.headers.get("range"), int(size))
    except RangeError: return Response(status_code=416, headers={"Content-Range":f"bytes */{size}"})
    upstream_range = f"bytes={br.start}-{br.end}" if br else None
    try: r=drive.stream_request(file_id, upstream_range)
    except Exception: raise HTTPException(502,"Could not connect to Google Drive.")
    if r.status_code not in (200,206):
        r.close(); raise HTTPException(r.status_code,"Google Drive could not provide the video data.")
    if br and r.status_code != 206:
        # Some intermediaries may ignore Range. Do not silently send an oversized body.
        r.close(); raise HTTPException(502,"Google Drive did not honor the requested byte range.")
    headers={"Accept-Ranges":"bytes","Content-Type":meta.get("mimeType") or "application/octet-stream","Cache-Control":"no-store"}
    if br:
        end=br.end; length=end-br.start+1
        headers.update({"Content-Range":f"bytes {br.start}-{end}/{size}","Content-Length":str(length)})
        status=206
    else:
        headers["Content-Length"]=str(size); status=200
    def iterator():
        try:
            for chunk in r.iter_content(chunk_size=1024*1024):
                if chunk: yield chunk
        finally: r.close()
    return StreamingResponse(iterator(), status_code=status, headers=headers, media_type=meta.get("mimeType"))

@app.get("/api/search")
def search(q: str, db: Session=Depends(get_db)):
    try:
        items = drive.search(None, q)
    except Exception:
        raise HTTPException(502, "Search failed.")

    favs = {
        x.google_drive_id
        for x in db.scalars(select(Favorite)).all()
    }

    return {
        "items": [
            public_file(x, x.get("id") in favs)
            for x in items
            if is_video(x)
        ]
    }
@app.get("/api/history")
def history(db: Session=Depends(get_db)):
    rows=db.scalars(select(WatchHistory).order_by(WatchHistory.last_watched.desc()).limit(50)).all()
    return {"items":[{"id":r.google_drive_id,"filename":r.filename,"position":r.position,"duration":r.duration,"lastWatched":r.last_watched.isoformat()} for r in rows]}

@app.post("/api/history")
async def save_history(request: Request, db: Session=Depends(get_db)):
    p=await request.json(); gid=p.get("id")
    if not gid: raise HTTPException(400,"Missing video id")
    row=db.scalar(select(WatchHistory).where(WatchHistory.google_drive_id==gid))
    if not row: row=WatchHistory(google_drive_id=gid); db.add(row)
    row.filename=str(p.get("filename",row.filename)); row.position=float(p.get("position",0)); row.duration=float(p.get("duration",0)); row.last_watched=datetime.now(timezone.utc); db.commit()
    return {"ok":True}

@app.get("/api/favorites")
def favorites(db: Session=Depends(get_db)):
    rows=db.scalars(select(Favorite).order_by(Favorite.created_at.desc())).all(); out=[]
    for r in rows:
        try: f=drive.get_file(r.google_drive_id); out.append(public_file(f,True))
        except Exception: pass
    return {"items":out}

@app.post("/api/favorites/{file_id}")
def add_favorite(file_id: str, db: Session=Depends(get_db)):
    if not db.scalar(select(Favorite).where(Favorite.google_drive_id==file_id)): db.add(Favorite(google_drive_id=file_id)); db.commit()
    return {"ok":True}

@app.delete("/api/favorites/{file_id}")
def remove_favorite(file_id: str, db: Session=Depends(get_db)):
    db.execute(delete(Favorite).where(Favorite.google_drive_id==file_id)); db.commit(); return {"ok":True}

@app.post("/api/sync")
def sync(db: Session = Depends(get_db)):
    # Refresh My Drive; folder navigation reads Drive live.
    items = drive.list_root()

    for f in items:
        row = db.scalar(
            select(FileCache).where(
                FileCache.google_drive_id == f["id"]
            )
        )

        if not row:
            row = FileCache(
                google_drive_id=f["id"]
            )
            db.add(row)

        row.name = f.get("name", "")
        row.mime_type = f.get("mimeType", "")
        row.size = int(f["size"]) if f.get("size") else None
        row.modified_time = f.get("modifiedTime")
        row.created_time = f.get("createdTime")
        row.parent_id = (f.get("parents") or [None])[0]
        row.thumbnail_url = f.get("thumbnailLink")
        row.is_folder = int(
            f.get("mimeType") == FOLDER_MIME
        )
        row.cached_at = datetime.now(timezone.utc)

    db.commit()

    return {
        "ok": True,
        "count": len(items)
    }
@app.get("/api/settings")
def settings_api(db: Session=Depends(get_db)):
    return {"rootFolderId": "root"}
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
