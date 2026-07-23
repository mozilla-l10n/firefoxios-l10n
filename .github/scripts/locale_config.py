#! /usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""
Per-project configuration for the XLIFF localization scripts.

Each project defines:
- 'mapping': Pontoon folder name -> XLIFF target-language code, for locales
  whose folder name differs from the language code that should be used in the
  XLIFF. The keys must match the actual folder names as they appear in the
  project (the scripts normalize underscores to hyphens *after* this lookup,
  so a folder named 'nb_NO' is keyed as 'nb_NO', a folder 'nb-NO' as 'nb-NO').
- 'excluded_folders': top-level folders that sit next to the locale folders
  but are not locales, or locales managed by automation (e.g. `es`), and
  should be skipped when listing locales.

Select a project on the command line with '--project <name>'. When no project
is passed the scripts fall back to an empty config (no remapping, no excluded
folders).
"""

PROJECTS = {
    "vpn": {
        "mapping": {},
        "excluded_folders": [],
    },
    "ios": {
        "mapping": {
            "ga-IE": "ga",
            "nb-NO": "nb",
            "nn-NO": "nn",
            "sat": "sat-Olck",
            "sv-SE": "sv",
            "tl": "fil",
            "zgh": "tzm",
        },
        "excluded_folders": [
            "es",
            "templates",
        ],
    },
}


def get_project_config(project=None):
    """
    Return a project's config as {"mapping": {...}, "excluded_folders": [...]}.

    With no project selected (None), return empty defaults so the scripts run
    with no remapping and no excluded folders. An unknown project name raises
    ValueError.
    """
    if project is None:
        return {"mapping": {}, "excluded_folders": []}

    try:
        config = PROJECTS[project]
    except KeyError:
        available = ", ".join(sorted(PROJECTS))
        raise ValueError(f"Unknown project '{project}'. Available: {available}")

    return {
        "mapping": dict(config.get("mapping", {})),
        "excluded_folders": list(config.get("excluded_folders", [])),
    }


def get_locale_code(mapping, folder):
    """
    Resolve a Pontoon folder name to its XLIFF target-language code: apply the
    project 'mapping' (if the folder has an entry), then normalize underscores
    to hyphens (e.g. 'en_GB' -> 'en-GB').
    """
    return mapping.get(folder, folder).replace("_", "-")
