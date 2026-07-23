#! /usr/bin/env python3

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""
update_other_locales.py --reference <locale> --path <folder>
     [--type standard|nofile|matchid] [--project <name>] [locales...]

 --project selects the locale mapping and excluded folders from
 locale_config.py. When no project name is provided, empty defaults are used
 (no remapping, no excluded folders).

 How each localized file is updated depends on the '--type' argument. The two
 behaviors exist because they serve different goals.

 'standard' (in-place, updates owned by Pontoon)
 -----------------------------------------------
 Every locale file is already kept structurally in sync with the reference
 by Pontoon (same <file> and <trans-unit> elements), so this mode only edits
 translations in place and never adds, removes, or reorders <trans-unit> elements.

 A localized <target> is removed when the source text of that string changed
 in the reference (same ID, same file). It is also removed when the string
 moved to a different <file> and its source text changed.
 In every other case the localized file is left untouched:
 - Strings removed from the reference are left in place (Pontoon will remove them).
 - Strings moved to a different file with an unchanged source are left in place
   ('nofile'/'matchid' relocate the translation; Pontoon syncs the structure).

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


def iter_units_by_filenode(root):
    """
    Yield (original, trans_node) for every <trans-unit> in the tree.

    Iterating by <file> lets us read each file's 'original' attribute once.
    """
    for file_node in root.xpath("//x:file", namespaces=NS):
        original = file_node.get("original")
        for trans_node in file_node.xpath(".//x:trans-unit", namespaces=NS):
            yield original, trans_node


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

    This structure is necessary to differentiate strings with the same ID but
    placed in different <file> blocks (e.g. CFBundleDisplayName in iOS),
    possibly with different source text.

    Using a set() should be unnecessary, since the same ID shouldn't appear
    more than once in the same <file> block, but it protects against broken
    extractions.
    """
    reference_index = {}
    for file_original, trans_node in iter_units_by_filenode(reference_root):
        source = trans_node.find("x:source", namespaces=NS)
        tu_id = trans_node.get("id")
        if source is None:
            # A reference unit without a source means a broken extraction.
            sys.exit(
                f"ERROR: Reference trans-unit '{tu_id}' has no source in {filename}"
            )
        sources_by_id = reference_index.setdefault(tu_id, {})
        sources_by_id.setdefault(file_original, set()).add(source.text)
    return reference_index


def update_in_place(reference_index, locale_root):
    """
    'standard' mode: remove a localized <target> when the source text changed
    in the reference for the same XLIFF file, or when the string moved to a
    different <file> and its source text changed. Strings removed upstream,
    and pure moves where the source text is unchanged, are left untouched.
    """
    for file_original, trans_node in iter_units_by_filenode(locale_root):
        target = trans_node.find("x:target", namespaces=NS)
        if target is None:
            # Untranslated string, nothing to do.
            continue

        tu_id = trans_node.get("id")
        sources_by_id = reference_index.get(tu_id)
        if sources_by_id is None:
            # String was completely removed from the reference. Pontoon will
            # remove it on next sync, so leave it in place here to avoid noise.
            continue

        source_node = trans_node.find("x:source", namespaces=NS)
        if source_node is None:
            # Malformed locale unit; log and skip.
            print(f"WARNING: Skipping trans-unit '{tu_id}' without source")
            continue

        files_for_id = sources_by_id.get(file_original)
        if files_for_id is None:
            # The ID exists in the reference but only in a different <file>: the
            # string moved. A pure move (source text unchanged) is left in place
            # ('nofile'/'matchid' can relocate the translation). If the source
            # text also changed, the translation is stale, so drop the target.
            all_sources = set()
            for file_sources in sources_by_id.values():
                all_sources.update(file_sources)
            if source_node.text not in all_sources:
                target.getparent().remove(target)
            continue

        # Same file: remove only when the source text actually changed here.
        if source_node.text not in files_for_id:
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
                     reference. An ID not in this set = obsolete string.
    """

    new_file_nodes = {
        fn.get("original"): fn for fn in new_root.xpath("//x:file", namespaces=NS)
    }
    # Track the last surviving <file> in the rebuilt tree, so a <file> block
    # removed upstream can be reinserted in its original position (right after
    # the previous surviving <file>) instead of being appended at the end,
    # which would create a reordering diff.
    file_anchor = None
    for loc_file in locale_root.xpath("//x:file", namespaces=NS):
        file_original = loc_file.get("original")
        new_dest = new_file_nodes.get(file_original)

        old_loc_trans_units = loc_file.xpath("./x:body/x:trans-unit", namespaces=NS)
        nothing_obsolete = all(
            tu.get("id") in reference_ids for tu in old_loc_trans_units
        )

        if new_dest is not None:
            # This <file> still exists in the reference; it anchors the
            # position of any following removed <file> block.
            file_anchor = new_dest
            if nothing_obsolete:
                continue
            new_dest_body = new_dest.find("x:body", namespaces=NS)
        else:
            if nothing_obsolete:
                # The <file> is gone from the reference but all its strings
                # only moved elsewhere (still in reference_ids); they are
                # re-emitted under their new <file>, so nothing to carry over.
                continue
            # The whole <file> block was removed from the reference: recreate
            # it and empty its <body> (no <trans-unit> elements), preserving
            # the <file> attributes. Insert it in its original position, right
            # after the previous surviving <file> (or first if none precedes
            # it), to avoid reordering. Obsolete strings are reinserted later.
            new_dest = deepcopy(loc_file)
            new_dest.set("target-language", locale_code)
            new_dest_body = new_dest.find("x:body", namespaces=NS)
            for tu in new_dest_body.xpath("./x:trans-unit", namespaces=NS):
                new_dest_body.remove(tu)
            if file_anchor is None:
                new_root.insert(0, new_dest)
            else:
                file_anchor.addnext(new_dest)
            new_file_nodes[file_original] = new_dest
            file_anchor = new_dest

        # At this point, new_dest_body is the <file><body> of the new XLIFF
        # tree, rebuilt from the reference and already containing any
        # surviving translations. If the <file> was completely removed
        # from the reference, new_dest_body is empty.
        # Index the units already placed in the rebuilt block, to
        # anchor each obsolete unit after its previous sibling.
        new_dest_index = {}
        for tu_candidate in new_dest_body.xpath("./x:trans-unit", namespaces=NS):
            new_dest_index.setdefault(tu_candidate.get("id"), tu_candidate)

        # Walk the localized units in order, reinserting the obsolete ones.
        anchor = None
        for tu in old_loc_trans_units:
            tu_id = tu.get("id")
            if tu_id in reference_ids:
                # Surviving unit already in the rebuilt block: use as anchor.
                anchor = new_dest_index.get(tu_id, anchor)
            else:
                copy = deepcopy(tu)
                if anchor is None:
                    new_dest_body.insert(0, copy)
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
    That prevents automation from touching localized files, leaving the removal
    to Pontoon instead, and reducing merge conflicts.

    'locale_root' is the current localized content of an existing file.
    """
    # Remember each localized <file>'s attribute order, to restore it on the
    # rebuilt tree (which otherwise inherits the reference's order).
    # Without this, different automations (this script, extraction, Pontoon)
    # would start fighting over the attribute order, creating unnecessary diffs.
    locale_file_attr_order = {
        fn.get("original"): list(fn.attrib.keys())
        for fn in locale_root.xpath("//x:file", namespaces=NS)
    }

    # Collect existing translations, keyed according to the update type. Keep a
    # per-file map so a shared ID (e.g. iOS default IDs reused across files with
    # different translations) can't clobber another file's translation, plus a
    # file-agnostic fallback used only to relocate a translation whose string
    # moved to a different <file> block.
    translations_by_file = {}
    translations_any = {}
    for file_original, trans_node in iter_units_by_filenode(locale_root):
        target = trans_node.find("x:target", namespaces=NS)
        if target is None:
            continue
        source_node = trans_node.find("x:source", namespaces=NS)
        source_string = source_node.text if source_node is not None else None
        key = translation_key(update_type, trans_node.get("id"), source_string)
        translations_by_file[(file_original, key)] = target.text
        translations_any.setdefault(key, target.text)

    # Build the new localized tree from the reference structure.
    new_tree = deepcopy(reference_tree)
    new_root = new_tree.getroot()

    reference_ids = {
        tu.get("id") for tu in new_root.xpath("//x:trans-unit", namespaces=NS)
    }

    for file_original, trans_node in iter_units_by_filenode(new_root):
        source_node = trans_node.find("x:source", namespaces=NS)
        if source_node is None:
            # Malformed reference unit (broken extraction): can't match or
            # inject a translation without a <source> to anchor it.
            # Log and skip.
            print(
                f"WARNING: Skipping trans-unit '{trans_node.get('id')}' without source"
            )
            continue
        source_string = source_node.text
        key = translation_key(update_type, trans_node.get("id"), source_string)

        # Prefer the translation from the same file; fall back to any file only
        # to relocate a string that moved to a different <file> block.
        file_key = (file_original, key)
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
                source_node.addnext(target)
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
        help="Locale code for source strings (usually en-US)",
    )
    parser.add_argument(
        "--path",
        required=True,
        dest="base_folder",
        help="Path to folder containing subfolders for all locales",
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

    parser.add_argument(
        "locales",
        nargs="*",
        help="Locales to process; if none are listed, all locale subfolders "
        "in the path will be processed",
    )
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
        # Build once here instead of within the locale loop.
        reference_index = (
            build_reference_index(reference_root, filename)
            if update_type == "standard"
            else None
        )

        for locale in locales:
            l10n_file = os.path.join(base_folder, locale, filename)

            # Every mode requires an existing localized file. In rebuild modes a
            # missing file would only be recreated with no translations, so its
            # creation is left to Pontoon.
            if not os.path.isfile(l10n_file):
                continue

            try:
                locale_tree = etree.parse(l10n_file)
                locale_root = locale_tree.getroot()
            except Exception as e:
                print(f"ERROR: Can't parse {l10n_file}")
                print(e)
                continue

            if update_type == "standard":
                # In-place update.
                print(f"Processing {l10n_file}")
                update_in_place(reference_index, locale_root)
                write_xliff(locale_tree, l10n_file)
            else:
                # Rebuild from reference, moving existing translations.
                print(f"Updating {l10n_file}")
                # Resolve the folder name to its XLIFF target-language code.
                locale_code = get_locale_code(mapping, locale)
                new_tree = rebuild_from_reference(
                    reference_tree, locale_root, update_type, locale_code
                )
                write_xliff(new_tree, l10n_file)

            updated_files += 1

    if updated_files == 0:
        # No localized file matched the reference (e.g. a brand-new project that
        # isn't localized yet). This is not an error: exit cleanly so a first
        # import doesn't fail CI, leaving the file creation to Pontoon.
        print("WARNING: No localized files to update.")
    else:
        print(f"{updated_files} files processed.")


if __name__ == "__main__":
    main()
