import clamd

from .base import VirusScanner


class ClamAVScanner(VirusScanner):
    """Production virus scanner using ClamAV daemon."""
    def __init__(self, host='localhost', port=3310):
        self.cd = clamd.ClamdNetworkSocket(host, port)

    def scan(self, file_path: str) -> tuple[bool, str]:
        result = self.cd.scan(file_path)
        if result:
            file, status = result[0]
            if status == 'OK':
                return True, 'Clean'
            else:
                return False, status
        return False, 'Scan failed'
