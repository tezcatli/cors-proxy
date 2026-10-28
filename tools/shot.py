#!/usr/bin/env python3
"""
A screenshot of the dev app without driving a browser: Playwright (headless
Chromium) in the compose network, logged in with an admin token minted by
`peek.py token`. Run through `tools/shot.sh`.

    tools/shot.sh <route> [phone|desktop] [--full] [--text] [--wait SELECTOR]

The image is a small JPEG at device scale 1 (a phone shot is ~50 KB where a
browser screenshot or a PNG is ~1 MB): enough to judge a layout. `--text` prints
the page's accessibility tree instead, what the listener perceives
(`frontend/tests/helpers/find.js` finds the interface the same way): check text,
labels and order with it, and keep the image for what only looks can tell.
"""
import argparse
import os
import re

from playwright.sync_api import sync_playwright

APP = 'http://frontend:5173'
VIEWPORTS = {'phone': {'width': 390, 'height': 844}, 'desktop': {'width': 1280, 'height': 800}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('route')
    parser.add_argument('device', nargs='?', choices=VIEWPORTS, default='phone')
    parser.add_argument('--full', action='store_true', help='the whole page, not one screen')
    parser.add_argument('--text', action='store_true', help='the accessibility tree, no image')
    parser.add_argument('--wait', help='a selector to wait for before shooting')
    parser.add_argument('--out', default='/shots')
    args = parser.parse_args()

    route = args.route if args.route.startswith('/') else '/' + args.route
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport=VIEWPORTS[args.device], device_scale_factor=1,
                                is_mobile=args.device == 'phone', has_touch=args.device == 'phone',
                                reduced_motion='reduce')
        page.add_init_script(f"localStorage.setItem('soj-auth-token', {os.environ['TOKEN']!r})")
        page.goto(APP + route, wait_until='networkidle')
        if args.wait:
            page.wait_for_selector(args.wait)
        page.wait_for_timeout(500)   # palettes and images settle after the data
        if args.text:
            # A page over the Ludothèque is the app root's last element; the home
            # kept underneath is not what is being looked at.
            top = '#app > :last-child' if route.split('?')[0] != '/' else 'body'
            print(page.locator(top).aria_snapshot())
        else:
            name = re.sub(r'[^a-z0-9]+', '-', route.lower()).strip('-') or 'home'
            path = f'{args.out}/{name}-{args.device}.jpg'
            page.screenshot(path=path, type='jpeg', quality=60, full_page=args.full)
            print(f'shots/{os.path.basename(path)}  {os.path.getsize(path) // 1024} KB')
        browser.close()


if __name__ == '__main__':
    main()
