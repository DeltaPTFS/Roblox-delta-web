from pathlib import Path


def test_delta_six_advertisements_and_five_second_rotation():
    root=Path("website")
    home=(root/"templates/homepage.html").read_text()
    base=(root/"templates/community_base.html").read_text()
    js=(root/"static/delta-ads.js").read_text()
    css=(root/"static/delta-ads.css").read_text()
    names=["delta-lax","delta-new-york","delta-centennial-ad","delta-tech-ops","delta-engine","delta-skipping"]
    assert home.count('data-ad-slide=')==6
    assert home.count('data-ad-carousel')==1
    assert home.count('data-ad-dot=')==6
    assert "const intervalMs = 5000" in js
    assert "IntersectionObserver" in js
    assert "visibilitychange" in js
    assert "prefers-reduced-motion: reduce" in css
    assert "object-fit:contain" in css
    assert 'delta-ads.js' in base
    assert home.index('class="delta-advertising"')<home.index('class="community-hero"')
    assert "Every flight." in home
    assert "<script" not in home.split("{% block content %}",1)[0]
    for name in names:
        file=root/"static/ads"/(name+".webp")
        assert file.is_file()
        raw=file.read_bytes()
        assert raw[:4]==b"RIFF" and raw[8:12]==b"WEBP"
        assert 20000<len(raw)<500000
