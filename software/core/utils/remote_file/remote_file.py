from __future__ import annotations

import os
import fnmatch
import posixpath
import stat
from typing import Optional, Iterable
import paramiko
from core.utils.logging_utils import Logger


class RemoteFileClient:
    """
    Simple SFTP-based file transfer client for a Raspberry Pi (or any SSH host).

    Usage:
        from remote_file_client import RemoteFileClient

        with RemoteFileClient(
            host="192.168.0.42",
            username="pi",
            password="your_password",  # or key_filename="~/.ssh/id_rsa"
        ) as client:
            client.upload_file("local.txt", "/home/pi/remote.txt")
            client.download_file("/home/pi/log.txt", "log.txt")
    """

    def __init__(
            self,
            host: str,
            username: str,
            password: Optional[str] = None,
            *,
            port: int = 22,
            key_filename: Optional[str] = None,
            timeout: int = 10,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.key_filename = os.path.expanduser(key_filename) if key_filename else None
        self.timeout = timeout

        self._ssh: Optional[paramiko.SSHClient] = None
        self._sftp: Optional[paramiko.SFTPClient] = None

        self.logger = Logger(f"RFC {self.host}")

    # --- context manager -------------------------------------------------

    def __enter__(self) -> RemoteFileClient:
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    # --- connection handling ---------------------------------------------

    def connect(self) -> None:
        """Open SSH + SFTP connection to the remote host."""
        if self._ssh is not None:
            self.logger.info("Already connected, skipping connect().")
            return

        self.logger.info(
            f"Connecting to {self.username}@{self.host}:{self.port} "
            f"(key={self.key_filename is not None})..."
        )

        ssh = paramiko.SSHClient()
        ssh.load_system_host_keys()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            ssh.connect(
                hostname=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                key_filename=self.key_filename,
                timeout=self.timeout,
            )
            self._ssh = ssh
            self._sftp = ssh.open_sftp()
        except Exception as e:
            self.logger.error(f"Failed to connect to {self.host}: {e!r}")
            raise

    def close(self) -> None:
        """Close SFTP + SSH connections."""
        if self._sftp is not None:
            try:
                self._sftp.close()
            except Exception as e:
                self.logger.error(f"Error while closing SFTP connection: {e!r}")
            self._sftp = None

        if self._ssh is not None:
            try:
                self._ssh.close()
            except Exception as e:
                self.logger.error(f"Error while closing SSH connection: {e!r}")
            self._ssh = None

        self.logger.info("SSH + SFTP connection closed.")

    # --- internal helpers -----------------------------------------------

    @property
    def sftp(self) -> paramiko.SFTPClient:
        if self._sftp is None:
            msg = "Not connected. Call .connect() first or use 'with' context."
            self.logger.error(msg)
            raise RuntimeError(msg)
        return self._sftp

    def _mkdir_p_remote(self, remote_directory: str) -> None:
        """
        Recursively create a directory on the remote host (like mkdir -p).
        """
        remote_directory = posixpath.normpath(remote_directory)
        if remote_directory in ("", "/"):
            return

        dirs = []
        cur = remote_directory
        while cur not in ("", "/"):
            dirs.append(cur)
            cur, _ = posixpath.split(cur)

        for d in reversed(dirs):
            try:
                self.sftp.stat(d)
                # Directory already exists
            except IOError:
                self.logger.info(f"Creating remote directory: {d}")
                try:
                    self.sftp.mkdir(d)
                except Exception as e:
                    self.logger.error(f"Failed to create remote directory '{d}': {e!r}")
                    raise

    # --- basic operations -----------------------------------------------

    def upload_file(self, local_path: str, remote_path: str) -> None:
        """
        Upload a single file from macOS to the remote host.

        local_path:
            Path on your Mac.
        remote_path:
            POSIX-style path on the remote. If this is a directory (existing
            or passed with a trailing "/"), the file will be uploaded into
            that directory keeping its local basename.
        """
        local_path = os.path.expanduser(local_path)
        raw_remote_path = remote_path  # preserve original for trailing-slash check
        remote_path = posixpath.normpath(remote_path)

        self.logger.info(f"Preparing to upload file '{local_path}' -> '{remote_path}'")

        if not os.path.isfile(local_path):
            msg = f"Local file does not exist: {local_path}"
            self.logger.error(msg)
            raise FileNotFoundError(msg)

        # Determine whether remote_path should be treated as a directory
        is_remote_dir = False
        try:
            st = self.sftp.stat(remote_path)
            is_remote_dir = stat.S_ISDIR(st.st_mode)
        except IOError:
            # Path doesn't exist yet. If user gave a trailing slash, treat
            # it as a directory to be created.
            if raw_remote_path.endswith("/"):
                is_remote_dir = True

        if is_remote_dir:
            remote_dir = remote_path
            self._mkdir_p_remote(remote_dir)
            remote_file = posixpath.join(remote_dir, os.path.basename(local_path))
        else:
            # Treat as file path
            remote_dir = posixpath.dirname(remote_path)
            if remote_dir:
                self._mkdir_p_remote(remote_dir)
            remote_file = remote_path

        self.logger.info(f"Uploading file '{local_path}' to remote '{remote_file}'")
        try:
            self.sftp.put(local_path, remote_file)
            self.logger.info(f"Upload successful: '{local_path}' -> '{remote_file}'")
        except Exception as e:
            self.logger.error(
                f"Upload failed for '{local_path}' -> '{remote_file}': {e!r}"
            )
            raise

    def download_file(self, remote_path: str, local_path: str) -> str:
        """
        Download a single file from the remote host to macOS.

        remote_path:
            POSIX-style path on the remote host.
        local_path:
            Path on your Mac. If this is an existing directory or ends with
            a path separator ("/" on macOS), the file is downloaded into that
            directory keeping its remote basename.
        """
        local_path = os.path.expanduser(local_path)
        remote_path = posixpath.normpath(remote_path)

        self.logger.info(f"Preparing to download file '{remote_path}' -> '{local_path}'")

        # Determine if local_path is a directory or should be treated as one
        is_local_dir = False
        if os.path.isdir(local_path):
            is_local_dir = True
        elif local_path.endswith(os.sep):
            is_local_dir = True

        if is_local_dir:
            local_dir = local_path
            os.makedirs(local_dir, exist_ok=True)
            filename = posixpath.basename(remote_path)
            final_local_path = os.path.join(local_dir, filename)
        else:
            local_dir = os.path.dirname(local_path)
            if local_dir and not os.path.isdir(local_dir):
                self.logger.info(f"Creating local directory: {local_dir}")
                os.makedirs(local_dir, exist_ok=True)
            final_local_path = local_path

        self.logger.info(f"Downloading remote '{remote_path}' to local '{final_local_path}'")
        try:
            self.sftp.get(remote_path, final_local_path)
            self.logger.info(f"Download successful: '{remote_path}' -> '{final_local_path}'")
            return final_local_path
        except Exception as e:
            self.logger.error(
                f"Download failed for '{remote_path}' -> '{final_local_path}': {e!r}"
            )
            raise

    def list_remote(self, remote_path: str = ".", *, full_paths: bool = False) -> Iterable[str]:
        """
        List files in a remote directory.

        Parameters
        ----------
        remote_path:
            Directory to list on the remote host.
        full_paths:
            If False (default), returns only filenames.
            If True, returns full paths including `remote_path` prefix.
        """
        remote_path = posixpath.normpath(remote_path)
        try:
            entries = self.sftp.listdir_attr(remote_path)
        except Exception as e:
            self.logger.error(f"Failed to list remote directory '{remote_path}': {e!r}")
            raise

        if full_paths:
            paths = [posixpath.join(remote_path, f.filename) for f in entries]
        else:
            paths = [f.filename for f in entries]
        return paths

    # --- directory helpers ----------------------------------------------

    def upload_directory(
            self,
            local_dir: str,
            remote_dir: str,
            *,
            pattern: str = "*",
    ) -> None:
        """
        Recursively upload a directory from macOS to the remote host.

        pattern:
            Shell-style pattern to filter uploaded files (e.g. "*.txt").
        """
        local_dir = os.path.expanduser(local_dir)
        remote_dir = posixpath.normpath(remote_dir)

        self.logger.info(
            f"Uploading directory '{local_dir}' -> '{remote_dir}' "
            f"with pattern '{pattern}'"
        )

        if not os.path.isdir(local_dir):
            msg = f"Local directory does not exist: {local_dir}"
            self.logger.error(msg)
            raise NotADirectoryError(msg)

        for root, _, files in os.walk(local_dir):
            rel_root = os.path.relpath(root, local_dir)
            if rel_root == ".":
                rel_root = ""
            # build corresponding remote directory path
            remote_root = remote_dir if not rel_root else posixpath.join(
                remote_dir, rel_root.replace(os.sep, "/")
            )

            self._mkdir_p_remote(remote_root)

            for f in files:
                if not fnmatch.fnmatch(f, pattern):
                    continue
                local_file = os.path.join(root, f)
                remote_file = posixpath.join(remote_root, f)
                self.logger.info(f"Uploading file '{local_file}' -> '{remote_file}'")
                try:
                    self.sftp.put(local_file, remote_file)
                except Exception as e:
                    self.logger.error(
                        f"Upload failed for '{local_file}' -> '{remote_file}': {e!r}"
                    )
                    raise

        self.logger.info(
            f"Directory upload completed: '{local_dir}' -> '{remote_dir}'"
        )

    def download_directory(
            self,
            remote_dir: str,
            local_dir: str,
    ) -> None:
        """
        Recursively download a directory from the remote host to macOS.
        """
        remote_dir = posixpath.normpath(remote_dir)
        local_dir = os.path.expanduser(local_dir)
        self.logger.info(
            f"Downloading remote directory '{remote_dir}' -> '{local_dir}'"
        )
        os.makedirs(local_dir, exist_ok=True)

        def _walk_remote(path_remote: str, path_local: str) -> None:
            os.makedirs(path_local, exist_ok=True)
            try:
                entries = self.sftp.listdir_attr(path_remote)
            except Exception as e:
                self.logger.error(
                    f"Failed to list remote directory '{path_remote}': {e!r}"
                )
                raise

            for entry in entries:
                remote_path = posixpath.join(path_remote, entry.filename)
                local_path = os.path.join(path_local, entry.filename)
                if stat.S_ISDIR(entry.st_mode):
                    self.logger.info(
                        f"Descending into remote directory '{remote_path}'"
                    )
                    _walk_remote(remote_path, local_path)
                else:
                    self.logger.info(
                        f"Downloading file '{remote_path}' -> '{local_path}'"
                    )
                    try:
                        self.sftp.get(remote_path, local_path)
                    except Exception as e:
                        self.logger.error(
                            f"Download failed for '{remote_path}' -> '{local_path}': {e!r}"
                        )
                        raise

        _walk_remote(remote_dir, local_dir)
        self.logger.info(
            f"Directory download completed: '{remote_dir}' -> '{local_dir}'"
        )


if __name__ == '__main__':
    client = RemoteFileClient(host="bilbo2.lan", username="admin", password="beutlin")
    client.connect()
    experiments = client.list_remote('/home/admin/robot/experiments', full_paths=True)
    print("Experiments:", experiments)
    client.download_file(
        '/home/admin/robot/experiments/test_20251207_131914.json',
        local_path='/Users/lehmann/Desktop/test/'
    )
    client.close()
