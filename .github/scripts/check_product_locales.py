#! /usr/bin/env python3

"""
Check if Pontoon locales are missing in the repository for iOS projects.
"""

import argparse
import json
import sys
from urllib.parse import quote as urlquote
from urllib.request import urlopen


def getPontoonLocales(project_slug):

    query = f"""
{{
  project: project(slug: "{project_slug}") {{
    localizations {{
        locale {{
            code
        }},
        missingStrings,
        totalStrings
    }}
  }}
}}
"""
    url = f"https://pontoon.mozilla.org/graphql?query={urlquote(query)}"

    try:
        response = urlopen(url)
        json_data = json.load(response)
        if "errors" in json_data:
            sys.exit(f"Project {project_slug} not found in Pontoon.")

        locale_list = []
        for e in json_data["data"]["project"]["localizations"]:
            # Only add locales not at 0%
            if e["missingStrings"] != e["totalStrings"]:
                locale_list.append(e["locale"]["code"])
        locale_list.sort()

        return locale_list
    except Exception as e:
        sys.exit(e)


def getGithubLocales(repo, path):
    query = f"/repos/{repo}/contents/{path}"
    url = f"https://api.github.com{urlquote(query)}"

    ignored_locales = ["en", "en-US"]
    locale_mapping = {
        # iOS locale: Pontoon locale
        "fil": "tl",
        "ga": "ga-IE",
        "nb": "nb-NO",
        "nn": "nn-NO",
        "sat-Olck": "sat",
        "sv": "sv-SE",
        "tmz": "zgh",
    }

    try:
        response = urlopen(url)
        json_data = json.load(response)

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
            "github_path": "Client",
            "pontoon_slug": "firefox-for-ios",
        },
        "focus": {
            "name": "Focus for iOS",
            "github_repo": "mozilla-mobile/focus-ios",
            "github_path": "Blockzilla",
            "pontoon_slug": "focus-for-ios",
        },
    }

    project = config[args.product]
    pontoon_locales = getPontoonLocales(project["pontoon_slug"])
    github_locales = getGithubLocales(project["github_repo"], project["github_path"])

    missing_locales = list(set(pontoon_locales) - set(github_locales))
    missing_locales.sort()

    if missing_locales:
        sys.exit(
            f"{project['name']}\nMissing locales in repository: {', '.join(missing_locales)}\n"
        )
    else:
        print(f"{project['name']}\nNo missing locales\n")


if __name__ == "__main__":
    main()
