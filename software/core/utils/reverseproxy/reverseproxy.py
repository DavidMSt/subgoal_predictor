import asyncio
import os
import json
import signal
from typing import Dict

from aiohttp import (
    web,
    ClientSession,
    ClientConnectionError,
    WSMsgType,
    WSCloseCode,
)

# Static routes
STATIC_HOSTNAME_TO_PORT = {
    "example.local": 9001,
    "app2.local": 9002,
}

# File to persist dynamic routes
ROUTES_FILE = os.path.join(os.path.dirname(__file__), "routes.json")

# Dynamic routes in memory
DYNAMIC_HOSTNAME_TO_PORT: Dict[str, int] = {}
HOSTS_LOCK = asyncio.Lock()


def is_valid_hostname(hostname: str) -> bool:
    return bool(hostname and "." in hostname and " " not in hostname)


def is_valid_port(port: int) -> bool:
    return isinstance(port, int) and 1 <= port <= 65535


async def get_port_for_host(hostname: str) -> int:
    async with HOSTS_LOCK:
        return DYNAMIC_HOSTNAME_TO_PORT.get(hostname) or STATIC_HOSTNAME_TO_PORT.get(hostname)


async def load_routes_from_disk():
    if os.path.exists(ROUTES_FILE):
        try:
            with open(ROUTES_FILE, "r") as f:
                data = json.load(f)
            async with HOSTS_LOCK:
                DYNAMIC_HOSTNAME_TO_PORT.clear()
                DYNAMIC_HOSTNAME_TO_PORT.update(data)
            print(f"📅 Loaded {len(DYNAMIC_HOSTNAME_TO_PORT)} routes from disk")
        except Exception as e:
            print(f"⚠️ Failed to load routes from disk: {e}")


async def save_routes_to_disk():
    try:
        print("💾 Attempting to save routes...")
        with open(ROUTES_FILE, "w") as f:
            json.dump(DYNAMIC_HOSTNAME_TO_PORT, f, indent=2)
        print(f"💾 Saved {len(DYNAMIC_HOSTNAME_TO_PORT)} routes to disk")
    except Exception as e:
        print(f"⚠️ Failed to save routes: {e}")


# Graceful shutdown handler to close all live WebSockets
async def on_shutdown(app: web.Application):
    sockets = set(app.get("websockets", []))
    for ws in sockets:
        try:
            await ws.close(
                code=WSCloseCode.GOING_AWAY,
                message=b"Server shutting down",
            )
        except Exception:
            pass


async def handle_proxy(request: web.Request) -> web.StreamResponse:
    hostname = request.headers.get("Host", "")
    port = await get_port_for_host(hostname)

    if not port:
        return web.Response(status=502, text=f"Unknown host: {hostname}")

    # WebSocket proxy
    if request.headers.get("Upgrade", "").lower() == "websocket":
        ws_server = web.WebSocketResponse(autoping=True, heartbeat=30)
        await ws_server.prepare(request)

        # Track this WebSocket for shutdown
        request.app.setdefault("websockets", set()).add(ws_server)
        try:
            ws_url = f"ws://127.0.0.1:{port}{request.rel_url}"
            async with ClientSession() as session:
                async with session.ws_connect(ws_url, heartbeat=30) as ws_client:

                    async def ws_forward(src, dst):
                        async for msg in src:
                            if msg.type == WSMsgType.TEXT:
                                await dst.send_str(msg.data)
                            elif msg.type == WSMsgType.BINARY:
                                await dst.send_bytes(msg.data)
                            elif msg.type == WSMsgType.PING:
                                await dst.ping()
                            elif msg.type == WSMsgType.PONG:
                                await dst.pong()
                            elif msg.type == WSMsgType.CLOSE:
                                await dst.close()
                                return
                    # Run both directions, close when one finishes
                    tasks = [
                        asyncio.create_task(ws_forward(ws_server, ws_client)),
                        asyncio.create_task(ws_forward(ws_client, ws_server)),
                    ]
                    done, pending = await asyncio.wait(
                        tasks,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    for t in pending:
                        t.cancel()

                    # Ensure both ends close
                    await ws_client.close()
                    await ws_server.close()
        except ClientConnectionError as e:
            print(f"❌ Could not connect to backend WS at {ws_url}: {e}")
            await ws_server.close(code=1011, message=b"Backend WS connection failed")
        except Exception as e:
            print(f"⚠️ Unexpected error in WS proxy: {e}")
            await ws_server.close()
        finally:
            request.app.get("websockets", set()).discard(ws_server)

        return ws_server

    # Regular HTTP proxy
    target_url = f"http://127.0.0.1:{port}{request.rel_url}"
    try:
        async with ClientSession() as session:
            async with session.request(
                method=request.method,
                url=target_url,
                headers=request.headers,
                data=await request.read(),
            ) as resp:
                body = await resp.read()
                return web.Response(
                    status=resp.status,
                    body=body,
                    headers=resp.headers,
                )
    except ClientConnectionError as e:
        return web.Response(
            status=502,
            text=f"Could not connect to backend HTTP server at {target_url}: {e}",
        )
    except Exception as e:
        print(f"⚠️ Error handling HTTP proxy: {e}")
        return web.Response(status=500, text="Internal Server Error")


async def register_host(request: web.Request) -> web.Response:
    data = await request.json()
    hostname = data.get("hostname")
    port = data.get("port")

    if not is_valid_hostname(hostname) or not is_valid_port(port):
        return web.Response(status=400, text="Invalid hostname or port")

    if hostname in STATIC_HOSTNAME_TO_PORT:
        return web.Response(status=400, text="Cannot overwrite static route")

    async with HOSTS_LOCK:
        DYNAMIC_HOSTNAME_TO_PORT[hostname] = port
        print(f"✅ Registered: {hostname} -> {port}")
        await save_routes_to_disk()

    return web.Response(text=f"Registered {hostname} -> {port}")


async def unregister_host(request: web.Request) -> web.Response:
    data = await request.json()
    hostname = data.get("hostname")

    if not is_valid_hostname(hostname):
        return web.Response(status=400, text="Invalid hostname")

    async with HOSTS_LOCK:
        removed = DYNAMIC_HOSTNAME_TO_PORT.pop(hostname, None)
        if removed:
            print(f"❌ Unregistered: {hostname}")
            await save_routes_to_disk()
            return web.Response(text=f"Unregistered {hostname}")
        else:
            return web.Response(status=404, text="Hostname not found in dynamic routes")


async def list_routes(request: web.Request) -> web.Response:
    async with HOSTS_LOCK:
        combined = {**STATIC_HOSTNAME_TO_PORT, **DYNAMIC_HOSTNAME_TO_PORT}
        return web.json_response(combined)


async def static_routes(request: web.Request) -> web.Response:
    return web.json_response(STATIC_HOSTNAME_TO_PORT)


async def admin_ui(request):
    return web.Response(content_type="text/html", text="""
<!DOCTYPE html>
<html>
<head>
    <title>Reverse Proxy Admin</title>
    <style>
        body {
            font-family: sans-serif;
            padding: 2rem;
            background: #f9f9f9;
        }
        h1 {
            color: #333;
        }
        table {
            border-collapse: collapse;
            width: 100%;
            margin-top: 1rem;
        }
        th, td {
            border: 1px solid #ddd;
            padding: 0.5rem;
            text-align: left;
        }
        th {
            background-color: #eee;
        }
        input, button {
            margin: 0.5rem 0;
            padding: 0.5rem;
            font-size: 1rem;
        }
    </style>
</head>
<body>
    <h1>🛠 Reverse Proxy Admin</h1>
      <div>
        <h3>Add Route</h3>
        <input id="hostname" placeholder="Hostname (e.g. myapp.local)" />
        <input id="port" type="number" placeholder="Port (e.g. 8080)" />
        <button onclick="registerRoute()">Register</button>
        <div id="message" style="color: red; margin-top: 0.5rem;"></div>
    </div>

    <h3>Active Routes</h3>
    <table id="routesTable">
        <thead><tr><th>Hostname</th><th>Port</th><th>Type</th><th>Action</th></tr></thead>
        <tbody></tbody>
    </table>

    <script>
    let staticHosts = [];

    async function fetchStaticRoutes() {
        const res = await fetch('/_static_routes');
        staticHosts = Object.keys(await res.json());
    }

    async function fetchRoutes() {
        const res = await fetch('/_routes');
        const data = await res.json();
        const table = document.querySelector("#routesTable tbody");
        table.innerHTML = "";
        for (const [host, port] of Object.entries(data)) {
            const isStatic = staticHosts.includes(host);
            const row = document.createElement("tr");
            row.innerHTML = `
                <td>${host}</td>
                <td>${port}</td>
                <td>${isStatic ? "static" : "dynamic"}</td>
                <td>
                    ${isStatic ? "-" : `<button onclick="unregisterRoute('${host}')">Remove</button>`}
                </td>
            `;
            table.appendChild(row);
        }
    }

    function showMessage(text, isError = true) {
        const msg = document.getElementById("message");
        msg.style.color = isError ? "red" : "green";
        msg.textContent = text;
    }

    function clearMessage() {
        document.getElementById("message").textContent = "";
    }

    async function registerRoute() {
        clearMessage();
        const hostname = document.getElementById("hostname").value.trim();
        const port = parseInt(document.getElementById("port").value);
        if (!hostname || !port) {
            showMessage("Please enter a valid hostname and port.");
            return;
        }

        const res = await fetch('/_register', {
            method: "POST",
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ hostname, port })
        });

        if (res.ok) {
            showMessage("✅ Route registered.", false);
            await fetchRoutes();
        } else {
            const text = await res.text();
            showMessage(`❌ ${text}`);
        }
    }

    async function unregisterRoute(hostname) {
        clearMessage();
        if (!confirm(`Remove ${hostname}?`)) return;

        const res = await fetch('/_unregister', {
            method: "POST",
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ hostname })
        });

        if (res.ok) {
            showMessage("✅ Route removed.", false);
            await fetchRoutes();
        } else {
            const text = await res.text();
            showMessage(`❌ ${text}`);
        }
    }

    (async () => {
        await fetchStaticRoutes();
        await fetchRoutes();
    })();
</script>

</body>
</html>
""")


async def start_reverse_proxy(port: int = 80, host: str = "0.0.0.0") -> None:
    """Start the reverse proxy server (blocking async function)."""
    await load_routes_from_disk()

    app = web.Application()
    app["websockets"] = set()
    app.on_shutdown.append(on_shutdown)

    # Register routes
    app.router.add_route("*", "/{tail:.*}", handle_proxy)
    app.router.add_post("/_register", register_host)
    app.router.add_post("/_unregister", unregister_host)
    app.router.add_get("/_routes", list_routes)
    app.router.add_get("/_static_routes", static_routes)
    app.router.add_get('/admin', admin_ui)

    # Setup runner with shorter shutdown timeout
    runner = web.AppRunner(app, shutdown_timeout=5)
    await runner.setup()
    site = web.TCPSite(runner, host=host, port=port)
    await site.start()
    print(f"🔁 Reverse proxy listening on {host}:{port}")

    stop_event = asyncio.Event()

    def _shutdown():
        print("🛑 Gracefully shutting down...")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _shutdown)
        except NotImplementedError:
            # Signal handlers not supported on Windows
            pass

    await stop_event.wait()
    await runner.cleanup()
    print("✅ Shutdown complete.")


class ReverseProxyServer:
    """
    Reverse proxy server that can run in a background thread.

    Usage:
        server = ReverseProxyServer(port=8080)
        server.start()  # Starts in background thread
        # ... do other stuff ...
        server.stop()   # Graceful shutdown
    """

    def __init__(self, port: int = 80, host: str = "0.0.0.0"):
        self.port = port
        self.host = host
        self._thread = None
        self._loop = None
        self._runner = None
        self._stop_event = None
        self._started = False

    def start(self) -> bool:
        """Start the reverse proxy in a background thread. Returns True if started successfully."""
        if self._started:
            print("Reverse proxy already running")
            return True

        import threading

        def run_server():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            try:
                self._loop.run_until_complete(self._run())
            except Exception as e:
                print(f"Reverse proxy error: {e}")
            finally:
                self._loop.close()

        self._thread = threading.Thread(target=run_server, daemon=True)
        self._thread.start()

        # Wait a bit for the server to start
        import time
        time.sleep(0.5)
        self._started = True
        return True

    async def _run(self):
        """Internal async run method."""
        await load_routes_from_disk()

        app = web.Application()
        app["websockets"] = set()
        app.on_shutdown.append(on_shutdown)

        app.router.add_post("/_register", register_host)
        app.router.add_post("/_unregister", unregister_host)
        app.router.add_get("/_routes", list_routes)
        app.router.add_get("/_static_routes", static_routes)
        app.router.add_get('/admin', admin_ui)
        app.router.add_route("*", "/{tail:.*}", handle_proxy)

        self._runner = web.AppRunner(app, shutdown_timeout=5)
        await self._runner.setup()
        site = web.TCPSite(self._runner, host=self.host, port=self.port)
        await site.start()
        print(f"🔁 Reverse proxy listening on {self.host}:{self.port}")

        self._stop_event = asyncio.Event()
        await self._stop_event.wait()

        await self._runner.cleanup()
        print("✅ Reverse proxy shutdown complete.")

    def stop(self):
        """Stop the reverse proxy server."""
        if not self._started:
            return

        if self._loop and self._stop_event:
            self._loop.call_soon_threadsafe(self._stop_event.set)

        if self._thread:
            self._thread.join(timeout=5)

        self._started = False
        print("Reverse proxy stopped")

    @property
    def is_running(self) -> bool:
        return self._started


if __name__ == "__main__":
    try:
        asyncio.run(start_reverse_proxy())
    except PermissionError:
        print("❌ You need sudo to bind to port 80 on macOS/Linux")

"""
======================
💡 EXAMPLE USAGE (cURL)
======================

# Register a new route:
curl -X POST http://localhost/_register \
     -H "Content-Type: application/json" \
     -d '{"hostname": "myapp.local", "port": 8080}'

# Unregister a route:
curl -X POST http://localhost/_unregister \
     -H "Content-Type: application/json" \
     -d '{"hostname": "myapp.local"}'

# List all routes:
curl http://localhost/_routes

==========================
💡 EXAMPLE USAGE (Python)
==========================

import requests

# Register a new route
requests.post("http://localhost/_register", json={
    "hostname": "myapp.local",
    "port": 8080
})

# Unregister a route
requests.post("http://localhost/_unregister", json={
    "hostname": "myapp.local"
})

# List all routes
response = requests.get("http://localhost/_routes")
print(response.json())
"""
