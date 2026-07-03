#! /usr/bin/env python3

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""
update_other_locales.py --reference <locale> --path <base_l10n_folder> [optional list of locales]

 Every locale file is already kept structurally in sync with the reference by
 Pontoon (same <file> and <trans-unit> elements). This script only edits
 translations in place: for each existing <target>, it decides whether the
 translation is still valid given the current reference, and removes it
 otherwise. It never adds, removes, or reorders <trans-unit> elements.

 For each reference file, an index of the reference is built, keyed by
 trans-unit ID and storing the list of (file, source) pairs where that ID
 appears. Then, for each localized <trans-unit> that has a <target>:

 - If the ID isn't in the reference, the trans-unit is left untouched (the
   string is obsolete and will be removed by Pontoon).
 - If the ID is in the reference, the '--type' argument decides:
   - 'standard': keep the translation only if a reference entry matches both
     file and source. Removes it if the source changed or the string moved to
     a different file.
   - 'nofile': keep the translation if a reference entry matches the source,
     ignoring the file. This retains translations when a string moves as-is
     from one file to another.
   - 'matchid': always keep the translation, and update <source> to the
     reference text if it changed. This retains translations for trivial
     source changes.
"""

from argparse import RawTextHelpFormatter
from functions import write_xliff
from glob import glob
from lxml import etree
import argparse
import os
import sys


NS = {"x": "urn:oasis:names:tc:xliff:document:1.2"}


def main():
    parser = argparse.ArgumentParser(formatter_class=RawTextHelpFormatter)
    parser.add_argument(
        "--reference",
        required=True,
        dest="reference_locale",
        help="Reference locale code",
    )
    parser.add_argument(
        "--path",
        required=True,
        dest="base_folder",
        help="Path to folder including subfolders for all locales",
    )
    parser.add_argument(
        "--type",
        required=False,
        default="standard",
        dest="update_type",
        help="""Type of update. Existing translation is maintained if:
    - 'standard': matches file, ID, and source text
    - 'nofile': matches ID and source text, ignoring file
    - 'matchid': matches ID""",
    )

    parser.add_argument("locales", nargs="*", help="Locales to process")
    args = parser.parse_args()

    reference_locale = args.reference_locale
    update_type = args.update_type

    # Get a list of files to update (absolute paths)
    base_folder = os.path.realpath(args.base_folder)
    reference_path = os.path.join(base_folder, reference_locale)

    # Get a list of all the reference XLIFF files
    reference_files = []
    for xliff_path in glob(reference_path + "/**/*.xliff", recursive=True):
        reference_files.append(os.path.relpath(xliff_path, reference_path))
    if not reference_files:
        sys.exit(
            f"No reference file found in {os.path.join(base_folder, reference_locale)}"
        )

    # Get the list of locales. 'templates' is generated separately, so it's
    # excluded together with the reference locale.
    if args.locales:
        locales = args.locales
    else:
        locales = [
            d
            for d in os.listdir(base_folder)
            if os.path.isdir(os.path.join(base_folder, d)) and not d.startswith(".")
        ]
        for excluded in (reference_locale, "templates"):
            if excluded in locales:
                locales.remove(excluded)
        locales.sort()

    updated_files = 0
    for filename in reference_files:
        # Read reference XML file
        try:
            reference_file_path = os.path.join(base_folder, reference_locale, filename)
            reference_tree = etree.parse(reference_file_path)
            reference_root = reference_tree.getroot()
        except Exception as e:
            sys.exit(f"ERROR: Can't parse reference file {filename}\n{e}")

        """
        Build an index of the reference content, keyed by trans-unit ID.
        Each ID maps to the list of (file, source) pairs where it appears:
        the same ID can be reused in different files (e.g. common keys like "
        OK" or "Cancel"), so it isn't unique on its own.
        """
        reference_index = {}
        for trans_node in reference_root.xpath("//x:trans-unit", namespaces=NS):
            source = trans_node.find("x:source", namespaces=NS)
            if source is None:
                # A reference unit without a source means a broken extraction.
                # Exit with an error.
                sys.exit(
                    f"ERROR: Reference trans-unit '{trans_node.get('id')}' "
                    f"has no source in {filename}"
                )
            original_id = trans_node.get("id")
            file_name = trans_node.getparent().getparent().get("original")
            reference_index.setdefault(original_id, []).append(
                (file_name, source.text)
            )

        for locale in locales:
            l10n_file = os.path.join(base_folder, locale, filename)
            if not os.path.isfile(l10n_file):
                continue

            print(f"Processing {l10n_file}")

            # Read localized XML file
            try:
                locale_tree = etree.parse(l10n_file)
                locale_root = locale_tree.getroot()
            except Exception as e:
                print(f"ERROR: Can't parse {l10n_file}")
                print(e)
                continue

            for trans_node in locale_root.xpath("//x:trans-unit", namespaces=NS):
                targets = trans_node.xpath("./x:target", namespaces=NS)
                if not targets:
                    # Untranslated string, nothing to do.
                    continue
                target = targets[0]

                original_id = trans_node.get("id")
                reference_entries = reference_index.get(original_id)
                if reference_entries is None:
                    # Obsolete string, not available in reference content.
                    # Leave its removal to Pontoon.
                    continue

                source_node = trans_node.find("x:source", namespaces=NS)
                if source_node is None:
                    # Malformed locale unit; log and skip.
                    print(
                        f"WARNING: Skipping trans-unit '{trans_node.get('id')}' "
                        f"without source in {l10n_file}"
                    )
                    continue
                file_name = trans_node.getparent().getparent().get("original")
                source_string = source_node.text

                if update_type == "matchid":
                    # Keep the translation and align the source to the reference.
                    # Prefer the entry from the same file, since an ID can appear
                    # in more than one file; otherwise fall back to the first.
                    reference_source = reference_entries[0][1]
                    for ref_file, ref_source in reference_entries:
                        if ref_file == file_name:
                            reference_source = ref_source
                            break
                    if source_string != reference_source:
                        source_node.text = reference_source
                    continue

                if update_type == "nofile":
                    # Keep if any reference entry has the same source.
                    keep = any(
                        source_string == ref_source
                        for _, ref_source in reference_entries
                    )
                else:
                    # 'standard': keep if a reference entry matches file and source.
                    keep = any(
                        file_name == ref_file and source_string == ref_source
                        for ref_file, ref_source in reference_entries
                    )

                if not keep:
                    target.getparent().remove(target)

            # Replace the existing locale file with the updated XML content
            write_xliff(locale_tree, l10n_file)
            updated_files += 1

    if updated_files == 0:
        sys.exit("No files updated.")
    else:
        print(f"{updated_files} files processed.")


if __name__ == "__main__":
    main()
