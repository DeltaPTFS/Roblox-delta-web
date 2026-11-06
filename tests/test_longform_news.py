"""News feature: durable articles, visibility, editor, limits and publication."""
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from website.app.database import Base
from website.app.models import CommunityNewsArticle, User
from website.app.news import published_articles


def test_articles_are_durable_and_drafts_never_public(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'articles.db'}")
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)
    with Session(engine) as db:
        user = User(
            discord_user_id="111111", discord_username="author",
            discord_display_name="Author", roblox_user_id="222222",
            roblox_username="writer", roblox_display_name="Writer", skymiles_number="SM-TEST-NEWS"
        )
        db.add(user)
        db.flush()
        db.add_all([
            CommunityNewsArticle(title="Draft", body="Do not publish", published=False,
                                 author_id=user.id, created_at=now, updated_at=now),
            CommunityNewsArticle(title="Published", body="Visible community news", published=True,
                                 author_id=user.id, created_at=now, updated_at=now),
        ])
        db.commit()
        articles = published_articles(db)
        assert [x.title for x in articles] == ["Published"]
        articles[0].published = False
        db.commit()
        assert published_articles(db) == []
    engine.dispose()


def test_owner_editor_supports_10000_words_and_separates_short_banner():
    main = Path("website/app/main.py").read_text()
    editor = Path("website/templates/admin.html").read_text()
    js = Path("website/static/news-editor.js").read_text()
    assert '@app.post("/owner/news/publish")' in main
    assert 'await require_owner(request, db)' in main
    assert 'word_count <= 10_000' in main
    assert 'len(body.encode("utf-8")) > 500_000' in main
    assert 'check_csrf(request, csrf)' in main
    assert 'data-ops-tab="news"' in editor
    assert 'data-ops-group="news"' in editor
    assert 'id="longform-news-body"' in editor
    assert 'action="/owner/news/publish"' in editor
    assert 'owner-news-history' in editor
    assert '10000' in js
    assert 'maxlength="220"' in editor  # existing short banner unaffected


def test_published_articles_in_news_and_homepage_without_raw_html():
    home = Path("website/templates/homepage.html").read_text()
    page = Path("website/templates/news.html").read_text()
    migration = Path("migrations/versions/0016_community_news_articles.py").read_text()
    assert 'featured_news[0]' in home
    assert 'href="/news#news-article-{{ article.id }}"' in home
    assert "article.body.split()[:58]" in home
    assert "for article in articles" in page
    assert "{{ article.body }}" in page  # Jinja autoescape
    assert "white-space:pre-wrap" in Path("website/static/news-longform.css").read_text()
    assert 'down_revision = "0015"' in migration
    assert 'op.create_table(' in migration
