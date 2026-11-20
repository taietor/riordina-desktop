# Riordina Desktop - installazione con un solo comando (incollalo in PowerShell):
#
#   irm https://raw.githubusercontent.com/taietor/riordina-desktop/main/installa.ps1 | iex
#
# Cosa fa:
#   1. cerca Python 3.9+ (con tkinter); se manca lo installa con winget, solo per l'utente
#   2. scarica l'ultima versione da GitHub in %LOCALAPPDATA%\Programs\Riordina Desktop
#   3. crea i collegamenti (Desktop e menu Start) e la voce in Impostazioni > App installate
#   4. apre il programma
# Niente amministratore. Funziona anche con Smart App Control attivo (Python e' firmato).
# Rilanciarlo aggiorna all'ultima versione. Impostazioni e registro restano in %LOCALAPPDATA%\RiordinaDesktop.
#
# Prove: $env:RIORDINA_TEST_DIR = cartella di prova (niente collegamenti/registro/avvio),
#        $env:RIORDINA_ZIP = zip locale al posto del download.

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$Nome = 'Riordina Desktop'
$Url = 'https://github.com/taietor/riordina-desktop/archive/refs/heads/main.zip'
$Dest = if ($env:RIORDINA_TEST_DIR) { $env:RIORDINA_TEST_DIR } else { Join-Path $env:LOCALAPPDATA "Programs\$Nome" }

function Test-PythonCommand([string]$Exe, [string[]]$Extra) {
    try {
        $out = & $Exe @Extra -c "import sys, tkinter; assert sys.version_info >= (3, 9); print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $out) {
            $path = "$($out | Select-Object -Last 1)".Trim()
            if (Test-Path $path) { return $path }
        }
    } catch { }
    return $null
}

function Find-Python {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $p = Test-PythonCommand 'py' @('-3'); if ($p) { return $p }
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        $p = Test-PythonCommand 'python' @(); if ($p) { return $p }
    }
    $found = Get-ChildItem "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe" -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending
    foreach ($f in $found) {
        $p = Test-PythonCommand $f.FullName @(); if ($p) { return $p }
    }
    return $null
}

function Write-Step([string]$Text) { Write-Host "  > $Text" -ForegroundColor Cyan }

Write-Host ''
Write-Host "  $Nome - installazione" -ForegroundColor Magenta
Write-Host ''

try {
    # 1. Python
    Write-Step 'Cerco Python...'
    $py = Find-Python
    if (-not $py) {
        if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
            throw 'Python non trovato e winget non disponibile. Installa Python da https://www.python.org/downloads/ e rilancia il comando.'
        }
        Write-Step 'Python non trovato: lo installo (solo la prima volta, 1-2 minuti)...'
        winget install --id Python.Python.3.13 -e --scope user --silent --accept-package-agreements --accept-source-agreements | Out-Host
        $py = Find-Python
        if (-not $py) { throw 'Python installato ma non trovato: chiudi PowerShell, riaprilo e rilancia il comando.' }
    }
    Write-Step "Python: $py"

    # 2. scarica ed estrae
    $tmp = Join-Path $env:TEMP ('riordina_' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $tmp | Out-Null
    $zip = Join-Path $tmp 'app.zip'
    if ($env:RIORDINA_ZIP) {
        Copy-Item $env:RIORDINA_ZIP $zip
    } else {
        Write-Step 'Scarico l''ultima versione da GitHub...'
        Invoke-WebRequest -Uri $Url -OutFile $zip -UseBasicParsing
    }
    Expand-Archive -Path $zip -DestinationPath $tmp -Force
    $src = Get-ChildItem $tmp -Directory | Select-Object -First 1
    if (-not $src -or -not (Test-Path (Join-Path $src.FullName 'riordina_desktop.pyw'))) { throw 'Archivio scaricato non valido.' }

    if (Test-Path $Dest) {
        Write-Step 'Aggiorno la versione installata...'
        try { Remove-Item -Recurse -Force $Dest } catch { throw "Chiudi $Nome e rilancia il comando (file in uso)." }
    }
    New-Item -ItemType Directory -Force -Path (Split-Path $Dest) | Out-Null
    Move-Item $src.FullName $Dest
    Remove-Item -Recurse -Force $tmp
    Write-Step "Installato in: $Dest"

    # 3. collegamenti e "App installate"
    & $py (Join-Path $Dest 'strumenti\collegamento.py') | ForEach-Object { Write-Step $_ }
    if ($LASTEXITCODE -ne 0) { throw 'Creazione dei collegamenti non riuscita.' }

    # 4. avvio
    if (-not $env:RIORDINA_TEST_DIR) {
        $pyw = Join-Path (Split-Path $py) 'pythonw.exe'
        if (-not (Test-Path $pyw)) { $pyw = $py }
        Start-Process -FilePath $pyw -ArgumentList "`"$(Join-Path $Dest 'riordina_desktop.pyw')`"" -WorkingDirectory $Dest
    }
    Write-Host ''
    Write-Host "  Fatto! $Nome e' sul Desktop e nel menu Start." -ForegroundColor Green
    Write-Host "  Per toglierlo: Impostazioni > App > App installate > $Nome > Disinstalla." -ForegroundColor DarkGray
    Write-Host ''
} catch {
    Write-Host ''
    Write-Host "  Errore: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host ''
}
