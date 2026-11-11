# Milestone plan template

A 5-step plan to share with stakeholders. Replace the dates; keep the order and
the gaps between steps.

| # | Step | What it means | When |
|---|---|---|---|
| 1 | **Export records** | Export the zone from the registrar. Freeze DNS and email record changes from now on. | Day 1 |
| 2 | **Import into Route 53 and check** | Import into the hosted zone; parity check confirms every record matches, including MX, SPF, DKIM and DMARC. | Day 1–3 |
| 3 | **Lower TTLs** | Set registrar records to 300 s, at least 24 h before the switch. | Day before switch |
| 4 | **Switch nameservers** | Replace the registrar's nameservers with Route 53's. Test website and email. | Switch day (early, midweek) |
| 5 | **Hold, then confirm** | Keep the old zone untouched as rollback for ~3 days. If all is well, the move is complete. | Switch + 3 days |

**What stays the same:** domain ownership and registration, website hosting,
mailboxes.

**Rollback:** put the registrar's nameservers back. Takes minutes to apply.

**Expected user impact:** none, provided the parity check is clean.

## Message templates

**Before:**

> Heads-up: today I'm moving the DNS for *&lt;scope&gt;* to AWS Route 53.
> Nothing else is touched. No downtime is expected: the records are identical
> on both sides. Rollback is ready and takes a few minutes. I'll post here when
> it's done.

**After:**

> Done: *&lt;scope&gt;* is now on Route 53, verified and working. Nothing else
> was touched. I'll keep an eye on it for the next couple of days with the
> rollback ready.
