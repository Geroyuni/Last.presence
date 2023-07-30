from datetime import datetime
import threading
import traceback
import logging
import ctypes
import time
import json
import os

from PIL import Image
import pypresence
import winshell
import pystray
import pylast


logging.basicConfig(
    filename="log.txt", encoding="utf-8", level=logging.INFO,
    format='%(asctime)s %(levelname)-8s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S')

for l in logging.root.manager.loggerDict:
    logging.getLogger(l).setLevel(logging.WARN)

class LastPresence:
    """Takes your current song in Last.fm, puts it in your Discord profile."""
    def __init__(self):
        with open("settings.json") as f:
            self.settings = json.load(f)

        self.confirm_settings_setup()

        self.network = pylast.LastFMNetwork(
            api_key=self.settings["lastfm_api_key"],
            api_secret=self.settings["lastfm_api_secret"])
        self.user = self.network.get_user(self.settings["username"])
        self.rpc = pypresence.Presence(self.settings["discord_rpc_presence"])

        self.shortcut_startup_path = os.path.join(
            os.getenv("appdata"),
            "Microsoft\\Windows\\Start Menu\\Programs\\Startup",
            "Last.presence.lnk")

        self.last_track = None
        self.last_track_timestamp = None
        self.tray_icon = None

        self.rpc.connect()

    def confirm_settings_setup(self):
        """Guide people through setting up the script properly."""
        if "Put your Last.fm username here" in self.settings["username"]:
            message = (
                u"You must add your Last.fm username, API key and secret "
                u"to 'settings.json' before using this script.")

            ctypes.windll.user32.MessageBoxW(0, message, u"Last.presence", 0)
            quit()

    def run_tray_icon(self):
        """Create and run tray icon that contains settings."""

        def toggle_setting(setting_name, tray_item):
            """Helper function to alter and save a setting tweak."""
            self.settings[setting_name] = not tray_item.checked

            with open("settings.json", "w") as f:
                json.dump(self.settings, f, indent=4)

        def toggle_rpc(_, item):
            """Allows or prevents RPC from updating while script is running."""
            toggle_setting("rpc_enabled", item)

            if self.settings["rpc_enabled"]:
                self.update_presence(force_update=True)
            else:
                self.rpc.clear()

        def toggle_startup(_, item):
            """Creates or removes startup shortcut for the script."""
            if os.path.exists(self.shortcut_startup_path):
                os.remove(self.shortcut_startup_path)
                logging.info(f"Removed {self.shortcut_startup_path} shortcut")
                return

            file_path = os.path.abspath(__file__)

            with winshell.shortcut(self.shortcut_startup_path) as link:
                link.path = file_path
                link.working_directory = os.path.dirname(file_path)

            logging.info(f"Created shortcut at {self.shortcut_startup_path}")

        def toggle_button(_, item):
            toggle_setting("profile_button_enabled", item)
            self.update_presence(force_update=True)

        def open_log(_, item):
            os.startfile("log.txt")

        rpc_check = lambda _: self.settings["rpc_enabled"]
        button_check = lambda _: self.settings["profile_button_enabled"]
        startup_check = lambda _: os.path.exists(self.shortcut_startup_path)

        menu = pystray.Menu(
            pystray.MenuItem(f"Connected as {lastpresence.user.name}", None),
            pystray.MenuItem("Enable Last.presence", toggle_rpc, rpc_check),
            pystray.MenuItem("Run at startup", toggle_startup, startup_check),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Show profile button", toggle_button, button_check),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Open log file", open_log),
            pystray.MenuItem('Quit', self.close))

        name = "Last.presence"
        icon = Image.open("assets/icon.ico")

        self.tray_icon = pystray.Icon(name, icon, name, menu)
        self.tray_icon.run()

    def update_presence(self, force_update=False):
        """Look for current playing track and update presence accordingly."""
        if not self.settings["rpc_enabled"]:
            return

        track = self.user.get_now_playing()

        if track != self.last_track:
            self.last_track = track
            self.last_track_timestamp = datetime.now().timestamp()
        elif not force_update:
            return

        self.last_track = track

        if track == None:
            self.rpc.clear()
            logging.info("No song detected, cleared rich presence.")
            return

        album = track.get_album()
        cover = track.get_cover_image()
        duration = track.get_duration()

        details = track.title.ljust(2)
        state = track.artist.name.ljust(2)
        large_text = None
        end = None
        button = None

        if album:
            state = f"{track.artist.name} | {album.title}"
            large_text = f"Album: {album.title}"

        if duration:
            end = self.last_track_timestamp + (duration / 1000)

        if not cover or "2a96cbd8b46e442fc41c2b86b821562f" in cover:
            cover = "https://files.catbox.moe/ai8jco.png"

        if self.settings["profile_button_enabled"]:
            button = [{
                "label": "View Last.fm profile",
                "url": f"https://last.fm/user/{self.user.name}"}]

        self.rpc.update(
            details=details, state=state, end=end, large_image=cover,
            large_text=large_text, buttons=button)

        logging.info(f"Updated: {track.artist.name} - {track.title}")

    def presence_update_loop(self):
        """Main loop responsible for updating presence."""
        while True:
            try:
                lastpresence.update_presence()
            except pypresence.exceptions.PipeClosed:
                logging.info("Re-connecting RPC due to pipe closing")
                self.rpc.connect()
                lastpresence.update_presence(force_update=True)
            except (pylast.PyLastError, pypresence.PyPresenceException):
                logging.warn(traceback.format_exc())

            time.sleep(10)

    def close(self):
        """Clean things up and close cleanly."""
        self.tray_icon.stop()
        self.rpc.clear()
        self.rpc.close()
        logging.info("Closed RPC and tray icon cleanly")


if __name__ == "__main__":
    lastpresence = LastPresence()
    logging.info(f"Connected as {lastpresence.user.name}")

    thread = threading.Thread(target=lastpresence.presence_update_loop)
    thread.daemon = True
    thread.start()

    lastpresence.run_tray_icon()
