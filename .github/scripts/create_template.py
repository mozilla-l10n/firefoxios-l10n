#! /usr/bin/env python3

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""
create_template.py --reference <ref_folder> --output <template_folder>

 Generate the source-only template used by Pontoon from the reference locale.
 For each reference XLIFF file, the tree is copied, all <target> elements are
 removed, and the 'target-language' attribute is dropped from every <file>
 node.
"""

from functions import write_xliff
from glob import glob
from lxml import etree
import argparse
import os
import sys


NS = {"x": "urn:oasis:names:tc:xliff:document:1.2"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--reference",
        required=True,
        dest="reference_path",
        help="Path to folder with the reference XLIFF files",
    )
    parser.add_argument(
        "--output",
        required=True,
        dest="output_path",
        help="Path to the template folder",
    )
    args = parser.parse_args()

    reference_path = os.path.realpath(args.reference_path)
    output_path = os.path.realpath(args.output_path)

    reference_files = glob(reference_path + "/**/*.xliff", recursive=True)
    if not reference_files:
        sys.exit(f"No reference file found in {reference_path}")
    reference_files.sort()

    for file_path in reference_files:
        try:
            tree = etree.parse(file_path)
            root = tree.getroot()
        except Exception as e:
            sys.exit(f"ERROR: Can't parse reference file {file_path}\n{e}")

        # Drop the target-language attribute from each <file> node.
        for file_node in root.xpath("//x:file", namespaces=NS):
            file_node.attrib.pop("target-language", None)

        # Remove all translations.
        for target in root.xpath("//x:target", namespaces=NS):
            target.getparent().remove(target)

        # Write the template mirroring the reference file paths.
        relative_path = os.path.relpath(file_path, reference_path)
        template_file = os.path.join(output_path, relative_path)
        os.makedirs(os.path.dirname(template_file), exist_ok=True)
        write_xliff(tree, template_file)
        print(f"Created template {template_file}")


if __name__ == "__main__":
    main()
