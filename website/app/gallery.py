"""Website-managed flight/gallery photos stored in PostgreSQL instead of ephemeral CDN links."""
from datetime import datetime,timezone
from pathlib import Path
import re
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from .database import get_db
from .models import SiteGalleryImage
from .security import check_csrf
from .community import verified_viewer, access_level, page_context

router=APIRouter()
templates=Jinja2Templates(directory=Path(__file__).resolve().parents[1]/"templates")
ROOT=Path(__file__).resolve().parents[1]/"static"/"gallery"
GALLERY={
    "delta-hangar":"Hangar & aircraft",
    "delta-centennial":"Flight operations / centennial livery",
    "delta-terminal":"Passenger check-in",
    "delta-lounge":"Delta lounge",
    "delta-hq":"Delta HQ",
    "delta-electric":"Ground operations",
    "delta-tail":"Aircraft tail / promo",
    "flight-promo":"Flight format announcement image"
}
MIME={"image/png":".png","image/jpeg":".jpg","image/webp":".webp"}
MAX_BYTES=3_000_000


def actual_mime(content:bytes)->str|None:
    if content.startswith(b"\x89PNG\r\n\x1a\n"):return "image/png"
    if content.startswith(b"\xff\xd8\xff"):return "image/jpeg"
    if content.startswith(b"RIFF") and content[8:12]==b"WEBP":return "image/webp"
    return None


@router.get("/gallery/media/{slug}")
def get_gallery_image(slug:str,db:Session=Depends(get_db)):
    if slug not in GALLERY:raise HTTPException(404,"Image not found")
    saved=db.get(SiteGalleryImage,slug)
    if saved:
        return Response(content=saved.content,media_type=saved.mime_type,
                        headers={"Cache-Control":"public, max-age=120, stale-while-revalidate=3600"})
    for ext,mime in [(".png","image/png"),(".jpg","image/jpeg"),(".jpeg","image/jpeg"),(".webp","image/webp")]:
        source=ROOT/(slug+ext)
        if source.is_file():
            return Response(content=source.read_bytes(),media_type=mime,
                            headers={"Cache-Control":"public, max-age=120"})
    raise HTTPException(404,"Gallery image not uploaded yet")


@router.get("/gallery/manage",response_class=HTMLResponse)
async def gallery_manage(request:Request,db:Session=Depends(get_db)):
    result=await verified_viewer(request,db)
    if isinstance(result,RedirectResponse):return result
    user,roles=result
    if access_level(roles)=="MEMBER":raise HTTPException(403,"Only authorized staff may update website photos")
    saved={name:db.get(SiteGalleryImage,name) is not None for name in GALLERY}
    return templates.TemplateResponse("gallery_manage.html",
        page_context(request,user,roles,gallery=GALLERY,saved=saved))


@router.post("/gallery/manage")
async def gallery_upload(request:Request,csrf:str=Form(...),slug:str=Form(...),
                         image:UploadFile=File(...),db:Session=Depends(get_db)):
    check_csrf(request,csrf)
    result=await verified_viewer(request,db)
    if isinstance(result,RedirectResponse):raise HTTPException(401,"Please sign in")
    _,roles=result
    if access_level(roles)=="MEMBER":raise HTTPException(403,"Only authorized staff can upload photos")
    if slug not in GALLERY:raise HTTPException(422,"Invalid gallery slot")
    content=await image.read(MAX_BYTES+1)
    if not content or len(content)>MAX_BYTES:
        raise HTTPException(413,"Upload PNG/JPG/WEBP up to 3 MB")
    mime=actual_mime(content)
    if mime is None:
        raise HTTPException(422,"Unsupported photo type. Use PNG, JPEG or WebP.")
    item=db.get(SiteGalleryImage,slug)
    if item is None:
        item=SiteGalleryImage(slug=slug,mime_type=mime,content=content)
        db.add(item)
    else:
        item.mime_type=mime
        item.content=content
        item.updated_at=datetime.now(timezone.utc)
    db.commit()
    return RedirectResponse("/gallery/manage?uploaded="+slug,303)
