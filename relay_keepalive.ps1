# Keeps the agent-channel relay alive on this box -- Task Scheduler edition.
# Idempotent: if something already listens on 8765, exits silently. Otherwise starts
# relay.py hidden with the shared log. Paired with a schtasks entry that runs this every
# 30 minutes, so a crashed relay is down for at most half an hour, and a running one is
# never doubled.
#   Register:  schtasks /create /tn AgentChannelRelay /sc minute /mo 30 /tr "powershell -NoProfile -ExecutionPolicy Bypass -File D:\agent-channel\relay_keepalive.ps1" /f
if (Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue) { exit 0 }
$env:CHANNEL_LOG = "D:\agent-channel\channel.jsonl"
Start-Process -FilePath "python" -ArgumentList "D:\agent-channel\relay.py" `
    -WorkingDirectory "D:\agent-channel" -WindowStyle Hidden
