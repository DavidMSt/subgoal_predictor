from core.utils.network.network import getInterfaceIP

if __name__ == "__main__":
    interface = "en0"  # Example interface name for MacOS, "eth0" or "wlan0" for Linux, or "Ethernet" for Windows
    ip_address = getInterfaceIP(interface)
    if ip_address:
        print(f"IP address for {interface}: {ip_address}")
    else:
        print(f"Could not find IP address for {interface}")