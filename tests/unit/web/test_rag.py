"""RAG top-level page tests"""


class TestRagPage:
    def test_rag_page_for_existing_company(self, seeded_aapl_client):
        resp = seeded_aapl_client.get("/rag/US_AAPL")
        assert resp.status_code == 200
        assert "Apple Inc" in resp.text
        assert "US_AAPL" in resp.text
        assert "保存済み定型分析" in resp.text

    def test_unknown_company_404(self, auth_client):
        resp = auth_client.get("/rag/US_NOPE")
        assert resp.status_code == 404

    def test_unauthenticated_redirects(self, client):
        resp = client.get("/rag/US_AAPL", follow_redirects=False)
        assert resp.status_code == 303
