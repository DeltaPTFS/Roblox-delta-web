"""Vercel entry point for the existing FastAPI application.

There is deliberately no second FastAPI instance here: every route, middleware,
template, static mount, OAuth callback, and health check comes from the canonical
website application.
"""
from website.app.main import app

__all__ = ("app",)
