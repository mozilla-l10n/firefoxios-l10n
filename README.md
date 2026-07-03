# Firefox for iOS localization

Localization for the Firefox for iOS project.

The application code with build instructions can be found
at <https://github.com/mozilla-mobile/firefox-ios>.

Matrix channel: [#fx-ios](https://chat.mozilla.org/#/room/%23fx-ios:mozilla.org).

## String updates

Automation is used to extract strings from the code repository, and expose them to all other locales.

1. Strings are extracted and saved in the `en-US` XLIFF file (the reference).
2. A source-only version (no translations) is written to `templates`, which is what Pontoon reads to keep every locale in sync.
3. Existing translations are then updated in place: a translation is removed when its source string no longer matches the reference. This step only invalidates stale translations; adding and removing strings is left to Pontoon.

By default, a translation is kept only if all of these match against the reference:
* `id` attribute of `trans-unit`.
* `original` attribute of `file`.
* `source` text.

As a consequence, the default update removes a translation if:
* The source text was changed.
* The string was moved from one file to another.

This is not ideal when the change in the source text is trivial, or the string move is caused by code refactoring.

It’s possible to invoke [automation manually](https://github.com/mozilla-l10n/firefoxios-l10n/actions/workflows/import_strings.yml), and use a different matching criterion:
* `nofile` keeps translations if the ID and source text match, ignoring the file. This is useful to minimize the impact of code refactoring.
* `matchid` keeps translations if the ID matches, ignoring the file and source text. This is useful for source changes that don’t require invalidating existing translations.

## Linter for reference strings

When opening a pull request that touches the `en-US` folder, a GitHub workflow is used to check for common issues in the reference strings (misused quotes or ellipsis, hard-coded brand names). It's possible to add exceptions in this [JSON file](.github/scripts/linter_config.json).

## Target language check

When opening a pull request that touches localized files, a GitHub workflow checks that each locale declares the expected `target-language`. This is a safety net for syncs that leave a locale with the wrong or missing language code. A few locales use a language code that differs from their folder name; the mapping lives in [`locale_config.py`](.github/scripts/locale_config.py).

## Locales in build

[![Check product locales](https://github.com/mozilla-l10n/firefoxios-l10n/actions/workflows/check_product_locales.yml/badge.svg)](https://github.com/mozilla-l10n/firefoxios-l10n/actions/workflows/check_product_locales.yml)

Brand new locales might not be correctly imported in the product. This workflow tries to identify missing locales looking at `.lproj` folders in the product repository.

## License

Translations in this repository are available under the terms of the [Mozilla Public License v2.0](http://www.mozilla.org/MPL/2.0/).
