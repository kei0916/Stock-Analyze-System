"""PdfConverter単体テスト"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from stock_analyze_system.services.pdf_converter import PdfConverter, _build_safe_url_fetcher


class TestConvert:
    @patch("stock_analyze_system.services.pdf_converter.asyncio")
    @patch("stock_analyze_system.services.pdf_converter.weasyprint")
    async def test_convert_creates_pdf(self, mock_wp, mock_asyncio, tmp_path):
        html_path = tmp_path / "test.html"
        html_path.write_text("<html><body>Hello</body></html>")
        output_path = tmp_path / "output.pdf"

        async def fake_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        mock_asyncio.to_thread = fake_to_thread
        mock_doc = MagicMock()
        mock_wp.HTML.return_value = mock_doc

        converter = PdfConverter()
        result = await converter.convert(html_path, output_path)

        assert result == output_path
        mock_wp.HTML.assert_called_once()
        assert mock_wp.HTML.call_args.kwargs["filename"] == str(html_path)
        assert callable(mock_wp.HTML.call_args.kwargs["url_fetcher"])
        mock_doc.write_pdf.assert_called_once_with(str(output_path))


class TestSafeUrlFetcher:
    @patch("stock_analyze_system.services.pdf_converter.URLFetcher")
    def test_delegates_to_url_fetcher_with_allowed_protocols(
        self, mock_url_fetcher, tmp_path,
    ):
        mock_fetcher = MagicMock()
        mock_fetcher.fetch.return_value = {"string": b"ok"}
        mock_url_fetcher.return_value = mock_fetcher
        asset = tmp_path / "style.css"
        asset.write_text("body { color: black; }")
        fetcher = _build_safe_url_fetcher(
            fetch_base_dir=tmp_path,
            allowed_root=tmp_path,
        )

        response = fetcher(asset.as_uri())

        assert response == {"string": b"ok"}
        mock_url_fetcher.assert_called_once_with(
            allowed_protocols={"file", "data"},
        )
        mock_fetcher.fetch.assert_called_once_with(
            asset.resolve().as_uri(),
        )

    def test_allows_data_url(self, tmp_path):
        fetcher = _build_safe_url_fetcher(
            fetch_base_dir=tmp_path,
            allowed_root=tmp_path,
        )

        response = fetcher("data:text/plain;base64,SGVsbG8=")

        assert response is not None

    def test_allows_local_file_within_root(self, tmp_path):
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        asset = raw_dir / "style.css"
        asset.write_text("body { color: black; }")

        fetcher = _build_safe_url_fetcher(
            fetch_base_dir=raw_dir,
            allowed_root=tmp_path,
        )

        response = fetcher(asset.as_uri())

        assert response is not None

    def test_allows_relative_file_within_html_directory(self, tmp_path):
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        asset = raw_dir / "style.css"
        asset.write_text("body { color: black; }")

        fetcher = _build_safe_url_fetcher(
            fetch_base_dir=raw_dir,
            allowed_root=tmp_path,
        )

        response = fetcher("style.css")

        assert response is not None

    def test_rejects_http_url(self, tmp_path):
        fetcher = _build_safe_url_fetcher(
            fetch_base_dir=tmp_path,
            allowed_root=tmp_path,
        )

        with pytest.raises(ValueError, match="Disallowed URL scheme"):
            fetcher("http://127.0.0.1:8765/evil.css")

    def test_rejects_relative_network_url(self, tmp_path):
        fetcher = _build_safe_url_fetcher(
            fetch_base_dir=tmp_path,
            allowed_root=tmp_path,
        )

        with pytest.raises(ValueError, match="relative-network"):
            fetcher("//127.0.0.1/evil.css")

    def test_rejects_file_outside_root(self, tmp_path):
        outside = tmp_path.parent / "outside.css"
        outside.write_text("body { color: red; }")
        fetcher = _build_safe_url_fetcher(
            fetch_base_dir=tmp_path,
            allowed_root=tmp_path,
        )

        with pytest.raises(ValueError, match="outside allowed root"):
            fetcher(outside.as_uri())

    def test_rejects_relative_path_outside_allowed_root(self, tmp_path):
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        outside = tmp_path.parent / "outside.css"
        outside.write_text("body { color: red; }")
        fetcher = _build_safe_url_fetcher(
            fetch_base_dir=raw_dir,
            allowed_root=tmp_path,
        )

        with pytest.raises(ValueError, match="outside allowed root"):
            fetcher("../../outside.css")


class TestGetOrConvert:
    @patch("stock_analyze_system.services.pdf_converter.asyncio")
    @patch("stock_analyze_system.services.pdf_converter.weasyprint")
    async def test_skip_if_pdf_exists(self, mock_wp, mock_asyncio, tmp_path):
        pdf_path = tmp_path / "converted.pdf"
        pdf_path.write_text("fake pdf")

        filing = MagicMock()
        filing.storage_path = str(tmp_path)

        converter = PdfConverter()
        result = await converter.get_or_convert(filing)

        assert result == pdf_path
        mock_wp.HTML.assert_not_called()

    @patch("stock_analyze_system.services.pdf_converter.asyncio")
    @patch("stock_analyze_system.services.pdf_converter.weasyprint")
    async def test_converts_when_no_pdf(self, mock_wp, mock_asyncio, tmp_path):
        html_dir = tmp_path / "raw"
        html_dir.mkdir()
        html_file = html_dir / "filing.html"
        html_file.write_text("<html>test</html>")

        filing = MagicMock()
        filing.storage_path = str(tmp_path)

        async def fake_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        mock_asyncio.to_thread = fake_to_thread
        mock_doc = MagicMock()
        mock_wp.HTML.return_value = mock_doc

        converter = PdfConverter()
        result = await converter.get_or_convert(filing)

        assert result == tmp_path / "converted.pdf"
        mock_wp.HTML.assert_called_once()

    @patch("stock_analyze_system.services.pdf_converter.asyncio")
    @patch("stock_analyze_system.services.pdf_converter.weasyprint")
    async def test_convert_uses_html_directory_for_relative_assets(
        self, mock_wp, mock_asyncio, tmp_path,
    ):
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        html_file = raw_dir / "filing.htm"
        css_file = raw_dir / "style.css"
        html_file.write_text("<html>test</html>")
        css_file.write_text("body { color: black; }")
        output_path = tmp_path / "converted.pdf"

        async def fake_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        mock_asyncio.to_thread = fake_to_thread
        mock_doc = MagicMock()
        mock_wp.HTML.return_value = mock_doc

        converter = PdfConverter()
        await converter.convert(html_file, output_path, allowed_root=tmp_path)

        fetcher = mock_wp.HTML.call_args.kwargs["url_fetcher"]
        response = fetcher("style.css")

        assert response is not None

    @patch("stock_analyze_system.services.pdf_converter.asyncio")
    @patch("stock_analyze_system.services.pdf_converter.weasyprint")
    async def test_converts_htm_filing_when_no_pdf(self, mock_wp, mock_asyncio, tmp_path):
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        html_file = raw_dir / "filing.htm"
        html_file.write_text("<html>test</html>")

        filing = MagicMock()
        filing.storage_path = str(tmp_path)

        async def fake_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        mock_asyncio.to_thread = fake_to_thread
        mock_doc = MagicMock()
        mock_wp.HTML.return_value = mock_doc

        converter = PdfConverter()
        result = await converter.get_or_convert(filing)

        assert result == tmp_path / "converted.pdf"
        mock_wp.HTML.assert_called_once()
        assert mock_wp.HTML.call_args.kwargs["filename"] == str(html_file)
        assert callable(mock_wp.HTML.call_args.kwargs["url_fetcher"])
        mock_doc.write_pdf.assert_called_once_with(str(tmp_path / "converted.pdf"))

    async def test_raises_when_no_html(self, tmp_path):
        filing = MagicMock()
        filing.storage_path = str(tmp_path)

        converter = PdfConverter()
        with pytest.raises(FileNotFoundError):
            await converter.get_or_convert(filing)
