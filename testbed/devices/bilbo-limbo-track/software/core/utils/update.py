import os
import requests
import shutil


def download_github_folder(repo_url, folder_path, destination):
    """
    Downloads a specific folder from a GitHub repository using the GitHub API.

    :param repo_url: The URL of the GitHub repository (e.g., "https://github.com/user/repo").
    :param folder_path: The path to the folder within the repo to download (e.g., "software/robot").
    :param destination: The destination directory where the folder will be saved.
    """
    # Extract the repo owner and name from the URL
    repo_parts = repo_url.rstrip("/").split("/")
    if len(repo_parts) < 2:
        raise ValueError("Invalid repository URL format. Expected 'https://github.com/user/repo'.")

    owner, repo = repo_parts[-2], repo_parts[-1]

    # GitHub API URL for the repository
    api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{folder_path}"

    # Get the folder contents from the GitHub API
    response = requests.get(api_url)
    if response.status_code != 200:
        raise Exception(f"Failed to fetch folder contents: {response.json().get('message', response.text)}")

    # Create the destination folder
    destination = os.path.expanduser(destination)
    os.makedirs(destination, exist_ok=True)

    # Download files in the folder
    for item in response.json():
        if item["type"] == "file":
            # Download each file
            file_url = item["download_url"]
            file_name = item["name"]
            file_response = requests.get(file_url)

            if file_response.status_code == 200:
                file_path = os.path.join(destination, file_name)
                with open(file_path, "wb") as file:
                    file.write(file_response.content)
            else:
                raise Exception(f"Failed to download file {file_name}: {file_response.status_code}")

        elif item["type"] == "dir":
            # Recursively download subdirectories
            subfolder_path = os.path.join(folder_path, item["name"])
            subfolder_destination = os.path.join(destination, item["name"])
            download_github_folder(repo_url, subfolder_path, subfolder_destination)

    print(f"Folder downloaded successfully to {destination}")


#
# def download_folder_from_github(repo_url, folder_path, destination):
#     """
#     Downloads a specific folder from a GitHub repository using `git sparse-checkout`.
#
#     :param repo_url: The URL of the GitHub repository.
#     :param folder_path: The path to the folder within the repo to download (e.g., "software/robot").
#     :param destination: The destination directory where the folder will be saved.
#     """
#     # Create a temporary directory for the repository
#     temp_dir = os.path.join(os.path.expanduser("~"), "temp_repo")
#
#     # Ensure the temp directory doesn't already exist
#     if os.path.exists(temp_dir):
#         shutil.rmtree(temp_dir)
#
#     try:
#         # Clone the repo with sparse-checkout enabled
#         subprocess.run(
#             ["git", "clone", "--filter=blob:none", "--sparse", repo_url, temp_dir],
#             check=True,
#         )
#
#         # Change to the repo directory
#         os.chdir(temp_dir)
#
#         # Enable sparse-checkout for the specific folder
#         subprocess.run(["git", "sparse-checkout", "init", "--cone"], check=True)
#         subprocess.run(["git", "sparse-checkout", "set", folder_path.lstrip("/")], check=True)
#
#         # # Ensure the destination directory exists
#         # os.makedirs(destination, exist_ok=True)
#         #
#         # # Copy the downloaded folder to the destination
#         # source_path = os.path.join(temp_dir, folder_path.lstrip("/"))
#         # shutil.copytree(source_path, destination)
#
#     finally:
#         # Clean up temporary directory
#         ...
#         # if os.path.exists(temp_dir):
#         #     shutil.rmtree(temp_dir)



def update(url, target_path, file_to_copy, file_destination):
    """
    Downloads a folder from the given URL, copies it to a target path, copies a specific file,
    and cleans up the downloaded folder.

    :param url: URL of the GitHub repository (must end with .git).
    :param target_path: Target location to copy the folder.
    :param file_to_copy: Path to the specific file within the folder to copy.
    :param file_destination: Destination to copy the specific file to.
    """
    # Define a temporary location to download the folder
    temp_folder = os.path.join(os.path.expanduser("~"), "downloaded_folder")

    # Extract the folder path from the URL
    folder_path = input("Enter the path of the folder in the repository to download: ")

    try:
        print("Downloading folder...")
        download_folder_from_github(url, folder_path, temp_folder)

        # Remove the existing folder at the target path if it exists
        if os.path.exists(target_path):
            print(f"Removing existing folder at {target_path}...")
            shutil.rmtree(target_path)

        # Copy the folder to the target path
        print(f"Copying folder to {target_path}...")
        shutil.copytree(temp_folder, target_path)

        # Copy the specified file to the desired location
        source_file = os.path.join(target_path, file_to_copy)
        print(f"Copying file {source_file} to {file_destination}...")
        shutil.copy(source_file, file_destination)

    finally:
        # Clean up the downloaded folder
        if os.path.exists(temp_folder):
            print("Cleaning up temporary files...")
            shutil.rmtree(temp_folder)

# Example usage
# update(
#     url="https://github.com/user/repo.git",
#     target_path="/desired/target/path",
#     file_to_copy="relative/path/to/file.txt",
#     file_destination="/destination/path/file.txt"
# )
