param(
    [switch]$PullModels
)

$ollamaCommand = Get-Command ollama -ErrorAction SilentlyContinue
if (-not $ollamaCommand) {
    $knownPath = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
    if (Test-Path -LiteralPath $knownPath) {
        $ollamaExecutable = $knownPath
    } else {
        Write-Error "Ollama is not installed. Install it from https://ollama.com/download/windows, then rerun this script."
        exit 1
    }
} else {
    $ollamaExecutable = $ollamaCommand.Source
}

try {
    Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -TimeoutSec 2 | Out-Null
} catch {
    Start-Process -FilePath $ollamaExecutable -ArgumentList "serve" -WindowStyle Hidden
    $ready = $false
    foreach ($attempt in 1..20) {
        Start-Sleep -Milliseconds 500
        try {
            Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -TimeoutSec 2 | Out-Null
            $ready = $true
            break
        } catch {
            $ready = $false
        }
    }
    if (-not $ready) {
        Write-Error "Ollama was started but its API did not become ready."
        exit 1
    }
}

if ($PullModels) {
    foreach ($model in @("gemma3:12b", "gemma3:4b", "bge-m3")) {
        & $ollamaExecutable pull $model
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Failed to pull $model"
            exit $LASTEXITCODE
        }
    }
}

Write-Output "Ollama is reachable at http://localhost:11434"
& $ollamaExecutable list
