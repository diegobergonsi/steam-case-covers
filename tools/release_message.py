#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""Maintainers and CI: the text of a release, taken from docs/CHANGELOG.md (standard library only).

    release_message.py body v1.5.0        the release page text: that version's changelog section and how to check the files
    release_message.py announce v1.5.0    the JSON for a Discord webhook: one embed with the same section and the release link

The release workflow runs both after it publishes a release, and the "Announce a release" workflow can send the message again by hand.
A missing or empty changelog section exits with status 1, so a release without notes is noticed."""
import argparse, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
CHANGELOG = os.path.join(HERE, "..", "docs", "CHANGELOG.md")
REPO = "diegobergonsi/steam-case-covers"
LIMIT = 3800                        # of the 4096 characters a Discord embed description may hold: room left for the link to the rest


def section(text, version):
    """The bullets under `## [X.Y.Z]` in a changelog (`version` with or without a leading v), up to the next version header."""
    version = version[1:] if version.startswith("v") else version
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("%r is not a version like v1.5.0" % version)
    match = re.search(r"^## \[%s\][^\n]*\n(.*?)(?=^## \[|\Z)" % re.escape(version), text, re.S | re.M)
    body = match.group(1).strip() if match else ""
    if not body:
        raise ValueError("docs/CHANGELOG.md has no notes for %s" % version)
    return body


def release_body(text, version, repo=REPO):
    """The text of the GitHub release page: the changelog section, then how to check the downloaded files."""
    return ("%s\n\n---\nVerify your download: the files are listed in `SHA256SUMS` (`sha256sum -c SHA256SUMS`), and each one carries a signed "
            "build attestation (`gh attestation verify <file> --repo %s`)." % (section(text, version), repo))


def announcement(text, version, url):
    """The JSON body of a Discord webhook message: one embed with the changelog section, cut between lines when it is long, and the release link."""
    notes = section(text, version)
    if len(notes) > LIMIT:
        more = "\n\n[Read the full changelog on the release page](%s)" % url
        kept, size = [], len(more)
        for line in notes.splitlines():
            if size + len(line) + 1 > LIMIT:
                break
            kept.append(line)
            size += len(line) + 1
        notes = ("\n".join(kept) or notes[:LIMIT - len(more) - 1] + "…") + more
    return {"embeds": [{"title": "steam-case-covers %s is out" % version, "url": url, "description": notes, "color": 0x66C0F4,
                        "footer": {"text": "Downloads for Windows, macOS and Linux are on the release page."}}],
            "allowed_mentions": {"parse": []}}                       # words in the changelog can never ping anyone


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("what", choices=("body", "announce"))
    ap.add_argument("version", help="the release tag, like v1.5.0")
    ap.add_argument("--changelog", default=CHANGELOG)
    ap.add_argument("--repo", default=REPO, help="owner/name, for the links")
    args = ap.parse_args(argv)
    try:
        with open(args.changelog, encoding="utf-8") as f:
            text = f.read()
        if args.what == "body":
            print(release_body(text, args.version, args.repo))
        else:
            print(json.dumps(announcement(text, args.version, "https://github.com/%s/releases/tag/%s" % (args.repo, args.version))))
    except (OSError, ValueError) as e:
        print("release_message: %s" % e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
