# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""
Shared locale configuration.

A handful of locales use a different language code in the product (iOS) than
the folder/Pontoon code used in this repository. This is the single source of
truth for that mapping; consumers import the direction they need.
"""

# Canonical direction: Pontoon/folder code -> iOS target-language code.
PONTOON_TO_IOS = {
    "ga-IE": "ga",
    "nb-NO": "nb",
    "nn-NO": "nn",
    "sat": "sat-Olck",
    "sv-SE": "sv",
    "tl": "fil",
    "zgh": "tzm",
}

# Inverse: iOS product code -> Pontoon/folder code.
IOS_TO_PONTOON = {ios: pontoon for pontoon, ios in PONTOON_TO_IOS.items()}
