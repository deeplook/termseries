# Fitbit JSON conversion


This converter is a repository utility. Run the following commands from a checkout
of [termseries](https://github.com/deeplook/termseries), not an arbitrary directory
containing only the installed package.

`tools/fitbit_to_csv.py` combines Fitbit JSON exports in `data/` into the
standard two-column CSV consumed by `termseries csv`. Fitbit timestamps have no
timezone marker, so the converter interprets them as `Europe/Berlin` by default
and writes normalized UTC timestamps; override this with `--timezone` as needed.

```bash
python tools/fitbit_to_csv.py steps data data/steps.csv
python tools/fitbit_to_csv.py heart data data/heart.csv
python tools/fitbit_to_csv.py sleep data data/sleep.csv

termseries csv data/steps.csv --unit steps --last max
termseries csv data/heart.csv --unit bpm --last max
termseries --line-style step-post --gaps show csv data/sleep.csv --unit stage --last max
```

The sleep CSV represents detailed main-session sleep stages as a numeric step
series: `wake=0`, `REM=1`, `light=2`, and `deep=3`. The converter sorts records
and removes duplicate timestamps, and uses a temporary on-disk index so large
heart-rate exports do not need to fit in memory.
