"""Static checks for the GitHub Pages website (no network or external validator needed)."""
import re
from html.parser import HTMLParser
from pathlib import Path


SITE = Path(__file__).resolve().parents[1] / "website"
PAGES = ("index.html", "privacy.html", "terms.html")
WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "deploy-pages.yml"


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.assets = []
        self.titles = []
        self.descriptions = []
        self.scripts = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "a" and "href" in values:
            self.links.append(values["href"])
        if tag == "img" and "src" in values:
            self.assets.append(values["src"])
        if tag == "link" and "href" in values:
            self.assets.append(values["href"])
        if tag == "title":
            self._in_title = True
        if tag == "meta" and values.get("name") == "description":
            self.descriptions.append(values.get("content", ""))
        if tag == "script":
            self.scripts += 1

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.titles.append(data)


def _parse(page):
    parser = PageParser()
    parser.feed((SITE / page).read_text(encoding="utf-8"))
    parser.close()
    return parser


def test_pages_parse_with_titles_and_descriptions():
    for page in PAGES:
        parsed = _parse(page)
        assert "".join(parsed.titles).strip(), page
        assert any(len(description) >= 40 for description in parsed.descriptions), page
        assert parsed.scripts == 0, page


def test_internal_links_and_assets_resolve():
    for page in PAGES:
        parsed = _parse(page)
        for target in parsed.links + parsed.assets:
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            assert (SITE / target.split("#", 1)[0]).exists(), f"{page}: {target}"


def test_navigation_and_footer_link_all_pages():
    for page in PAGES:
        links = set(_parse(page).links)
        for target in PAGES:
            assert target in links, f"{page} is missing a link to {target}"


def test_no_external_scripts_or_tracking_services():
    for page in PAGES:
        text = (SITE / page).read_text(encoding="utf-8").lower()
        assert "<script" not in text, page
        for marker in ("googletagmanager", "google-analytics", "gtag(", "adsense", "facebook.net"):
            assert marker not in text, f"{page}: {marker}"


def test_privacy_statements_match_implementation():
    text = (SITE / "privacy.html").read_text(encoding="utf-8")
    assert "https://www.googleapis.com/auth/youtube.upload" in text
    for phrase in (
        "videos.insert",
        "GitHub Actions Secrets",
        "private",
        "SHA-256",
        "myaccount.google.com/permissions",
        "not sold, shared with third parties, or used for advertising",
        "19 November 2026",
    ):
        assert phrase in text, phrase


def test_contact_email_is_present():
    for page in PAGES:
        text = (SITE / page).read_text(encoding="utf-8")
        assert "mailto:keneth.a.liwanag@gmail.com" in text, page
        assert "keneth.a.liwanag@gmail.com" in text, page
        assert "CONTACT_PLACEHOLDER" not in text, page


def test_no_credential_values_in_website_files():
    for path in SITE.rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        assert not re.search(r"ya29\.|GOCSPX-|AIza[0-9A-Za-z_-]{20,}|ghp_[0-9A-Za-z]{20,}", text), path.name


def test_responsive_layout_and_accessibility_basics():
    css = (SITE / "assets" / "styles.css").read_text(encoding="utf-8")
    assert "@media (max-width: 640px)" in css
    assert "auto-fit" in css
    for page in PAGES:
        text = (SITE / page).read_text(encoding="utf-8")
        assert 'name="viewport"' in text, page
        assert '<html lang="en">' in text, page
        assert 'class="skip-link"' in text, page
        assert 'aria-label="Main navigation"' in text, page


def test_deploy_workflow_is_manual_least_privilege_and_isolated():
    text = WORKFLOW.read_text(encoding="utf-8")
    trigger_section = text.split("permissions:", 1)[0]
    assert "workflow_dispatch:" in trigger_section
    for forbidden in ("schedule:", "pull_request:", "  push:"):
        assert forbidden not in trigger_section
    assert "contents: read" in text
    assert "pages: write" in text
    assert "id-token: write" in text
    assert "path: ./website" in text
    assert "secrets." not in text
