import subprocess
import re
import time
import json
import socket
import os
import subprocess
import sys
import time
import platform

from elevate import elevate

elevate()


def get_wifi_interfaces_info():
    """
    Retrieves information about all Wi-Fi interfaces on the system, including whether
    each interface supports Hosted Network or not.

    Returns:
    - A dictionary where keys are interface names (e.g., 'Wi-Fi 2') and values are booleans
      indicating whether the interface supports Hosted Network.
    """
    try:
        # Run netsh command to list Wi-Fi drivers and their properties
        result = subprocess.run(["netsh", "wlan", "show", "drivers"],
                                capture_output=True, text=True, check=True)
        output = result.stdout

        # Split output by "Interface name" entries which indicate separate adapters
        adapters = output.split("Interface name")

        # Dictionary to store interface names and whether they support Hosted Network
        interfaces_info = {}

        # Parse each adapter block to find Hosted Network support
        for adapter_info in adapters[1:]:  # Skip the first split part as it's before the first interface name
            # Extract the Interface name
            match_interface = re.search(r"^\s*:\s*(.+)$", adapter_info, re.MULTILINE)
            if match_interface:
                interface_name = match_interface.group(1).strip()

                # Check if this adapter supports Hosted Network
                supports_hosted_network = "Hosted network supported  : Yes" in adapter_info

                # Store the interface and its Hosted Network support status in the dictionary
                interfaces_info[interface_name] = supports_hosted_network

        print(interfaces_info)
        return interfaces_info

    except subprocess.CalledProcessError:
        print("Failed to retrieve network adapter information.")
        return {}


def enable_interfaces(interfaces_info):
    for iface, supports in interfaces_info.items():
        if supports is False:
            subprocess.run(
                ["netsh", "interface", "set", "interface", f'name="{iface}"', "admin=enabled"],
                check=True
            )
            print(f"Enabled interface: {iface}")


def disable_interfaces(interfaces_info):
    for iface, supports in interfaces_info.items():
        if supports is False:
            subprocess.run(
                ["netsh", "interface", "set", "interface", f'name="{iface}"', "admin=disabled"],
                check=True
            )
            print(f"Disabled interface: {iface}")


# def configure_wifi_hotspot(ssid: str, password: str):
#     """
#     Configures the Wi-Fi adapter on a Windows PC to act as an Access Point (Hotspot)
#     with the specified SSID and password, if the adapter supports Hosted Network.
#
#     Args:
#     - ssid (str): The SSID (network name) for the access point.
#     - password (str): The password for the access point (must be at least 8 characters).
#
#     Returns:
#     - None
#     """
#     if len(password) < 8:
#         print("Error: Password must be at least 8 characters.")
#         return
#
#         # Start the hosted network
#     subprocess.run(
#         ["netsh", "wlan", "stop", "hostednetwork"],
#         check=True
#     )
#
#     # Get information about all Wi-Fi interfaces
#     interfaces_info = get_wifi_interfaces_info()
#
#     if not interfaces_info:
#         print("No Wi-Fi interfaces found.")
#         return
#
#     # Find the first interface that supports Hosted Network
#     supported_interface = next((iface for iface, supports in interfaces_info.items() if supports), None)
#
#     if not supported_interface:
#         print("No Wi-Fi interfaces support Hosted Network.")
#         return
#
#     disable_interfaces(interfaces_info)
#
#     try:
#         # Set up the hosted network with the given SSID and password using the selected interface
#         subprocess.run(
#             ["netsh", "wlan", "set", "hostednetwork",
#              "mode=allow",
#              f"ssid={ssid}",
#              f"key={password}"],
#             check=True
#         )
#
#         # Start the hosted network
#         subprocess.run(
#             ["netsh", "wlan", "start", "hostednetwork"],
#             check=True
#         )
#
#         print(f"Access point '{ssid}' started successfully on adapter '{supported_interface}'.")
#
#     except subprocess.CalledProcessError as e:
#         print("Failed to configure or start the access point.")
#         print(f"Error: {e}")
#
#     finally:
#         # Re-enable all interfaces after setting up the hosted network
#         enable_interfaces(interfaces_info)
def configure_wifi_hotspot(ssid: str, password: str):
    """
    Configures the Wi-Fi adapter on a Windows PC to act as an Access Point (Hotspot)
    with the specified SSID and password, if the adapter supports Hosted Network.

    Args:
    - ssid (str): The SSID (network name) for the access point.
    - password (str): The password for the access point (must be at least 8 characters).

    Returns:
    - None
    """
    if len(password) < 8:
        print("Error: Password must be at least 8 characters.")
        print("ERROR")
        sys.exit(1)

    # Stop any running hosted network
    subprocess.run(["netsh", "wlan", "stop", "hostednetwork"], check=False)

    # Get information about all Wi-Fi interfaces
    interfaces_info = get_wifi_interfaces_info()

    if not interfaces_info:
        print("No Wi-Fi interfaces found.")
        print("ERROR")
        sys.exit(1)

    # Find the first interface that supports Hosted Network
    supported_interface = next((iface for iface, supports in interfaces_info.items() if supports), None)

    if not supported_interface:
        print("No Wi-Fi interfaces support Hosted Network.")
        print("ERROR")
        sys.exit(1)

    disable_interfaces(interfaces_info)

    try:
        # Set up the hosted network with the given SSID and password using the selected interface
        subprocess.run(
            ["netsh", "wlan", "set", "hostednetwork",
             "mode=allow",
             f"ssid={ssid}",
             f"key={password}"],
            check=True
        )

        # Start the hosted network
        subprocess.run(
            ["netsh", "wlan", "start", "hostednetwork"],
            check=True
        )

        print(f"Access point '{ssid}' started successfully on adapter '{supported_interface}'.")
        print("SUCCESS")
        sys.exit(0)

    except subprocess.CalledProcessError as e:
        print("Failed to configure or start the access point.")
        print("ERROR")
        sys.exit(1)

    finally:
        # Re-enable all interfaces after setting up the hosted network
        enable_interfaces(interfaces_info)


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: hosted_network_windows.py <ssid> <password>")
        print("ERROR")
        sys.exit(1)

    ssid = sys.argv[1]
    password = sys.argv[2]

    configure_wifi_hotspot(ssid, password)
