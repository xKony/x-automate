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
        Attempts to connect to a specific VPN location using country/region code.
        Per user request, we prioritize 'location' (Country/Region) over specific servers
        due to reliability issues with specific server IDs.
        """
        # We ignore 'specific_server' as it is deemed unreliable.
        # specific_server: Optional[str] = vpn_preferences.get("specific_server")
        
        location: Optional[str] = vpn_preferences.get("location")
        fallback_locations: List[str] = vpn_preferences.get("fallback_locations", [])
        
        # Merge global fallbacks
        if config.VPN_FALLBACK_LIST:
             for loc in config.VPN_FALLBACK_LIST:
                 if loc not in fallback_locations:
                     fallback_locations.append(loc)

        # 1. Try Specific Location (Country/Group)
        # Command syntax for Windows: nordvpn -c -g "United States"
        if location:
            self.log.info(f"Attempting to connect to location: {location}")
            # We use -g for group/country
            if self._run_nordvpn_command(f'-c -g "{location}"'):
                self.log.info(f"Successfully connected to location: {location}")
                # Wait for adapter to settle
                time.sleep(5)
                return True
            self.log.warning(f"Failed to connect to location: {location}")

        # 2. Try Fallbacks
        for fallback in fallback_locations:
            self.log.info(f"Attempting fallback location: {fallback}")
            if self._run_nordvpn_command(f'-c -g "{fallback}"'):
                self.log.info(f"Successfully connected to fallback: {fallback}")
                # Wait for adapter to settle
                time.sleep(5)
                return True
            self.log.warning(f"Failed to connect to fallback: {fallback}")

        self.log.error("All specific VPN connection attempts failed.")
        return False

    def _run_nordvpn_command(self, argument_str: str) -> bool:
        """
        Executes a NordVPN CLI command.
        
        Args:
            argument_str (str): The arguments to pass to the executable (e.g. '-c -g "United States"')
        """
        # Get absolute path from the switcher settings (which auto-detected it)
        exe_path = self._switcher.settings.exe_path
        
        # Construct the full command: "Path\To\NordVPN.exe" -c -g "Region"
        # We assume argument_str handles its own internal quoting for values.
        cmd = f'"{exe_path}" {argument_str}'
        
        self.log.debug(f"Executing command: {cmd}")
        try:
            # shell=True is often needed on Windows for path resolution if not using list args
            # We use a single string command here.
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                check=False
            )
            
            if result.returncode == 0:
                # Heuristic check for success message or failure keywords
                output = result.stdout.lower()
                # NordVPN CLI sometimes prints errors to stdout
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
