# q.ps1 - run one statement against the ARQEDIA cluster and print it as a table.
#
#   . .\q.ps1            once per window
#   q "SELECT 1"         thereafter
#
# The ARNs live here rather than in a variable a new window forgets, and the
# cluster pauses at zero capacity, so a wake-up is retried rather than shown.
# JSON from the Data API is unreadable at any width; this prints rows.

$script:ArqCluster = "arn:aws:rds:us-east-2:667523685221:cluster:arqedia-dev-aurora"
$script:ArqSecret  = "arn:aws:secretsmanager:us-east-2:667523685221:secret:rds!cluster-8f9fa8a3-b863-480a-b1cf-d00308c8b9f1-0e65rq"

function q {
    param([Parameter(Mandatory = $true)][string]$sql)

    for ($try = 1; $try -le 6; $try++) {
        $raw = aws rds-data execute-statement `
            --profile arqedia `
            --resource-arn $script:ArqCluster `
            --secret-arn $script:ArqSecret `
            --database arqedia `
            --include-result-metadata `
            --sql $sql `
            --output json 2>&1

        if ($LASTEXITCODE -eq 0) { break }
        if ("$raw" -notmatch "DatabaseResuming") { Write-Host "$raw"; return }
        Start-Sleep -Seconds 8
    }
    if ($LASTEXITCODE -ne 0) { Write-Host "$raw"; return }

    $r = "$raw" | ConvertFrom-Json

    if ($null -eq $r.records -or $r.records.Count -eq 0) {
        Write-Host ("(no rows; {0} updated)" -f $r.numberOfRecordsUpdated)
        return
    }

    # Column names come from the metadata, so the output reads like a table
    # rather than a list of positions nobody can match up.
    $names = @($r.columnMetadata | ForEach-Object { $_.label })

    $out = foreach ($row in $r.records) {
        $o = [ordered]@{}
        for ($i = 0; $i -lt $names.Count; $i++) {
            $cell = $row[$i]
            $v = $null
            foreach ($k in 'stringValue','longValue','doubleValue','booleanValue') {
                if ($null -ne $cell.$k) { $v = $cell.$k; break }
            }
            if ($cell.isNull -eq $true) { $v = $null }
            $o[$names[$i]] = $v
        }
        [pscustomobject]$o
    }

    $out | Format-Table -AutoSize
    Write-Host ("{0} row(s)" -f $r.records.Count)
}
