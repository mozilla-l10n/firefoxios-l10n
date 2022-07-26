#! /usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""
 update_other_locales.py --reference <locale> --path <base_l10n_folder> [optional list of locales]

  First, get a list of all XLIFF files in the reference locale. Then, for
  each folder (locale) available in base_l10n_folder:

  1. Read existing translations, store them in an array: IDs use the structure
     file_name:string_id:source_hash. Using the hash of the source string
     prevents from keeping an existing translation if the ID doesn't change
     but the source string does.

     If the '--nofile' argument is passed, the 'file_name' won't be used when
     storing translations. This allows to retain translations when a string
     moves as-is from one file to another.

  2. Inject available translations in the reference XLIFF file, updating
     the target-language where available on file elements.

  3. Store the updated content in existing locale files, without backup.
"""

from argparse import RawTextHelpFormatter
from copy import deepcopy
from glob import glob
from lxml import etree
from translate.misc.xml_helpers import reindent
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

    # Get the list of locales
    if args.locales:
        locales = args.locales
    else:
        locales = [
            d
            for d in os.listdir(base_folder)
            if os.path.isdir(os.path.join(base_folder, d)) and not d.startswith(".")
        ]
        locales.remove(reference_locale)
        locales.sort()

    updated_files = 0
    for filename in reference_files:
        # Read reference XML file
        try:
            reference_file_path = os.path.join(base_folder, reference_locale, filename)
            reference_tree = etree.parse(reference_file_path)
        except Exception as e:
            sys.exit(f"ERROR: Can't parse reference file {filename}\n{e}")

        for locale in locales:
            l10n_file = os.path.join(base_folder, locale, filename)
            if not os.path.isfile(l10n_file):
                continue

            # Make a copy of the reference tree and root
            reference_tree_copy = deepcopy(reference_tree)
            reference_root_copy = reference_tree_copy.getroot()

            print(f"Updating {l10n_file}")

            # Read localized XML file
            try:
                locale_tree = etree.parse(l10n_file)
                locale_root = locale_tree.getroot()
            except Exception as e:
                print(f"ERROR: Can't parse {l10n_file}")
                print(e)
                continue

            """
            Using locale folder as locale code for the target-language attribute.
            This can be use to map a locale code to a different one.
            Structure: "locale folder" -> "locale code"
            """
            locale_mapping = {
                "ga_IE": "ga",
                "nb_NO": "nb",
                "nn_NO": "nn",
                "sat": "sat-Olck",
                "sv_SE": "sv",
                "templates": "en",
                "tl": "fil",
            }
            # Normaliza the locale code, using dashes instead of underscores
            locale_code = locale_mapping.get(locale, locale).replace("_", "-")

            """
            Store existing localizations in a dictionary.
            The key for each translation is a combination of the <file> "original"
            attribute, the <trans-unit> "id", and the <source> text.
            This allows to invalidate a translation if the source string
            changed without using a new ID (can be bypassed with --onlyid).
            """
            translations = {}
            for trans_node in locale_root.xpath("//x:trans-unit", namespaces=NS):
                for child in trans_node.xpath("./x:target", namespaces=NS):
                    file_name = trans_node.getparent().getparent().get("original")
                    source_string = trans_node.xpath("./x:source", namespaces=NS)[
                        0
                    ].text
                    original_id = trans_node.get("id")
                    if args.update_type == "matchid":
                        # Ignore source text and file attribute
                        string_id = original_id
                    else:
                        if args.update_type == "nofile":
                            string_id = f"{original_id}:{hash(source_string)}"
                        else:
                            string_id = (
                                f"{file_name}:{original_id}:{hash(source_string)}"
                            )
                    translations[string_id] = child.text

            # Inject available translations in the reference XML
            for trans_node in reference_root_copy.xpath(
                "//x:trans-unit", namespaces=NS
            ):
                # Add xml:space="preserve" to all trans-units, to avoid conflict
                # with Pontoon
                attrib_name = "{http://www.w3.org/XML/1998/namespace}space"
                xml_space = trans_node.get(attrib_name)
                if xml_space is None:
                    trans_node.set(attrib_name, "preserve")

                file_name = trans_node.getparent().getparent().get("original")
                source_string = trans_node.xpath("./x:source", namespaces=NS)[0].text
                original_id = trans_node.get("id")

                if args.update_type == "matchid":
                    # Ignore source text and file attribute
                    string_id = original_id
                else:
                    if args.update_type == "nofile":
                        string_id = f"{original_id}:{hash(source_string)}"
                    else:
                        string_id = f"{file_name}:{original_id}:{hash(source_string)}"
                updated = False
                translated = string_id in translations
                for child in trans_node.xpath("./x:target", namespaces=NS):
                    if translated:
                        child.text = translations[string_id]
                    else:
                        # No translation available, remove the target
                        child.getparent().remove(child)
                    updated = True

                if translated and not updated:
                    # Translation is available, but the refence XLIFF has no target.
                    # Create a target node and insert it after source.
                    child = etree.Element("target")
                    child.text = translations[string_id]
                    trans_node.insert(1, child)

            # Update target-language where defined, replace underscores with
            # hyphens if necessary (e.g. en_GB => en-GB).
            for file_node in reference_root_copy.xpath("//x:file", namespaces=NS):
                file_node.set("target-language", locale_code)

            # Replace the existing locale file with the new XML content
            with open(l10n_file, "w") as fp:
                # Fix identation of XML file
                reindent(reference_root_copy)
                xliff_content = etree.tostring(
                    reference_tree_copy,
                    encoding="UTF-8",
                    xml_declaration=True,
                    pretty_print=True,
                )
                fp.write(xliff_content.decode("utf-8"))
            updated_files += 1

    if updated_files == 0:
        sys.exit("No files updated.")
    else:
        print(f"{updated_files} updated files.")


if __name__ == "__main__":
    main()
