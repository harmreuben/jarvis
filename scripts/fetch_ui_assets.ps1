# Downloads the Classic interface's images and video from their original source (they are not part of this
# repository because they belong to another project). Safe to run repeatedly; skips files already present.
$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$dest = Join-Path $Root "web\assets"
New-Item -ItemType Directory -Force -Path $dest | Out-Null
$base = "https://raw.githubusercontent.com/Divy0The0Fire/J4E/main/"
$files = @{
    "glowing-button.png" = "glowing-button.png"
    "nevbg-image-1.png"  = "nevbg-image-1.png"
    "r-icons.svg"        = "r-icons.svg"
    "mp4-vmake.mp4"      = "mp4-vmake%20(1).mp4"
}
$missing = 0
foreach ($name in $files.Keys) {
    $out = Join-Path $dest $name
    if ((Test-Path $out) -and ((Get-Item $out).Length -gt 0)) { continue }
    try {
        Invoke-WebRequest -UseBasicParsing -Uri ($base + $files[$name]) -OutFile $out -TimeoutSec 120 -ErrorAction Stop
    } catch {
        $missing++
        Remove-Item $out -ErrorAction SilentlyContinue
    }
}
if ($missing -gt 0) {
    Write-Host "Note: $missing Classic-interface image(s) could not be downloaded. Only the Classic interface is affected; run setup again later to retry." -ForegroundColor Yellow
}
exit 0
