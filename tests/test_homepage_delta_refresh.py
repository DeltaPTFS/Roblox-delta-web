from pathlib import Path

def source(path):
    return Path(path).read_text(encoding="utf-8")

def test_homepage_airline_booking_uses_real_links():
    home=source("website/templates/homepage.html")
    assert 'class="delta-journey-tabs"' in home
    assert 'class="delta-service-tabs"' in home
    assert 'class="delta-route-fields"' in home
    assert 'class="delta-home-promo"' in home
    assert 'href="/flights"' in home
    assert 'href="/trips"' in home
    assert 'href="/news"' in home
    assert 'not real-world airline services' in home
    assert 'class="air-hero"' in home
    assert 'featured_news' in home

def test_homepage_footer_is_scoped_to_home_and_accessible():
    base=source("website/templates/community_base.html")
    footer=source("website/templates/_homepage_airline_footer.html")
    css=source("website/static/homepage-delta-refresh.css")
    assert '{% include "_homepage_airline_footer.html" %}' in base
    assert '<footer class="community-footer">' in base
    assert 'request.url.path in [\' /\', \'/home\']' not in base
    assert '<details>' in footer and '<summary>' in footer
    assert 'role="search"' in footer
    assert 'Not affiliated with' in footer
    assert 'max-width:700px' in css
    assert 'body.delta-airline-home .delta-home-footer' in css
