#!/usr/bin/env python3
"""
Inspect what game names are extracted from each SOJ RSS episode.

Usage:
    python tools/check_games.py [--file PATH] [--game NAME] [--chapters] [--limit N]
"""

import os
import re
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'corsproxy')))

import argparse
import requests

from rss import (
    RSS_URL,
    _NS_CONTENT,
    _SKIP_RE,
    _correct,
    _extract_chapters,
    _extract_game_names,
    _find_timestamp,
    _strip_html,
)


def fetch_xml(args):
    if args.file:
        try:
            with open(args.file, 'rb') as f:
                return f.read()
        except OSError as e:
            print(f"Error reading file: {e}", file=sys.stderr)
            sys.exit(1)
    url = args.url or RSS_URL
    try:
        r = requests.get(url, timeout=10, headers={'User-Agent': 'SilenceOnJoue/check-games'})
        r.raise_for_status()
        return r.content
    except requests.exceptions.RequestException as e:
        print(f"Error fetching feed: {e}", file=sys.stderr)
        sys.exit(1)


def iter_episodes(xml_bytes):
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        print(f"Error parsing XML: {e}", file=sys.stderr)
        sys.exit(1)

    channel = root.find('channel')
    if channel is None:
        channel = root
    for item in channel.findall('item'):
        title = (item.findtext('title') or '').strip()
        if not title or any(p.search(title) for p in _SKIP_RE):
            continue
        raw_names = _extract_game_names(title)
        if not raw_names:
            continue
        game_names = [_correct(re.sub(r'^[,\s]+', '', n).strip()) for n in raw_names]
        game_names = [n for n in game_names if len(n) >= 2]
        if not game_names:
            continue
        pub_date = (item.findtext('pubDate') or '').strip() or None
        raw_desc = (item.findtext(f'{{{_NS_CONTENT}}}encoded') or
                    item.findtext('description') or '')
        chapters = _extract_chapters(_strip_html(raw_desc))
        yield {
            'title':      title,
            'pub_date':   pub_date,
            'game_names': game_names,
            'chapters':   chapters,
        }


def print_episode(ep, show_chapters, filter_game):
    sep = '─' * 72
    title_line = ep['title'][:70]
    print(f"\n┌{sep}")
    print(f"│ {title_line}")
    if ep['pub_date']:
        print(f"│ {ep['pub_date']}")
    print(f"└{sep}")

    if show_chapters:
        for name in ep['game_names']:
            ts = _find_timestamp(name, ep['chapters'])
            if ts:
                marker = f"→ {ts['timestamp']}"
            else:
                marker = '→ (no timestamp match)'
            flag = ' ◀' if filter_game and filter_game.lower() in name.lower() else ''
            print(f"  - {name:<40} {marker}{flag}")
    else:
        games_str = ', '.join(ep['game_names'])
        print(f"  Games: {games_str}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--file', metavar='PATH', help='local XML file instead of network fetch')
    parser.add_argument('--url', metavar='URL', help='override default RSS URL')
    parser.add_argument('--game', metavar='NAME', help='only show episodes containing this game (substring, case-insensitive)')
    parser.add_argument('--chapters', action='store_true', help='show matched chapter timestamp for each game')
    parser.add_argument('--limit', metavar='N', type=int, help='stop after N episodes printed')
    args = parser.parse_args()

    xml_bytes = fetch_xml(args)
    filter_game = args.game.strip() if args.game else None

    episodes_shown = 0
    games_total = 0

    for ep in iter_episodes(xml_bytes):
        if filter_game and not any(filter_game.lower() in g.lower() for g in ep['game_names']):
            continue
        print_episode(ep, args.chapters, filter_game)
        episodes_shown += 1
        games_total += len(ep['game_names'])
        if args.limit and episodes_shown >= args.limit:
            break

    print()
    if episodes_shown == 0:
        print("No matching episodes found.")
    else:
        filter_note = f'  (filtered by: "{filter_game}")' if filter_game else ''
        print(f"{episodes_shown} episodes shown, {games_total} game mentions total{filter_note}")


if __name__ == '__main__':
    main()
