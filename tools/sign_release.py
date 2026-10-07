"""Optional Authenticode signing using an existing Windows certificate store entry."""
import os,re,subprocess
from pathlib import Path

def optional_sign(executable):
    tool=os.environ.get('XAG_SIGNTOOL','');certificate=os.environ.get('XAG_SIGN_CERT_SHA1','')
    if not tool and not certificate:return False
    if not Path(tool).is_file() or not re.fullmatch(r'[0-9a-fA-F]{40}',certificate):raise ValueError('Set a valid XAG_SIGNTOOL and XAG_SIGN_CERT_SHA1')
    command=[tool,'sign','/sha1',certificate,'/fd','SHA256']
    timestamp=os.environ.get('XAG_SIGN_TIMESTAMP_URL','')
    if timestamp:
        if not timestamp.startswith('https://'):raise ValueError('Timestamp server requires HTTPS')
        command += ['/tr',timestamp,'/td','SHA256']
    subprocess.run(command+[str(executable)],check=True)
    subprocess.run([tool,'verify','/pa',str(executable)],check=True)
    return True
