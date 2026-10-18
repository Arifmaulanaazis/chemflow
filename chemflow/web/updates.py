"""Pemeriksaan GitHub read-only; tidak pernah menarik atau memasang kode pada workspace aktif."""
from __future__ import annotations
import subprocess
import threading
import time
from pathlib import Path
import requests
from packaging.version import Version, InvalidVersion
from chemflow import __version__


def source_revision():
    root = Path(__file__).resolve().parents[2]
    if not (root / '.git').exists():
        return None
    try:
        remote = subprocess.check_output(['git', '-C', str(root), 'remote', 'get-url', 'origin'], stderr=subprocess.DEVNULL, timeout=3).decode().strip()
        if remote.rstrip('/').removesuffix('.git') not in {'https://github.com/Arifmaulanaazis/chemflow', 'git@github.com:Arifmaulanaazis/chemflow'}:
            return None
        return subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], stderr=subprocess.DEVNULL, timeout=3).decode().strip()
    except (OSError, subprocess.SubprocessError):
        return None


class UpdateChecker:
    def __init__(self):
        self.lock = threading.Lock()
        self.value = {'status': 'checking', 'current': __version__}
        self.checked = 0
        self.source = source_revision()

    def check(self, force=False):
        with self.lock:
            if not force and time.time() - self.checked < 6 * 3600:
                return dict(self.value)
            self.checked = time.time()
            result = {'status': 'unavailable', 'current': __version__, 'checked_at': self.checked,
                      'url': 'https://github.com/Arifmaulanaazis/chemflow/releases'}
            try:
                response = requests.get('https://api.github.com/repos/Arifmaulanaazis/chemflow/releases/latest', headers={'Accept': 'application/vnd.github+json'}, timeout=10)
                response.raise_for_status()
                release = response.json()
                latest = release['tag_name']
                newer = Version(latest.lstrip('v')) > Version(__version__)
                result.update(status='available' if newer else 'current', latest=latest)
            except (requests.RequestException, ValueError, KeyError, InvalidVersion):
                result['message'] = 'Release GitHub belum dapat diperiksa. Source code tidak diubah.'
            if self.source:
                result['source_local'] = self.source
                try:
                    response = requests.get('https://api.github.com/repos/Arifmaulanaazis/chemflow/commits/main', headers={'Accept': 'application/vnd.github+json'}, timeout=10)
                    response.raise_for_status()
                    remote = response.json()['sha']
                    if not isinstance(remote, str) or len(remote) != 40 or any(c not in '0123456789abcdef' for c in remote):
                        raise ValueError('Invalid commit')
                    result.update(source_remote=remote, source_status='current' if remote == self.source else 'different')
                except (requests.RequestException, ValueError, KeyError):
                    result['source_status'] = 'unavailable'
            self.value = result
            return dict(result)
