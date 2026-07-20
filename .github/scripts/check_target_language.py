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
 language code differs from their Pontoon folder (see the project 'mapping' in
 locale_config.py, selected with --project). The reference locale is skipped.
"""

import argparse
import os
import sys
from glob import glob

from functions import list_locales
from locale_config import PROJECTS, get_locale_code, get_project_config
from lxml import etree

NS = {"x": "urn:oasis:names:tc:xliff:document:1.2"}


def check_target_languages(
    base_folder, reference_locale="en", mapping={}, excluded_folders=()
):
    """
    Check every localized XLIFF file and return
    (locales, parse_errors, target_errors):
    - 'parse_errors': files that couldn't be parsed.
    - 'target_errors': <file> nodes that don't declare the expected
      target-language.
    Both lists empty means everything is correct.

    'mapping' is a Pontoon-folder -> XLIFF-code dict; 'excluded_folders' lists
    non-locale folders to skip (see locale_config.get_project_config).
    """
    base_folder = os.path.realpath(base_folder)
    locales = list_locales(
        base_folder, excluded=excluded_folders, skip={reference_locale}
    )

    parse_errors = []
    target_errors = []
    for locale in locales:
        expected = get_locale_code(mapping, locale)
        locale_path = os.path.join(base_folder, locale)
        for xliff_path in glob(locale_path + "/**/*.xliff", recursive=True):
            try:
                root = etree.parse(xliff_path).getroot()
            except Exception as e:
                parse_errors.append(f"{xliff_path}: can't parse ({e})")
                continue

            for file_node in root.xpath("//x:file", namespaces=NS):
                actual = file_node.get("target-language")
                if actual != expected:
                    original = file_node.get("original")
                    target_errors.append(
                        f"{os.path.relpath(xliff_path, base_folder)} ({original}): "
                        f"target-language is '{actual}', expected '{expected}'"
                    )

    return locales, parse_errors, target_errors


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
        default="en",
        dest="reference_locale",
        help="Reference locale code to skip (default: en)",
    )
    parser.add_argument(
        "--project",
        required=False,
        default=None,
        choices=sorted(PROJECTS),
        help="Project config to use (locale mapping + excluded folders). "
        "Defaults to no mapping and no excluded folders.",
    )
    args = parser.parse_args()

    config = get_project_config(args.project)
    locales, parse_errors, target_errors = check_target_languages(
        args.base_folder,
        args.reference_locale,
        mapping=config["mapping"],
        excluded_folders=config["excluded_folders"],
    )

    if parse_errors:
        print("Files that could not be parsed:")
        for error in parse_errors:
            print(f"  {error}")

    if target_errors:
        print("Incorrect target-language found:")
        for error in target_errors:
            print(f"  {error}")

    if parse_errors or target_errors:
        sys.exit(1)

    print(f"target-language is correct in {len(locales)} locales.")


if __name__ == "__main__":
    main()
