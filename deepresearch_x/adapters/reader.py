from __future__ import annotations

import re
from dataclasses import dataclass

import httpx
from lxml import html as lxml_html


@dataclass
class PageReadResult:
    preview_text: str
    status: str
    error: str = ""


class HybridPageReader:
    """
    Extracts readable text from web pages with a robust fallback path.
    """

    def __init__(self, timeout_seconds: float = 8.0) -> None:
        self.timeout_seconds = timeout_seconds

    def read(self, url: str, max_chars: int) -> PageReadResult:
        direct = self._try_direct(url=url, max_chars=max_chars)
        if direct.preview_text:
            return direct

        fallback = self._try_jina_reader(url=url, max_chars=max_chars)
        if fallback.preview_text:
            return fallback
        if fallback.error:
            return fallback
        return direct

    def _try_direct(self, url: str, max_chars: int) -> PageReadResult:
        try:
            with httpx.Client(
                timeout=self.timeout_seconds,
                headers={"User-Agent": "DeepResearch-X/0.2"},
                follow_redirects=True,
            ) as client:
                resp = client.get(url)
            if resp.status_code >= 400:
                return PageReadResult(
                    preview_text="",
                    status="fetch_failed",
                    error=f"HTTP {resp.status_code}",
                )
            text = self._extract_readable_text(resp.text)
            if len(text) < 140:
                return PageReadResult(
                    preview_text="",
                    status="low_content",
                    error="Page contains too little readable text.",
                )
            return PageReadResult(
                preview_text=text[:max_chars],
                status="fulltext_direct",
            )
        except Exception as exc:
            return PageReadResult(preview_text="", status="fetch_failed", error=str(exc))

    def _try_jina_reader(self, url: str, max_chars: int) -> PageReadResult:
        try:
            normalized = self._jina_reader_url(url)
            with httpx.Client(
                timeout=self.timeout_seconds,
                headers={"User-Agent": "DeepResearch-X/0.2"},
            ) as client:
                resp = client.get(normalized)
            if resp.status_code >= 400:
                return PageReadResult(
                    preview_text="",
                    status="reader_failed",
                    error=f"Jina Reader HTTP {resp.status_code}",
                )
            cleaned = self._clean_plain_text(resp.text)
            if len(cleaned) < 120:
                return PageReadResult(
                    preview_text="",
                    status="reader_failed",
                    error="Jina Reader returned too little text.",
                )
            return PageReadResult(
                preview_text=cleaned[:max_chars],
                status="fulltext_reader",
            )
        except Exception as exc:
            return PageReadResult(preview_text="", status="reader_failed", error=str(exc))

    @staticmethod
    def _jina_reader_url(url: str) -> str:
        if url.startswith("https://"):
            return f"https://r.jina.ai/http://{url.removeprefix('https://')}"
        if url.startswith("http://"):
            return f"https://r.jina.ai/{url}"
        return f"https://r.jina.ai/http://{url}"

    def _extract_readable_text(self, raw_html: str) -> str:
        try:
            doc = lxml_html.fromstring(raw_html)
            for bad in doc.xpath("//script|//style|//noscript|//footer|//header|//nav|//svg"):
                bad.drop_tree()
            blocks = doc.xpath("//article//p|//main//p|//p|//li|//h1|//h2|//h3")
            chunks = []
            for block in blocks:
                text = " ".join(block.text_content().split())
                if len(text) >= 40:
                    chunks.append(text)
            merged = "\n".join(chunks)
            return self._clean_plain_text(merged)
        except Exception:
            text = re.sub(r"<[^>]+>", " ", raw_html)
            return self._clean_plain_text(text)

    @staticmethod
    def _clean_plain_text(text: str) -> str:
        text = re.sub(r"\s+", " ", text)
        return text.strip()

