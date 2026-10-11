import os
os.environ.setdefault("DATABASE_URL","sqlite://")
os.environ.setdefault("SESSION_SECRET","unit-test-secret-with-32-or-more-characters")
os.environ.setdefault("COOKIE_SECURE","false")
from website.app.community import access_level,can_see
from website.app.config import Settings
from website.app.gallery import actual_mime,GALLERY,MAX_BYTES
from website.app.models import CommunityForm


def test_gallery_supports_all_seven_photos_plus_flight_promo():
    assert len(GALLERY)==8
    assert "flight-promo" in GALLERY
    assert "delta-hangar" in GALLERY
    assert MAX_BYTES>=2000000


def test_gallery_checks_bytes_not_untrusted_extension():
    assert actual_mime(b"\x89PNG\r\n\x1a\n"+b"0"*50)=="image/png"
    assert actual_mime(b"\xff\xd8\xff"+b"0"*50)=="image/jpeg"
    assert actual_mime(b"RIFF0000WEBP"+b"0"*50)=="image/webp"
    assert actual_mime(b"<script>alert(1)</script>") is None


def test_role_specific_forms_are_visible_only_for_authorized_guild_role_ids():
    form=CommunityForm(status="PUBLISHED",allowed_roles={"crew":["1554666482988875788"],"airlines":["1539016506216812567"]})
    assert can_see(form,{"crew":["1554666482988875788"]})
    assert can_see(form,{"airlines":["1539016506216812567"]})
    assert not can_see(form,{"crew":["1554669633573888010"]})
    form.status="CLOSED"
    assert not can_see(form,{"crew":["1554666482988875788"]})


def test_crew_authentication_only_role_does_not_get_staff_editor_access():
    assert access_level({"crew":["1554671178893885480"]})=="MEMBER"
    assert access_level({"crew":["1554665018690248714"]})=="OWNER"
    assert access_level({"crew":["1554666461644197988"]})=="ADMIN"
    assert access_level({"crew":["1554666482988875788"]})=="STAFF"


def test_role_defaults_do_not_confuse_main_and_crew_roles():
    settings=Settings()
    assert settings.crew_owner_role_ids=="1554665018690248714"
    assert settings.crew_admin_role_ids=="1554666461644197988"
    assert settings.crew_staff_role_ids=="1554666482988875788"
    assert settings.forms_staff_discord_role_ids=="1539016506216812567"
    assert settings.discord_invite_url=="https://discord.gg/u8GJF2br2M"


def test_join_button_uses_discord_oauth_and_not_raw_invitation():
    from pathlib import Path
    base=Path("website/templates/community_base.html").read_text()
    home=Path("website/templates/homepage.html").read_text()
    main=Path("website/app/main.py").read_text()
    oauth=Path("website/app/oauth.py").read_text()
    assert 'href="/join"' in home
    assert 'href="/join"' in base
    assert 'Gallery</a>' not in base
    assert '@app.get("/join")' in main
    assert '@app.get("/welcome", response_class=HTMLResponse)' in main
    assert 'guilds.join' in oauth
    assert 'client.put(' in oauth


def test_customer_navigation_does_not_link_to_protected_gallery_editor():
    from pathlib import Path
    nav=Path("website/templates/community_base.html").read_text()
    assert '/gallery/manage' not in nav
    assert '{% if access is defined' in nav


def test_forms_empty_state_is_role_aware_and_uses_modal():
    from pathlib import Path
    page=Path("website/templates/forms/index.html").read_text()
    endpoint=Path("website/app/community.py").read_text()
    styles=Path("website/static/community.css").read_text()
    assert 'open_forms_count' in endpoint
    assert 'if not open_forms_count' in page
    assert 'showModal()' in page
    assert 'There aren\'t any forms open for you.' in page
    assert 'href="/forms/new"' in page
    assert 'class="community-btn primary create-form-fab"' in page
    assert 'if access != "MEMBER"' in page
    assert 'position:fixed' in styles


def test_sky_miles_navigation_does_not_delay_clicks():
    from pathlib import Path
    html = Path("website/templates/base.html").read_text()
    assert 'setTimeout(()=>location.assign(next.href),720)' not in html
    assert 'id="deployment-modal"' not in html
    assert 'id="route-transition"' not in html
    assert 'visibilitychange' in html


def test_homepage_prioritizes_main_image_and_defers_gallery_decode():
    from pathlib import Path
    html = Path("website/templates/homepage.html").read_text()
    assert 'fetchpriority="high"' in html
    assert 'loading="lazy" decoding="async"' in html
    assert 'href="/join">Join Delta Air Lines on Discord' in html



def test_public_homepage_header_and_footer_branding():
    from pathlib import Path
    base = Path("website/templates/community_base.html").read_text()
    css = Path("website/static/community.css").read_text()
    assert 'class="community-primary-nav"' in base
    assert '<a href="/flights">Flights</a>' in base
    assert '<a href="/forms">Forms</a>' in base
    assert '<a href="/dashboard">SkyMiles</a>' in base
    assert '.community-header .community-primary-nav a{' in css
    assert 'font-size:clamp(15px,1.13vw,19px)' in css
    assert 'class="community-footer-brand"' in base
    assert '<img src="/static/delta-emblem.svg"' in base
    assert '.community-footer-brand img{' in css
    assert '@media(max-width:700px)' in css
