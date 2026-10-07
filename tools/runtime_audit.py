"""Audit bundled PE dependencies without exposing host-specific paths."""
from pathlib import Path
import hashlib
import json
import os
import pefile


def inventory(runtime):
    runtime=Path(runtime)
    files=sorted(p for p in runtime.rglob('*') if p.is_file() and p.relative_to(runtime).as_posix()!='licenses/runtime-inventory.json')
    return [{'path':p.relative_to(runtime).as_posix(),'bytes':p.stat().st_size,
             'sha256':hashlib.file_digest(p.open('rb'),'sha256').hexdigest()} for p in files]


def audit_dependencies(runtime):
    runtime=Path(runtime)
    binaries=[p for p in runtime.rglob('*') if p.suffix.lower() in {'.dll','.pyd','.exe'}]
    bundled={p.name.casefold() for p in binaries}
    system=Path(os.environ['WINDIR'])/'System32'
    system_names={p.name.casefold() for p in system.iterdir() if p.is_file()}
    missing=[]
    windows_icu=[]
    for path in binaries:
        pe=pefile.PE(str(path),fast_load=True)
        try:
            pe.parse_data_directories(directories=[1,13])
            for group in ('DIRECTORY_ENTRY_IMPORT','DIRECTORY_ENTRY_DELAY_IMPORT'):
                for entry in getattr(pe,group,[]):
                    name=entry.dll.decode('ascii').casefold()
                    if name in {'icuuc.dll','icuin.dll','icu.dll'}:
                        windows_icu.append({'consumer':path.relative_to(runtime).as_posix(),'dependency':name,
                                            'provided_by':'runtime' if name in bundled else 'Windows System32'})
                    if name in bundled or name in system_names or name.startswith(('api-ms-','ext-ms-')):
                        continue
                    missing.append({'consumer':path.relative_to(runtime).as_posix(),'dependency':name,
                                    'delay_load':group=='DIRECTORY_ENTRY_DELAY_IMPORT'})
        finally:
            pe.close()
    return {'binary_count':len(binaries),'unresolved':missing,'windows_icu':windows_icu}
