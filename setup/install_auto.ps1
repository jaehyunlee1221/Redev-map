# Register a weekly task that runs auto.bat (no admin rights needed).
# Runs every Saturday 10:00; if the PC is off then, it runs as soon as the PC is on (and online) again.
#   -Daily : run every day instead (recently downloaded data is skipped, so this is cheap too)
param([switch]$Remove, [switch]$Daily)
$name = 'RedevMap'
if ($Remove) {
    Unregister-ScheduledTask -TaskName $name -Confirm:$false
    Write-Host 'Removed.'
    return
}
$dir = Split-Path -Parent $PSScriptRoot
$bat = Join-Path $dir 'auto.bat'
$a = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument "/c start `"RedevMap`" /min `"$bat`"" -WorkingDirectory $dir
if ($Daily) { $t = New-ScheduledTaskTrigger -Daily -At 9:00; $when = 'daily at 9:00' }
else { $t = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Saturday -At 10:00; $when = 'every Saturday 10:00' }
$s = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 20)
Register-ScheduledTask -TaskName $name -Action $a -Trigger $t -Settings $s -Description 'Redev-map: VWorld data -> GitHub' -Force | Out-Null
Write-Host "Installed: runs $bat $when, or right after the PC turns on if it was off then."
Write-Host "Log: $dir\logs\auto.log   (remove: install_auto.bat remove)"
