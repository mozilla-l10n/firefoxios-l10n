#! /usr/bin/env python3

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from collections import defaultdict
from glob import glob
from lxml import etree
import argparse
import json
import os
import sys


def main():
    NS = {"x": "urn:oasis:names:tc:xliff:document:1.2"}

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--path",
        required=True,
        dest="ref_path",
        help="Path to folder with reference XLIFF file",
    )
    parser.add_argument(
        "--config",
        nargs="?",
        dest="config_file",
        help="Path to JSON config file",
    )
    args = parser.parse_args()

    # Get a list of files to check (absolute paths)
    reference_path = os.path.realpath(args.ref_path)

    file_paths = []
    for xliff_path in glob(reference_path + "/**/*.xliff", recursive=True):
        file_paths.append(xliff_path)

    if not file_paths:
        sys.exit("File not found.")
    else:
        file_paths.sort()

    # Load config
    if not args.config_file:
        config = defaultdict(dict)
    else:
        try:
            with open(args.config_file) as f:
                config = json.load(f)
        except Exception as e:
            sys.exit(e)

    errors = []
    for file_path in file_paths:
        # Read XML file
        try:
            tree = etree.parse(file_path)
            root = tree.getroot()
        except Exception as e:
            print(f"ERROR: Can't parse {file_path}")
            print(e)
            continue

        for trans_node in root.xpath("//x:trans-unit", namespaces=NS):
            for child in trans_node.xpath("./x:source", namespaces=NS):
                rel_file_path = os.path.relpath(file_path, reference_path)
                string_id = f"{rel_file_path}:{trans_node.get('id')}"
                ref_string = child.text

                # Check ellipsis
                if config.get("ellipsis", {}).get("enabled", False):
                    if (
                        "..." in ref_string
                        and string_id not in config["ellipsis"]["exclusions"]
                    ):
                        errors.append(f"'...' in {string_id}\n  Text: {ref_string}")

                # Check quotes
                if config.get("quotes", {}).get("enabled", False):
                    if string_id not in config["quotes"]["exclusions"]:
                        if "'" in ref_string:
                            errors.append(
                                f"' in {string_id} (should use ’)\n  Text: {ref_string}"
                            )
                        if '"' in ref_string:
                            errors.append(
                                f'" in {string_id} (should use “”)\n  Text: {ref_string}'
                            )

                # Check for brand names
                if config.get("brands", {}).get("enabled", False):
                    if string_id not in config["brands"]["exclusions"]:
                        brand_names = config["brands"].get("brand_names", [])
                        for brand in brand_names:
                            if brand in ref_string:
                                errors.append(
                                    f"{brand} in {string_id} (should use a run-time placeable)\n  Text: {ref_string}"
                                )

    if errors:
        output = []
        output.append(f"\nSource errors ({len(errors)})")
        for e in errors:
            output.append(f"\n  {e}")
        print("\n".join(output))
        sys.exit(1)
    else:
        print("No issues found.")


if __name__ == "__main__":
    main()
