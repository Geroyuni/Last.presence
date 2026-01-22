from logging.handlers import RotatingFileHandler
from datetime import datetime
import subprocess
import threading
import traceback
import logging
import ctypes
import time
import json
import sys
import os

from PIL import Image
from pystray import Menu, MenuItem
import flet as ft
import webbrowser
import pypresence
import winshell
import pystray
import pylast


ctypes.windll.shcore.SetProcessDpiAwareness(True)  # Avoids blurry context menu

rotating_file_handler = RotatingFileHandler(
    filename="log.txt", mode="a", maxBytes=5 * 1024 * 1024,
    backupCount=1, encoding="utf-8", delay=0)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S", handlers=[rotating_file_handler])

for logger in logging.root.manager.loggerDict:
    logging.getLogger(logger).setLevel(logging.WARNING)


class LastPresence:
    """Takes your current song in Last.fm, puts it in your Discord profile."""
    def __init__(self):
        self.app_names = [
            "Use artist name", "Last.fm", "Music", "YT Music",
            "YouTube Music", "Apple Music", "Tidal"]
        self.shortcut_startup_path = os.path.join(
            os.getenv("appdata"),
            "Microsoft\\Windows\\Start Menu\\Programs\\Startup",
            "Last.presence.lnk")
        self.last_track = None
        self.last_track_timestamp = None
        self.tray_icon = None
        self.build_version = "2026-01-21"

        self.load_and_check_settings()
        self.setup_lastfm()
        self.setup_rpc()

    def load_and_check_settings(self):
        """Load settings.json and warn user if settings are default."""
        default_settings = {
            "username": "",
            "lastfm_api_key": "",
            "app_name": "Use artist name",
            "rpc_enabled": True}

        try:
            with open("settings.json") as f:
                self.settings = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.settings = default_settings

        # For people upgrading from old versions
        if self.settings.get("discord_rpc_presence"):
            self.old_app_ids = {
                "1131823801454297190": "Last.fm",
                "1204332455729827900": "Music",
                "1204315253085839371": "YT Music",
                "1204329359616376882": "YouTube Music",
                "1204329881563828274": "Apple Music",
                "1204332410872004628": "Tidal"}

            old_setting = self.settings.pop("discord_rpc_presence")
            self.settings["app_name"] = self.old_app_ids[old_setting]
            self.save_settings()

        for setting in ("username", "lastfm_api_key"):
            if not self.settings[setting]:
                ft.app(target=self.configuration_page)
                break

        for setting in ("username", "lastfm_api_key"):
            if not self.settings[setting]:
                sys.exit(0)

    def save_settings(self):
        with open("settings.json", "w") as f:
            json.dump(self.settings, f, indent=4)

    def configuration_page(self, page: ft.Page):
        """Setup page shown to user when first using the app."""
        page.title = "Last.presence"
        page.padding = 40
        page.window.width = 600
        page.window.height = 450
        page.window.center()
        page.window.resizable = False
        page.window.maximizable = False
        page.theme = ft.Theme(color_scheme_seed=ft.Colors.INDIGO)
        center = ft.MainAxisAlignment.CENTER

        container_description = ft.Container(content=ft.Text(
            "Enter the Last.fm username you want to use, and an API key "
            "obtained from Last.fm.",
            size=20, width=500, text_align=ft.TextAlign.CENTER))
        container_description.margin = ft.margin.only(bottom=40)
        username = ft.TextField(
            label="Last.fm username", value=self.settings["username"],
            autofocus=True, width=400)
        api_key = ft.TextField(
            label="Last.fm API key", value=self.settings["lastfm_api_key"],
            width=400)
        container_api_key = ft.Container(content=api_key)
        container_api_key.margin = ft.margin.only(bottom=40)

        def continue_click(_):
            network = pylast.LastFMNetwork(api_key=api_key.value)
            user = network.get_user(username.value)

            try:
                user.get_playcount()
            except pylast.WSError:
                page.open(failure_dialog)
                page.update()
            else:
                self.settings["username"] = username.value
                self.settings["lastfm_api_key"] = api_key.value
                self.save_settings()

                page.open(success_dialog)
                page.update()

        def create_api_click(_, *args):
            webbrowser.open("http://last.fm/api/account/create")

        def manage_api_click(_, *args):
            webbrowser.open("http://last.fm/api/accounts")

        def close_failure_dialog(_):
            page.close(failure_dialog)
            page.update()

        def close_success_dialog(_):
            page.window.close()

        continue_button = ft.FilledButton(
            "Continue", on_click=continue_click)
        create_api_button = ft.OutlinedButton(
            "Create API key", on_click=create_api_click)
        manage_api_button = ft.OutlinedButton(
            "Manage API keys", on_click=manage_api_click)
        failure_dialog = ft.AlertDialog(
            title=ft.Text("Error"),
            content=ft.Text("Invalid username or API key, please re-check."),
            actions=[ft.TextButton(
                "OK", on_click=close_failure_dialog, autofocus=True)])
        success_dialog = ft.AlertDialog(
            title=ft.Text("Setup successful"),
            content=ft.Text(
                "Last.presence will run in your taskbar as a tray icon. "
                "Right-click it for settings."),
            actions=[ft.TextButton(
                "Finish", on_click=close_success_dialog, autofocus=True)])

        page.add(
            ft.Row([container_description], alignment=center),
            ft.Row([username], alignment=center),
            ft.Row([container_api_key], alignment=center),
            ft.Row(
                [continue_button, create_api_button, manage_api_button],
                alignment=center))

    def setup_lastfm(self):
        """Set up Last.fm."""
        self.network = pylast.LastFMNetwork(
            api_key=self.settings["lastfm_api_key"])
        self.user = self.network.get_user(self.settings["username"])
        logging.info(f"Connected as {self.user.name}")
        logging.info(f"Using Last.presence {self.build_version}")

    def setup_rpc(self):
        """Set up Discord RPC."""
        self.rpc = pypresence.Presence("1204332455729827900")

        while True:
            try:
                self.rpc.connect()
                logging.info("Connected to Discord RPC")
                break
            except pypresence.exceptions.DiscordNotFound:
                logging.error("Discord not found, retrying in 10s")

            time.sleep(10)

    def close(self):
        """Clean things up and close cleanly."""
        self.rpc.clear()
        self.rpc.close()
        self.tray_icon.stop()
        logging.info("Closed RPC and tray icon cleanly")

    def restart(self):
        """Clean things up and restart."""
        self.close()
        logging.info("Restarting")

        if hasattr(sys, 'frozen'):
            subprocess.Popen(
                [sys.executable],
                env={**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"})
        else:
            subprocess.Popen([sys._MEIPASS])

    def run_tray_icon(self):
        """Create and run tray icon that contains settings."""

        def toggle_setting(setting_name, tray_item):
            """Helper function to alter and save a setting tweak."""
            self.settings[setting_name] = not tray_item.checked
            self.save_settings()

        def show_setup(_, item):
            """Let user reconfigure username and API key."""
            username = self.settings["username"]
            api_key = self.settings["lastfm_api_key"]
            ft.app(target=self.configuration_page)

            new_username = self.settings["username"]
            new_api_key = self.settings["lastfm_api_key"]

            if username == new_username and api_key == new_api_key:
                return

            self.restart()

        def set_rpc(_, item):
            """Allows or prevents RPC from updating while script is running."""
            toggle_setting("rpc_enabled", item)

            if self.settings["rpc_enabled"]:
                self.update_presence(force_update=True)
            else:
                self.rpc.clear()

        def set_startup(_, item):
            """Creates or removes startup shortcut for the script."""
            if os.path.exists(self.shortcut_startup_path):
                os.remove(self.shortcut_startup_path)
                logging.info(f"Removed {self.shortcut_startup_path} shortcut")
                return

            file_path = sys.executable

            with winshell.shortcut(self.shortcut_startup_path) as link:
                link.path = file_path
                link.working_directory = os.path.dirname(file_path)

            logging.info(f"Created shortcut at {self.shortcut_startup_path}")

        def set_name(_, item):
            """Alters name shown next to music icon and above song name."""
            self.settings["app_name"] = str(item)

            self.save_settings()
            self.update_presence(force_update=True)

        def open_log(_, item):
            os.startfile("log.txt")

        @staticmethod
        def check_name(item):
            return str(item) == self.settings["app_name"]

        check_rpc = lambda _: self.settings["rpc_enabled"]
        check_startup = lambda _: os.path.exists(self.shortcut_startup_path)

        app_names = []
        for app in self.app_names:
            app_names.append(MenuItem(app, set_name, check_name, radio=True))

        menu = Menu(
            MenuItem(f"Connected as {lastpresence.user.name}", show_setup),
            MenuItem("Enable Last.presence", set_rpc, check_rpc),
            MenuItem("Run at startup", set_startup, check_startup),
            Menu.SEPARATOR,
            MenuItem("Application name", Menu(*app_names)),
            Menu.SEPARATOR,
            MenuItem("Open log file", open_log),
            MenuItem("Restart", self.restart),
            MenuItem('Quit', self.close))

        name = f"Last.presence ({self.build_version})"
        if os.path.isfile("assets/icon.ico"):
            icon = Image.open("assets/icon.ico")  # when using .pyw for testing
        else:
            icon = Image.open(os.path.join(sys._MEIPASS, "icon.ico"))  # .exe

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

        if track is None:
            self.rpc.clear()
            logging.info("No song detected, cleared rich presence.")
            return

        album = track.get_album()
        cover = track.get_cover_image()
        duration = track.get_duration()

        name_app = self.settings["app_name"]
        name_track = track.title.ljust(2)[:128]
        name_artist = track.artist.name.ljust(2)[:128]
        name_album = None
        end_timestamp = None

        if name_app == "Use artist name":
            name_app = name_artist[:64]

        if album:
            name_album = album.title.ljust(2)[:128]

        if duration:
            end_timestamp = self.last_track_timestamp + (duration / 1000)

        if not cover or "2a96cbd8b46e442fc41c2b86b821562f" in cover:
            cover = "https://files.catbox.moe/qqh1rn.png"

        self.rpc.update(
            name=name_app,
            details=name_track,
            state=name_artist,
            large_text=name_album,
            large_image=cover,
            start=self.last_track_timestamp,
            end=end_timestamp,
            activity_type=pypresence.ActivityType.LISTENING)

        logging.info(f"Updated: {track.artist.name} - {track.title}")

    def presence_update_loop(self):
        """Main loop responsible for updating presence."""
        while True:
            try:
                lastpresence.update_presence()
            except pypresence.exceptions.PipeClosed:
                logging.warning("Restarting connection to Discord RPC")
                self.setup_rpc()
                lastpresence.update_presence(force_update=True)
            except pylast.WSError as e:
                if str(e) == "Track not found":
                    logging.warning(
                        "Track not found. It's possible you're scrobbling "
                        "something very recently added to Last.fm")
                elif str(e).endswith("HTTP code 500"):
                    logging.warning(
                        "Connection to Last.fm API failed with HTTP code 500. "
                        "Your internet or Last.fm may be down")
                else:
                    logging.warning(f"pylast.WSError '{e}'")
            except pylast.NetworkError as e:
                logging.warning(f"pylast.NetworkError '{e}'")
            except (pylast.PyLastError, pypresence.PyPresenceException):
                logging.warning(traceback.format_exc())
            except Exception:
                logging.error(traceback.format_exc())
                logging.error(
                    "Uncatched exception. Restarting program shortly")

                time.sleep(10)  # In case this loops, avoid hammering system
                self.restart()

            time.sleep(10)


if __name__ == "__main__":
    lastpresence = LastPresence()

    thread = threading.Thread(target=lastpresence.presence_update_loop)
    thread.daemon = True
    thread.start()

    lastpresence.run_tray_icon()
