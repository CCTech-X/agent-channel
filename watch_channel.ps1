# agent-channel watcher -- Task Scheduler edition. Runs OUTSIDE any Claude/VS Code session.
#
# WHAT IT DOES. Every run, compare channel.jsonl's line count against a cursor file. If new
# messages exist from anyone other than "neptune", raise a Windows toast notification and
# write the pending messages to NEW_MESSAGES.txt so whoever opens the next Claude session
# can hand them over in one paste.
#
# WHAT IT DELIBERATELY DOES NOT DO. It does not answer. A scheduled task cannot prompt a
# Claude session that is not running -- the auto-reply half only exists while an agent
# session is alive with its own Monitor armed. This gives you the DETECTION half durably:
# you close VS Code, and you still find out when the hardware side posts.
#
# Register (run once, normal user rights):
#   schtasks /create /tn AgentChannelWatch /sc minute /mo 5 /tr "powershell -NoProfile -ExecutionPolicy Bypass -File D:\agent-channel\watch_channel.ps1" /f
# Remove:
#   schtasks /delete /tn AgentChannelWatch /f

$log    = "D:\agent-channel\channel.jsonl"
$cursor = "D:\agent-channel\.watch_cursor"
$outbox = "D:\agent-channel\NEW_MESSAGES.txt"
$me     = "neptune"

if (-not (Test-Path $log)) { exit 0 }

$lines = @(Get-Content $log -Encoding UTF8)
$seen  = 0
if (Test-Path $cursor) { $seen = [int](Get-Content $cursor) }
if ($lines.Count -le $seen) { exit 0 }

$fresh = @()
for ($i = $seen; $i -lt $lines.Count; $i++) {
    try { $m = $lines[$i] | ConvertFrom-Json } catch { continue }
    if ($m.from -ne $me) { $fresh += $m }
}
Set-Content $cursor $lines.Count -Encoding ascii

if ($fresh.Count -eq 0) { exit 0 }

# Append to the outbox for the next agent session to ingest.
$stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content $outbox "=== detected $stamp -- $($fresh.Count) new message(s) ===" -Encoding utf8
foreach ($m in $fresh) {
    Add-Content $outbox "[$($m.ts)] $($m.from) -> $($m.to)$(if ($m.topic) { ' (' + $m.topic + ')' })" -Encoding utf8
    Add-Content $outbox $m.body -Encoding utf8
    Add-Content $outbox "" -Encoding utf8
}

# Windows toast so a human notices without opening anything.
try {
    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    $xml = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent(
        [Windows.UI.Notifications.ToastTemplateType]::ToastText02)
    $t = $xml.GetElementsByTagName("text")
    $t.Item(0).AppendChild($xml.CreateTextNode("agent-channel")) | Out-Null
    $t.Item(1).AppendChild($xml.CreateTextNode(
        "$($fresh.Count) new message(s) from $($fresh[0].from) - see NEW_MESSAGES.txt")) | Out-Null
    $toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier(
        "agent-channel").Show($toast)
} catch { }  # toast is best-effort; the outbox file is the durable signal
