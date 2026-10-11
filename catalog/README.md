# Mashwright catalog

`index.json` is the list of mashups Mashwright shows under **Discover → From the catalog**. Every
Mashwright reads it from this repository (raw.githubusercontent.com) unless the player sets other
catalogs in `~/.config/mashwright/catalogs.json` (a JSON list of https URLs).

## Adding a mashup
1. Build your `.mashwright` package (see the main README) and attach it to a GitHub Release
   (in this repo or your own).
2. Run `python3 tools/catalog_entry.py your-mashup.mashwright <release asset URL> [--cover-url URL]
   [--melty https://melty.gg/m/your-slug]` — it fills in the checksum, size and details.
3. Open a pull request with the updated `index.json`.

Mashwright checks every download against its sha256 before installing. Only list mashups you made
or have permission to share, and never include files from the games themselves.
