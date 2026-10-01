# Chaos Engine

Real data is never perfect. Chaos Engine takes a clean dataset and gives you back a realistically messy copy, so you can practise cleaning it.

It's a small utility for students learning data analysis. Load any dataset (a Kaggle download, a spreadsheet, whatever you have), press **Create Chaos**, and download the messy version to play with. You also get an answer key that lists every change, so you can check your own cleaning against it.

**Use it online:** https://tidyweb.github.io/Chaos-Engine/

Your file never leaves your computer. Everything runs in your browser.

## How to use it

1. Load a file: CSV, TSV, text, JSON or Excel. For Excel files with several sheets, pick the one you want.
2. Choose the amount of chaos (Light, Realistic or Heavy) and, if you like, a seed number. The same file and the same seed always give the same mess.
3. Press **Create Chaos**.
4. Download the messy file (CSV or Excel) and the answer key (CSV).

You can switch between the original and the messy table on screen. Changed cells and added rows are highlighted, and hovering shows what was done.

## What it breaks

The mess is meant to look like real life, not like a corrupted file. Depending on the columns in your data, it can add:

- missing values written in different ways (blank, `N/A`, `-`, `null`)
- dates in mixed formats, and a few impossible ones
- numbers stored as text, with currency symbols or commas
- stray spaces and inconsistent upper/lower case
- typos in categories
- yes/no columns written several different ways
- badly formed email addresses
- outliers
- duplicate rows, near-duplicates, and the same ID with conflicting details
- blank rows and repeated header rows
- messy column headers

Chaos Engine looks at each column and guesses what kind of data it holds. You can correct a guess from the column list if it gets one wrong.

## The answer key

The key is a CSV with one line per change: the row, the column, the type of problem, the original value and the messy value. Row 0 is the header line. Use it to check your work, or to see what you missed.

## Size limits

The web version holds everything in your browser's memory, so it has limits: 25 MB, 100,000 rows and 200 columns per file. That is enough for most course datasets. Larger files need a standalone version, which is planned.

## Run it on your own computer

You need Python 3 with `numpy`, `pandas` and `openpyxl`.

```
python tools/build_web.py my_site
python -m http.server --directory my_site 8000
```

Then open http://localhost:8000. To run the engine's tests:

```
python tests/engine_test.py
```

## Licence

MIT. See `LICENSE`.

A [Tidy Web](https://github.com/TidyWeb) project.
