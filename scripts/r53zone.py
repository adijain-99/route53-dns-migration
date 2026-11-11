#!/usr/bin/env python3
"""
r53zone.py - turn a registrar's DNS zone export into a Route 53 import-ready zone file.

Two modes:

  full       Clean a whole-domain export for import into a Route 53 hosted zone
             for the same domain (drops SOA, apex NS and registrar-only records,
             and flags anything that needs manual work).

  subdomain  Pull every record at or below one subdomain (e.g. "test") out of the
             parent export, so the subdomain can be delegated to its own Route 53
             hosted zone. Records are re-written relative to the new zone.

Both modes also write a list of record names you can feed to the parity check
scripts (scripts/Compare-DnsParity.ps1 or scripts/check-parity.sh).

Usage:
  python3 r53zone.py full      export.txt --out clean.zone
  python3 r53zone.py subdomain export.txt --sub test --out test.zone

Only the Python standard library is used.
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# Records that only make sense at the old registrar.
REGISTRAR_ONLY_NAMES = {"_domainconnect"}
SKIP_TYPES_ALWAYS = {"SOA"}


@dataclass
class Record:
    name: str      # relative to the original origin ("@" for apex)
    ttl: int
    rtype: str
    rdata: str
    line_no: int


def parse_zone(text: str) -> tuple[str, list[Record]]:
    """Parse a simple BIND-style export (one record per line, SOA may span lines)."""
    origin = ""
    records: list[Record] = []
    in_parens = False
    for i, raw in enumerate(text.splitlines(), start=1):
        line = raw.split(";", 1)[0] if '"' not in raw else _strip_comment_outside_quotes(raw)
        if in_parens:
            if ")" in line:
                in_parens = False
            continue
        if not line.strip():
            continue
        if line.startswith("$ORIGIN"):
            origin = line.split()[1].rstrip(".").lower()
            continue
        if line.startswith("$"):
            continue
        if "(" in line and ")" not in line:
            in_parens = True  # multi-line record (SOA) - skipped
            continue
        m = re.match(r"^(\S+)\s+(\d+)\s+IN\s+(\S+)\s+(.+?)\s*$", line)
        if not m:
            print(f"warning: line {i} not understood, skipped: {raw.strip()}", file=sys.stderr)
            continue
        name, ttl, rtype, rdata = m.groups()
        records.append(Record(name=name.lower() if name != "@" else "@", ttl=int(ttl),
                              rtype=rtype.upper(), rdata=rdata, line_no=i))
    if not origin:
        sys.exit("error: no $ORIGIN line found in the export")
    return origin, records


def _strip_comment_outside_quotes(line: str) -> str:
    out, in_q = [], False
    for ch in line:
        if ch == '"':
            in_q = not in_q
        if ch == ";" and not in_q:
            break
        out.append(ch)
    return "".join(out)


def fqdn(name: str, origin: str) -> str:
    return origin if name == "@" else f"{name}.{origin}"


def is_ip(value: str) -> bool:
    return bool(re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", value)) or ":" in value


def format_record(name: str, r: Record) -> str:
    return f"{name}\t{r.ttl}\tIN\t{r.rtype}\t{r.rdata}"


def cmd_full(origin: str, records: list[Record]) -> tuple[list[str], list[str], list[str]]:
    out, notes, names = [f"$ORIGIN {origin}."], [], []
    for r in records:
        if r.rtype in SKIP_TYPES_ALWAYS:
            continue
        if r.rtype == "NS" and r.name == "@":
            notes.append(f"dropped apex NS {r.rdata} (Route 53 creates its own)")
            continue
        if r.name in REGISTRAR_ONLY_NAMES:
            notes.append(f"dropped {r.name} (registrar-only helper record)")
            continue
        if r.rtype in ("A", "AAAA") and not is_ip(r.rdata):
            notes.append(f"NEEDS ACTION: {fqdn(r.name, origin)} {r.rtype} '{r.rdata}' is a registrar "
                         f"special value (e.g. parking/forwarding), not an IP - recreate it manually")
            continue
        if r.rtype == "CNAME" and r.name == "@":
            notes.append(f"NEEDS ACTION: apex CNAME -> {r.rdata} is not allowed in Route 53; "
                         f"create an Alias A record instead")
            continue
        if r.rtype == "NS":
            notes.append(f"kept delegation {fqdn(r.name, origin)} NS {r.rdata} - check it points to the right zone")
        out.append(format_record(r.name, r))
        names.append(fqdn(r.name, origin))
    notes.append("REMINDER: web/email forwarding configured in the registrar UI is not in the export - "
                 "check for it separately")
    return out, notes, sorted(set(names))


def cmd_subdomain(origin: str, records: list[Record], sub: str) -> tuple[list[str], list[str], list[str]]:
    sub = sub.lower().rstrip(".")
    if sub.endswith("." + origin):
        sub = sub[: -(len(origin) + 1)]
    new_origin = f"{sub}.{origin}"
    out, notes, names = [f"$ORIGIN {new_origin}."], [], []
    selected = [r for r in records if r.name == sub or r.name.endswith("." + sub)]
    if not selected:
        sys.exit(f"error: no records at or below '{sub}' in {origin}")
    for r in selected:
        rel = "@" if r.name == sub else r.name[: -(len(sub) + 1)]
        names.append(fqdn(r.name, origin))
        if rel == "@" and r.rtype == "CNAME":
            notes.append(f"NEEDS ACTION: {new_origin} CNAME -> {r.rdata} becomes the zone apex; "
                         f"create it by hand as an Alias A record (to an ELB/CloudFront target) "
                         f"or as plain A records")
            continue
        if r.rtype in SKIP_TYPES_ALWAYS:
            continue
        out.append(format_record(rel, r))
        if "acm-validations.aws" in r.rdata:
            notes.append(f"kept certificate validation record {fqdn(r.name, origin)} "
                         f"(without it the certificate will not renew)")
    notes.append(f"{len(selected)} record(s) live at or below {new_origin}; ALL of them must exist in the "
                 f"new zone before the parent delegates '{sub}'")
    return out, notes, sorted(set(names))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("mode", choices=["full", "subdomain"])
    p.add_argument("export", type=Path, help="zone file exported from the current DNS provider")
    p.add_argument("--sub", help="subdomain label to extract, e.g. 'test' (subdomain mode)")
    p.add_argument("--out", type=Path, required=True, help="where to write the import-ready zone file")
    p.add_argument("--names-out", type=Path, help="where to write the list of names for the parity check "
                                                   "(default: <out>.names.txt)")
    a = p.parse_args()

    origin, records = parse_zone(a.export.read_text(encoding="utf-8"))
    if a.mode == "subdomain":
        if not a.sub:
            p.error("--sub is required in subdomain mode")
        lines, notes, names = cmd_subdomain(origin, records, a.sub)
    else:
        lines, notes, names = cmd_full(origin, records)

    a.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    names_out = a.names_out or a.out.with_suffix(a.out.suffix + ".names.txt")
    names_out.write_text("\n".join(names) + "\n", encoding="utf-8")

    print(f"wrote {len(lines) - 1} record(s) to {a.out}")
    print(f"wrote {len(names)} name(s) to {names_out}")
    for n in notes:
        print(f"  - {n}")


if __name__ == "__main__":
    main()
