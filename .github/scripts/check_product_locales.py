#! /usr/bin/env python3

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""
Check if Pontoon locales are missing in the repository for iOS projects.
"""

import argparse
import requests
import sys
from urllib.parse import quote as urlquote


def getPontoonLocales(project_slug):
    try:
        locale_list = []
        url = f"https://pontoon.mozilla.org/api/v2/projects/{project_slug}"
        page = 1
        while url:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()

            for locale_data in data.get("localizations", []):
                locale = locale_data["locale"]["code"]
                if (
                    locale_data["unreviewed_strings"] != locale_data["total_strings"]
                    and locale != "es-ES"
                ):
                    locale_list.append(locale)
            # Get the next page URL
            url = data.get("next")
            page += 1
        locale_list.sort()
    except requests.RequestException as e:
        print(f"Error fetching data: {e}")
        sys.exit()

    return locale_list


def getGithubLocales(repo, path):
    query = f"/repos/{repo}/contents/{urlquote(path)}"
    url = f"https://api.github.com{query}"

    ignored_locales = ["Base", "en", "en-US"]
    locale_mapping = {
        # iOS locale: Pontoon locale
        "fil": "tl",
        "ga": "ga-IE",
        "nb": "nb-NO",
        "nn": "nn-NO",
        "sat-Olck": "sat",
        "sv": "sv-SE",
        "tzm": "zgh",
    }

    try:
        response = requests.get(url)
        response.raise_for_status()
        json_data = response.json()

        locale_list = [
            e["name"][:-6]
            for e in json_data
            if e["type"] == "dir" and e["name"].endswith(".lproj")
        ]

        # Remap locales and exclude en/en-US
        locale_list = [
            locale_mapping.get(loc, loc)
            for loc in locale_list
            if loc not in ignored_locales
        ]
        locale_list.sort()

        return locale_list
    except Exception as e:
        sys.exit(f"GitHub error: {e}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--product",
        required=True,
        choices=["firefox", "focus"],
        help="Product code",
    )
    args = parser.parse_args()

    config = {
        "firefox": {
            "name": "Firefox for iOS",
            "github_repo": "mozilla-mobile/firefox-ios",
            "github_path": "firefox-ios/Client",
            "pontoon_slug": "firefox-for-ios",
        },
        "focus": {
            "name": "Focus for iOS",
            "github_repo": "mozilla-mobile/firefox-ios",
            "github_path": "focus-ios/Blockzilla",
            "pontoon_slug": "focus-for-ios",
        },
    }

    project = config[args.product]
    pontoon_locales = getPontoonLocales(project["pontoon_slug"])
    github_locales = getGithubLocales(project["github_repo"], project["github_path"])

    missing_locales = list(set(pontoon_locales) - set(github_locales))
    missing_locales.sort()

    print(f"{project['name']}")
    print(
        f"Locales available in Pontoon ({len(pontoon_locales)}): {','.join(pontoon_locales)}"
    )
    print(
        f"\nLocales available in GitHub ({len(github_locales)}): {','.join(github_locales)}"
    )

    if missing_locales:
        sys.exit(
            f"\nMissing locales in GitHub repository: {', '.join(missing_locales)}\n"
        )
    else:
        print("\nNo missing locales\n")


if __name__ == "__main__":
    main()
