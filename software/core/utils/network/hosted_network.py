import os
import json
import sys
import time
import subprocess
import platform

def hostNetwork(ssid, password):
    """
    Runs the network configuration in an elevated subprocess.
    Dynamically resolves the path to 'hosted_network_windows.py'.
    Raises NotImplementedError for unsupported operating systems.
    """
    # Check the operating system
    current_os = platform.system()
    if current_os != "Windows":
        raise NotImplementedError(f"Hosting a network is not implemented for {current_os}.")

    stopAllHostedNetworks()

    # Get the directory of the current script
    current_dir = os.path.dirname(os.path.abspath(__file__))

    # Resolve the full path to the 'hosted_network_windows.py' script
    script_path = os.path.join(current_dir, "hosted_network_windows.py")

    # Check if the script exists
    if not os.path.exists(script_path):
        print(f"Script not found: {script_path}")
        return False

    try:
        # Run the script with the current Python executable
        result = subprocess.run(
            [sys.executable, script_path, ssid, password],
            capture_output=True, text=True
        )

        # Check the exit code
        if result.returncode == 0:
            print("Network hosted successfully.")
            return True
        else:
            print("Failed to host the network.")
            return False

    except FileNotFoundError as e:
        print(f"File not found: {e}")
        return False
    except subprocess.CalledProcessError as e:
        print(f"Failed to run elevated network configuration: {e}")
        return False

def write_network_info(interface_name, ip_address):
    """
    Writes the network information (timestamp, interface name, and IP address) to a JSON file.
    Args:
    - interface_name (str): The name of the network interface.
    - ip_address (str): The IP address assigned to the interface.
    Returns:
    - None
    """
    data = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "interface_name": interface_name,
        "ip_address": ip_address
    }
    with open("network.json", "w") as json_file:
        json.dump(data, json_file, indent=4)
    print(f"Network information saved to 'network.json': {data}")


def checkAndPrintNetworkInfo():
    """
    Checks if the network.json file is valid and prints its information.
    """
    json_file_path = "network.json"

    if not os.path.exists(json_file_path):
        print("Network configuration file not found.")
        return

    try:
        # Read the JSON file
        with open(json_file_path, "r") as file:
            data = json.load(file)

        # Extract and validate the timestamp
        timestamp = data.get("timestamp")
        interface_name = data.get("interface_name")
        ip_address = data.get("ip_address")

        if not timestamp or not interface_name or not ip_address:
            print("Invalid data in network configuration file.")
            return

        # Convert the timestamp to a time object
        file_time = time.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
        file_time_epoch = time.mktime(file_time)
        current_time_epoch = time.time()

        # Check if the timestamp is within the last 10 seconds
        if current_time_epoch - file_time_epoch <= 10:
            print(f"Interface: {interface_name}")
            print(f"IP Address: {ip_address}")
        else:
            print("The network information is outdated (more than 10 seconds old).")

    except (json.JSONDecodeError, KeyError, ValueError) as e:
        print(f"Error reading network configuration: {e}")
    finally:
        # Delete the JSON file
        if os.path.exists(json_file_path):
            os.remove(json_file_path)
            print(f"Deleted {json_file_path}.")
        else:
            print(f"{json_file_path} not found for deletion.")


def stopAllHostedNetworks():
    subprocess.run(
        ["netsh", "wlan", "stop", "hostednetwork"],
        check=True
    )


if __name__ == "__main__":
    # stopAllHostedNetworks()
    success = hostNetwork("bilbo_net", "bilbobeutlin")

    print(success)
    time.sleep(4)
