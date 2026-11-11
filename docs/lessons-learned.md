# Lessons learned

Things that came up during a real migration, roughly in the order they happened.

### 1. "Just the test site" was 9 records, not 1
The subdomain looked like a single CNAME. The full export showed 9 records at
or below it: three more sites and five certificate validation records. Delegating
without them would have broken three sites immediately and **every certificate
at its next renewal**, weeks later, when nobody would connect it to DNS.

**Do:** always work from the full zone export, never from screenshots or a
filtered UI list. Let a script select the records.

### 2. Certificate validation records are invisible until they hurt
`_<hash>.name` CNAMEs pointing at `acm-validations.aws` do nothing day to day.
Lose one and the certificate silently fails to renew.

**Do:** treat every `acm-validations.aws` record as critical in the parity check.

### 3. A CNAME can't sit at a zone apex
Once `test.example.org` gets its own hosted zone, it becomes that zone's apex,
where CNAMEs are not allowed. Route 53's **Alias A** record does the same job,
and also follows a load balancer's changing IPs.

### 4. The console pre-selected the wrong load balancer
The alias target dropdown only lists load balancers in the current account. The
test load balancer lived in another account, and the box was showing a similarly
named **production** load balancer. Saving it would have pointed the test site
at the live app.

**Do:** read the ID before saving. For cross-account targets, type the
`dualstack.…elb.amazonaws.com` name.

### 5. Parity checks must compare the Answer section only
The first version of the check reported a false `DIFF`: the query also returned
the addresses of AWS's own nameservers in the Additional section, and they were
counted as answers.

**Do:** filter on `Section -eq 'Answer'` (PowerShell) or `+noall +answer` (dig).

### 6. Registrar 2-step verification belonged to someone else
The registrar account was shared, and sensitive DNS changes asked for an
authenticator code. Codes kept failing until it became clear which device and
which verification method the action actually wanted.

**Do:** before the change window, confirm who receives the codes and that they
are reachable. Better: give the engineer their own registrar login.

### 7. Deleting before adding creates a small outage
The registrar wouldn't allow NS records for `test` while the `test` CNAME
existed, so the CNAME had to go first. For the few minutes between the two
steps, the subdomain didn't resolve, and any resolver that asked could cache
"not found" for up to an hour.

**Do:** have the NS records ready to paste and keep the gap to seconds. A
full-domain nameserver switch doesn't have this step.

### 8. Changing IAM permissions trips security alarms
Adding Route 53 permissions to an SSO permission set fired a CloudTrail-based
"IAM modification" alarm. That's the alarm doing its job.

**Do:** tell whoever receives security alerts before you change permissions,
and use a proper role rather than a break-glass one for planned work.

### 9. Keep all DNS in one production account
Hosted zones scattered across development and production accounts are easy to
lose track of. Production domains belong in the production (or a shared
networking) account.

### 10. Timelines: separate the work from the waiting
The first plan stretched to six weeks because it was fitted around a website
launch and included the registration transfer. The DNS work itself was 2–3
working days. Show stakeholders both: the technical minimum and the buffered plan.
