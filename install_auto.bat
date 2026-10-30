@echo off
rem Register a daily Windows task that runs auto.bat (no admin rights needed).
rem If the PC is off at that time, it runs as soon as the PC is on again.
rem   install_auto.bat          -> install / update
rem   install_auto.bat remove   -> uninstall
cd /d "%~dp0"
if /i "%~1"=="remove" (
  powershell -NoProfile -Command "Unregister-ScheduledTask -TaskName 'RedevMap' -Confirm:$false" && echo Removed.
  pause & exit /b
)
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$d='%~dp0'.TrimEnd('\');" ^
  "$a=New-ScheduledTaskAction -Execute 'cmd.exe' -Argument ('/c start \"RedevMap\" /min \"' + $d + '\auto.bat\"') -WorkingDirectory $d;" ^
  "$t=New-ScheduledTaskTrigger -Daily -At 9:00;" ^
  "$s=New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 20);" ^
  "Register-ScheduledTask -TaskName 'RedevMap' -Action $a -Trigger $t -Settings $s -Description 'Redev-map: VWorld data -> GitHub' -Force | Out-Null;" ^
  "Write-Host 'Installed: runs daily at 9:00, or right after the PC turns on if it was off.'"
pause
