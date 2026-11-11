<#
.SYNOPSIS
  Compare what two authoritative DNS servers answer for a list of names.

.DESCRIPTION
  Use before a cutover: ask the OLD provider's nameserver and the NEW Route 53
  nameserver directly, record type by record type, and flag every difference.
  Read-only: it only sends DNS queries.

  Only the Answer section is compared (extra records in the Additional section,
  such as nameserver addresses, are ignored).

  Alias handling: where the old provider answers with a CNAME and Route 53 answers
  with A records (an Alias, e.g. at a zone apex), the CNAME target is resolved and
  the IP sets are compared instead.

.EXAMPLE
  ./Compare-DnsParity.ps1 -NamesFile test.zone.names.txt `
      -OldServer ns1.old-provider.example -NewServer ns-123.awsdns-45.net
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory)] [string] $NamesFile,
  [Parameter(Mandatory)] [string] $OldServer,
  [Parameter(Mandatory)] [string] $NewServer,
  [string[]] $Types = @('A', 'AAAA', 'CNAME', 'MX', 'TXT')
)

function Get-Answers([string]$Name, [string]$Type, [string]$Server) {
  $params = @{ Name = $Name; Type = $Type; DnsOnly = $true; ErrorAction = 'SilentlyContinue' }
  if ($Server) { $params.Server = $Server }
  Resolve-DnsName @params |
    Where-Object { $_.Section -eq 'Answer' -and "$($_.Type)" -eq $Type } |
    ForEach-Object {
      switch ($Type) {
        'A'     { $_.IPAddress }
        'AAAA'  { $_.IPAddress }
        'CNAME' { $_.NameHost.TrimEnd('.').ToLower() }
        'MX'    { '{0} {1}' -f $_.Preference, $_.NameExchange.TrimEnd('.').ToLower() }
        'TXT'   { $_.Strings -join '' }
      }
    } | Sort-Object -Unique
}

$names = Get-Content $NamesFile | Where-Object { $_.Trim() } | ForEach-Object { $_.Trim().TrimEnd('.') }
$diffs = 0

foreach ($n in $names) {
  $oldCname = @(Get-Answers $n 'CNAME' $OldServer)
  $newCname = @(Get-Answers $n 'CNAME' $NewServer)
  $newA     = @(Get-Answers $n 'A' $NewServer)

  # CNAME at the old provider, Alias (A) at Route 53
  if ($oldCname.Count -and -not $newCname.Count -and $newA.Count) {
    $targetA = @(Get-Answers $oldCname[0] 'A' $null)
    if (-not (Compare-Object $targetA $newA)) {
      '{0,-12} {1,-6} {2}' -f 'MATCH', 'ALIAS', $n
    } else {
      '{0,-12} {1,-6} {2}  (alias {3} vs target {4})' -f 'CHECK', 'ALIAS', $n, ($newA -join ','), ($targetA -join ',')
    }
    continue
  }

  foreach ($t in $Types) {
    $old = @(Get-Answers $n $t $OldServer)
    $new = @(Get-Answers $n $t $NewServer)
    if (-not $old.Count -and -not $new.Count) { continue }
    if (-not (Compare-Object $old $new)) {
      '{0,-12} {1,-6} {2}' -f 'MATCH', $t, $n
    } else {
      $diffs++
      '{0,-12} {1,-6} {2}  (old: {3} | new: {4})' -f 'DIFF', $t, $n, ($old -join ', '), ($new -join ', ')
    }
  }
}

''
if ($diffs) { "$diffs difference(s) found. Do NOT cut over until they are fixed."; exit 1 }
'No differences found.'
