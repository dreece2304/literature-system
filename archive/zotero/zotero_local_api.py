"""
Zotero Local API integration for detecting running Zotero instance.

NOTE: Zotero 7's connector API (port 23119) is designed for browser extensions
to SAVE items to Zotero, not for reading items. For reading items, use:
- Web API via pyzotero (ZoteroSync class) - recommended
- Direct SQLite database access (for offline-only scenarios)

This class provides:
- Detection of running Zotero instance
- Basic connectivity checking
- Library info retrieval
"""
import requests
from typing import Dict, List, Optional, Tuple
from loguru import logger

# Unused imports removed - not needed for connector API
# from literature_core.database import get_session
# from literature_core.models import Paper, Author, Collection, Tag


class ZoteroLocalAPI:
    """
    Handle Zotero local connector API (port 23119).

    IMPORTANT: The connector API is designed for browser extensions and has limited
    functionality for programmatic access. Use the web API (pyzotero) for full sync.

    This class is useful for:
    - Checking if Zotero is running
    - Getting library/collection info
    - Detecting available collections for saving
    """

    # Required headers for Zotero 7 connector API
    CONNECTOR_HEADERS = {
        'Content-Type': 'application/json',
        'X-Zotero-Connector-API-Version': '3',
        'User-Agent': 'Literature-Database/1.0'
    }

    def __init__(self, base_url: Optional[str] = None):
        """
        Initialize Zotero local API client.

        Args:
            base_url: Base URL for Zotero connector. If not provided:
                      1. Checks config for proxy_url (recommended for WSL2)
                      2. Falls back to auto-detection
        """
        self.base_url = self._determine_base_url(base_url)
        self.session = requests.Session()
        self.session.headers.update(self.CONNECTOR_HEADERS)

    def _get_proxy_url_from_config(self) -> Optional[str]:
        """Get proxy URL from config file if configured."""
        try:
            import yaml
            from pathlib import Path

            # Config is at data/config/settings.yml
            config_path = Path(__file__).parent.parent.parent / "data" / "config" / "settings.yml"
            if config_path.exists():
                with open(config_path, 'r') as f:
                    config = yaml.safe_load(f)
                    proxy_url = config.get('zotero', {}).get('proxy_url', '')
                    if proxy_url and proxy_url.strip():
                        return proxy_url.strip()
        except Exception as e:
            logger.debug(f"Could not read proxy_url from config: {e}")
        return None

    def _determine_base_url(self, provided_url: Optional[str]) -> str:
        """Determine the correct base URL for Zotero connector."""
        if provided_url:
            return provided_url.rstrip('/')

        # Check for proxy URL in config (recommended for WSL2)
        proxy_url = self._get_proxy_url_from_config()
        if proxy_url:
            logger.info(f"Using Zotero proxy URL from config: {proxy_url}")
            if self._test_connector_ping(proxy_url):
                logger.info(f"Zotero proxy available at: {proxy_url}")
                return proxy_url.rstrip('/')
            else:
                logger.warning(f"Zotero proxy not responding at: {proxy_url}")
                # Fall through to auto-detection

        # Standard Zotero connector port
        base_port = 23119
        candidate_urls = []

        # Check if we're in WSL2
        import os

        is_wsl2 = False
        try:
            if os.path.exists('/proc/version'):
                with open('/proc/version', 'r') as f:
                    proc_version = f.read().lower()
                    is_wsl2 = 'microsoft' in proc_version or 'wsl' in proc_version
        except Exception:
            pass

        if is_wsl2:
            networking_mode = self._detect_wsl2_networking_mode()
            logger.debug(f"Detected WSL2 environment with {networking_mode} networking")

            if networking_mode == "mirrored":
                # In mirrored networking mode, localhost routes directly to Windows
                # Note: localhostForwarding setting has NO effect in mirrored mode
                candidate_urls.append(f"http://localhost:{base_port}")
                candidate_urls.append(f"http://127.0.0.1:{base_port}")
            else:
                # NAT mode: try localhost first, then Windows host IP
                candidate_urls.append(f"http://localhost:{base_port}")
                candidate_urls.append(f"http://127.0.0.1:{base_port}")

                # Get Windows host IP from /etc/resolv.conf (DNS server = Windows host)
                windows_host_ip = self._get_windows_host_ip()
                if windows_host_ip:
                    candidate_urls.append(f"http://{windows_host_ip}:{base_port}")
                    logger.debug(f"Added Windows host IP as fallback: {windows_host_ip}")

        # Default fallback for non-WSL environments
        if not candidate_urls:
            candidate_urls = [f"http://localhost:{base_port}"]

        # Test each URL using the connector ping endpoint
        for url in candidate_urls:
            if self._test_connector_ping(url):
                logger.info(f"Zotero connector available at: {url}")
                return url
            else:
                logger.debug(f"Zotero not responding at: {url}")

        # Return first URL even if not working (for error handling)
        logger.warning(f"Zotero not detected, defaulting to: {candidate_urls[0]}")
        return candidate_urls[0]

    def _detect_wsl2_networking_mode(self) -> str:
        """
        Detect WSL2 networking mode (mirrored vs NAT).

        Mirrored mode (Windows 11 22H2+): WSL shares the host's network stack.
        NAT mode (default/older): WSL has its own virtual network with NAT.
        """
        try:
            # In mirrored mode, the default route doesn't go through a typical gateway IP
            # In NAT mode, there's usually a 172.x.x.x or similar gateway
            import subprocess
            result = subprocess.run(
                ['ip', 'route', 'show', 'default'],
                capture_output=True, text=True, timeout=5
            )
            route_output = result.stdout.strip()

            # Mirrored mode typically shows 'dev eth0' without a via gateway
            # or has a gateway that's the same as the host's actual gateway
            if route_output:
                # Check for typical NAT gateway patterns (172.x, 192.168.x)
                if 'via 172.' in route_output or 'via 192.168.' in route_output:
                    return "nat"

                # If there's no 'via' or it's a different pattern, likely mirrored
                if 'via' not in route_output:
                    return "mirrored"

            # Check /etc/resolv.conf for hints
            # In mirrored mode, nameserver is often a specific Windows DNS
            with open('/etc/resolv.conf', 'r') as f:
                resolv_content = f.read()
                # Typical mirrored mode has Windows DNS or 10.255.255.254
                if '10.255.255.254' in resolv_content:
                    return "mirrored"

        except Exception as e:
            logger.debug(f"Could not detect networking mode: {e}")

        return "unknown"

    def _get_windows_host_ip(self) -> Optional[str]:
        """
        Get Windows host IP address for WSL2 NAT mode.

        In NAT mode, the nameserver in /etc/resolv.conf is typically the Windows host.
        """
        try:
            with open('/etc/resolv.conf', 'r') as f:
                for line in f:
                    if line.strip().startswith('nameserver'):
                        parts = line.strip().split()
                        if len(parts) >= 2:
                            ip = parts[1]
                            # Validate it looks like an IP
                            if ip.count('.') == 3:
                                return ip
        except Exception as e:
            logger.debug(f"Could not read Windows host IP: {e}")

        return None

    def _test_connector_ping(self, url: str) -> bool:
        """Test if Zotero connector is responding at the given URL."""
        try:
            # The /connector/ping endpoint works with GET
            response = requests.get(f"{url}/connector/ping", timeout=2)
            return response.status_code == 200
        except Exception:
            return False

    def is_available(self) -> bool:
        """Check if Zotero is running and connector is accessible."""
        return self._test_connector_ping(self.base_url)

    def get_library_info(self) -> Optional[Dict]:
        """
        Get information about the Zotero library via connector API.

        Returns library name, ID, and available collections for saving.
        """
        try:
            # Use the getSelectedCollection endpoint which returns library info
            response = self.session.post(
                f"{self.base_url}/connector/getSelectedCollection",
                json={},
                timeout=10
            )
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Failed to get library info: {response.status_code}")
                return None
        except requests.RequestException as e:
            logger.error(f"Error getting library info: {e}")
            return None

    def get_zotero_version(self) -> Optional[str]:
        """Get the running Zotero version."""
        try:
            response = requests.get(f"{self.base_url}/connector/ping", timeout=2)
            if response.status_code == 200:
                return response.headers.get('X-Zotero-Version')
            return None
        except Exception:
            return None

    def get_available_collections(self) -> List[Dict]:
        """
        Get collections available for saving items to.

        Note: This returns collections for the connector to save TO,
        not a full list of items in each collection.
        """
        try:
            info = self.get_library_info()
            if info and 'targets' in info:
                return info['targets']
            return []
        except Exception as e:
            logger.error(f"Error getting collections: {e}")
            return []

    # =========================================================================
    # DEPRECATED METHODS - Use ZoteroSync with web API instead
    # =========================================================================
    # The connector API (port 23119) is designed for browser extensions to
    # SAVE items to Zotero. It does NOT support reading/listing items.
    # For syncing items FROM Zotero, use the ZoteroSync class with web API.
    # =========================================================================

    def sync_to_database(self) -> Tuple[int, int]:
        """
        DEPRECATED: The connector API cannot read items from Zotero.

        Use ZoteroSync.sync_from_api() instead, which uses the web API.

        Raises:
            NotImplementedError: Always raises - use web API instead
        """
        raise NotImplementedError(
            "The Zotero connector API (port 23119) cannot list items. "
            "Use ZoteroSync.sync_from_api() with the web API instead."
        )
