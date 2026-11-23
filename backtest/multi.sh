#!/bin/bash
# Run one idea across every leak-free season and compare it with the baseline, paired by game.
#
#   backtest/multi.sh TAG "ENV=VALUE [ENV=VALUE ...]" [SEASONS]
#   backtest/multi.sh _lf ""                       # the baselines themselves (live defaults)
#   backtest/multi.sh _s105 "MIN_SCALE_HI=1.05"    # a candidate, then: python -m backtest.multi_report _lf _s105
#
# Every run is leak-free (LOCK_STATUS=1: who plays comes from the NBA injury report at the lock), prices winner legs
# like live (REPLAY_ML=1, where moneylines exist) and uses the books' X+ prices where they exist (2024-25; rows from
# backtest/alt_rows.py in ~/.cache/tipoff_alt). The 2022-23 and 2023-24 Ladders are priced at the books' main lines.
# At most 6 replays at once, one BLAS thread each. Results: /tmp/tickets_{season}{TAG}.json and
# /tmp/ladder_{season}{TAG}.json, copied to ~/.cache/tipoff_replays/ (a restart clears /tmp); logs in /tmp/multi_*.
cd "$(dirname "$0")/.." || exit 1
TAG=${1:?tag, e.g. _s105}
CAND=${2:-}
SEASONS=${3:-"2019 2020 2021 2022 2023 2024 2025 2026 2027"}
PY=${PY:-/tmp/tipoff_venv/bin/python}
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
export ALT_BLEND=0.2987,0.5242,-0.0711 ALT_ROWS=${ALT_ROWS:-$HOME/.cache/tipoff_alt/alt_rows_2025.pkl} ALT_MODE=live REPLAY_ML=1 LOCK_STATUS=1
[ -n "$CAND" ] && export $CAND
range() {  # first and last day replayed: injury reports start 2018-12-18; the 2019-20 season ended in the bubble
  case $1 in
    2019) echo 2018-12-18 2019-04-30 ;;
    2020) echo 2019-10-01 2020-08-31 ;;
    2021) echo 2020-12-01 2021-05-31 ;;
    *) echo $(($1 - 1))-10-01 $1-04-30 ;;
  esac
}
for s in $SEASONS; do
  while [ "$(jobs -r | wc -l)" -ge 6 ]; do sleep 10; done
  # 2022-23 and 2023-24: ESPN's books posted main player lines only (no X+ rungs): they price the Ladder (LADDER_MAIN)
  case $s in 2023|2024) LM=open ;; *) LM= ;; esac
  LADDER_MAIN=$LM TAG=$TAG nohup $PY -u -m backtest.tickets $s $(range $s) base > /tmp/multi_${s}${TAG}.log 2>&1 &
done
wait
mkdir -p ~/.cache/tipoff_replays
for s in $SEASONS; do
  grep -q "milestone blend on" /tmp/multi_${s}${TAG}.log || echo "WARNING: $s ran without the milestone blend"
  cp /tmp/tickets_${s}${TAG}.json /tmp/ladder_${s}${TAG}.json ~/.cache/tipoff_replays/ 2>/dev/null
done
echo "done: $TAG ($CAND) on $SEASONS"
