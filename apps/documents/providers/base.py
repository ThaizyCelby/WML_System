from abc import ABC, abstractmethod


class VirusScanner(ABC):
    @abstractmethod
    def scan(self, file_path: str) -> tuple[bool, str]:
        """
        Scan a file for viruses.
        Returns (is_clean: bool, details: str).
        """
        pass
