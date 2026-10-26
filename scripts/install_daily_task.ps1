# Windows PowerShell 5.1+. Run only after verifying daily on the production database.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
try {
    $root = Split-Path -Parent $PSScriptRoot
    foreach ($required in @('data\sentinel.sqlite3', '.venv\Scripts\python.exe', 'scripts\run_daily.ps1')) {
        if (-not (Test-Path -LiteralPath (Join-Path $root $required) -PathType Leaf)) { throw 'missing-local-installation' }
    }
    $taskName = 'PriceSentinel-Daily'
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) { throw 'task-already-exists' }
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $folder = Join-Path $root 'private\scheduler'
    [void][IO.Directory]::CreateDirectory($folder)
    $acl = New-Object Security.AccessControl.DirectorySecurity
    $acl.SetOwner($identity.User)
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($sid in @($identity.User, [Security.Principal.SecurityIdentifier]::new('S-1-5-18'))) {
        $rule = [Security.AccessControl.FileSystemAccessRule]::new($sid, [Security.AccessControl.FileSystemRights]::FullControl,
            [Security.AccessControl.InheritanceFlags]'ContainerInherit,ObjectInherit',
            [Security.AccessControl.PropagationFlags]::None, [Security.AccessControl.AccessControlType]::Allow)
        $acl.AddAccessRule($rule)
    }
    Set-Acl -LiteralPath $folder -AclObject $acl
    $secretFile = Join-Path $folder 'webhook.dpapi'
    if (Test-Path -LiteralPath $secretFile) {
        # Reuse a previously provisioned blob only if this Windows user can decrypt it.
        $existingSecret = (Get-Content -LiteralPath $secretFile -Raw).Trim() | ConvertTo-SecureString
        $existingSecret.Dispose()
    }
    else {
        $raw = [IO.File]::ReadAllText((Join-Path $root '.env'))
        $entries = @($raw -split '\r?\n' | ForEach-Object {
            if ($_ -match '^\s*(?:export\s+)?DISCORD_WEBHOOK_URL\s*=\s*(.*?)\s*$') { $Matches[1].Trim().Trim('"').Trim("'") }
        })
        if ($entries.Count -eq 0 -and $raw.Trim() -match '^https://discord\.com/api/webhooks/\d+/[A-Za-z0-9_-]+$') {
            $entries = @($raw.Trim())
        }
        if ($entries.Count -ne 1 -or $entries[0] -notmatch '^https://discord\.com(?::443)?/api/webhooks/\d+/[A-Za-z0-9_-]+$') { throw 'invalid-local-secret' }
        $secure = ConvertTo-SecureString -String $entries[0] -AsPlainText -Force
        try { ConvertFrom-SecureString -SecureString $secure | Set-Content -LiteralPath $secretFile -Encoding ascii }
        finally { $secure.Dispose(); $raw = $null; $entries = $null }
    }
    $fileAcl = New-Object Security.AccessControl.FileSecurity
    $fileAcl.SetOwner($identity.User)
    $fileAcl.SetAccessRuleProtection($true, $false)
    foreach ($sid in @($identity.User, [Security.Principal.SecurityIdentifier]::new('S-1-5-18'))) {
        $fileAcl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new($sid, 'FullControl', 'Allow'))
    }
    Set-Acl -LiteralPath $secretFile -AclObject $fileAcl
    $powershell = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $runner = Join-Path $root 'scripts\run_daily.ps1'
    $action = New-ScheduledTaskAction -Execute $powershell -Argument ('-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy RemoteSigned -File "' + $runner + '"') -WorkingDirectory $root
    $trigger = New-ScheduledTaskTrigger -Daily -At '20:00'
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 15)
    $principal = New-ScheduledTaskPrincipal -UserId $identity.Name -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'Price Sentinel: one local daily at 20:00, DPAPI secret, no automatic retry.' | Out-Null
    $task = Get-ScheduledTask -TaskName $taskName
    $info = Get-ScheduledTaskInfo -TaskName $taskName
    $report = [ordered]@{task_name=$taskName; state=[string]$task.State; start_when_available=$task.Settings.StartWhenAvailable;
        allow_battery=(-not $task.Settings.DisallowStartIfOnBatteries); continue_on_battery=(-not $task.Settings.StopIfGoingOnBatteries);
        execution_time_limit=$task.Settings.ExecutionTimeLimit; multiple_instances=[string]$task.Settings.MultipleInstances;
        logon_type=[string]$task.Principal.LogonType; run_level=[string]$task.Principal.RunLevel;
        next_run=$info.NextRunTime.ToString('o'); working_directory=$task.Actions[0].WorkingDirectory;
        secret_storage='DPAPI CurrentUser; ACL current SID + SYSTEM'; secret_value_displayed=$false}
    $report | ConvertTo-Json -Depth 4
}
catch {
    Write-Output '{"status":"not_configured","detail":"Setup failed; inspect task existence and local permissions; no secret output"}'
    exit 2
}
