"""Public news page for the independent Roblox aviation community."""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).resolve().parents[1] / "templates")

ARTICLES = [
    {"date":"October 30, 2026","category":"Awards","title":"Delta named Best U.S. Airline by Forbes Travel Guide for third consecutive year","url":"https://news.delta.com/"},
    {"date":"October 21, 2026","category":"Community","title":"Delta's DREAM Flight introduces students to aviation careers","url":"https://news.delta.com/"},
    {"date":"October 20, 2026","category":"Connectivity","title":"Delta expands Wi-Fi across Asia-Pacific routes","url":"https://news.delta.com/"},
    {"date":"October 16, 2026","category":"Destinations","title":"Delta announces new nonstop Boston–Reykjavík service","url":"https://news.delta.com/no-one-better-connects-boston-world-delta-announces-new-route-iceland"},
    {"date":"October 9, 2026","category":"Company","title":"Delta releases September quarter financial results","url":"https://news.delta.com/delta-air-lines-announces-september-quarter-2026-financial-results"},
]

@router.get("/news", response_class=HTMLResponse)
async def news_center(request: Request):
    return templates.TemplateResponse("news.html", {"request":request,"articles":ARTICLES})
