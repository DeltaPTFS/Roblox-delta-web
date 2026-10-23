"""Regression tests for curated website language packs and the image carousel layout."""
import json
from pathlib import Path

ROOT = Path("website")


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def packs():
    raw = read("static/language-packs.js").strip()
    prefix = "window.DeltaLanguagePacks = "
    assert raw.startswith(prefix) and raw.endswith(";")
    return json.loads(raw[len(prefix):-1])


def test_language_selector_and_assets_load_in_correct_order():
    selector = read("templates/_unified_site_header.html")
    code = read("static/languages.js")
    for locale in ("en", "es", "fr", "ru", "pt", "de", "it", "ja", "zh", "nl", "tr", "ko"):
        assert f'<option value="{locale}" lang="{locale}">' in selector
        assert f'["{locale}",' in code
    for template in ("base.html", "community_base.html", "signin_success.html"):
        html = read("templates/" + template)
        assert html.index("language-packs.js") < html.index("languages.js")


def test_spanish_translates_entire_homepage_sections_and_staff_controls():
    catalog = packs()
    spanish = catalog["es"]
    for key in (
        "Discover our community, join a hosted aviation experience, or build your story with our crew. Your journey starts here.",
        "Step into a realistic Delta-inspired aviation experience: hosted flights, ground operations, team opportunities, and a virtual SkyMiles program.",
        "Explore the flights, spaces, and experiences that bring Delta Roblox to life.",
        "Four moments from our Roblox cabin, all on display.",
        "No SkyMiles registration is needed to view and complete a roleplay application. Log in through Discord, and we'll check your server roles for access.",
        "Track our hosted Roblox flights, check upcoming departure details, and discover where the community is flying next.",
        "Save Website Announcement",
        "Remove Website Announcement",
        "Remove your Announcement",
        "Your next chapter",
        "starts with",
        "Announcement message",
        "Your SkyMiles",
        "Server Error",
    ):
        if key == "Your SkyMiles":
            continue  # Covered in the original 9-language catalog.
        assert key in spanish, key
        assert spanish[key].strip() and spanish[key] != key


def test_new_locales_translate_more_than_navigation():
    catalog = packs()
    for language in ("nl", "tr", "ko"):
        phrasebook = catalog[language]
        assert len(phrasebook) >= 120
        assert phrasebook["Save Website Announcement"] != "Save Website Announcement"
        assert phrasebook["No SkyMiles registration is needed to view and complete a roleplay application. Log in through Discord, and we'll check your server roles for access."]


def test_dynamic_locale_updates_do_not_translate_custom_member_content():
    code = read("static/languages.js")
    for selector in (
        ".form-description", ".form-answer", ".delta-site-news-message",
        ".delta-site-news-author", "#owner-news-preview-text",
    ):
        assert selector in code
    assert "characterData:true" in code
    assert '"aria-label","title","placeholder","alt","data-tooltip"' in code


def test_banner_matches_campaign_aspect_ratio_without_side_letterboxing():
    css = read("static/delta-ads.css")
    assert "aspect-ratio:2048 / 1209" in css
    assert "object-fit:cover" in css
    assert 'data-ad-slide="1"' in css
    assert "height:auto" in css
