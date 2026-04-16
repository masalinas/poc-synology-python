import requests
import urllib3
from typing import Optional

# Disable SSL warnings for self-signed certs (common on local NAS)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ── Config ────────────────────────────────────────────────────────────────────

NAS_HOST     = "<YOUR_NAS_HOST>"   # or your DS225+ hostname
NAS_PORT     = 5001              # 5000 = HTTP, 5001 = HTTPS
NAS_USER     = "<YOUR_NAS_USERNAME>"
NAS_PASSWORD = "<YOUR_NAS_PASSWORD>"
BASE_URL     = f"https://{NAS_HOST}:{NAS_PORT}/webapi"


# ── Client ────────────────────────────────────────────────────────────────────

class SynologyDS225:
    """
    Python client for Synology DSM API (tested on DS225+, DSM 7.x).
    Covers: auth, system info, storage, file station, download station.
    """

    def __init__(self, host: str, port: int, username: str, password: str):
        self.base_url = f"https://{host}:{port}/webapi"
        self.username = username
        self.password = password
        self.sid: Optional[str] = None          # session token
        self.session = requests.Session()
        self.session.verify = False             # self-signed cert on local NAS

    # ── Auth ──────────────────────────────────────────────────────────────────

    def login(self) -> dict:
        """Authenticate and store session ID (sid)."""
        resp = self.session.get(self.base_url + "/auth.cgi", params={
            "api":      "SYNO.API.Auth",
            "version":  "3",
            "method":   "login",
            "account":  self.username,
            "passwd":   self.password,
            "session":  "FileStation",
            "format":   "sid",
        })
        data = resp.json()
        if not data.get("success"):
            raise ConnectionError(f"Login failed: {data.get('error')}")
        self.sid = data["data"]["sid"]
        print(f"Logged in — sid: {self.sid[:8]}...")
        return data

    def logout(self) -> dict:
        """Invalidate the current session."""
        resp = self.session.get(self.base_url + "/auth.cgi", params={
            "api":     "SYNO.API.Auth",
            "version": "1",
            "method":  "logout",
            "session": "FileStation",
            "_sid":    self.sid,
        })
        self.sid = None
        return resp.json()

    def _get(self, endpoint: str, api: str, version: int, method: str, **extra) -> dict:
        """Authenticated GET helper."""
        if not self.sid:
            raise RuntimeError("Not logged in. Call .login() first.")
        params = {"api": api, "version": version, "method": method, "_sid": self.sid, **extra}
        resp = self.session.get(self.base_url + endpoint, params=params)
        resp.raise_for_status()
        return resp.json()

    # ── System info ───────────────────────────────────────────────────────────

    def get_system_info(self) -> dict:
        """DSM version, model, uptime, serial number."""
        return self._get(
            "/entry.cgi",
            api="SYNO.DSM.Info",
            version=2,
            method="getinfo"
        )

    def get_utilization(self) -> dict:
        """CPU, memory, network, disk I/O usage."""
        return self._get(
            "/entry.cgi",
            api="SYNO.Core.System.Utilization",
            version=1,
            method="get"
        )

    def get_network_info(self) -> dict:
        """IP, MAC, link speed per interface (2.5GbE + 1GbE on DS225+)."""
        return self._get(
            "/entry.cgi",
            api="SYNO.Core.Network",
            version=1,
            method="list"
        )

    # ── Storage ───────────────────────────────────────────────────────────────

    def get_storage_info(self) -> dict:
        """Volume usage, RAID status, drive health."""
        return self._get(
            "/entry.cgi",
            api="SYNO.Storage.CGI.Storage",
            version=1,
            method="load_info"
        )

    def get_volumes(self) -> dict:
        """List volumes and their free/total space."""
        return self._get(
            "/entry.cgi",
            api="SYNO.Core.Storage.Volume",
            version=1,
            method="list",
            limit=50
        )

    def get_disks(self) -> dict:
        """Per-drive health, temperature, model (Bay 1 + Bay 2 on DS225+)."""
        return self._get(
            "/entry.cgi",
            api="SYNO.Core.Storage.Disk",
            version=1,
            method="list",
            limit=50
        )

    # ── File Station ──────────────────────────────────────────────────────────

    def list_shares(self) -> dict:
        """List all shared folders."""
        return self._get(
            "/entry.cgi",
            api="SYNO.FileStation.List",
            version=2,
            method="list_share",
            additional="real_path,owner,time,perm"
        )

    def list_folder(self, folder_path: str, offset: int = 0, limit: int = 100) -> dict:
        """
        List files inside a shared folder.
        folder_path: e.g. '/volume1/documents'
        """
        return self._get(
            "/entry.cgi",
            api="SYNO.FileStation.List",
            version=2,
            method="list",
            folder_path=folder_path,
            offset=offset,
            limit=limit,
            additional="real_path,size,time,perm"
        )

    def get_file_info(self, path: str) -> dict:
        """Get metadata for a specific file or folder."""
        return self._get(
            "/entry.cgi",
            api="SYNO.FileStation.Info",
            version=2,
            method="getinfo",
            path=path,
            additional="real_path,size,time,perm"
        )

    def search_files(self, folder_path: str, pattern: str) -> dict:
        """Search files by name pattern inside a folder."""
        return self._get(
            "/entry.cgi",
            api="SYNO.FileStation.Search",
            version=2,
            method="start",
            folder_path=folder_path,
            pattern=pattern
        )

    def create_folder(self, folder_path: str, name: str) -> dict:
        """Create a new folder at folder_path/name."""
        return self._get(
            "/entry.cgi",
            api="SYNO.FileStation.CreateFolder",
            version=2,
            method="create",
            folder_path=folder_path,
            name=name,
            force_parent=True
        )

    def delete_file(self, path: str) -> dict:
        """Delete a file or folder (starts async task, returns task_id)."""
        return self._get(
            "/entry.cgi",
            api="SYNO.FileStation.Delete",
            version=2,
            method="start",
            path=path,
            accurate_progress=True
        )

    # ── Download Station ──────────────────────────────────────────────────────

    def list_downloads(self) -> dict:
        """List all active/queued downloads."""
        return self._get(
            "/DownloadStation/task.cgi",
            api="SYNO.DownloadStation.Task",
            version=1,
            method="list",
            additional="detail,transfer"
        )

    def add_download(self, uri: str, destination: str = "/downloads") -> dict:
        """Add a URL to Download Station (HTTP, magnet, torrent URL)."""
        return self._get(
            "/DownloadStation/task.cgi",
            api="SYNO.DownloadStation.Task",
            version=1,
            method="create",
            uri=uri,
            destination=destination
        )

    # ── Context manager support ───────────────────────────────────────────────

    def __enter__(self):
        self.login()
        return self

    def __exit__(self, *args):
        self.logout()


# ── Pretty printer ────────────────────────────────────────────────────────────

def print_storage_summary(client: SynologyDS225) -> None:
    disks = client.get_disks()
    vols  = client.get_volumes()

    print("\n── Drives ──────────────────────────────────────")
    for disk in disks.get("data", {}).get("disks", []):
        temp   = disk.get("temp", "N/A")
        status = disk.get("status", "unknown")
        model  = disk.get("model", "unknown")
        slot   = disk.get("slot_number", "?")
        size   = disk.get("size_total", 0) / (1024**4)
        print(f"  Bay {slot}: {model:<30} {size:.1f} TB  {temp}°C  [{status}]")

    print("\n── Volumes ─────────────────────────────────────")
    for vol in vols.get("data", {}).get("volumes", []):
        total = vol.get("size", {}).get("total", 0) / (1024**3)
        free  = vol.get("size", {}).get("free",  0) / (1024**3)
        used  = total - free
        pct   = (used / total * 100) if total else 0
        name  = vol.get("volume_path", "unknown")
        print(f"  {name}: {used:.1f} / {total:.1f} GB used ({pct:.1f}%)")


# ── Usage ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    with SynologyDS225(NAS_HOST, NAS_PORT, NAS_USER, NAS_PASSWORD) as nas:

        # System
        info = nas.get_system_info()
        print(f"Model   : {info['data']['model']}")
        print(f"DSM     : {info['data']['version_string']}")
        print(f"Uptime  : {info['data']['uptime']} seconds")

        # Storage overview
        print_storage_summary(nas)

        # Browse files
        shares = nas.list_shares()
        for share in shares.get("data", {}).get("shares", []):
            print(f"\nShare: {share['path']}")
            files = nas.list_folder(share["path"])
            for f in files.get("data", {}).get("files", []):
                size = f.get("additional", {}).get("size", 0) / 1024
                print(f"  {f['name']:<40} {size:>8.1f} KB")