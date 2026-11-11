"""Unit tests for scripts/r53zone.py (standard library unittest only)."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import r53zone  # noqa: E402

EXAMPLE = (ROOT / "examples" / "example.org.export.txt").read_text(encoding="utf-8")


class ParseZoneTests(unittest.TestCase):
    def setUp(self):
        self.origin, self.records = r53zone.parse_zone(EXAMPLE)

    def test_origin_is_read(self):
        self.assertEqual(self.origin, "example.org")

    def test_multiline_soa_is_skipped(self):
        self.assertFalse(any(r.rtype == "SOA" for r in self.records))

    def test_multi_string_txt_is_kept_intact(self):
        dkim = next(r for r in self.records if r.name == "selector1._domainkey")
        self.assertEqual(dkim.rdata.count('"'), 4)

    def test_semicolon_inside_quotes_is_not_a_comment(self):
        dmarc = next(r for r in self.records if r.name == "_dmarc")
        self.assertIn("p=none;", dmarc.rdata)


class FullModeTests(unittest.TestCase):
    def setUp(self):
        origin, records = r53zone.parse_zone(EXAMPLE)
        self.lines, self.notes, self.names = r53zone.cmd_full(origin, records)
        self.body = "\n".join(self.lines)

    def test_apex_ns_and_registrar_helpers_are_dropped(self):
        self.assertNotIn("registrar-dns.example", self.body)
        self.assertNotIn("_domainconnect", self.body)

    def test_mail_records_are_kept(self):
        self.assertIn("MX\t1\tmx1.mailprovider.example.", self.body)
        self.assertIn("v=spf1", self.body)
        self.assertIn("v=DMARC1", self.body)

    def test_forwarding_reminder_is_always_printed(self):
        self.assertTrue(any("forwarding" in n for n in self.notes))

    def test_non_ip_a_record_needs_action(self):
        origin, records = r53zone.parse_zone(EXAMPLE + "\nparked\t600\tIN\tA\tParked\n")
        lines, notes, _ = r53zone.cmd_full(origin, records)
        self.assertNotIn("Parked", "\n".join(lines))
        self.assertTrue(any("NEEDS ACTION" in n and "parked" in n for n in notes))


class SubdomainModeTests(unittest.TestCase):
    def setUp(self):
        origin, records = r53zone.parse_zone(EXAMPLE)
        self.lines, self.notes, self.names = r53zone.cmd_subdomain(origin, records, "test")
        self.body = "\n".join(self.lines)

    def test_new_origin(self):
        self.assertEqual(self.lines[0], "$ORIGIN test.example.org.")

    def test_everything_below_the_subdomain_is_selected(self):
        self.assertEqual(self.names, sorted([
            "test.example.org", "mb.test.example.org", "logs.test.example.org",
            "_aaaa1111.test.example.org", "_cccc3333.logs.test.example.org",
        ]))

    def test_lookalike_names_are_not_selected(self):
        self.assertNotIn("test2", self.body)

    def test_names_are_rewritten_relative_to_new_zone(self):
        self.assertIn("\nmb\t600\tIN\tCNAME", self.body)
        self.assertIn("\n_cccc3333.logs\t3600\tIN\tCNAME", self.body)

    def test_apex_cname_is_not_emitted_but_flagged(self):
        self.assertNotIn("\n@\t", self.body)
        self.assertTrue(any("NEEDS ACTION" in n and "Alias" in n for n in self.notes))

    def test_certificate_validation_records_are_called_out(self):
        self.assertEqual(sum("certificate validation" in n for n in self.notes), 2)

    def test_fqdn_sub_argument_is_accepted(self):
        origin, records = r53zone.parse_zone(EXAMPLE)
        lines, _, _ = r53zone.cmd_subdomain(origin, records, "test.example.org")
        self.assertEqual(lines, self.lines)


class CliTests(unittest.TestCase):
    def test_cli_writes_zone_and_names_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "test.zone"
            subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "r53zone.py"), "subdomain",
                 str(ROOT / "examples" / "example.org.export.txt"), "--sub", "test", "--out", str(out)],
                check=True, capture_output=True, text=True,
            )
            self.assertTrue(out.read_text().startswith("$ORIGIN test.example.org."))
            self.assertEqual(len(Path(str(out) + ".names.txt").read_text().split()), 5)


if __name__ == "__main__":
    unittest.main()
