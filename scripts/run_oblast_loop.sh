#!/bin/bash
# Run the whole-oblast satellite job in short, fresh processes (8 pieces each) until
# every (year, tile) piece exists. A fresh process resets memory (one long process crept
# up towards the 4 GB limit); finished pieces are always skipped, so this is safe to
# stop and start at any time.
#
# Run from anywhere:  bash scripts/run_oblast_loop.sh
cd "$(dirname "$0")/.." || exit 1
LOG=data/interim/oblast/run_output.txt
PY="conda run --no-capture-output -n agri python -W ignore"

TOTAL=$($PY -c "
import pandas as pd
from agridisrupt.config import load_config
c = load_config('configs/kharkiv_v1.yaml')
tiles = pd.read_csv(c['paths']['data_interim'] + '/oblast_cell_tiles.csv').tile_id.nunique()
print(tiles * (c['time']['end_year'] - c['time']['start_year'] + 1))")
count() { ls data/interim/oblast/composites_*.csv 2>/dev/null | wc -l | tr -d ' '; }

for round in $(seq 1 40); do
  before=$(count)
  echo "=== round $round $(date '+%a %H:%M') - $before/$TOTAL pieces ===" >> "$LOG"
  PYTHONUNBUFFERED=1 $PY scripts/run_oblast_timeseries.py --max-pieces 8 >> "$LOG" 2>&1
  after=$(count)
  if [ "$after" -ge "$TOTAL" ]; then
    echo "ALL $TOTAL PIECES DONE" >> "$LOG"
    break
  fi
  if [ "$after" -eq "$before" ]; then
    echo "no progress this round - waiting 10 min before retrying" >> "$LOG"
    sleep 600
  fi
done
echo "EXIT after round $round: $(count)/$TOTAL pieces" >> "$LOG"
