"""
wifi_setup.py — On-screen Wi-Fi configuration for the Raspberry Pi touchscreen.

Shown at startup when no network connectivity is detected.
Renders a QWERTY keyboard in pygame so the user can enter their SSID and
password without a physical keyboard.

Credential application order:
  1. nmcli      — Raspberry Pi OS Bookworm (NetworkManager)
  2. wpa_supplicant.conf  — Raspberry Pi OS Bullseye and earlier

On desktop / Windows this module is imported but run_wifi_setup() is never
called — the caller skips it when args.desktop is True.
"""
import socket
import subprocess
import time

import pygame

# ---------------------------------------------------------------------------
# Palette (matches ui.py)
# ---------------------------------------------------------------------------
DARK_GRAY  = (22,  22,  28)
MID_GRAY   = (55,  55,  65)
LIGHT_GRAY = (140, 140, 150)
WHITE      = (255, 255, 255)
ACCENT     = (0,   160, 255)
GREEN      = (0,   210,  90)
ORANGE     = (255, 140,   0)
RED        = (220,  55,  55)

# ---------------------------------------------------------------------------
# Network detection
# ---------------------------------------------------------------------------

def has_network() -> bool:
    """Return True if the device can reach the internet (DNS on 8.8.8.8:53)."""
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=3)
        return True
    except OSError:
        return False

# ---------------------------------------------------------------------------
# Keyboard layout
# ---------------------------------------------------------------------------
# Each key: (display_label, action, width_units)
# action: char to type | "⌫" | "⇧" | "DONE" | "SKIP"
# width_units: relative width within the row (integers sum to row total)

_ROWS = [
    # Numbers row
    [("1","1",1),("2","2",1),("3","3",1),("4","4",1),("5","5",1),
     ("6","6",1),("7","7",1),("8","8",1),("9","9",1),("0","0",1)],
    # QWERTY row
    [("Q","q",1),("W","w",1),("E","e",1),("R","r",1),("T","t",1),
     ("Y","y",1),("U","u",1),("I","i",1),("O","o",1),("P","p",1)],
    # ASDF row  (⌫ fills the right end at same unit width)
    [("A","a",1),("S","s",1),("D","d",1),("F","f",1),("G","g",1),
     ("H","h",1),("J","j",1),("K","k",1),("L","l",1),("⌫","⌫",1)],
    # ZXCV row  (wider shift + backspace)
    [("⇧","⇧",15),("Z","z",10),("X","x",10),("C","c",10),("V","v",10),
     ("B","b",10),("N","n",10),("M","m",10),("⌫","⌫",15)],
    # Specials / space / done
    [("@","@",8),(".",".",8),("-","-",8),("_","_",8),
     ("SPACE"," ",32),("DONE","DONE",20),("SKIP","SKIP",16)],
]

# Layout geometry
_KB_TOP    = 185   # y pixel where keyboard starts
_KEY_H     = 56    # key cell height (px)
_ROW_STEP  = 59    # y distance between row origins (key height + gap)
_KEY_INNER = 2     # visual shrink on all sides for the gap effect


def _build_keys():
    """Return list of {label, action, rect} for every key."""
    keys = []
    for ri, row in enumerate(_ROWS):
        total_units = sum(w for _, _, w in row)
        unit_w = 800.0 / total_units
        ry = _KB_TOP + ri * _ROW_STEP
        x_f = 0.0
        for label, action, w_units in row:
            x0 = round(x_f)
            x_f += w_units * unit_w
            x1 = round(x_f)
            kw = x1 - x0
            i = _KEY_INNER
            keys.append({
                "label":  label,
                "action": action,
                "rect":   pygame.Rect(x0 + i, ry + i, kw - i * 2, _KEY_H - i * 2),
            })
    return keys


# ---------------------------------------------------------------------------
# Setup screen
# ---------------------------------------------------------------------------

class WifiSetupScreen:
    _FIELD_X = 10
    _FIELD_W = 690
    _FIELD_H = 46

    # Vertical positions
    _TITLE_Y      = 8
    _SSID_LBL_Y   = 42
    _SSID_Y       = 58
    _PW_LBL_Y     = 108
    _PW_Y         = 124
    _STATUS_Y     = 172

    def __init__(self, screen, fonts):
        self._screen  = screen
        self._f       = fonts
        self._ssid    = ""
        self._pw      = ""
        self._active  = 0        # 0 = SSID field, 1 = password field
        self._shift   = False
        self._show_pw = False
        self._status  = "Enter your Wi-Fi network name and password."
        self._scolor  = LIGHT_GRAY
        self._keys    = _build_keys()

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def run(self) -> str:
        """
        Blocking event loop.

        Returns:
          "connected" — credentials applied and network confirmed
          "skipped"   — user pressed Skip
          "quit"      — window closed / ESC pressed
        """
        clock = pygame.time.Clock()
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return "quit"
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        return "quit"
                    result = self._on_keydown(event)
                    if result:
                        return result
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    result = self._on_touch(event.pos)
                    if result:
                        return result
            self._draw()
            pygame.display.flip()
            clock.tick(30)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_keydown(self, event) -> "str | None":
        """Physical keyboard input (desktop testing convenience)."""
        if event.key == pygame.K_BACKSPACE:
            self._backspace()
        elif event.key == pygame.K_TAB:
            self._active = 1 - self._active
        elif event.key == pygame.K_RETURN:
            return self._try_connect()
        elif event.unicode and event.unicode.isprintable():
            self._type(event.unicode)
        return None

    def _on_touch(self, pos) -> "str | None":
        x, y = pos

        # SSID field tap
        if (self._SSID_Y <= y <= self._SSID_Y + self._FIELD_H
                and self._FIELD_X <= x <= self._FIELD_X + self._FIELD_W):
            self._active = 0
            return None

        # Password field tap
        if (self._PW_Y <= y <= self._PW_Y + self._FIELD_H
                and self._FIELD_X <= x <= self._FIELD_X + self._FIELD_W):
            self._active = 1
            return None

        # Show / hide password toggle (right of password field)
        if self._PW_Y <= y <= self._PW_Y + self._FIELD_H and x > self._FIELD_X + self._FIELD_W:
            self._show_pw = not self._show_pw
            return None

        # On-screen keys
        for key in self._keys:
            if key["rect"].collidepoint(pos):
                return self._press(key["action"])

        return None

    def _press(self, action) -> "str | None":
        if action == "⌫":
            self._backspace()
        elif action == "⇧":
            self._shift = not self._shift
        elif action == "DONE":
            return self._try_connect()
        elif action == "SKIP":
            return "skipped"
        else:
            ch = action.upper() if (self._shift and action.isalpha()) else action
            self._type(ch)
            if self._shift and action.isalpha():
                self._shift = False   # one-shot shift
        return None

    def _type(self, ch: str):
        if self._active == 0 and len(self._ssid) < 64:
            self._ssid += ch
        elif self._active == 1 and len(self._pw) < 64:
            self._pw += ch

    def _backspace(self):
        if self._active == 0 and self._ssid:
            self._ssid = self._ssid[:-1]
        elif self._active == 1 and self._pw:
            self._pw = self._pw[:-1]

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def _try_connect(self) -> "str | None":
        if not self._ssid.strip():
            self._status = "Network name cannot be empty."
            self._scolor = ORANGE
            return None

        self._status = "Connecting…"
        self._scolor = ACCENT
        self._draw()
        pygame.display.flip()

        ok, msg = _apply_wifi(self._ssid.strip(), self._pw)
        if ok:
            self._status = "Connected!  Starting app in 2 seconds…"
            self._scolor = GREEN
            self._draw()
            pygame.display.flip()
            time.sleep(2)
            return "connected"

        self._status = f"Failed: {msg}  Check name / password and try again."
        self._scolor = RED
        return None

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _draw(self):
        s = self._screen
        f = self._f
        s.fill(DARK_GRAY)

        # Title
        s.blit(f["lg"].render("Wi-Fi Setup", True, WHITE), (10, self._TITLE_Y))

        # SSID
        self._draw_field(
            label="Network Name (SSID)",
            value=self._ssid,
            y_label=self._SSID_LBL_Y,
            y_field=self._SSID_Y,
            active=(self._active == 0),
            mask=False,
        )

        # Password
        self._draw_field(
            label="Password",
            value=self._pw,
            y_label=self._PW_LBL_Y,
            y_field=self._PW_Y,
            active=(self._active == 1),
            mask=(not self._show_pw),
        )

        # Show/hide toggle
        eye = f["xs"].render("Show" if not self._show_pw else "Hide", True, ACCENT)
        s.blit(eye, (self._FIELD_X + self._FIELD_W + 8,
                     self._PW_Y + (self._FIELD_H - eye.get_height()) // 2))

        # Status message
        s.blit(f["xs"].render(self._status, True, self._scolor), (10, self._STATUS_Y))

        # Keyboard
        self._draw_keyboard()

    def _draw_field(self, label, value, y_label, y_field, active, mask):
        s = self._screen
        f = self._f
        border = ACCENT if active else MID_GRAY

        s.blit(
            f["xs"].render(label, True, ACCENT if active else LIGHT_GRAY),
            (self._FIELD_X, y_label),
        )

        pygame.draw.rect(s, MID_GRAY,
            (self._FIELD_X, y_field, self._FIELD_W, self._FIELD_H),
            border_radius=5)
        pygame.draw.rect(s, border,
            (self._FIELD_X, y_field, self._FIELD_W, self._FIELD_H),
            2, border_radius=5)

        display_val = ("●" * len(value)) if mask else value
        cursor = "│" if active else ""
        txt_surf = f["md"].render(display_val + cursor, True, WHITE)

        # Clip to field width if text overflows
        max_w = self._FIELD_W - 20
        if txt_surf.get_width() > max_w:
            txt_surf = txt_surf.subsurface(
                pygame.Rect(txt_surf.get_width() - max_w, 0, max_w, txt_surf.get_height())
            )
        s.blit(txt_surf, (self._FIELD_X + 10, y_field + (self._FIELD_H - txt_surf.get_height()) // 2))

    def _draw_keyboard(self):
        s = self._screen
        f = self._f
        for key in self._keys:
            action = key["action"]
            rect   = key["rect"]

            # Background
            if action == "⇧" and self._shift:
                bg = ACCENT
            elif action in ("⌫", "⇧", "DONE", "SKIP"):
                bg = (70, 70, 88)
            else:
                bg = MID_GRAY

            pygame.draw.rect(s, bg, rect, border_radius=5)

            # Label — apply shift to alpha keys
            display = key["label"]
            if action.isalpha() and len(action) == 1:
                display = action.upper() if self._shift else action.lower()

            lbl = f["sm"].render(display, True, WHITE)
            s.blit(lbl, lbl.get_rect(center=rect.center))


# ---------------------------------------------------------------------------
# WiFi application helpers
# ---------------------------------------------------------------------------

def _apply_wifi(ssid: str, password: str) -> "tuple[bool, str]":
    """
    Try to connect to the given network.
    Returns (success: bool, message: str).
    """
    # --- Method 1: nmcli (Pi OS Bookworm / NetworkManager) ---------------
    try:
        cmd = ["nmcli", "dev", "wifi", "connect", ssid]
        if password:
            cmd += ["password", password]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if r.returncode == 0:
            return True, "OK"
        err = (r.stderr or r.stdout).strip().splitlines()
        return False, (err[0] if err else "nmcli failed")
    except FileNotFoundError:
        pass          # nmcli not present — try wpa_supplicant
    except subprocess.TimeoutExpired:
        return False, "Connection timed out"
    except Exception:
        pass

    # --- Method 2: wpa_supplicant (Pi OS Bullseye and earlier) -----------
    try:
        psk_line = f'psk="{password}"' if password else "key_mgmt=NONE"
        conf = (
            "country=US\n"
            "ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev\n"
            "update_config=1\n\n"
            "network={\n"
            f'    ssid="{ssid}"\n'
            f"    {psk_line}\n"
            "}\n"
        )
        with open("/etc/wpa_supplicant/wpa_supplicant.conf", "w") as fh:
            fh.write(conf)
        subprocess.run(["wpa_cli", "-i", "wlan0", "reconfigure"],
                       capture_output=True, timeout=10)
        time.sleep(5)   # allow time to associate
        if has_network():
            return True, "OK"
        return False, "Could not associate — check SSID and password"
    except PermissionError:
        return False, "Permission denied — is the app running as root?"
    except Exception as e:
        return False, str(e)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_wifi_setup(desktop: bool = False) -> str:
    """
    Initialize pygame, show the Wi-Fi setup screen, tear down pygame.

    Returns:
      "connected" — credentials applied and network is up
      "skipped"   — user tapped Skip
      "quit"      — window closed or ESC pressed
    """
    pygame.init()
    if desktop:
        screen = pygame.display.set_mode((800, 480))
        pygame.display.set_caption("Flight Tracker — Wi-Fi Setup")
    else:
        screen = pygame.display.set_mode(
            (800, 480), pygame.FULLSCREEN | pygame.NOFRAME
        )
        pygame.mouse.set_visible(False)

    fonts = {
        "lg": pygame.font.SysFont("DejaVu Sans,Arial,sans-serif", 22, bold=True),
        "md": pygame.font.SysFont("DejaVu Sans,Arial,sans-serif", 18),
        "sm": pygame.font.SysFont("DejaVu Sans,Arial,sans-serif", 15),
        "xs": pygame.font.SysFont("DejaVu Sans,Arial,sans-serif", 13),
    }

    result = WifiSetupScreen(screen, fonts).run()
    pygame.quit()
    return result
