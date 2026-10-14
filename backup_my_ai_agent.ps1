$ErrorActionPreference = "Stop"

Set-Location "C:\Users\Dell\my_ai_agent"

$backupDir = "$env:USERPROFILE\Documents\MyAIAgentBackups"

if (!(Test-Path $backupDir)) {
    New-Item -ItemType Directory -Path $backupDir | Out-Null
}

$date = Get-Date -Format "yyyy-MM-dd_HH-mm"
$backupFile = Join-Path $backupDir "my_ai_agent_$date.dump"

$dbLine = railway variable list -s Postgres --kv |
    Where-Object { $_ -match "^DATABASE_PUBLIC_URL=" } |
    Select-Object -First 1

if (!$dbLine) {
    throw "DATABASE_PUBLIC_URL not found."
}

$dbUrl = $dbLine.Substring(
    "DATABASE_PUBLIC_URL=".Length
).Trim()

if (!$dbUrl.StartsWith("postgres")) {
    throw "Invalid DATABASE_PUBLIC_URL."
}

$pgDump = "C:\Program Files\PostgreSQL\18\bin\pg_dump.exe"

& $pgDump `
    "--dbname=$dbUrl" `
    "--format=custom" `
    "--no-owner" `
    "--no-privileges" `
    "--file=$backupFile"

if ($LASTEXITCODE -ne 0) {
    Remove-Item $backupFile -ErrorAction SilentlyContinue
    throw "Database backup failed."
}

Get-ChildItem $backupDir -Filter "*.dump" |
    Where-Object {
        $_.LastWriteTime -lt (Get-Date).AddDays(-14)
    } |
    Remove-Item -Force

Write-Host "Backup completed:"
Write-Host $backupFile
