import os
from pathlib import Path
from xml.etree import ElementTree

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SESSION_SECRET", "test-secret-at-least-thirty-two-characters")
os.environ.setdefault("COOKIE_SECURE", "false")

from website.app.main import PUBLIC_SITE_URL, robots_txt, sitemap_xml


def test_robots_txt_points_to_public_sitemap_without_exposing_member_routes():
    response = robots_txt()
    text = response.body.decode("utf-8")
    assert response.media_type == "text/plain"
    assert "Allow: /\n" in text
    assert "Disallow: /admin" in text
    assert "Disallow: /dashboard" in text
    assert "Disallow: /auth/" in text
    assert f"Sitemap: {PUBLIC_SITE_URL}/sitemap.xml" in text


def test_sitemap_lists_only_indexable_public_homepage():
    response = sitemap_xml()
    assert response.media_type == "application/xml"
    root = ElementTree.fromstring(response.body)
    urls = [item.text for item in root.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc")]
    assert urls == [PUBLIC_SITE_URL + "/", PUBLIC_SITE_URL + "/partnerships"]


def test_homepage_has_search_metadata_and_private_pages_noindex():
    public = Path("website/templates/community_base.html").read_text()
    home = Path("website/templates/homepage.html").read_text()
    private = Path("website/templates/base.html").read_text()
    assert 'rel="canonical"' in public
    assert 'og:description' in public
    assert 'application/ld+json' in public
    assert "request.url.path in ['/', '/home']" in public
    assert "Delta Air Lines Roblox" in home
    assert 'content="noindex, nofollow"' in private
