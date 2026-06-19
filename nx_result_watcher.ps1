$root = "C:\Users\HP\nx-mcp"
$marker = Join-Path $root "latest_nx_result.txt"
$router = "C:\Program Files\Siemens\NX2206\NXBIN\ugs_router.exe"
$last = ""

Write-Host "NX result watcher running. Watching: $marker"
Write-Host "Leave this window open while using Codex NX generation."

while ($true) {
    if (Test-Path -LiteralPath $marker) {
        $path = (Get-Content -LiteralPath $marker -Raw).Trim()
        if ($path -and $path -ne $last -and (Test-Path -LiteralPath $path)) {
            $last = $path
            Write-Host "Opening NX result: $path"
            Start-Process -FilePath $router -ArgumentList @("-ug", "-use_file_dir", $path)
        }
    }
    Start-Sleep -Seconds 1
}
