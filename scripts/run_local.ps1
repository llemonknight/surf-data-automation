param(
    [ValidateSet("Morning", "Afternoon")]
    [string]$SessionName = "Morning"
)

$ErrorActionPreference = "Stop"

# SessionName is retained for old commands; collection now includes both sessions.

python "$PSScriptRoot\..\collect_data.py"
