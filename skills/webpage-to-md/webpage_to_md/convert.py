"""Public convert() — orchestration over fetch + parse + persist (spec §5.2)."""
from __future__ import annotations
import hashlib
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Union
from bs4 import BeautifulSoup
from webpage_to_md._clock import _clock
from webpage_to_md.config import load_config, fingerprint
from webpage_to_md.errors import ConvertError
from webpage_to_md.extraction import select_content_node
from webpage_to_md.html_to_md import convert_to_markdown
from webpage_to_md.manifest import append_manifest_row
from webpage_to_md.naming import derive_stem
from webpage_to_md.provenance import (
    build_frontmatter,
    normalize_relative_urls,
    read_meta_sidecar,
    resolve_base,
    write_meta_sidecar,
)
from webpage_to_md.result import ConvertResult
from webpage_to_md.routing import SourceKind, resolve_source
from webpage_to_md.skill_imports import use, validate_imported

# Import web-fetch via the sibling-skill helper (spec §8.1).
use("web-fetch")
import webfetch  # noqa: E402
validate_imported("webfetch", "web-fetch")
from webfetch import fetch as _wf_fetch  # noqa: E402
WEB_FETCH_VERSION = getattr(webfetch, "__version__", "unknown")


def _fetch(url: str):
    """Indirection so tests can patch webpage_to_md.convert._fetch."""
    return _wf_fetch(url)


def _extract_title(soup: BeautifulSoup) -> str:
    t = soup.find("title")
    if t and t.get_text(strip=True):
        return t.get_text(strip=True)
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(strip=True)
    return ""


def _extract_canonical(soup: BeautifulSoup) -> str | None:
    link = soup.find("link", rel="canonical")
    if link and link.get("href"):
        return link["href"]
    return None


def convert(
    source: Union[str, Path],
    output_dir: Path,
    *,
    selector: str | None = None,
    output_stem: str | None = None,
    emit_frontmatter: bool = True,
    cfg: dict[str, Any] | None = None,
) -> ConvertResult:
    """Convert URL or local HTML to Markdown with persisted source (spec §5.2)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    if cfg is None:
        cfg = load_config()
    config_sha256 = fingerprint(cfg)
    extraction_strategy = cfg["convert"]["extraction"]["strategy"]
    manifest_path = output_dir / "manifest.jsonl"

    kind, value = resolve_source(source)

    if kind == SourceKind.URL:
        return _convert_url(
            url=value,
            output_dir=output_dir,
            selector=selector,
            output_stem=output_stem,
            emit_frontmatter=emit_frontmatter,
            cfg=cfg,
            config_sha256=config_sha256,
            extraction_strategy=extraction_strategy,
            manifest_path=manifest_path,
        )
    return _convert_local(
        path=value,
        output_dir=output_dir,
        selector=selector,
        output_stem=output_stem,
        emit_frontmatter=emit_frontmatter,
        cfg=cfg,
        config_sha256=config_sha256,
        extraction_strategy=extraction_strategy,
        manifest_path=manifest_path,
    )


def _convert_url(
    *,
    url: str,
    output_dir: Path,
    selector: str | None,
    output_stem: str | None,
    emit_frontmatter: bool,
    cfg: dict[str, Any],
    config_sha256: str,
    extraction_strategy: str,
    manifest_path: Path,
) -> ConvertResult:
    started = _clock()
    try:
        result = _fetch(url)
    except Exception as e:
        completed = _clock()
        append_manifest_row(
            manifest_path,
            status="failed",
            result=None,
            requested_url=url,
            error_category=getattr(e, "error_category", "unknown"),
            error_message=str(e),
            config_sha256=config_sha256,
            duration_ms=(completed - started).total_seconds() * 1000,
            started_at=started,
            completed_at=completed,
            extraction_strategy=extraction_strategy,
            selector=selector,
        )
        raise

    stem = output_stem or derive_stem(result.final_url)

    # PDF passthrough (B.1.14 finishes this branch)
    if (result.content_type or "").lower().startswith("application/pdf"):
        return _persist_pdf_only(
            result=result,
            output_dir=output_dir,
            stem=stem,
            config_sha256=config_sha256,
            extraction_strategy=extraction_strategy,
            selector=selector,
            manifest_path=manifest_path,
            started=started,
        )

    if not (result.content_type or "").lower().startswith("text/html"):
        completed = _clock()
        msg = f"unsupported content type: {result.content_type}"
        append_manifest_row(
            manifest_path,
            status="failed",
            result=result,
            error_category="unsupported_content_type",
            error_message=msg,
            config_sha256=config_sha256,
            duration_ms=(completed - started).total_seconds() * 1000,
            extraction_strategy=extraction_strategy,
            selector=selector,
        )
        raise ConvertError(msg)

    # Persist source HTML + sidecar
    out_html = output_dir / f"{stem}.html"
    out_html.write_bytes(result.content)
    write_meta_sidecar(
        out_html.with_suffix(".html.meta.json"),
        result=result,
        web_fetch_version=WEB_FETCH_VERSION,
    )

    # Work on a soup copy; persisted HTML stays untouched (§5.2 invariant).
    working_soup = BeautifulSoup(result.content, "html.parser")
    base = resolve_base(working_soup, final_url=result.final_url)
    working_soup = normalize_relative_urls(working_soup, base_url=base)

    title = _extract_title(working_soup)
    canonical = _extract_canonical(working_soup)

    content_node = select_content_node(
        working_soup, selector=selector, strategy=extraction_strategy
    )
    md_body = convert_to_markdown(content_node, cfg)

    out_md = output_dir / f"{stem}.md"
    if emit_frontmatter:
        fm = build_frontmatter(
            result=result,
            source_artifact=out_html.name,
            derived_artifact=out_md.name,
            selector=selector,
            extraction_strategy=extraction_strategy,
            config_sha256=config_sha256,
            title=title,
            canonical_url=canonical,
        )
        out_md.write_text(fm + md_body, encoding="utf-8")
    else:
        out_md.write_text(md_body, encoding="utf-8")

    completed = _clock()
    append_manifest_row(
        manifest_path,
        status="ok",
        result=result,
        source_artifact=out_html.name,
        derived_artifact=out_md.name,
        selector=selector,
        extraction_strategy=extraction_strategy,
        config_sha256=config_sha256,
        duration_ms=(completed - started).total_seconds() * 1000,
    )
    return ConvertResult(
        markdown_path=out_md,
        source_path=out_html,
        pdf_path=None,
        md_generated=True,
        content_type=result.content_type,
    )


def _persist_pdf_only(
    *,
    result,
    output_dir: Path,
    stem: str,
    config_sha256: str,
    extraction_strategy: str,
    selector: str | None,
    manifest_path: Path,
    started,
) -> ConvertResult:
    """Spec §5.9 (v0.1 callout): save <stem>.pdf, no MD generated."""
    out_pdf = output_dir / f"{stem}.pdf"
    out_pdf.write_bytes(result.content)

    completed = _clock()
    append_manifest_row(
        manifest_path,
        status="ok",
        result=result,
        source_artifact=out_pdf.name,
        derived_artifact=None,
        selector=selector,
        extraction_strategy=extraction_strategy,
        config_sha256=config_sha256,
        duration_ms=(completed - started).total_seconds() * 1000,
    )
    return ConvertResult(
        markdown_path=None,
        source_path=None,
        pdf_path=out_pdf,
        md_generated=False,
        content_type=result.content_type,
    )


def _convert_local(
    *,
    path: Path,
    output_dir: Path,
    selector: str | None,
    output_stem: str | None,
    emit_frontmatter: bool,
    cfg: dict[str, Any],
    config_sha256: str,
    extraction_strategy: str,
    manifest_path: Path,
) -> ConvertResult:
    """Spec §5.3 iterate-without-re-fetching: convert a local HTML file.

    No network call is made. Provenance comes from the sidecar when present,
    falls back to <link rel="canonical"> in the HTML, then to the file path.
    """
    started = _clock()
    raw = path.read_bytes()
    sidecar = read_meta_sidecar(path.with_suffix(".html.meta.json"))

    # Parse to extract canonical / title (needed for both branches).
    working_soup = BeautifulSoup(raw, "html.parser")
    canonical_in_html = _extract_canonical(working_soup)
    title = _extract_title(working_soup)

    # Build a synthetic result record shaped like FetchResult for downstream helpers.
    if sidecar is not None:
        synthetic_url = sidecar.get("url") or sidecar.get("final_url") or str(path)
        synthetic_final = sidecar.get("final_url") or synthetic_url
        original_fetched_at_str = sidecar.get("fetched_at")
        source_sha256 = sidecar.get("source_sha256") or _sha256(raw)
    else:
        synthetic_url = canonical_in_html or f"file://{path}"
        synthetic_final = canonical_in_html or f"file://{path}"
        original_fetched_at_str = None
        source_sha256 = _sha256(raw)

    synthetic = SimpleNamespace(
        requested_url=synthetic_url,
        final_url=synthetic_final,
        redirect_chain=[],
        started_at=started,
        completed_at=started,
        content=raw,
        content_type="text/html",
        content_type_source=None,
        encoding="utf-8",
        content_length_bytes=len(raw),
        content_hash_sha256=source_sha256,
        http_status=None,
        fetch_method=None,  # local — no network fetch
        error_category=None,
        headers={},
        etag=None,
        last_modified=None,
        not_modified=False,
        playwright_details=None,
    )

    if synthetic_final.startswith("http"):
        stem = output_stem or derive_stem(synthetic_final)
    else:
        stem = output_stem or path.stem

    # Normalize URLs against canonical/sidecar/file:// in that order.
    try:
        base = resolve_base(working_soup, final_url=synthetic_final)
    except ConvertError:
        base = f"file://{path}"
    working_soup = normalize_relative_urls(working_soup, base_url=base)

    content_node = select_content_node(
        working_soup, selector=selector, strategy=extraction_strategy
    )
    md_body = convert_to_markdown(content_node, cfg)

    out_md = output_dir / f"{stem}.md"
    if emit_frontmatter:
        original_fetched_at: datetime | None = None
        if original_fetched_at_str:
            try:
                original_fetched_at = datetime.fromisoformat(original_fetched_at_str)
            except ValueError:
                original_fetched_at = None
        fm = build_frontmatter(
            result=synthetic,
            source_artifact=path.name,
            derived_artifact=out_md.name,
            selector=selector,
            extraction_strategy=extraction_strategy,
            config_sha256=config_sha256,
            title=title,
            canonical_url=canonical_in_html,
            original_fetched_at=original_fetched_at,
            re_converted_at=_clock(),
        )
        out_md.write_text(fm + md_body, encoding="utf-8")
    else:
        out_md.write_text(md_body, encoding="utf-8")

    completed = _clock()
    append_manifest_row(
        manifest_path,
        status="ok",
        result=synthetic,
        source_artifact=path.name,
        derived_artifact=out_md.name,
        selector=selector,
        extraction_strategy=extraction_strategy,
        config_sha256=config_sha256,
        duration_ms=(completed - started).total_seconds() * 1000,
    )
    return ConvertResult(
        markdown_path=out_md,
        source_path=path,
        pdf_path=None,
        md_generated=True,
        content_type="text/html",
    )


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
