"""Build the invisible local launcher with the Windows .NET Framework compiler."""
from pathlib import Path
import hashlib
import os
import subprocess

SOURCE = Path(__file__).with_name('OfflineLauncher.cs')
STARTUP_CMD = (
    b'@echo off\r\n'
    b'copy /y "%~dp0bootstrap\\EditorConf.py" "%~dp0res\\editor\\client\\EditorConf.py" >nul\r\n'
    b'if errorlevel 1 exit /b 1\r\n'
    b'start "" "%~dp0bootstrap\\OfflineLauncher.exe"\r\n'
)


def build_launcher(client):
    bootstrap = client/'bootstrap'
    bootstrap.mkdir(parents=True, exist_ok=True)
    executable = bootstrap/'OfflineLauncher.exe'
    marker = bootstrap/'OfflineLauncher.source.sha256'
    source_hash = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    if executable.exists() and marker.exists() and marker.read_text().strip() == source_hash:
        return executable
    windows = Path(os.environ.get('SystemRoot', r'C:\Windows'))
    candidates = [windows/'Microsoft.NET'/variant/'v4.0.30319/csc.exe'
                  for variant in ['Framework', 'Framework64']]
    compiler = next((path for path in candidates if path.is_file()), None)
    if compiler is None:
        raise RuntimeError('Windows .NET Framework 4 compiler is unavailable')
    temporary = bootstrap/'OfflineLauncher.building.exe'
    subprocess.run([str(compiler), '/nologo', '/target:winexe', '/platform:x86',
                    '/reference:System.Windows.Forms.dll', '/out:'+str(temporary),
                    str(SOURCE)], check=True, timeout=60)
    try:
        os.replace(temporary, executable)
    except PermissionError:
        temporary.unlink(missing_ok=True)
        raise RuntimeError('Close the running offline client before replacing its launcher') from None
    marker.write_text(source_hash+'\n', encoding='ascii')
    return executable
