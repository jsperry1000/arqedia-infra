param(
  [string]$Profile  = "arqedia",
  [string]$Region   = "us-east-2",
  [string]$Cluster  = "arn:aws:rds:us-east-2:667523685221:cluster:arqedia-dev-aurora",
  [string]$Secret   = "arn:aws:secretsmanager:us-east-2:667523685221:secret:rds!cluster-8f9fa8a3-b863-480a-b1cf-d00308c8b9f1-0e65rq",
  [string]$Database = "arqedia"
)

# The cluster pauses at zero capacity and takes ~15s to wake. Retry rather
# than fail: the application code must do the same.
function Invoke-Sql($sql) {
  for ($i = 1; $i -le 12; $i++) {
    $out = aws rds-data execute-statement --profile $Profile --region $Region `
      --resource-arn $Cluster --secret-arn $Secret --database $Database `
      --sql $sql --output json 2>&1
    if ($LASTEXITCODE -eq 0) { return $out }
    if ("$out" -match "DatabaseResuming") {
      Write-Host "  waking..." -ForegroundColor DarkGray
      Start-Sleep -Seconds 5
      continue
    }
    throw "FAILED: $($sql.Substring(0, [Math]::Min(80, $sql.Length)))`n$out"
  }
  throw "Cluster did not resume in time."
}

Invoke-Sql "CREATE TABLE IF NOT EXISTS schema_migration (filename VARCHAR(255) PRIMARY KEY, applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)" | Out-Null

$applied = (Invoke-Sql "SELECT filename FROM schema_migration") | ConvertFrom-Json
$done = @($applied.records | ForEach-Object { $_[0].stringValue })

Get-ChildItem "$PSScriptRoot\migrations\*.sql" | Sort-Object Name | ForEach-Object {
  if ($done -contains $_.Name) {
    Write-Host "skip  $($_.Name)" -ForegroundColor DarkGray
    return
  }
  Write-Host "apply $($_.Name)" -ForegroundColor Cyan

  $body = Get-Content $_.FullName -Raw
  $statements = ($body -split ";`r`n|;`n") |
    ForEach-Object { ($_ -replace "(?m)^\s*--.*$", "").Trim() } |
    Where-Object { $_ -ne "" }

  foreach ($s in $statements) { Invoke-Sql $s | Out-Null }

  Invoke-Sql "INSERT INTO schema_migration (filename) VALUES ('$($_.Name)')" | Out-Null
  Write-Host "  done" -ForegroundColor Green
}
