"""
mDNS Service Advertiser

Advertises a hostname on the local network using mDNS (Multicast DNS).
This allows other devices on the network to access the service via a .local hostname
without needing DNS configuration.

Usage:
    from core.utils.mdns.mdns_advertiser import MDNSAdvertiser

    # Advertise bilbolab.local pointing to port 8400
    advertiser = MDNSAdvertiser(hostname="bilbolab", port=8400)
    advertiser.start()

    # Now other devices can access http://bilbolab.local:8400/gui

    # When done:
    advertiser.stop()
"""

import socket
from typing import Optional
from zeroconf import Zeroconf, ServiceInfo
from core.utils.logging_utils import Logger
from core.utils.network.network import getHostIP


class MDNSAdvertiser:
    """
    Advertises a service on the local network via mDNS.

    This makes the service discoverable via a .local hostname.
    For example, advertising "bilbolab" on port 8400 allows access via:
    http://bilbolab.local:8400/
    """

    def __init__(self,
                 hostname: str = "bilbolab",
                 port: int = 8400,
                 service_type: str = "_http._tcp.local.",
                 service_name: Optional[str] = None):
        """
        Initialize the mDNS advertiser.

        Args:
            hostname: The hostname to advertise (without .local suffix)
            port: The port the service is running on
            service_type: The mDNS service type (default: HTTP)
            service_name: Optional service name for discovery (defaults to hostname)
        """
        self.hostname = hostname
        self.port = port
        self.service_type = service_type
        self.service_name = service_name or f"{hostname}.{service_type}"

        self.logger = Logger("mDNS")
        self.zeroconf: Optional[Zeroconf] = None
        self.service_info: Optional[ServiceInfo] = None
        self._started = False

    def start(self) -> bool:
        """
        Start advertising the service on the network.

        Returns:
            True if started successfully, False otherwise
        """
        if self._started:
            self.logger.warning("mDNS advertiser already running")
            return True

        try:
            # Get the local IP address
            ip = getHostIP()
            if ip is None:
                self.logger.error("Could not determine local IP address")
                return False

            self.logger.info(f"Advertising {self.hostname}.local -> {ip}:{self.port}")

            # Create the service info
            self.service_info = ServiceInfo(
                type_=self.service_type,
                name=self.service_name,
                port=self.port,
                properties={
                    'path': '/gui',
                    'app_path': '/app',
                },
                server=f"{self.hostname}.local.",
                addresses=[socket.inet_aton(ip)],
            )

            # Start zeroconf and register the service
            self.zeroconf = Zeroconf()
            self.zeroconf.register_service(self.service_info)

            self._started = True
            self.logger.info(f"mDNS service registered: http://{self.hostname}.local:{self.port}/")
            return True

        except Exception as e:
            self.logger.error(f"Failed to start mDNS advertiser: {e}")
            return False

    def stop(self):
        """Stop advertising the service."""
        if not self._started:
            return

        try:
            if self.zeroconf and self.service_info:
                self.zeroconf.unregister_service(self.service_info)
                self.zeroconf.close()
                self.logger.info("mDNS service unregistered")
        except Exception as e:
            self.logger.error(f"Error stopping mDNS advertiser: {e}")
        finally:
            self.zeroconf = None
            self.service_info = None
            self._started = False

    @property
    def is_running(self) -> bool:
        return self._started

    @property
    def url(self) -> str:
        """Get the URL for accessing the service."""
        return f"http://{self.hostname}.local:{self.port}/"

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        return False


if __name__ == "__main__":
    import time

    # Test the advertiser
    advertiser = MDNSAdvertiser(hostname="bilbolab-test", port=8400)
    advertiser.start()

    print(f"Service advertised at: {advertiser.url}")
    print("Press Ctrl+C to stop...")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        advertiser.stop()
        print("Stopped")
