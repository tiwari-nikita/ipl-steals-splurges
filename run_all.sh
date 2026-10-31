#!/bin/sh
# Rebuild everything from the raw data and verify it. Usage: ./run_all.sh
set -e
P="$(cd "$(dirname "$0")" && pwd)"
PY="$P/.venv/bin/python -I"
cd /tmp
$PY "$P/pipeline/01_deliveries.py" "$P/data/raw/cricsheet/json" "$P/out"
$PY "$P/pipeline/02_salaries.py" "$P/data/raw/wiki/personnel_2026.json" 2026 "$P/out/salaries_2026.csv"
$PY "$P/pipeline/03_value.py" "$P/out"
$PY "$P/pipeline/04_match.py" "$P/out" "$P/data/manual_name_map.csv" 2026
$PY "$P/pipeline/05_fair_value.py" "$P/out" 2026 "$P/site/data/season_2026.json"
$PY -c "import sys; d=open(sys.argv[1]).read(); open(sys.argv[2],'w').write('window.SEASON_2026 = '+d.strip()+';\n')" "$P/site/data/season_2026.json" "$P/site/data/season_2026.js"
$PY "$P/verify.py" "$P"
