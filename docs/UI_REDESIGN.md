# UI organization in v1.5.x

This revision changes presentation only. Database schema remains version 9. Archive parsing and backup, Analytics calculations, post-text matching and annotation storage are unchanged.

| Screen | Previously | Now |
| --- | --- | --- |
| First launch | Four-step strip and long optional explanations | Central welcome, destination, ZIP, review, import; one current primary action |
| Analytics during setup | Presented before the first import | Offered after successful import; optional expandable section |
| Archive updates | Narrow drawer sharing gallery width | Resizable 860 px window, minimum 720 px, scrollable content and fixed action footer |
| Tag editing | Name, aliases, prefix, group and colors shown together | Left list plus New tag; right Basic / Automatic tags / Advanced sections |
| Automatic tag options | Numeric limits and notes always visible | Master switch, basic options, advanced limits and exclusions |
| Keyword rules | Additional modal window | Editable word list inside the same settings page |
| Group management | Small dialog and nested name prompts | Full management tab, group and tag-count columns, inline name entry |
| Main toolbar | Archive import alongside frequent browsing controls | Archive and Analytics under the … menu; gallery controls remain |

The existing automatic-tag defaults and saved settings are preserved. Turning the master switch off sets the existing body/hashtag switches off; the registered keyword definitions are retained. Saving and reconciliation use the previous handlers.

First-run guidance no longer displays all steps or long explanations together. ZIP acquisition help and detailed settings open on request. Japanese and English UI and both color themes are supported. Tests use isolated profiles and synthetic archives; no production library is reset.

## First-run setup revision

The main gallery area contains three spacious cards: destination, official X archive ZIP, and start import. Completed choices have check marks. ZIP selection and starting remain disabled until prerequisites are valid. Native pickers and the existing ImportController are reused; no archive, Analytics, tag or database schema changes are introduced. Progress and recoverable errors stay in the main screen. Once a successful import has loaded artworks, the gallery opens automatically. Analytics remains optional and is accessible later from the settings menu.

Setup is based on the existence of saved artworks, never on the filtered gallery count. Empty configured libraries continue setup; existing libraries with no search matches retain the normal gallery. Unfinished destination and ZIP choices are saved in private settings; reopening revalidates an available ZIP without importing automatically. Existing libraries can be opened directly.

Startup validates the actual catalog before treating a remembered destination as configured. Missing paths reopen central setup with inline recovery guidance. If loading a catalog fails before any artworks are loaded, recovery stays in the main screen without a blocking modal. Library settings, account records, tags and favorites are retained so a disconnected or relocated library can be reopened.

The central first-run setup now includes a compact optional Analytics CSV section. It expands on request, supports removal of a selected CSV and optional preservation of the original file, and reuses the existing combined archive/CSV pipeline. The gallery opens when both selected imports complete. CSV selections and retention preferences resume with unfinished setup.
