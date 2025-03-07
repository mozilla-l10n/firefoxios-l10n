#! /usr/bin/env python3

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import json
import argparse
import sys
from pathlib import Path


def merge_section(section_name, source_section, target_section):
    """
    Merge array values from source_section into target_section for keys
    "exclusions" and "brand_names". Leave "enabled" unchanged.

    Print a warning if an element exists in target but is not found in source.
    """
    array_keys = ["exclusions", "brand_names"]

    for key in array_keys:
        if key in target_section:
            source_items = set(source_section.get(key, []))
            target_items = set(target_section.get(key, []))

            # Report elements in target that are not in source.
            extra_items = target_items - source_items
            for item in extra_items:
                print(
                    f"Note: In section '{section_name}', element '{item}' in '{key}' is available in target file but not in source."
                )

            merged = list(target_items.union(source_items))
            merged.sort(key=str.lower)
            target_section[key] = merged

    return target_section


def merge_json(source_data, target_data):
    """
    For each top-level key in the JSON, if both source and target have the section,
    integrate arrays using merge_section. "enabled" is kept as in target.
    """
    for section, target_section in target_data.items():
        source_section = source_data.get(section)
        if source_section:
            target_data[section] = merge_section(
                section, source_section, target_section
            )
        else:
            print(
                f"Warning: Section '{section}' exists in target file but not in source. Skipping merge for this section."
            )
    return target_data


def load_json_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading JSON file {path}: {e}")
        sys.exit(1)


def save_json_file(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving JSON file {path}: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Merge JSON files: integrate source array elements into target arrays."
    )
    parser.add_argument("--source", help="Path to the source JSON file")
    parser.add_argument("--target", help="Path to the target JSON file")
    args = parser.parse_args()

    source_path = Path(args.source)
    target_path = Path(args.target)

    source_data = load_json_file(source_path)
    target_data = load_json_file(target_path)

    merged_data = merge_json(source_data, target_data)

    # Save the merged data back to the target file.
    save_json_file(target_path, merged_data)


if __name__ == "__main__":
    main()
