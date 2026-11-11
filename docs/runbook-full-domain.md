# Runbook: move a whole domain to Route 53

Moves DNS hosting for `example.org`, including the email records, from the
registrar to Route 53. Website, mailboxes and registration stay where they are.

**Typical duration:** about 2 hours hands-on, spread over 2–3 working days
because of DNS caching.

| Day | Step |
|---|---|
| 1 | Export, import, parity check, lower TTLs |
| 2 | Switch nameservers, test web and email |
| 3–5 | Hold period with the old zone untouched |

---

## Before you start

- **Find out where email lives.** Look at the MX records. `aspmx.l.google.com`
  means Google Workspace; `*.mail.protection.outlook.com` means Microsoft 365.
  Mailboxes don't move; only the records pointing at them do.
- **List every mail sender.** SPF, DKIM and DMARC records for each one (the
  mail provider, help desk, transactional email, marketing tools). A missed
  DKIM record doesn't bounce mail; it quietly sends it to spam.
- **Check DNSSEC at the registrar.** If it's on, turn it off and let it clear
  before changing nameservers, or resolvers will reject the new answers.
- **Check registrar web/email forwarding.** It isn't in the zone export and
  stops working when the nameservers move.
- **Get access sorted.** A Route 53 role in the production account, and the
  registrar's 2-step verification on a phone you can reach.

## Day 1

1. **Freeze.** No DNS or email record changes at the registrar until the hold
   period ends.
2. **Export** the zone (123 Reg: Manage DNS → Actions → Export Zone File).
3. **Clean it:**
   ```bash
   python3 scripts/r53zone.py full example.org.export.txt --out example.org.zone
   ```
   Do every `NEEDS ACTION` item by hand (apex CNAME → Alias, "parked"
   placeholders, forwarding).
4. **Create the hosted zone** (public) and **Import zone file**.
5. **Recreate any subdomain delegations** in the new zone (see the subdomain runbook).
6. **Parity check** against one of the Route 53 nameservers:
   ```bash
   ./scripts/check-parity.sh example.org.zone.names.txt <old-ns> <route53-ns>
   ```
7. **Lower TTLs** at the registrar to 300 seconds, at least 24 hours before
   the switch. Lowering them on the day of the switch does almost nothing.

## Day 2: switch

1. At the registrar, replace its nameservers with the **4 Route 53 nameservers**
   of the hosted zone. Do it early in a working day, never on a Friday.
2. Verify:
   - `dig example.org NS` (or `Resolve-DnsName -Type NS`) shows the AWS nameservers
   - Website loads over HTTPS
   - Send and receive email to and from an outside account (Gmail, Outlook)
   - Check the test mail's headers: SPF, DKIM and DMARC = pass

## Hold period

Resolvers can cache the old nameservers for up to 48 hours. Keep the registrar's
zone **untouched and identical**; if a change is unavoidable, make it in both.

**Rollback:** put the registrar's nameservers back. Everything returns to how it
was, because the old zone was never changed.

When the hold period closes, raise TTLs back to normal (e.g. 3600).

## Not part of this runbook

- **Registration transfer** to Route 53 Domains: do it later, once DNS is
  stable. Transferring first risks the old provider's DNS going away before
  Route 53 has the records.
- **Mailbox migration**: Route 53 can't host mailboxes. Amazon WorkMail is
  being retired, so use a dedicated mail provider.
