#! /usr/bin/env python3

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""
This script is called from the firefox-ios repository. It parses all
XLIFF file and rewrite the original attributes to use 'en-US.lproj' instead of
'en.lproj'.

This is a workaround to avoid losing translation after Firefox for iOS moved
from en to en-US as default locale
"""

from lxml import etree
import argparse
import os


def main():
    NS = {"x": "urn:oasis:names:tc:xliff:document:1.2"}

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--path",
        required=True,
        dest="locales_path",
        help="Path to folder with locale folders",
    )
    args = parser.parse_args()

    # List all folders in the current directory
    locales_path = args.locales_path
    locale_folders = [
        f
        for f in os.listdir(locales_path)
        if os.path.isdir(os.path.join(locales_path, f))
    ]
    locale_folders = [
        f for f in locale_folders if not f.startswith(".") and f not in ("templates")
    ]
    locale_folders.sort()

    # Process each folder
    for locale in locale_folders:
        locale_path = os.path.join(locales_path, locale)

        # Process each file in the folder
        for file_name in os.listdir(locale_path):
            file_path = os.path.join(locale_path, file_name)

            # Ensure we process only XML files
            if file_name.endswith(".xliff"):
                try:
                    # Parse the XML file
                    tree = etree.parse(file_path)
                    root = tree.getroot()
                    # Find all <original> tags
                    for file_node in root.xpath("//x:file", namespaces=NS):
                        file_node.set(
                            "original",
                            file_node.get("original").replace(
                                "en.lproj", "en-US.lproj"
                            ),
                        )
                    tree.write(
                        file_path,
                        pretty_print=True,
                        xml_declaration=True,
                        encoding="UTF-8",
                    )
                    print(f"Updated file: {file_path}")

                except Exception as e:
                    print(f"Error processing file {file_path}: {e}")


if __name__ == "__main__":
    main()
