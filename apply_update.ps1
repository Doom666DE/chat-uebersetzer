$ErrorActionPreference = 'Stop'

function Replace-Executable($source, $target, $backup) {
    $deadline = [DateTime]::UtcNow.AddSeconds(15)
    do {
        try {
            [IO.File]::Replace($source, $target, $backup)
            return
        } catch {
            $cause = $_.Exception.GetBaseException()
            if ($cause -isnot [IO.IOException] -or ($cause.HResult -band 0xffff) -notin 32, 33 -or
                [DateTime]::UtcNow -ge $deadline) {
                throw
            }
            Start-Sleep -Milliseconds 250
        }
    } while ($true)
}

function Start-Translator($path, $arguments = '') {
    $start = [Diagnostics.ProcessStartInfo]::new($path, $arguments)
    $start.UseShellExecute = $false
    $start.WorkingDirectory = [IO.Path]::GetDirectoryName($path)
    return [Diagnostics.Process]::Start($start)
}

function Get-Sha256($path) {
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $file = [IO.File]::OpenRead($path)
        try {
            return [BitConverter]::ToString($sha.ComputeHash($file)).Replace('-', '')
        } finally {
            $file.Dispose()
        }
    } finally {
        $sha.Dispose()
    }
}

function Wait-ForTranslatorExit([int]$processId, $path) {
    $running = $null
    try {
        $running = [Diagnostics.Process]::GetProcessById($processId)
    } catch [ArgumentException] { return }
    try {
        if (-not $running.HasExited -and $running.Path -ieq $path -and -not $running.WaitForExit(15000)) {
            throw 'App did not close'
        }
    } finally {
        $running.Dispose()
    }
}

$ready = $null
$next = $null
$backup = $null
$replaced = $false
$validated = $false
$readySucceeded = $false
try {
    $target = [IO.Path]::GetFullPath($env:CHAT_UPDATE_TARGET)
    $source = [IO.Path]::GetFullPath($env:CHAT_UPDATE_SOURCE)
    $folder = [IO.Path]::GetDirectoryName($source)
    if ([IO.Path]::GetExtension($target) -ine '.exe' -or
        [IO.Path]::GetDirectoryName($target) -ine [IO.Path]::GetDirectoryName($folder) -or
        [IO.Path]::GetFileName($folder) -cnotmatch '^\.chat-update-[a-z0-9_]+\z' -or
        [IO.Path]::GetFileName($source) -cne 'Chat-Uebersetzer-win-x64.exe' -or
        $env:CHAT_UPDATE_HASH -cnotmatch '^[a-f0-9]{64}\z' -or
        $env:CHAT_UPDATE_EVENT -cnotmatch '^Local\\ChatUebersetzerUpdate-[a-f0-9]{32}\z') {
        throw 'Invalid update parameters'
    }
    $backup = Join-Path $folder 'previous.exe'
    $validated = $true
    if ((Get-Sha256 $source) -ine $env:CHAT_UPDATE_HASH) {
        throw 'Update checksum mismatch'
    }
    $created = $false
    $ready = [Threading.EventWaitHandle]::new($false, [Threading.EventResetMode]::ManualReset, $env:CHAT_UPDATE_EVENT, [ref]$created)
    if (-not $created) { throw 'Update event already exists' }
    Wait-ForTranslatorExit $env:CHAT_UPDATE_PID $target
    Wait-ForTranslatorExit $env:CHAT_UPDATE_BOOTLOADER $target
    Replace-Executable $source $target $backup
    $replaced = $true
    $next = Start-Translator $target ('--update-ready ' + $env:CHAT_UPDATE_EVENT)
    $deadline = [DateTime]::UtcNow.AddSeconds(45)
    while (-not $ready.WaitOne(300)) {
        if ($next.HasExited -or [DateTime]::UtcNow -ge $deadline) { throw 'New app did not start' }
    }
    $readySucceeded = $true
} catch {
    $restored = -not $replaced
    if ($replaced) {
        try {
            if ($next -and -not $next.HasExited) {
                $taskkill = Join-Path $env:SystemRoot 'System32\taskkill.exe'
                & $taskkill /PID $next.Id /T /F | Out-Null
                [void]$next.WaitForExit(5000)
            }
            Replace-Executable $backup $target (Join-Path $folder 'failed.exe')
            $restored = $true
        } catch {}
    }
    $de = $env:CHAT_UPDATE_LANGUAGE -eq 'de'
    if ($restored) {
        $message = if ($de) { 'Das Update ist fehlgeschlagen. Die vorherige Version ist weiterhin vorhanden.' }
                   else { 'The update failed. The previous version is still available.' }
        if ($validated -and [IO.File]::Exists($target)) {
            try { (Start-Translator $target).Dispose() } catch {}
        }
    } else {
        $message = if ($de) { "Das Update ist fehlgeschlagen. Die Sicherung liegt unter `n$backup" }
                   else { "The update failed. The backup is at `n$backup" }
    }
    Add-Type -AssemblyName System.Windows.Forms
    [void][Windows.Forms.MessageBox]::Show($message, 'Chat-Update', 'OK', 'Error')
    exit 1
} finally {
    if ($ready) { $ready.Dispose() }
    if ($next) { $next.Dispose() }
    if ($validated) {
        if ($readySucceeded) { try { [IO.File]::Delete($backup) } catch {} }
        $failed = Join-Path $folder 'failed.exe'
        try { [IO.File]::Delete($failed) } catch {}
        try { [IO.File]::Delete($source) } catch {}
        try { [IO.Directory]::Delete($folder) } catch {}
    }
}
