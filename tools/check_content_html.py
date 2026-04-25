#!/usr/bin/env python3
"""Validate whether article detail responses contain non-empty content_html."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


def build_headers(token: str | None = None) -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def fetch_json(url: str, timeout: int = 15, token: str | None = None) -> dict[str, Any]:
    request = urllib.request.Request(url, headers=build_headers(token))
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def login_and_get_token(base_url: str, username: str, password: str, timeout: int) -> str:
    form_data = urllib.parse.urlencode({"username": username, "password": password}).encode()
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/v1/wx/auth/login",
        data=form_data,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.load(response)
    token = ((payload.get("data") or {}).get("access_token") or "").strip()
    if not token:
        raise ValueError("login succeeded but access_token was missing")
    return token


def summarize_article_detail(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data") or {}
    content = data.get("content") or ""
    content_html = data.get("content_html") or ""
    return {
        "article_id": data.get("id", ""),
        "title": data.get("title", ""),
        "has_content": int(data.get("has_content", 0) or 0),
        "content_length": len(content),
        "content_html_length": len(content_html),
        "content_html_present": bool(content_html.strip()),
    }


def get_article_ids(base_url: str, mp_id: str, limit: int, timeout: int, token: str | None) -> list[str]:
    query = urllib.parse.urlencode(
        {
            "offset": 0,
            "limit": limit,
            "mp_id": mp_id,
        }
    )
    url = f"{base_url.rstrip('/')}/api/v1/wx/articles?{query}"
    payload = fetch_json(url, timeout=timeout, token=token)
    articles = (payload.get("data") or {}).get("list") or []
    return [article.get("id", "") for article in articles if article.get("id")]


def check_article(base_url: str, article_id: str, timeout: int, token: str | None) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/api/v1/wx/articles/{article_id}"
    payload = fetch_json(url, timeout=timeout, token=token)
    return summarize_article_detail(payload)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check whether we-mp-rss article detail responses have non-empty content_html."
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8001",
        help="Base URL of the running we-mp-rss service.",
    )
    parser.add_argument(
        "--article-id",
        help="Single article ID to check.",
    )
    parser.add_argument(
        "--mp-id",
        help="Fetch the newest articles for a specific mp_id and check each one.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="How many latest articles to inspect when --mp-id is provided.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=15,
        help="HTTP timeout in seconds.",
    )
    parser.add_argument(
        "--token",
        help="Bearer token used to access protected article APIs.",
    )
    parser.add_argument(
        "--username",
        help="Username used to log in and obtain a token automatically.",
    )
    parser.add_argument(
        "--password",
        help="Password used to log in and obtain a token automatically.",
    )
    return parser


def print_result(result: dict[str, Any]) -> None:
    print(
        "\t".join(
            [
                result["article_id"],
                result["title"],
                f"has_content={result['has_content']}",
                f"content_len={result['content_length']}",
                f"content_html_len={result['content_html_length']}",
                f"content_html_present={str(result['content_html_present']).lower()}",
            ]
        )
    )


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not args.article_id and not args.mp_id:
        parser.error("one of --article-id or --mp-id is required")

    try:
        token = args.token
        if not token and args.username and args.password:
            token = login_and_get_token(args.base_url, args.username, args.password, args.timeout)

        article_ids = []
        if args.article_id:
            article_ids.append(args.article_id)
        if args.mp_id:
            article_ids.extend(get_article_ids(args.base_url, args.mp_id, args.limit, args.timeout, token))

        deduped_ids = []
        seen = set()
        for article_id in article_ids:
            if article_id in seen:
                continue
            seen.add(article_id)
            deduped_ids.append(article_id)

        if not deduped_ids:
            print("no article ids found", file=sys.stderr)
            return 2

        all_have_content_html = True
        print("article_id\ttitle\thas_content\tcontent_len\tcontent_html_len\tcontent_html_present")
        for article_id in deduped_ids:
            result = check_article(args.base_url, article_id, args.timeout, token)
            print_result(result)
            all_have_content_html = all_have_content_html and result["content_html_present"]

        return 0 if all_have_content_html else 1
    except urllib.error.HTTPError as exc:
        print(f"http error: {exc.code} {exc.reason}", file=sys.stderr)
        return 3
    except urllib.error.URLError as exc:
        print(f"request failed: {exc}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
