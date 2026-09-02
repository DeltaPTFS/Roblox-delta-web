import secrets
from datetime import datetime, timedelta, timezone
from starlette.datastructures import MutableHeaders
from .database import SessionLocal
from .models import WebSession


class DatabaseSessionMiddleware:
    """Opaque, revocable database sessions; the browser receives only a random ID."""
    def __init__(self, app, secure=True, max_age=86400): self.app,self.secure,self.max_age=app,secure,max_age
    async def __call__(self, scope, receive, send):
        if scope["type"] not in {"http","websocket"}: return await self.app(scope,receive,send)
        cookies=dict(part.strip().split("=",1) for part in dict(scope.get("headers",[])).get(b"cookie",b"").decode().split(";") if "=" in part)
        session_id=cookies.get("skymiles_session"); original_id=session_id
        with SessionLocal() as db:
            row=db.get(WebSession,session_id) if session_id else None
            if row and row.expires_at.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc): data=dict(row.data or {})
            else: row=None; data={}; session_id=secrets.token_urlsafe(32)
        scope["session"]=data
        async def send_wrapper(message):
            if message["type"]=="http.response.start":
                with SessionLocal() as db:
                    current=db.get(WebSession,session_id)
                    if data:
                        if not current: current=WebSession(id=session_id); db.add(current)
                        current.data=dict(data); current.expires_at=datetime.now(timezone.utc)+timedelta(seconds=self.max_age); db.commit()
                        value=f"skymiles_session={session_id}; Path=/; Max-Age={self.max_age}; HttpOnly; SameSite=Lax"+("; Secure" if self.secure else "")
                    else:
                        if current: db.delete(current); db.commit()
                        value="skymiles_session=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax"+("; Secure" if self.secure else "")
                    MutableHeaders(scope=message).append("set-cookie",value)
            await send(message)
        await self.app(scope,receive,send_wrapper)
