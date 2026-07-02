#! /usr/bin/env python3

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""
check_target_language.py --path <base_l10n_folder>

 Verify that every localized XLIFF file declares the expected
 'target-language' on each <file> node. Pontoon owns this attribute, so this
 is a safety net that fails when a sync leaves a locale with the wrong (or
 missing) language code.

 The expected code matches the folder name, except for a few locales whose
 language code differs from their Pontoon folder (see PONTOON_TO_IOS in
 locale_config.py). The reference locale and the source-only 'templates' folder
 are skipped.
"""

from glob import glob
from locale_config import PONTOON_TO_IOS
from lxml import etree
import argparse
import os
import sys


NS = {"x": "urn:oasis:names:tc:xliff:document:1.2"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--path",
        required=True,
        dest="base_folder",
        help="Path to folder including subfolders for all locales",
    )
    parser.add_argument(
        "--reference",
        required=False,
        default="en-US",
        dest="reference_locale",
        help="Reference locale code to skip (default: en-US)",
    )
    args = parser.parse_args()

    base_folder = os.path.realpath(args.base_folder)
    skip = {args.reference_locale, "templates"}

    locales = sorted(
        d
        for d in os.listdir(base_folder)
        if os.path.isdir(os.path.join(base_folder, d))
        and not d.startswith(".")
        and d not in skip
    )

    errors = []
    for locale in locales:
        expected = PONTOON_TO_IOS.get(locale, locale).replace("_", "-")
        locale_path = os.path.join(base_folder, locale)
        for xliff_path in glob(locale_path + "/**/*.xliff", recursive=True):
            try:
                root = etree.parse(xliff_path).getroot()
            except Exception as e:
                errors.append(f"{xliff_path}: can't parse ({e})")
                continue

            for file_node in root.xpath("//x:file", namespaces=NS):
                actual = file_node.get("target-language")
                if actual != expected:
                    original = file_node.get("original")
                    errors.append(
                        f"{os.path.relpath(xliff_path, base_folder)} ({original}): "
                        f"target-language is '{actual}', expected '{expected}'"
                    )

    if errors:
        print("Incorrect target-language found:")
        for error in errors:
            print(f"  {error}")
        sys.exit(1)

    print(f"target-language is correct in {len(locales)} locales.")


if __name__ == "__main__":
    main()
