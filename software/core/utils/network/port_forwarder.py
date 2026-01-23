"""
Simple HTTP/WebSocket Port Forwarder

Forwards all traffic from one port to another. Useful for making a service
on a high port (e.g., 8400) accessible on port 80 without modifying the service.

Usage:
    from core.utils.network.port_forwarder import PortForwarder

    # Forward port 80 -> 8400 (requires sudo for port 80)
    forwarder = PortForwarder(listen_port=80, target_port=8400)
    forwarder.start()

    # Now http://hostname:80/gui -> http://hostname:8400/gui

    forwarder.stop()
"""

import asyncio
import logging
import threading
import warnings
from typing import Optional

from aiohttp import web, ClientSession, WSMsgType, ClientConnectionError
from core.utils.logging_utils import Logger


class PortForwarder:
    """
    Forwards HTTP and WebSocket traffic from one port to another.
    Runs in a background thread.
    """

    def __init__(self, listen_port: int = 80, target_port: int = 8400, listen_host: str = "0.0.0.0", target_host: str = "127.0.0.1"):
        """
        Initialize the port forwarder.

        Args:
            listen_port: Port to listen on (e.g., 80)
            target_port: Port to forward to (e.g., 8400)
            listen_host: Host to bind to (default: all interfaces)
            target_host: Host to forward requests to (default: localhost)
        """
        self.listen_port = listen_port
        self.target_port = target_port
        self.listen_host = listen_host
        self.target_host = target_host

        self.logger = Logger("PortForwarder")
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._runner: Optional[web.AppRunner] = None
        self._stop_event: Optional[asyncio.Event] = None
        self._started = False
        self._stopping = False

    def start(self) -> bool:
        """
        Start the port forwarder in a background thread.

        Returns:
            True if started successfully, False otherwise

        Raises:
            PermissionError: If binding to a privileged port (< 1024) without root
        """
        if self._started:
            self.logger.warning("Port forwarder already running")
            return True

        def run_server():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            try:
                self._loop.run_until_complete(self._run())
            except PermissionError:
                self.logger.error(f"Permission denied binding to port {self.listen_port}. Run with sudo.")
                raise
            except Exception as e:
                if not self._stopping:
                    self.logger.error(f"Port forwarder error: {e}")
            finally:
                self._loop.close()

        self._thread = threading.Thread(target=run_server, daemon=True)
        self._thread.start()

        # Wait a bit for the server to start
        import time
        time.sleep(0.5)

        if self._thread.is_alive():
            self._started = True
            self.logger.info(f"Port forwarder started: {self.listen_host}:{self.listen_port} -> {self.target_host}:{self.target_port}")
            return True
        else:
            return False

    async def _run(self):
        """Internal async run method."""
        # Suppress aiohttp WebSocket protocol negotiation warnings
        logging.getLogger('aiohttp.web').setLevel(logging.ERROR)

        app = web.Application()
        app["websockets"] = set()

        # Handle all requests
        app.router.add_route("*", "/{path:.*}", self._handle_request)

        self._runner = web.AppRunner(app, shutdown_timeout=5)
        await self._runner.setup()
        site = web.TCPSite(self._runner, host=self.listen_host, port=self.listen_port)
        await site.start()

        self._stop_event = asyncio.Event()
        await self._stop_event.wait()

        # Clean up WebSockets
        for ws in set(app.get("websockets", [])):
            try:
                await ws.close()
            except:
                pass

        await self._runner.cleanup()

    async def _handle_request(self, request: web.Request) -> web.StreamResponse:
        """Handle incoming request and forward to target port."""
        target_url = f"http://{self.target_host}:{self.target_port}{request.rel_url}"

        # WebSocket proxy
        if request.headers.get("Upgrade", "").lower() == "websocket":
            return await self._proxy_websocket(request, target_url)

        # HTTP proxy
        return await self._proxy_http(request, target_url)

    async def _proxy_http(self, request: web.Request, target_url: str) -> web.Response:
        """Forward HTTP request to target."""
        if self._stopping:
            return web.Response(status=503, text="Service shutting down")

        try:
            async with ClientSession() as session:
                # Forward the request
                async with session.request(
                    method=request.method,
                    url=target_url,
                    headers={k: v for k, v in request.headers.items()
                             if k.lower() not in ('host', 'content-length')},
                    data=await request.read(),
                    allow_redirects=False,
                ) as resp:
                    # Build response
                    body = await resp.read()
                    headers = {k: v for k, v in resp.headers.items()
                               if k.lower() not in ('content-encoding', 'transfer-encoding', 'content-length')}
                    return web.Response(
                        status=resp.status,
                        body=body,
                        headers=headers,
                    )
        except ClientConnectionError as e:
            if not self._stopping:
                return web.Response(status=502, text=f"Cannot connect to backend: {e}")
            return web.Response(status=503, text="Service shutting down")
        except Exception as e:
            if not self._stopping:
                self.logger.error(f"HTTP proxy error: {e}")
            return web.Response(status=500, text="Internal Server Error")

    async def _proxy_websocket(self, request: web.Request, target_url: str) -> web.WebSocketResponse:
        """Forward WebSocket connection to target."""
        if self._stopping:
            ws_server = web.WebSocketResponse()
            await ws_server.prepare(request)
            await ws_server.close()
            return ws_server

        # Get requested protocols from client to forward them
        requested_protocols = request.headers.get('Sec-WebSocket-Protocol', '').split(', ')
        requested_protocols = [p.strip() for p in requested_protocols if p.strip()]

        # Suppress the protocol warning by accepting all requested protocols
        with warnings.catch_warnings():
            warnings.filterwarnings('ignore', message="Client protocols.*don't overlap")
            ws_server = web.WebSocketResponse(
                autoping=True,
                heartbeat=30,
                protocols=tuple(requested_protocols) if requested_protocols else None
            )
            await ws_server.prepare(request)

        request.app.setdefault("websockets", set()).add(ws_server)

        ws_url = target_url.replace("http://", "ws://")
        try:
            async with ClientSession() as session:
                async with session.ws_connect(
                    ws_url,
                    heartbeat=30,
                    protocols=tuple(requested_protocols) if requested_protocols else None
                ) as ws_client:
                    async def forward(src, dst):
                        async for msg in src:
                            if self._stopping:
                                break
                            if msg.type == WSMsgType.TEXT:
                                await dst.send_str(msg.data)
                            elif msg.type == WSMsgType.BINARY:
                                await dst.send_bytes(msg.data)
                            elif msg.type in (WSMsgType.CLOSE, WSMsgType.ERROR):
                                break

                    # Forward both directions
                    await asyncio.gather(
                        forward(ws_server, ws_client),
                        forward(ws_client, ws_server),
                        return_exceptions=True
                    )
        except Exception as e:
            if not self._stopping:
                self.logger.error(f"WebSocket proxy error: {e}")
        finally:
            request.app.get("websockets", set()).discard(ws_server)
            if not ws_server.closed:
                await ws_server.close()

        return ws_server

    def stop(self):
        """Stop the port forwarder."""
        if not self._started:
            return

        # Set stopping flag first to suppress error messages during shutdown
        self._stopping = True

        if self._loop and self._stop_event:
            self._loop.call_soon_threadsafe(self._stop_event.set)

        if self._thread:
            self._thread.join(timeout=5)

        self._started = False
        self.logger.info("Port forwarder stopped")

    @property
    def is_running(self) -> bool:
        return self._started


if __name__ == "__main__":
    import time

    # Test: forward port 8080 -> 8400 (use 8080 to avoid needing sudo)
    forwarder = PortForwarder(listen_port=8080, target_port=8400)
    forwarder.start()

    print(f"Forwarding localhost:8080 -> localhost:8400")
    print("Press Ctrl+C to stop...")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        forwarder.stop()
        print("Stopped")
