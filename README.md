# Firefox for iOS localization

Localization for the Firefox for iOS project.

The application code with build instructions can be found
at <https://github.com/mozilla-mobile/firefox-ios>.

Matrix channel: [#fx-ios](https://chat.mozilla.org/#/room/%23fx-ios:mozilla.org).

## String updates

Automation is used to extract strings from the code repository, and expose them to all other locales.

1. Strings are extracted and saved in the `en-US` XLIFF file.
2. The updated `en-US` XLIFF is used as a template. Existing translations are copied over if all these elements match:
    * `id` attribute of `trans-unit`.
    * `original` attribute of `file`.
    * `source` text.

As a consequence, the default update removes translations if:
* The source text was changed.
* The string was moved from one file to another.

This is not ideal when the change in the source text is trivial, or the string move is caused by code refactoring.

It’s possible to invoke [automation manually](https://github.com/mozilla-l10n/firefoxios-l10n/actions/workflows/export_strings.yml), and use a different matching criterion:
* `nofile` will copy translations if the ID and source text match, ignoring the file. This is useful to minimize the impact of code refactoring.
* `matchid` will ignore both file and source text, copying translations if the ID matches. This is useful for source changes that don’t require invalidating existing translations.

## Linter for reference strings

When opening a pull request that touches the `en-US` folder, a GitHub workflow is used to check for common issues in the reference strings (misused quotes or ellipsis, hard-coded brand names). It's possible to add exceptions in this [JSON file](.github/scripts/linter_config.json).

## Locales in build

[![Check product locales](https://github.com/mozilla-l10n/firefoxios-l10n/actions/workflows/check_product_locales.yml/badge.svg)](https://github.com/mozilla-l10n/firefoxios-l10n/actions/workflows/check_product_locales.yml)

Brand new locales might not be correctly imported in the product. This workflow tries to identify missing locales looking at `.lproj` folders in the product repository.

## License

Translations in this repository are available under the terms of the [Mozilla Public License v2.0](http://www.mozilla.org/MPL/2.0/).
