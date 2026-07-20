#! /usr/bin/env python3

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""
update_other_locales.py --reference <locale> --path <folder> [locales...]

 How each localized file is updated depends on the '--type' argument. The two
 behaviors exist because they serve different goals.

 'standard' (in-place, updates owned by Pontoon)
 -----------------------------------------------
 Every locale file is already kept structurally in sync with the reference
 by Pontoon (same <file> and <trans-unit> elements), so this mode only edits
 translations in place and never adds, removes, or reorders <trans-unit> elements.

 A localized <target> is removed *only* when the source text of that string
 changed in the reference, without using a new ID. In every other case the
 localized file is left untouched:
 - String removed from the reference are left in place (Pontoon will remove them).
 - String moved to a different file are left in place. 'nofile'/'matchid'
   should be used to actually move the translation).

 'nofile' / 'matchid' (rebuild from reference, move existing translations)
 -------------------------------------------------------------------------
 Used for manual runs, typically after a refactor that moves strings between
 files. These modes rebuild each localized file from the reference structure,
 injecting the existing translations. Because the translations are injected onto
 the reference structure, a string that moved to a different <file> block is
 recreated (with its translation) under its new location, so the translation
 isn't lost when Pontoon later syncs the structure.

 Existing translations are matched by:
 - 'nofile': trans-unit ID and source text, ignoring the file. Retains
   translations when a string moves as-is from one file to another.
 - 'matchid': trans-unit ID only. Retains translations for trivial source
   changes, updating the source to match the reference.

 Strings that are no longer in the reference (removed upstream) are *not*
 dropped from localized files: their removal is left to Pontoon, matching the
 'standard' behavior. This ensures that PRs have the minimal diff possible,
 making it easier to review and reducing merge conflicts.
"""

import argparse
import os
import sys
from argparse import RawTextHelpFormatter
from copy import deepcopy
from glob import glob

from functions import list_locales, write_xliff
from locale_config import PROJECTS, get_locale_code, get_project_config
from lxml import etree

NS = {"x": "urn:oasis:names:tc:xliff:document:1.2"}


def translation_key(update_type, original_id, source_string):
    """
    Build the key used to match an existing translation against the reference
    for the 'nofile'/'matchid' rebuild modes. Both ignore the file, so a moved
    string is matched wherever it lives now.
    """
    if update_type == "matchid":
        # Ignore source text: retain the translation even if the source changed.
        return original_id
    # 'nofile': invalidate on source change.
    return f"{original_id}:{hash(source_string)}"


def file_original(trans_node):
    """Return the 'original' attribute of the <file> a trans-unit belongs to."""
    return trans_node.xpath("ancestor::x:file", namespaces=NS)[0].get("original")


def reorder_attributes(node, preferred_order):
    """
    Rewrite `node`'s attributes to follow `preferred_order` (a list of attribute
    names); any attribute not listed keeps its relative order at the end. Used to
    keep a rebuilt <file>'s attribute order identical to the localized file's, so
    the reference declaring them in a different order doesn't create noise diffs.
    """
    current = dict(node.attrib)
    ordered = [key for key in preferred_order if key in current]
    ordered += [key for key in current if key not in ordered]
    for key in list(node.attrib):
        del node.attrib[key]
    for key in ordered:
        node.set(key, current[key])


def build_reference_index(reference_root, filename):
    """
    Index the reference content as {id: {original_file: set(sources)}}.
    """
    reference_index = {}
    for trans_node in reference_root.xpath("//x:trans-unit", namespaces=NS):
        source = trans_node.find("x:source", namespaces=NS)
        if source is None:
            # A reference unit without a source means a broken extraction.
            sys.exit(
                f"ERROR: Reference trans-unit '{trans_node.get('id')}' "
                f"has no source in {filename}"
            )
        per_file = reference_index.setdefault(trans_node.get("id"), {})
        per_file.setdefault(file_original(trans_node), set()).add(source.text)
    return reference_index


def update_in_place(reference_index, locale_root):
    """
    'standard' mode: remove a localized <target> only when the source text
    changed in the reference for the same XLIFF file. Strings removed upstream
    or moved to a different file are left untouched.
    """
    for trans_node in locale_root.xpath("//x:trans-unit", namespaces=NS):
        target = trans_node.find("x:target", namespaces=NS)
        if target is None:
            # Untranslated string, nothing to do.
            continue

        per_file = reference_index.get(trans_node.get("id"))
        if per_file is None:
            # String removed from the reference: leave its removal to Pontoon.
            continue

        source_node = trans_node.find("x:source", namespaces=NS)
        if source_node is None:
            # Malformed locale unit; log and skip.
            print(
                f"WARNING: Skipping trans-unit '{trans_node.get('id')}' without source"
            )
            continue

        reference_sources = per_file.get(file_original(trans_node))
        if reference_sources is None:
            # The ID exists in the reference but only in a different <file>: the
            # string moved, leave it in place ('nofile'/'matchid' relocate it).
            continue

        # Same file: remove only when the source text actually changed here.
        if source_node.text not in reference_sources:
            target.getparent().remove(target)


def carry_over_obsolete(new_root, locale_root, reference_ids, locale_code):
    """
    Keep strings that no longer exist in the reference (removed upstream) in the
    rebuilt localized file, so their removal is left to Pontoon instead of the
    automation dropping them. This applies to translated and untranslated
    strings alike, so removing a string upstream doesn't touch localized files
    here. Each obsolete string is reinserted in its original position (right
    after its previous surviving sibling), to avoid unnecessary reordering.

    - new_root: the freshly rebuilt tree (a deepcopy of the reference structure,
                with translations already injected).
    - locale_root: the original localized file's content (the source of truth
                   for what obsolete strings existed and where).
    - reference_ids: set of every trans-unit ID that still exists in the
                     reference. An ID not in this set = obsolete.
    """

    new_file_nodes = {
        fn.get("original"): fn for fn in new_root.xpath("//x:file", namespaces=NS)
    }
    for loc_file in locale_root.xpath("//x:file", namespaces=NS):
        units = loc_file.xpath("./x:body/x:trans-unit", namespaces=NS)
        if all(tu.get("id") in reference_ids for tu in units):
            # Nothing obsolete in this <file> block.
            continue

        original = loc_file.get("original")
        dest = new_file_nodes.get(original)
        if dest is None:
            # The whole <file> block is gone from the reference: recreate it
            # (empty), preserving the <file> attributes. Obsolete strings
            # will be reinserted below.
            dest = deepcopy(loc_file)
            dest.set("target-language", locale_code)
            dest_body = dest.find("x:body", namespaces=NS)
            for tu in dest_body.xpath("./x:trans-unit", namespaces=NS):
                dest_body.remove(tu)
            new_root.append(dest)
            new_file_nodes[original] = dest
        else:
            dest_body = dest.find("x:body", namespaces=NS)

        # Index the units already placed in the rebuilt block, to
        # anchor each obsolete unit after its previous sibling.
        dest_index = {}
        for cand in dest_body.xpath("./x:trans-unit", namespaces=NS):
            dest_index.setdefault(cand.get("id"), cand)

        # Walk the localized units in order, reinserting the obsolete ones.
        anchor = None
        for tu in units:
            tid = tu.get("id")
            if tid in reference_ids:
                # Surviving unit already in the rebuilt block: use as anchor.
                anchor = dest_index.get(tid, anchor)
            else:
                copy = deepcopy(tu)
                if anchor is None:
                    dest_body.insert(0, copy)
                else:
                    anchor.addnext(copy)
                anchor = copy


def rebuild_from_reference(reference_tree, locale_root, update_type, locale_code):
    """
    'nofile'/'matchid' mode: return a new localized tree built from the
    reference structure, with existing translations injected. Because it's
    based on the reference, strings that moved to a different <file> block are
    re-emitted (with their translation) under their new location. Translations
    for strings removed upstream are carried over (see carry_over_obsolete).

    'locale_root' is the current localized content of an existing file.
    """
    # Remember each localized <file>'s attribute order, to restore it on the
    # rebuilt tree (which otherwise inherits the reference's order).
    locale_file_attr_order = {
        fn.get("original"): list(fn.attrib.keys())
        for fn in locale_root.xpath("//x:file", namespaces=NS)
    }

    # Collect existing translations, keyed according to the update type. Keep a
    # per-file map so a shared ID (e.g. iOS default IDs reused across files with
    # different translations) can't clobber another file's translation, plus a
    # file-agnostic fallback used *only* to relocate a translation whose string
    # moved to a different <file> block.
    translations_by_file = {}
    translations_any = {}
    for trans_node in locale_root.xpath("//x:trans-unit", namespaces=NS):
        target = trans_node.find("x:target", namespaces=NS)
        if target is None:
            continue
        source_node = trans_node.find("x:source", namespaces=NS)
        source_string = source_node.text if source_node is not None else None
        key = translation_key(update_type, trans_node.get("id"), source_string)
        translations_by_file[(file_original(trans_node), key)] = target.text
        translations_any.setdefault(key, target.text)

    # Build the new localized tree from the reference structure.
    new_tree = deepcopy(reference_tree)
    new_root = new_tree.getroot()

    reference_ids = {
        tu.get("id") for tu in new_root.xpath("//x:trans-unit", namespaces=NS)
    }

    for trans_node in new_root.xpath("//x:trans-unit", namespaces=NS):
        source_node = trans_node.find("x:source", namespaces=NS)
        source_string = source_node.text if source_node is not None else None
        key = translation_key(update_type, trans_node.get("id"), source_string)

        # Prefer the translation from the same file; fall back to any file only
        # to relocate a string that moved to a different <file> block.
        file_key = (file_original(trans_node), key)
        if file_key in translations_by_file:
            translation = translations_by_file[file_key]
            has_translation = True
        elif key in translations_any:
            translation = translations_any[key]
            has_translation = True
        else:
            has_translation = False

        existing_target = trans_node.find("x:target", namespaces=NS)
        if has_translation:
            if existing_target is not None:
                existing_target.text = translation
            else:
                # Insert a new <target> right after <source>, in the XLIFF
                # namespace so the in-memory tree matches what is written to
                # disk (a bare etree.Element("target") would be namespaceless
                # in memory and only pick up the default namespace on save).
                target = etree.Element(f"{{{NS['x']}}}target")
                target.text = translation
                source_index = list(trans_node).index(source_node)
                trans_node.insert(source_index + 1, target)
        elif existing_target is not None:
            # No translation available, remove the target.
            existing_target.getparent().remove(existing_target)

    # Preserve strings removed from the reference (see carry_over_obsolete).
    # This prevents the diff from growing unnecessarily, leaving the removal
    # to Pontoon instead, and reducing merge conflicts.
    carry_over_obsolete(new_root, locale_root, reference_ids, locale_code)

    # Set the target-language on every <file> node to the locale code, and
    # restore the localized file's attribute order to avoid noise diffs.
    for file_node in new_root.xpath("//x:file", namespaces=NS):
        file_node.set("target-language", locale_code)
        preferred = locale_file_attr_order.get(file_node.get("original"))
        if preferred:
            reorder_attributes(file_node, preferred)

    return new_tree


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
        help="""Type of update:
    - 'standard': in place, remove a translation only if the source changed
    - 'nofile': rebuild from reference, move translations if ID and source text match
    - 'matchid': rebuild from reference, move translations if ID matches (ignore source text)""",
    )

    parser.add_argument(
        "--project",
        required=False,
        default=None,
        choices=sorted(PROJECTS),
        help="Project config to use (locale mapping + excluded folders).\n"
        "Defaults to no mapping and no excluded folders.",
    )

    parser.add_argument("locales", nargs="*", help="Locales to process")
    args = parser.parse_args()

    reference_locale = args.reference_locale
    update_type = args.update_type
    config = get_project_config(args.project)
    mapping = config["mapping"]
    excluded_folders = config["excluded_folders"]

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
        locales = list_locales(
            base_folder, excluded=excluded_folders, skip={reference_locale}
        )

    updated_files = 0
    for filename in reference_files:
        # Read reference XML file
        try:
            reference_file_path = os.path.join(base_folder, reference_locale, filename)
            reference_tree = etree.parse(reference_file_path)
            reference_root = reference_tree.getroot()
        except Exception as e:
            sys.exit(f"ERROR: Can't parse reference file {filename}\n{e}")

        # 'standard' only needs an index of the reference sources per ID.
        reference_index = (
            build_reference_index(reference_root, filename)
            if update_type == "standard"
            else None
        )

        for locale in locales:
            l10n_file = os.path.join(base_folder, locale, filename)

            if update_type == "standard":
                # In-place update, requires an existing localized file.
                if not os.path.isfile(l10n_file):
                    continue

                print(f"Processing {l10n_file}")
                try:
                    locale_tree = etree.parse(l10n_file)
                    locale_root = locale_tree.getroot()
                except Exception as e:
                    print(f"ERROR: Can't parse {l10n_file}")
                    print(e)
                    continue

                update_in_place(reference_index, locale_root)
                write_xliff(locale_tree, l10n_file)
                updated_files += 1
            else:
                # Rebuild from reference, moving existing translations. Requires an
                # existing localized file: a missing file would only be rebuilt
                # with no translations, so leave its creation to Pontoon.
                if not os.path.isfile(l10n_file):
                    continue

                print(f"Updating {l10n_file}")
                try:
                    locale_root = etree.parse(l10n_file).getroot()
                except Exception as e:
                    print(f"ERROR: Can't parse {l10n_file}")
                    print(e)
                    continue

                # Resolve the folder name to its XLIFF target-language code.
                locale_code = get_locale_code(mapping, locale)

                new_tree = rebuild_from_reference(
                    reference_tree, locale_root, update_type, locale_code
                )
                write_xliff(new_tree, l10n_file)
                updated_files += 1

    if updated_files == 0:
        sys.exit("No files updated.")
    else:
        print(f"{updated_files} files processed.")


if __name__ == "__main__":
    main()
