$ollamaExecutable = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
if (-not (Test-Path -LiteralPath $ollamaExecutable)) {
    throw "Existing Ollama installation was not found at $ollamaExecutable"
}

foreach ($model in @("gemma3:12b", "gemma3:4b", "bge-m3")) {
    & $ollamaExecutable pull $model
    if ($LASTEXITCODE -ne 0) {
        throw "Ollama failed to pull $model. Rerun this script to resume."
    }
}

& $ollamaExecutable list
