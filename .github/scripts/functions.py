#! /usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import os

from lxml import etree


def write_xliff(root, filename):
    with open(filename, "w+") as fp:
        # Fix indentation of XML file
        etree.indent(root)
        """
        Hack to avoid conflicts with Pontoon, which uses single quotes
        for the XML declaration:
            1. Exclude the XML declaration when using etree.tostring()
            2. Manually add the declaration with double quotes
        """
        xliff_content = etree.tostring(
            root,
            encoding="UTF-8",
            xml_declaration=False,
            pretty_print=True,
        )
        xliff_content = (
            '<?xml version="1.0" encoding="utf-8"?>\n' + xliff_content.decode("utf-8")
        )
        fp.write(xliff_content)


def list_locales(base_folder, excluded=(), skip=()):
    """
    Return a sorted list of locale folder names in base_folder, skipping
    hidden folders, any name in `excluded` (project-specific non-locale folders),
    and any name in `skip` (e.g. the reference locale).
    """
    excluded = set(excluded)
    skip = set(skip)
    return sorted(
        d
        for d in os.listdir(base_folder)
        if os.path.isdir(os.path.join(base_folder, d))
        and not d.startswith(".")
        and d not in excluded
        and d not in skip
    )
