# Hue Potato for Mashwright

Brotato × Hue as a Mashwright mashup. `mashwright.json` is the recipe; the three component zips are
Hue Potato's release packages.

    python3 ../../mashups/hue-potato/tools/fetch_vendor.py
    python3 ../../mashups/hue-potato/tools/build.py   # builds mashups/hue-potato/build/*.zip
    python3 make_package.py                         # -> hue-potato.mashwright (checksums filled in)
    python3 ../../mashwright.py import hue-potato.mashwright
    python3 ../../mashwright.py install hue-potato
    python3 ../../mashwright.py launch hue-potato

Needs Brotato and Hue installed (any store; Linux native or Proton, Windows, macOS).
