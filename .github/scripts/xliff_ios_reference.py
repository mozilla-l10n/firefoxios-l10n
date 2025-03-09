#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from glob import glob
from lxml import etree
import argparse
import json
import os
import re
import sys


def get_files(ref_path):
    ref_path = os.path.realpath(ref_path)
    files = [
        xliff_path
        for xliff_path in glob(os.path.join(ref_path, "**", "*.xliff"), recursive=True)
    ]
    if not files:
        sys.exit("No XLIFF files found.")
    files.sort()

    return files, ref_path


def check_placeables(
    ref_string, string_id, comment, config_placeables, errors, placeable_pattern
):
    if not config_placeables.get("enabled", False):
        return

    exclusions = set(config_placeables.get("exclusions", []))
    if string_id in exclusions:
        return

    xml_placeables = set(re.findall(placeable_pattern, ref_string))
    if xml_placeables:
        comment_placeables = (
            set(re.findall(placeable_pattern, comment)) if comment else set()
        )
        missing = xml_placeables - comment_placeables
        if missing:
            errors.append(
                f"Identified placeables in string {string_id}: {', '.join(sorted(xml_placeables))}\n"
                f"  Comment does not include the following placeables: {', '.join(sorted(missing))}\n"
                f"  Text: {ref_string!r}\n"
                f"  Comment: {comment}"
            )
        elif not comment:
            errors.append(
                f"Identified placeables in string {string_id}: {', '.join(sorted(xml_placeables))}\n"
                f"  The string doesn't have a comment.\n"
                f"  Text: {ref_string!r}\n"
            )


def check_ellipsis(ref_string, string_id, config_ellipsis, errors):
    if config_ellipsis.get("enabled", False):
        if "..." in ref_string and string_id not in set(
            config_ellipsis.get("exclusions", [])
        ):
            errors.append(f"'...' found in {string_id}\n  Text: {ref_string!r}")


def check_quotes(ref_string, string_id, config_quotes, errors):
    if not config_quotes.get("enabled", False) or string_id in set(
        config_quotes.get("exclusions", [])
    ):
        return
    if "'" in ref_string:
        errors.append(f"' found in {string_id} (should use ’)\n  Text: {ref_string!r}")
    if '"' in ref_string:
        errors.append(f'" found in {string_id} (should use “”)\n  Text: {ref_string!r}')


def check_brands(ref_string, string_id, config_brands, errors):
    if not config_brands.get("enabled", False) or string_id in set(
        config_brands.get("exclusions", [])
    ):
        return
    for brand in config_brands.get("brand_names", []):
        if brand in ref_string:
            errors.append(
                f"{brand} found in {string_id} (should use a run-time placeable)\n  Text: {ref_string!r}"
            )


def process_file(file_path, ref_path, config, errors):
    NS = {"x": "urn:oasis:names:tc:xliff:document:1.2"}
    placeable_pattern = r"%(?:\d+\$@|@|d)"

    try:
        tree = etree.parse(file_path)
    except Exception as e:
        print(f"ERROR: Can't parse {file_path}\n{e}")
        return

    root = tree.getroot()
    # Iterate over all trans-unit nodes in the file
    for trans_node in root.xpath("//x:trans-unit", namespaces=NS):
        # Retrieve the note (comment) text; XPath string() returns an empty string if missing.
        comment = trans_node.xpath("string(./x:note)", namespaces=NS)
        for source in trans_node.xpath("./x:source", namespaces=NS):
            rel_file_path = os.path.relpath(file_path, ref_path)
            string_id = f"{rel_file_path}:{trans_node.get('id')}"
            ref_string = source.text or ""

            check_placeables(
                ref_string,
                string_id,
                comment,
                config.get("placeables", {}),
                errors,
                placeable_pattern,
            )
            check_ellipsis(ref_string, string_id, config.get("ellipsis", {}), errors)
            check_quotes(ref_string, string_id, config.get("quotes", {}), errors)
            check_brands(ref_string, string_id, config.get("brands", {}), errors)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--path",
        required=True,
        dest="ref_path",
        help="Path to folder with reference XLIFF files",
    )
    parser.add_argument(
        "--config", required=True, dest="config_file", help="Path to JSON config file"
    )
    args = parser.parse_args()

    try:
        with open(args.config_file, "r") as f:
            config = json.load(f)
    except Exception as e:
        sys.exit(f"Error loading config: {e}")

    file_paths, ref_path = get_files(args.ref_path)

    errors = []

    for file_path in file_paths:
        process_file(file_path, ref_path, config, errors)

    if errors:
        output_lines = [f"\nSource errors ({len(errors)})"]
        output_lines.extend(f"\n  {err}" for err in errors)
        print("\n".join(output_lines))
        sys.exit(1)
    else:
        print("No issues found.")


if __name__ == "__main__":
    main()
