import time
import subprocess
import platform
from typing import Optional, Dict, List, Any
from utils.logger import get_logger
from nordvpn_switcher_pro import VpnSwitcher
from nordvpn_switcher_pro.exceptions import NordVpnConnectionError
import config


class VpnManager:
    """
    A utility class to manage NordVPN rotations with robust error handling,
    specific server targeting, and retry mechanisms.
    """

    def __init__(
        self,
        max_retries: int = 3,
        kill_wait_time: int = 5,
        reconnect_wait_time: int = 15,
    ):
        """
        Initialize the VpnManager.

        Args:
            max_retries (int): Number of times to retry after a critical error.
            kill_wait_time (int): Seconds to wait after killing the VPN process.
            reconnect_wait_time (int): Seconds to wait before attempting to rotate after a restart.
        """
        self.max_retries = max_retries
        self.kill_wait_time = kill_wait_time
        self.reconnect_wait_time = reconnect_wait_time
        self._switcher = VpnSwitcher()
        self.log = get_logger(__name__)

    def rotate_ip(self, vpn_preferences: Optional[Dict[str, Any]] = None) -> bool:
        """
        Attempts to rotate the VPN IP. If preferences are provided, tries those first.
        Otherwise falls back to random rotation logic.

        Args:
            vpn_preferences (Optional[Dict[str, Any]]): Dictionary containing specific VPN settings.
                Keys: 'specific_server', 'location', 'fallback_locations'.

        Returns:
            bool: True if rotation was successful, False otherwise.
        """
        # If specific preferences are given, try them first
        if vpn_preferences:
            if self.connect_to_specific_vpn(vpn_preferences):
                return True
            self.log.warning("Specific VPN preferences failed. Falling back to standard rotation.")

        # Standard rotation logic (existing behavior)
        # Initial session start attempt
        try:
            self._switcher.start_session()
        except Exception as e:
            self.log.warning(
                f"Initial session start flagged an issue: {e}. Proceeding to rotation logic."
            )

        attempt = 0
        while attempt <= self.max_retries:
            try:
                self.log.info(
                    f"Attempting to rotate VPN (Attempt {attempt + 1}/{self.max_retries + 1})..."
                )

                # Use default location from config if available and no specific prefs (or prefs failed)
                # But VpnSwitcher.rotate takes 'next_location' which interacts with random choice if None.
                # We can enforce default location if we want, but user didn't explicitly ask to change
                # base behavior for non-pref accounts. keeping it random or utilizing config default if desirable.
                # For now, let's pass config default if it exists and we're just doing a "general" rotation
                target_location = None
                if config.DEFAULT_VPN_LOCATION:
                     # This might restrict randomness if user wants pure random.
                     # But requested "fallback for another one, if reasonable setup in config".
                     # Let's treat config.DEFAULT_VPN_LOCATION as a "preferred random pool" if passed?
                     # Inspecting previous code: it called rotate() with no args.
                     # inspect_vpn output showed rotate(self, next_location=None).
                     pass

                self._switcher.rotate(next_location=target_location)

                self.log.info("Rotation complete. Connection secured.")
                return True

            except (NordVpnConnectionError, Exception) as e:
                self.log.error(f"Rotation failed: {e}")

                if attempt < self.max_retries:
                    self.log.info("Initiating recovery sequence...")
                    self._handle_critical_error()
                    attempt += 1
                else:
                    self.log.critical("Max retries reached. Unable to rotate VPN.")
                    return False

        return False

    def connect_to_specific_vpn(self, vpn_preferences: Dict[str, Any]) -> bool:
        """
        Attempts to connect to a specific VPN server or location based on preferences.

        Args:
            vpn_preferences (Dict[str, Any]): Dictionary with keys:
                - 'specific_server' (Optional[str]): e.g., "Poland #232"
                - 'location' (Optional[str]): e.g., "Poland"
                - 'fallback_locations' (Optional[List[str]]): e.g., ["Germany", "United States"]

        Returns:
            bool: True if connection successful, False otherwise.
        """
        specific_server: Optional[str] = vpn_preferences.get("specific_server")
        location: Optional[str] = vpn_preferences.get("location")
        fallback_locations: List[str] = vpn_preferences.get("fallback_locations", [])
        
        # Combine global fallbacks if local ones are exhausted or to augment them?
        # User stuck to "server list or if its unavailable fall back for another one".
        # We will append global fallbacks to the end.
        if config.VPN_FALLBACK_LIST:
             for loc in config.VPN_FALLBACK_LIST:
                 if loc not in fallback_locations:
                     fallback_locations.append(loc)

        # 1. Try Specific Server
        if specific_server:
            self.log.info(f"Attempting to connect to specific server: {specific_server}")
            if self._run_nordvpn_command(f"connect \"{specific_server}\""):
                self.log.info(f"Successfully connected to {specific_server}")
                return True
            self.log.warning(f"Failed to connect to specific server: {specific_server}")

        # 2. Try Specific Location (Country)
        if location:
            self.log.info(f"Attempting to connect to location: {location}")
            if self._run_nordvpn_command(f"connect \"{location}\""):
                self.log.info(f"Successfully connected to location: {location}")
                return True
            self.log.warning(f"Failed to connect to location: {location}")

        # 3. Try Fallbacks
        for fallback in fallback_locations:
            self.log.info(f"Attempting fallback location: {fallback}")
            if self._run_nordvpn_command(f"connect \"{fallback}\""):
                self.log.info(f"Successfully connected to fallback: {fallback}")
                return True
            self.log.warning(f"Failed to connect to fallback: {fallback}")

        self.log.error("All specific VPN connection attempts failed.")
        return False

    def _run_nordvpn_command(self, argument: str) -> bool:
        """
        Executes a NordVPN CLI command.

        Args:
            argument (str): The argument string for nordvpn command (e.g. 'connect "Poland #232"')

        Returns:
            bool: True if the command succeeded, False otherwise.
        """
        system = platform.system()
        # Different base commands based on OS?
        # Usually 'nordvpn' is in PATH on Linux/Mac.
        # On Windows, it's often 'nordvpn' if added to path, or specific executable.
        # Original code used 'nordvpn-switcher' library which handles some of this, 
        # but for specific server we need direct CLI or sophisticated wrapper use.
        # Assuming 'nordvpn' is available in CLI.
        
        # Get absolute path from the switcher settings (which auto-detected it)
        exe_path = self._switcher.settings.exe_path
        
        # Quote the executable path to handle spaces (e.g. "Program Files")
        cmd = f'"{exe_path}" {argument}'
        
        # On Windows, the CLI might be different or require full path if not in env.
        # But let's try standard 'nordvpn' first.
        
        self.log.debug(f"Executing command: {cmd}")
        try:
            # shell=True can be risky but needed for some path resolution on Windows if not configured perfectly.
            # Using subprocess.run
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                check=False # We check return code manually
            )
            
            if result.returncode == 0:
                # Some versions of nordvpn CLI return 0 even on failure messages, check stdout
                # Heuristic check
                output = result.stdout.lower()
                if "whoops" in output or "failure" in output or "error" in output:
                     self.log.warning(f"NordVPN command appeared to fail: {result.stdout.strip()}")
                     return False
                return True
            else:
                self.log.warning(f"NordVPN command failed with code {result.returncode}: {result.stderr.strip()}")
                return False

        except Exception as e:
            self.log.error(f"Exception executing NordVPN command: {e}")
            return False

    def _handle_critical_error(self) -> None:
        """
        Internal method to handle critical errors by killing the VPN process
        and waiting for the system to stabilize.
        """
        self._kill_vpn_process()

        self.log.info(f"Waiting {self.kill_wait_time}s for process termination...")
        time.sleep(self.kill_wait_time)

        try:
            self.log.info("Attempting to restart VPN session...")
            self._switcher.start_session()

            self.log.info(
                f"Session started. Waiting {self.reconnect_wait_time}s for network stability..."
            )
            time.sleep(self.reconnect_wait_time)
        except Exception as e:
            self.log.error(f"Error during recovery session start: {e}")

    def _kill_vpn_process(self) -> None:
        """
        Kills the NordVPN process. Detects OS to ensure safety.
        """
        system = platform.system()
        self.log.info(f"Killing NordVPN process on {system}...")

        if system == "Windows":
            # /F = Force, /IM = Image Name, /T = Tree (child processes)
            subprocess.run(
                "taskkill /F /IM nordvpn.exe /T",
                shell=True,
                stderr=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
            )
            # Run twice just to be sure, as per original logic
            subprocess.run(
                "taskkill /F /IM nordvpn.exe /T",
                shell=True,
                stderr=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
            )
        elif system == "Linux":
            subprocess.run("pkill -f nordvpn", shell=True)
        elif system == "Darwin":  # macOS
            subprocess.run("pkill -f NordVPN", shell=True)
        else:
            self.log.warning("Unknown Operating System. Skipping process kill.")
