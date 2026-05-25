"""Screening page route tests."""
import re


class TestScreeningPage:
    def test_authenticated_returns_screening_workspace(self, auth_client):
        resp = auth_client.get("/screening")

        assert resp.status_code == 200
        assert "スクリーニング" in resp.text
        assert 'data-fields-url="/api/screening/fields"' in resp.text
        assert 'data-run-url="/api/screening/run"' in resp.text
        assert 'data-distribution-url-template="/api/screening/distributions/{field}"' in resp.text
        assert 'data-targets-url="/api/screening/targets"' in resp.text
        # Histogram-range filter UI
        assert 'id="screening-histogram-grid"' in resp.text
        assert 'id="screening-add-field"' in resp.text
        assert 'id="screening-apply"' in resp.text
        assert 'id="screening-reset"' in resp.text
        assert 'id="screening-include-null"' in resp.text
        assert 'id="screening-limit"' in resp.text
        # Results
        assert 'id="screening-results"' in resp.text
        assert 'id="screening-results-count"' in resp.text
        assert 'id="screening-add-targets"' in resp.text

    def test_unauthenticated_redirects_to_login(self, client):
        resp = client.get("/screening", follow_redirects=False)

        assert resp.status_code == 303
        assert resp.headers["location"] == "/login"

    def test_rendered_sidebar_links_resolve_for_authenticated_user(self, auth_client):
        resp = auth_client.get("/")
        assert resp.status_code == 200

        hrefs = re.findall(r'<a class="sidebar__link" href="([^"]+)"', resp.text)
        assert hrefs
        assert "/screening" in hrefs

        for href in hrefs:
            linked = auth_client.get(href)
            assert linked.status_code != 404, href
