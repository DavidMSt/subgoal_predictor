"""
Reverse Proxy Client

Simple client for registering and unregistering routes with the reverse proxy server.

Usage:
    from core.utils.reverseproxy.client import ReverseProxyClient

    # Register a route
    client = ReverseProxyClient(proxy_port=8080)
    client.register("bilbolab.lan", 8400)

    # Or use the context manager for automatic cleanup
    with ReverseProxyClient(proxy_port=8080) as client:
        client.register("bilbolab.lan", 8400)
        # Route is automatically unregistered when exiting the context
"""

import requests
from typing import Optional
from core.utils.logging_utils import Logger

# Default port for the reverse proxy (use non-privileged port to avoid sudo)
DEFAULT_PROXY_PORT = 8080


class ReverseProxyClient:
    """Client for interacting with the reverse proxy server."""

    def __init__(self, proxy_host: str = "localhost", proxy_port: int = DEFAULT_PROXY_PORT):
        """
        Initialize the reverse proxy client.

        Args:
            proxy_host: Host where the reverse proxy is running (default: localhost)
            proxy_port: Port where the reverse proxy is running (default: 8080)
        """
        self.proxy_host = proxy_host
        self.proxy_port = proxy_port
        self.base_url = f"http://{proxy_host}:{proxy_port}"
        self.registered_routes: list[str] = []
        self.logger = Logger("ReverseProxyClient")

    def register(self, hostname: str, port: int) -> bool:
        """
        Register a route with the reverse proxy.

        Args:
            hostname: The hostname to route (e.g., "bilbolab.lan")
            port: The local port to forward to (e.g., 8400)

        Returns:
            True if registration was successful, False otherwise
        """
        try:
            response = requests.post(
                f"{self.base_url}/_register",
                json={"hostname": hostname, "port": port},
                timeout=5
            )
            if response.ok:
                self.logger.info(f"Registered route: {hostname} -> {port}")
                self.registered_routes.append(hostname)
                return True
            else:
                self.logger.error(f"Failed to register route {hostname}: {response.text}")
                return False
        except requests.exceptions.ConnectionError:
            self.logger.warning(f"Could not connect to reverse proxy at {self.base_url}. Is it running?")
            return False
        except Exception as e:
            self.logger.error(f"Error registering route {hostname}: {e}")
            return False

    def unregister(self, hostname: str) -> bool:
        """
        Unregister a route from the reverse proxy.

        Args:
            hostname: The hostname to unregister

        Returns:
            True if unregistration was successful, False otherwise
        """
        try:
            response = requests.post(
                f"{self.base_url}/_unregister",
                json={"hostname": hostname},
                timeout=5
            )
            if response.ok:
                self.logger.info(f"Unregistered route: {hostname}")
                if hostname in self.registered_routes:
                    self.registered_routes.remove(hostname)
                return True
            else:
                self.logger.error(f"Failed to unregister route {hostname}: {response.text}")
                return False
        except requests.exceptions.ConnectionError:
            self.logger.warning(f"Could not connect to reverse proxy at {self.base_url}")
            return False
        except Exception as e:
            self.logger.error(f"Error unregistering route {hostname}: {e}")
            return False

    def unregister_all(self) -> None:
        """Unregister all routes that were registered by this client."""
        for hostname in list(self.registered_routes):
            self.unregister(hostname)

    def list_routes(self) -> Optional[dict]:
        """
        List all routes currently registered with the reverse proxy.

        Returns:
            Dictionary of hostname -> port mappings, or None if request failed
        """
        try:
            response = requests.get(f"{self.base_url}/_routes", timeout=5)
            if response.ok:
                return response.json()
            else:
                self.logger.error(f"Failed to list routes: {response.text}")
                return None
        except requests.exceptions.ConnectionError:
            self.logger.warning(f"Could not connect to reverse proxy at {self.base_url}")
            return None
        except Exception as e:
            self.logger.error(f"Error listing routes: {e}")
            return None

    def is_available(self) -> bool:
        """Check if the reverse proxy is available."""
        try:
            response = requests.get(f"{self.base_url}/_routes", timeout=2)
            return response.ok
        except:
            return False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.unregister_all()
        return False
