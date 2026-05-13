"""Frontmatter, URL normalization, sidecar helpers (spec §5.4, §5.7, §5.3).

Frontmatter + sidecar functions are added in B.1.10; this file starts with
URL normalization so the symbols import cleanly.
"""
from __future__ import annotations
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from webpage_to_md.errors import ConvertError


# Attributes to normalize. Maps attribute name → tags it applies to.
_HREF_TAGS = ("a", "area")
_SRC_TAGS = ("img", "source", "iframe", "video", "audio", "embed")
_SRCSET_TAGS = ("img", "source")


def resolve_base(soup: BeautifulSoup, final_url: str | None) -> str:
    """Spec §5.7: <base href> wins, then final_url, then raise.

    Per HTML5, only the first <base> with an href attribute counts.
    """
    base_tag = soup.find("base", href=True)
    if base_tag is not None:
        href = base_tag.get("href")
        if href:
            return href
    if final_url:
        return final_url
    raise ConvertError(
        "no <base href> tag and no final_url; cannot resolve relative URLs"
    )


def _rewrite_srcset(value: str, base_url: str) -> str:
    """Parse comma-separated srcset, urljoin each non-data: URL, re-emit.

    data: URLs (which contain commas inside base64 payloads) are passed through
    by detecting them with a regex, replacing with sentinels before splitting on
    commas, then restoring them after processing.
    """
    if not value or not value.strip():
        return value

    # Strategy: protect data: URLs from the comma split by replacing them with
    # sentinels. A data: URL in a srcset looks like:
    #   data:<mime>[;<params>],<data>[ <descriptor>]
    # The tricky part is that base64 data may contain commas, so we match
    # "data:" followed by non-whitespace chars (including commas) up to the
    # optional whitespace + descriptor, then end of entry.
    #
    # We match greedily up to the next ", " that looks like a new srcset entry
    # (i.e., followed by a URL-ish token) or end of string.

    data_urls: dict[str, str] = {}
    counter = [0]

    def replace_data(m: re.Match) -> str:
        idx = counter[0]
        sentinel = f"__DATA_URL_{idx}__"
        data_urls[sentinel] = m.group(0)
        counter[0] += 1
        return sentinel

    # This pattern matches a data: URL including any embedded commas in the
    # base64 payload. It stops at a comma followed by whitespace and a
    # non-data non-comma character sequence (the start of the next srcset entry),
    # or at end of string.
    #
    # Simpler and more reliable: match "data:" then everything up to (but not
    # including) either ", <something_that_isnt_data>" or end-of-string.
    # We use a possessive approach: match data: then any chars that are NOT
    # the pattern ", [a-zA-Z/]" (which signals a new entry) or end.
    #
    # Practically: srcset entries are separated by ", " (comma + space).
    # A data: URL descriptor (e.g., "2x") comes after the last comma in the base64.
    # We match: data:[^,]*(,[^,\s][^,]*)* followed by optional \s+\S+
    # Breaking it down:
    #   data:      — literal
    #   [^,]*      — mime type up to first comma
    #   (,[^\s,]+[^\s]*)* — comma + data chunk (no leading space = not a new entry)
    #   (\s+\S+)?  — optional trailing descriptor like "2x"
    #
    # A new srcset entry after a comma always starts with optional whitespace,
    # so ", data:" or ", https:" etc. The key insight: inside a data: base64 blob
    # the characters after each comma are NOT preceded by whitespace when the
    # full string is split — they run together. But in the raw srcset value,
    # entries ARE separated by ", " (comma-space). So we can distinguish:
    # "base64data,morebytes" vs "entry1, entry2" by the presence of a space
    # after the comma.

    protected = re.sub(
        r'data:[^,\s]+(?:,[^\s][^,\s]*)*(?:,[^\s]+)*(?:\s+\S+)?',
        replace_data,
        value,
    )

    entries = [e.strip() for e in protected.split(",") if e.strip()]
    rewritten: list[str] = []
    for entry in entries:
        # Restore any sentinel that ended up in this entry
        restored_entry = entry
        for sentinel, original in data_urls.items():
            if sentinel in restored_entry:
                restored_entry = restored_entry.replace(sentinel, original)

        if restored_entry.startswith("data:"):
            rewritten.append(restored_entry)
            continue

        parts = restored_entry.split(None, 1)
        if len(parts) == 1:
            rewritten.append(urljoin(base_url, parts[0]))
        else:
            url, descriptor = parts
            rewritten.append(f"{urljoin(base_url, url)} {descriptor}")

    return ", ".join(rewritten)


def normalize_relative_urls(soup: BeautifulSoup, *, base_url: str) -> BeautifulSoup:
    """Mutate working `soup` so all Markdown-relevant URLs become absolute.

    `base_url` is used as the fallback final_url; if the soup contains a
    ``<base href>`` tag, that takes precedence per HTML5 (spec §5.7).
    The persisted source HTML must NOT be passed here — pass a working copy.
    """
    if base_url is None:
        raise ConvertError("normalize_relative_urls requires a non-None base_url")

    # Honour <base href> over the caller-supplied base_url (HTML5 precedence).
    resolved = resolve_base(soup, final_url=base_url)

    for tag_name in _HREF_TAGS:
        for el in soup.find_all(tag_name, href=True):
            el["href"] = urljoin(resolved, el["href"])

    for tag_name in _SRC_TAGS:
        for el in soup.find_all(tag_name, src=True):
            el["src"] = urljoin(resolved, el["src"])

    for tag_name in _SRCSET_TAGS:
        for el in soup.find_all(tag_name, srcset=True):
            el["srcset"] = _rewrite_srcset(el["srcset"], resolved)

    return soup
