"""Windows long-path I/O without changing displayed paths or library identities."""
import os
from pathlib import Path


def io_path(path):
    path = Path(path)
    if os.name != 'nt':
        return path
    name = os.path.abspath(path)
    if name.startswith('\\\\?\\'):
        return Path(name)
    if name.startswith('\\\\'):
        return Path('\\\\?\\UNC\\' + name[2:])
    return Path('\\\\?\\' + name)
