# Windows PowerShell 5.1+. No secret values or secret arguments in this file.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repoRoot '.venv\Scripts\python.exe'
$database = Join-Path $repoRoot 'data\sentinel.sqlite3'
$secretFile = Join-Path $repoRoot 'private\scheduler\webhook.dpapi'
$logFolder = Join-Path $repoRoot 'logs'
$logFile = Join-Path $logFolder ('daily-' + (Get-Date -Format 'yyyy-MM-dd') + '.log')
$webhook = $null
$webhookToken = $null
$startInfo = $null
$process = $null
$exitCode = 2
$utf8 = New-Object System.Text.UTF8Encoding($false)

function Write-SafeLog([string]$text) {
    if ($webhook) { $text = $text.Replace($webhook, 'https://discord.com/api/webhooks/***') }
    if ($webhookToken) { $text = $text.Replace($webhookToken, '***') }
    $text = [regex]::Replace($text, 'https://discord(?:app)?\.com(?::443)?/api/webhooks/[^\s"''<>]+', 'https://discord.com/api/webhooks/***')
    [System.IO.File]::AppendAllText($logFile, $text + [Environment]::NewLine, $utf8)
}

try {
    [void][System.IO.Directory]::CreateDirectory($logFolder)
    Write-SafeLog (([DateTimeOffset]::Now.ToString('o')) + ' start daily')
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'missing-python' }
    # Never silently create an empty production database after a path/setup mistake.
    if (-not (Test-Path -LiteralPath $database -PathType Leaf)) { throw 'missing-database' }
    $secure = (Get-Content -LiteralPath $secretFile -Raw).Trim() | ConvertTo-SecureString
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { $webhook = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer); $secure.Dispose() }
    if ($webhook -notmatch '^https://discord\.com(?::443)?/api/webhooks/\d+/[A-Za-z0-9_-]+$') {
        throw 'invalid-webhook'
    }
    $webhookToken = ($webhook -split '/')[-1]
    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $python
    $startInfo.Arguments = '-m price_sentinel --db "' + $database + '" daily'
    $startInfo.WorkingDirectory = $repoRoot
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.StandardOutputEncoding = $utf8
    $startInfo.StandardErrorEncoding = $utf8
    $startInfo.EnvironmentVariables['PYTHONUTF8'] = '1'
    $startInfo.EnvironmentVariables['DISCORD_WEBHOOK_URL'] = $webhook
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $startInfo
    [void]$process.Start()
    # Drain both streams concurrently; a full stderr pipe must not deadlock daily.
    $stdout = $process.StandardOutput.ReadToEndAsync()
    $stderr = $process.StandardError.ReadToEndAsync()
    if (-not $process.WaitForExit(600000)) {
        $process.Kill()
        [void]$process.WaitForExit(5000)
        $exitCode = 124
        Write-SafeLog 'timeout: daily exceeded 10 minutes; child terminated; no automatic retry'
    }
    else {
        Write-SafeLog ($stdout.GetAwaiter().GetResult())
        $errorText = $stderr.GetAwaiter().GetResult()
        if ($errorText) { Write-SafeLog $errorText }
        $exitCode = $process.ExitCode
    }
    Write-SafeLog (([DateTimeOffset]::Now.ToString('o')) + ' end daily exit_code=' + $exitCode)
}
catch {
    if ($exitCode -eq 0) { $exitCode = 2 }
    # Do not write exception input/context: decryption or HTTP data may be sensitive.
    try { Write-SafeLog ('wrapper_error; exit_code=' + $exitCode + '; verify paths, DPAPI user and permissions') }
    catch { [Console]::Error.WriteLine('Price Sentinel: cannot write diagnostic log') }
}
finally {
    if ($process) {
        try { if (-not $process.HasExited) { $process.Kill() } } catch {}
        $process.Dispose()
    }
    if ($startInfo) { $startInfo.EnvironmentVariables.Remove('DISCORD_WEBHOOK_URL') }
    $webhook = $null
    $webhookToken = $null
}
exit $exitCode
