from __future__ import annotations

import base64
import html
import re
from email import policy
from email.parser import BytesParser
from pathlib import Path
from urllib.parse import unquote

from playwright.sync_api import sync_playwright


def eml_to_pdf(
    input_file_path: str | Path,
    output_file_path: str | Path,
) -> None:
    """
    Convert an email file (.eml) to PDF.

    Parameters:
        input_file_path: Full path to the input .eml file.
        output_file_path: Full path for the output PDF file.

    The PDF includes email headers, body, and inline images.
    Regular attachments are listed by filename, not merged into the PDF.
    """

    source = Path(input_file_path).expanduser()
    destination = Path(output_file_path).expanduser()

    if not source.is_file():
        raise FileNotFoundError(
            f"Input email file not found: {source}"
        )

    if source.resolve() == destination.resolve():
        raise ValueError(
            "Input email and output PDF must be different files."
        )

    destination.parent.mkdir(parents=True, exist_ok=True)

    # Read and parse the email.
    with source.open("rb") as file:
        message = BytesParser(
            policy=policy.default
        ).parse(file)

    # Prefer HTML; use plain text if HTML is unavailable.
    body_part = message.get_body(
        preferencelist=("html", "plain")
    )

    if body_part is None:
        raise ValueError(
            "The email contains no readable text or HTML body."
        )

    try:
        body_content = body_part.get_content()
    except (LookupError, UnicodeDecodeError):
        raw = body_part.get_payload(decode=True) or b""
        charset = body_part.get_content_charset() or "utf-8"
        body_content = raw.decode(charset, errors="replace")

    if body_part.get_content_type() == "text/html":
        body_html = body_content
    else:
        body_html = (
            '<div style="white-space:pre-wrap; '
            'overflow-wrap:anywhere; '
            'font-family:Arial,sans-serif">'
            + html.escape(body_content)
            + "</div>"
        )

    # Embed inline images referenced using cid: in the email HTML.
    cid_images = {}

    for part in message.walk():
        content_id = part.get("Content-ID")

        if not content_id or part.is_multipart():
            continue

        data = part.get_payload(decode=True)

        if data is None:
            continue

        content_id = content_id.strip().strip("<>").lower()
        mime_type = part.get_content_type()

        encoded = base64.b64encode(data).decode("ascii")

        cid_images[content_id] = (
            f"data:{mime_type};base64,{encoded}"
        )

    def replace_cid(match):
        content_id = (
            unquote(match.group(1))
            .strip()
            .strip("<>")
            .lower()
        )

        return cid_images.get(content_id, match.group(0))

    body_html = re.sub(
        r"""cid:([^"'\s>)]+)""",
        replace_cid,
        body_html,
        flags=re.IGNORECASE,
    )

    # Collect email headers.
    rows = []

    for label, field in [
        ("From", "from"),
        ("To", "to"),
        ("Cc", "cc"),
        ("Date", "date"),
        ("Subject", "subject"),
    ]:
        value = message.get(field)

        if value:
            rows.append(
                f"<tr><th>{label}</th>"
                f"<td>{html.escape(str(value).strip())}</td></tr>"
            )

    # List regular attachments by filename.
    attachment_names = []

    for part in message.walk():
        filename = part.get_filename()

        if (
            filename
            and part.get_content_disposition() != "inline"
        ):
            attachment_names.append(str(filename))

    if attachment_names:
        names = ", ".join(
            html.escape(name) for name in attachment_names
        )

        rows.append(
            f"<tr><th>Attachments</th><td>{names}</td></tr>"
        )

    header_html = (
        '<section class="email-meta">'
        "<h1>Email</h1><table>"
        + "".join(rows)
        + "</table></section>"
    )

    styles = """
    <meta charset="utf-8">
    <style>
        @page {
            size: A4;
            margin: 16mm;
        }

        body {
            font-family: Arial, Helvetica, sans-serif;
            font-size: 10pt;
            color: #222;
            overflow-wrap: anywhere;
        }

        img {
            max-width: 100% !important;
            height: auto;
        }

        table {
            max-width: 100%;
        }

        .email-meta {
            font-size: 9pt;
            margin-bottom: 18px;
            padding-bottom: 12px;
            border-bottom: 1px solid #bbb;
            page-break-inside: avoid;
        }

        .email-meta h1 {
            font-size: 15pt;
            margin: 0 0 8px;
        }

        .email-meta table {
            border-collapse: collapse;
            width: 100%;
        }

        .email-meta th,
        .email-meta td {
            text-align: left;
            vertical-align: top;
            padding: 3px 8px 3px 0;
            overflow-wrap: anywhere;
        }

        .email-meta th {
            width: 82px;
            color: #666;
        }

        a {
            overflow-wrap: anywhere;
        }
    </style>
    """

    # Prepare a complete HTML document.
    if re.search(r"<html\b", body_html, re.IGNORECASE):
        if re.search(r"<head\b", body_html, re.IGNORECASE):
            body_html = re.sub(
                r"</head\s*>",
                styles + "</head>",
                body_html,
                count=1,
                flags=re.IGNORECASE,
            )
        else:
            body_html = re.sub(
                r"<html\b[^>]*>",
                lambda match: (
                    match.group(0)
                    + "<head>"
                    + styles
                    + "</head>"
                ),
                body_html,
                count=1,
                flags=re.IGNORECASE,
            )

        if re.search(r"<body\b", body_html, re.IGNORECASE):
            body_html = re.sub(
                r"(<body\b[^>]*>)",
                lambda match: match.group(1) + header_html,
                body_html,
                count=1,
                flags=re.IGNORECASE,
            )
        else:
            body_html = re.sub(
                r"</head\s*>",
                "</head><body>" + header_html,
                body_html,
                count=1,
                flags=re.IGNORECASE,
            ) + "</body>"
    else:
        body_html = (
            "<!doctype html><html><head>"
            + styles
            + "</head><body>"
            + header_html
            + body_html
            + "</body></html>"
        )

    # Render the email using Chromium and save as PDF.
    # External resources are blocked during rendering.
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()

        try:
            page = browser.new_page(
                java_script_enabled=False
            )

            def block_external_resources(route):
                scheme = route.request.url.split(":")[0].lower()

                if scheme in {"http", "https", "file", "ftp"}:
                    route.abort()
                else:
                    route.continue_()

            page.route("**/*", block_external_resources)

            page.set_content(
                body_html,
                wait_until="load",
                timeout=30000,
            )

            page.pdf(
                path=str(destination),
                format="A4",
                print_background=True,
                prefer_css_page_size=True,
            )

        finally:
            browser.close()