import hashlib
import os
import time

from .base import VirusScanner


class MockVirusScanner(VirusScanner):
    """Mock scanner for development/testing. Simulates scanning delay."""
    def scan(self, file_path: str) -> tuple[bool, str]:
        time.sleep(0.1)  # simulate scan
        # Deterministic "infection" for files containing 'EICAR' (test virus)
        with open(file_path, 'rb') as f:
            content = f.read()
        if b'EICAR' in content:
            return False, 'EICAR test signature detected'
        return True, 'Clean'
