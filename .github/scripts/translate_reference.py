#! /usr/bin/env python3

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from collections import defaultdict
from glob import glob
from lxml import etree
from translate.misc.xml_helpers import reindent
import argparse
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
            for source in trans_node.xpath("./x:source", namespaces=NS):
                reference = source.text
                targets = trans_node.xpath("./x:target", namespaces=NS)
                if len(targets) > 0:
                    # Copy over the reference as translation
                    targets[0].text = reference
                else:
                    # Create a target node and insert it after source.
                    target = etree.Element("target")
                    target.text = reference
                    trans_node.insert(1, target)

        # Replace the existing file
        with open(file_path, "w") as fp:
            # Fix identation of XML file
            reindent(root)
            xliff_content = etree.tostring(
                root,
                encoding="UTF-8",
                xml_declaration=True,
                pretty_print=True,
            )
            fp.write(xliff_content.decode("utf-8"))


if __name__ == "__main__":
    main()
