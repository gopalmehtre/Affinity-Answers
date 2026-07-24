#!/usr/bin/env bash
#
# company_year_sort.sh
#
# Downloads a CSV of companies (S&P 500 constituents format: Symbol,Security,
# GICS Sector,GICS Sub-Industry,Headquarters Location,Date added,CIK,Founded)
# and prints Company, Location, Founded year, sorted ascending by year.
#
# Usage:
#   ./company_year_sort.sh [CSV_URL] [-r]
#
#   CSV_URL   Optional. Defaults to the S&P 500 constituents CSV.
#   -r        Optional. Sort descending (most recently founded first).
#
# Requires: curl, gawk (for FPAT-based CSV field splitting), sort, column (optional)

set -euo pipefail

DEFAULT_URL="https://raw.githubusercontent.com/datasets/s-and-p-500-companies/refs/heads/main/data/constituents.csv"
URL="$DEFAULT_URL"
SORT_ORDER="asc"

for arg in "$@"; do
    case "$arg" in
        -r|--reverse)
            SORT_ORDER="desc"
            ;;
        http://*|https://*)
            URL="$arg"
            ;;
        *)
            echo "Unknown argument: $arg" >&2
            echo "Usage: $0 [CSV_URL] [-r]" >&2
            exit 1
            ;;
    esac
done

command -v gawk >/dev/null 2>&1 || { echo "Error: gawk is required (try: sudo apt install gawk)" >&2; exit 1; }
command -v curl >/dev/null 2>&1 || { echo "Error: curl is required" >&2; exit 1; }

TMP_CSV="$(mktemp)"
trap 'rm -f "$TMP_CSV"' EXIT

echo "Downloading CSV from: $URL" >&2
curl -fsSL "$URL" -o "$TMP_CSV"

# Parse with gawk using FPAT so we correctly split on commas that are
# outside of double-quoted fields (e.g. "Saint Paul, Minnesota").
# Columns: 1 Symbol, 2 Security, 3 Sector, 4 Sub-Industry,
#          5 Headquarters Location, 6 Date added, 7 CIK, 8 Founded
PARSED="$(gawk '
    BEGIN {
        FPAT = "(\"[^\"]*\")|([^,]+)"
        OFS = "\t"
    }
    function strip_quotes(s) {
        gsub(/^"|"$/, "", s)
        return s
    }
    NR == 1 { next }  # skip header row
    {
        name = strip_quotes($2)
        location = strip_quotes($5)
        founded_raw = strip_quotes($8)

        # Pull out the first 4-digit year mentioned in the Founded field
        # (handles messy values like "2013 (1888)" or "1904/1946/1959")
        year = ""
        if (match(founded_raw, /[0-9]{4}/)) {
            year = substr(founded_raw, RSTART, RLENGTH)
        }
        if (year == "") { year = "0000" }  # unknown -> sorts first/last

        print name, location, year
    }
' "$TMP_CSV")"

SORT_FLAG="-k3,3n"
[ "$SORT_ORDER" = "desc" ] && SORT_FLAG="-k3,3nr"

SORTED="$(echo "$PARSED" | sort -t$'\t' $SORT_FLAG)"

{
    printf "Company\tLocation\tFounded\n"
    printf "%s\n" "$SORTED"
} | gawk -F'\t' '
    {
        name[NR] = $1; loc[NR] = $2; year[NR] = $3
        if (length($1) > w1) w1 = length($1)
        if (length($2) > w2) w2 = length($2)
    }
    END {
        for (i = 1; i <= NR; i++) {
            printf "%-*s  %-*s  %s\n", w1, name[i], w2, loc[i], year[i]
        }
    }
'
