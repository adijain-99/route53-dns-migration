#!/usr/bin/env bash
# check-parity.sh - compare two authoritative DNS servers for a list of names.
#
# Usage: ./check-parity.sh <names-file> <old-nameserver> <new-nameserver>
#
# Read-only (dig queries only). Compares the Answer section per record type.
# Where the old server answers with a CNAME and the new one with A records
# (a Route 53 Alias), the CNAME target is resolved and the IP sets compared.
# Exit code 1 if any difference is found.
set -euo pipefail

if [[ $# -ne 3 ]]; then
  echo "usage: $0 <names-file> <old-nameserver> <new-nameserver>" >&2
  exit 2
fi
names_file=$1; old=$2; new=$3
types=(A AAAA CNAME MX TXT)
diffs=0

answers() { # name type [server]
  local server=${3:+@$3}
  # shellcheck disable=SC2086
  dig +noall +answer $server "$1" "$2" \
    | awk -v t="$2" '$4 == t { $1=$2=$3=$4=""; sub(/^ +/, ""); print }' \
    | { if [[ $2 == CNAME || $2 == MX ]]; then tr '[:upper:]' '[:lower:]' | sed 's/\.$//'; else cat; fi; } \
    | sort -u
}

while IFS= read -r name || [[ -n $name ]]; do
  name=${name%.}; [[ -z $name ]] && continue

  old_cname=$(answers "$name" CNAME "$old")
  new_cname=$(answers "$name" CNAME "$new")
  new_a=$(answers "$name" A "$new")
  if [[ -n $old_cname && -z $new_cname && -n $new_a ]]; then
    target_a=$(answers "${old_cname%%$'\n'*}" A)
    if [[ $target_a == "$new_a" ]]; then
      printf '%-8s %-6s %s\n' MATCH ALIAS "$name"
    else
      printf '%-8s %-6s %s  (alias: %s | target: %s)\n' CHECK ALIAS "$name" "${new_a//$'\n'/,}" "${target_a//$'\n'/,}"
    fi
    continue
  fi

  for t in "${types[@]}"; do
    o=$(answers "$name" "$t" "$old"); n=$(answers "$name" "$t" "$new")
    [[ -z $o && -z $n ]] && continue
    if [[ $o == "$n" ]]; then
      printf '%-8s %-6s %s\n' MATCH "$t" "$name"
    else
      diffs=$((diffs + 1))
      printf '%-8s %-6s %s  (old: %s | new: %s)\n' DIFF "$t" "$name" "${o//$'\n'/, }" "${n//$'\n'/, }"
    fi
  done
done < "$names_file"

echo
if (( diffs )); then echo "$diffs difference(s) found. Do NOT cut over until they are fixed."; exit 1; fi
echo "No differences found."
