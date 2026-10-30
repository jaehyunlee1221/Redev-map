# Register a daily task that runs auto.bat (no admin rights needed).
# If the PC is off at 9:00, it runs as soon as the PC is on again.
param([switch]$Remove)
$name = 'RedevMap'
if ($Remove) {
    Unregister-ScheduledTask -TaskName $name -Confirm:$false
    Write-Host 'Removed.'
    return
}
$dir = Split-Path -Parent $PSScriptRoot
$bat = Join-Path $dir 'auto.bat'
$a = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument "/c start `"RedevMap`" /min `"$bat`"" -WorkingDirectory $dir
$t = New-ScheduledTaskTrigger -Daily -At 9:00
$s = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 20)
Register-ScheduledTask -TaskName $name -Action $a -Trigger $t -Settings $s -Description 'Redev-map: VWorld data -> GitHub' -Force | Out-Null
Write-Host "Installed: runs $bat daily at 9:00, or right after the PC turns on if it was off."
