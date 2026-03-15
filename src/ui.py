"""
Pygame UI — 800×480 touchscreen display for the flight tracker.

Layout (live mode)
──────────────────
┌─────────────────────────────────────────────────────────────────┐  y=0
│  ✈ N aircraft  ·  last update HH:MM:SS          HEADER (h=40)  │  y=40
├──────────────────────┬──────────────────────────────────────────┤
│ Photo  300×168       │ Callsign / Airline            RIGHT COL  │
│ (x=10,y=40)         │ Route  origin → dest          x=320,w=480│
│                      │ A/C type · Registration                  │
│──────────────────────│ ┌──────┬──────┬──────┬──────┐ y=128     │
│ Registration text    │ │ ALT  │ SPD  │ GSPD │ HDG  │           │
│ (x=10,y=212)        │ │ VRAT │ DIST │ BRG  │ TRCK │           │
│ Map    300×168       │ │ SQWK │ GND  │ TRKD │ SIG  │           │
│ (x=10,y=234)        │ │ ICAO │ CAT  │ MSGS │ SEEN │           │
│                      │ └──────┴──────┴──────┴──────┘           │
├──────────────────────┴──────────────────────────────────────────┤  y=436
│ ◀ PREV (135) │    AUTO (165)    │ NEXT ▶(135)│ HIST(155)│SET(150)│
└─────────────────────────────────────────────────────────────────┘  y=480
"""
import datetime as _dt
import io
import os
import threading
import time

import pygame
from PIL import Image

# Path to the bundled Material Icons font (Apache 2.0)
_ICON_FONT_PATH = os.path.join(os.path.dirname(__file__), "assets", "MaterialIcons-Regular.ttf")

# Material Icons codepoints used in this app
#   Full reference: https://fonts.google.com/icons
ICON = {
    "prev":      "\ue5cb",   # navigate_before
    "next":      "\ue5cc",   # navigate_next
    "auto":      "\ue863",   # autorenew
    "pause":     "\ue034",   # pause
    "history":   "\ue889",   # history
    "settings":  "\ue8b8",   # settings
    "close":     "\ue5cd",   # close
    "flight":    "\ue539",   # flight (airplane)
    "live":      "\ue63e",   # wifi_tethering  (used for "back to live")
    "location":  "\ue0c8",   # location_on
    "wifi":      "\ue63e",   # wifi
    "delete":    "\ue872",   # delete
    "download":  "\uf090",   # file_download
}

try:
    import staticmap as _sm
    HAS_STATICMAP = True
except ImportError:
    HAS_STATICMAP = False

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

# ---------------------------------------------------------------------------
# Colour palette — Nord  https://www.nordtheme.com/
# ---------------------------------------------------------------------------
#  Polar Night  nord0–3      (backgrounds, panels, borders)
#  Snow Storm   nord4–6      (text)
#  Frost        nord7–10     (accents, interactive elements)
#  Aurora       nord11–15    (status colours)
_N0  = (46,  52,  64)    # nord0  darkest bg
_N1  = (59,  66,  82)    # nord1  panel bg
_N2  = (67,  76,  94)    # nord2  card / cell bg
_N3  = (76,  86, 106)    # nord3  borders / dim text
_N4  = (216, 222, 233)   # nord4  body text
_N6  = (236, 239, 244)   # nord6  bright text
_N7  = (143, 188, 187)   # nord7  teal
_N8  = (136, 192, 208)   # nord8  bright cyan  (primary accent)
_N9  = (129, 161, 193)   # nord9  muted blue
_N10 = (94,  129, 172)   # nord10 darker blue  (buttons)
_N11 = (191,  97, 106)   # nord11 red
_N12 = (208, 135, 112)   # nord12 orange
_N13 = (235, 203, 139)   # nord13 yellow
_N14 = (163, 190, 140)   # nord14 green
_N15 = (180, 142, 173)   # nord15 purple

BLACK      = (0,   0,   0)
WHITE      = _N6                  # bright snow-storm white
DARK_GRAY  = _N0                  # background
MID_GRAY   = _N2                  # cards / cells
LIGHT_GRAY = _N3                  # dim text / borders
ACCENT     = _N8                  # bright cyan
ORANGE     = _N12                 # soft orange
GREEN      = _N14                 # muted green
RED        = _N11                 # muted red
YELLOW     = _N13                 # warm yellow
SEMI_BLACK = (*_N0, 210)          # nord0 with alpha (overlay)

# Button colours
BLUE_ACCENT = _N10                # PREV / NEXT / HIST
GREEN_BTN   = _N14                # AUTO running
ORANGE_BTN  = _N12                # AUTO paused
PURPLE_BTN  = _N15                # SETTINGS

# Header bar
HEADER_BG   = _N1                 # slightly lighter than background

# Distance filter steps (miles); last value = "All" (no filter)
DIST_STEPS = [5, 10, 25, 50, 100, 150, 200, 250]

# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------
SCREEN_W,  SCREEN_H  = 800, 480
HEADER_H              = 40
BUTTON_H              = 44
BUTTON_Y              = SCREEN_H - BUTTON_H          # 436
CONTENT_Y             = HEADER_H                     # 40
CONTENT_H             = BUTTON_Y - CONTENT_Y         # 396

LEFT_W                = 320
RIGHT_X               = LEFT_W
RIGHT_W               = SCREEN_W - LEFT_W            # 480

PHOTO_X, PHOTO_Y      = 10, CONTENT_Y               # 10, 40
PHOTO_W, PHOTO_H      = 300, 168
REG_Y                 = PHOTO_Y + PHOTO_H + 4       # 212
MAP_X                 = 10
MAP_Y                 = 234
MAP_W, MAP_H          = 300, 168

GRID_INFO_Y           = CONTENT_Y                   # 40  — flight info header starts here
GRID_INFO_H           = 88                          # flight info section height
GRID_Y                = GRID_INFO_Y + GRID_INFO_H   # 128 — data grid rows start here
GRID_ROW_H            = 77                          # 4 rows × 77 = 308 ≈ fills to y=436
GRID_COL_W            = RIGHT_W // 4               # 120 px each column

FAST_BAR_H            = 5

# Button geometry (x, width, default-colour)
BTN_DEFS = [
    ("◀  PREV",    10, 135, BLUE_ACCENT),
    ("AUTO",      155, 165, GREEN_BTN),
    ("NEXT  ▶",   330, 135, BLUE_ACCENT),
    ("📋  HIST",  475, 155, BLUE_ACCENT),
    ("⚙   SET",  640, 150, PURPLE_BTN),
]

# ---------------------------------------------------------------------------
# Settings keyboard
# ---------------------------------------------------------------------------
_SKB_TOP  = 116
_SKB_H    = 52
_SKB_STEP = 56

_SKB_ROWS = [
    [("1","1",1),("2","2",1),("3","3",1),("4","4",1),("5","5",1),
     ("6","6",1),("7","7",1),("8","8",1),("9","9",1),("0","0",1)],
    [("Q","q",1),("W","w",1),("E","e",1),("R","r",1),("T","t",1),
     ("Y","y",1),("U","u",1),("I","i",1),("O","o",1),("P","p",1)],
    [("A","a",1),("S","s",1),("D","d",1),("F","f",1),("G","g",1),
     ("H","h",1),("J","j",1),("K","k",1),("L","l",1),("⌫","⌫",1)],
    [("⇧","⇧",15),("Z","z",10),("X","x",10),("C","c",10),("V","v",10),
     ("B","b",10),("N","n",10),("M","m",10),("⌫","⌫",15)],
    [(" "," ",30),(",",",",8),(".",".",8),("-","-",8),("SEARCH","SEARCH",26)],
]


def _build_settings_keys():
    GAP  = 2
    keys = []
    for ri, row in enumerate(_SKB_ROWS):
        total  = sum(w for _, _, w in row)
        unit_w = SCREEN_W / total
        ry     = _SKB_TOP + ri * _SKB_STEP
        xf     = 0.0
        for label, action, w_units in row:
            x0 = round(xf)
            xf += w_units * unit_w
            x1 = round(xf)
            kw = x1 - x0
            keys.append({
                "label":  label,
                "action": action,
                "rect":   pygame.Rect(x0 + GAP, ry + GAP, kw - GAP * 2, _SKB_H - GAP * 2),
            })
    return keys


# ---------------------------------------------------------------------------
# FlightUI
# ---------------------------------------------------------------------------

class FlightUI:
    AUTO_SWITCH_DELAY = 8.0

    def __init__(self, config: dict, desktop: bool = False):
        self.config  = config
        self.desktop = desktop

        # UI state
        self.mode           = "live"
        self.selected_index = 0
        self.history_page   = 0
        self.auto_rotate    = True

        # Data provided each frame
        self.live_aircraft:   list = []
        self.history_flights: list = []

        # Notification state
        self._notification = None
        self._summary      = None
        self._fast_mode    = False

        # Auto-rotate anchor
        self._last_rotate   = time.time()
        self._selected_icao = None

        # Photo state machine (keyed by icao_hex)
        self._photo_cache:    dict = {}
        self._photo_pending:  dict = {}
        self._photo_fetching: set  = set()
        self._photo_failed:   set  = set()

        # Map cache (keyed by icao_hex)
        self._map_cache:      dict  = {}
        self._map_pending:    set   = set()
        self._map_last_fetch: dict  = {}
        self.MAP_REFRESH_INTERVAL   = 30

        # Settings state
        self._settings_open    = False
        self._settings_sub     = "main"   # "main" | "location"
        self._settings_address = ""
        self._settings_shift   = False
        self._settings_status  = ""
        self._settings_scolor  = LIGHT_GRAY
        self._settings_keys:   list = []

        # Settings — display spinbox values (runtime only, saved on SAVE)
        self._set_rotate_interval = config.get("auto_rotate_interval", 300)
        self._set_idle_timeout    = config.get("idle_timeout_minutes", 5)
        self._set_display_range   = config.get("display_range_miles", 250)

        # Auto-switch
        self._switch_pending  = None
        self._switch_deadline = 0.0
        self._stay_zone       = pygame.Rect(0, 0, 0, 0)

        # pygame objects
        self._screen = None
        self._clock  = None
        self._fonts: dict = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def init(self):
        pygame.init()
        if self.desktop:
            self._screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
            pygame.display.set_caption("Flight Tracker — Desktop Mode")
        else:
            self._screen = pygame.display.set_mode(
                (SCREEN_W, SCREEN_H), pygame.FULLSCREEN | pygame.NOFRAME
            )
            pygame.mouse.set_visible(False)

        self._clock = pygame.time.Clock()

        def f(size, bold=False):
            return pygame.font.SysFont("DejaVu Sans,Arial,sans-serif", size, bold=bold)

        self._fonts = {
            "xl":  f(28, bold=True),
            "lg":  f(20, bold=True),
            "val": f(18, bold=True),   # data-grid primary value — large + bold
            "md":  f(16),
            "sm":  f(14),
            "xs":  f(12),
            "xxs": f(10),
        }

        # Icon font — falls back to None gracefully if file missing
        if os.path.isfile(_ICON_FONT_PATH):
            self._icon_font     = pygame.font.Font(_ICON_FONT_PATH, 22)
            self._icon_font_sm  = pygame.font.Font(_ICON_FONT_PATH, 18)
            self._icon_font_hdr = pygame.font.Font(_ICON_FONT_PATH, 16)
        else:
            self._icon_font = self._icon_font_sm = self._icon_font_hdr = None

        self._settings_keys = _build_settings_keys()

    def quit(self):
        pygame.quit()

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------

    def handle_event(self, event) -> "str | None":
        if event.type == pygame.QUIT:
            return "quit"
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                return "quit"
            self._handle_key(event.key)
        if event.type == pygame.MOUSEBUTTONDOWN:
            self._handle_touch(event.pos)
        return None

    def _handle_key(self, key):
        if key == pygame.K_LEFT:
            self._prev()
        elif key == pygame.K_RIGHT:
            self._next()
        elif key == pygame.K_SPACE:
            self.auto_rotate = not self.auto_rotate
        elif key == pygame.K_h:
            self._toggle_mode()
        elif key == pygame.K_s:
            self._settings_open = not self._settings_open

    def _handle_touch(self, pos):
        x, y = pos

        # Settings overlay — route content area taps to settings handler
        if self._settings_open and y < BUTTON_Y:
            self._handle_settings_touch(pos)
            return

        # [Stay] banner tap
        if (self._switch_pending is not None
                and self._stay_zone.collidepoint(pos)):
            self._switch_pending = None
            return

        # Summary overlay absorbs touches
        if self._summary:
            return

        # Button row
        if y >= BUTTON_Y:
            self._handle_button_touch(x)
            return

        # History-mode row tap
        if self.mode == "history":
            row_h = CONTENT_H // 8
            if row_h > 0:
                row    = (y - CONTENT_Y) // row_h
                tapped = self.history_page * 8 + row
                if 0 <= tapped < len(self.history_flights):
                    self.selected_index = tapped

    def _handle_button_touch(self, x):
        for i, (label, bx, bw, _color) in enumerate(BTN_DEFS):
            if bx <= x < bx + bw:
                if i == 0:
                    self._prev()
                elif i == 1:
                    self.auto_rotate = not self.auto_rotate
                    self._last_rotate = time.time()
                elif i == 2:
                    self._next()
                elif i == 3:
                    if not self._settings_open:
                        self._toggle_mode()
                elif i == 4:
                    self._settings_open = not self._settings_open
                    self._settings_sub  = "main"
                    self._settings_address = ""
                    self._settings_status  = ""
                    if not self._settings_open:
                        self.config["auto_rotate_interval"] = self._set_rotate_interval
                        self.config["idle_timeout_minutes"] = self._set_idle_timeout
                        self.config["display_range_miles"]  = self._set_display_range
                        import config as _cfg; _cfg.save_config(self.config)
                break

    def _prev(self):
        self.auto_rotate     = False
        self._switch_pending = None
        if self.mode == "live" and self.live_aircraft:
            self.selected_index = (self.selected_index - 1) % len(self.live_aircraft)
            self._selected_icao = self.live_aircraft[self.selected_index].get("icao_hex")
        elif self.mode == "history" and self.history_page > 0:
            self.history_page -= 1

    def _next(self):
        self.auto_rotate     = False
        self._switch_pending = None
        if self.mode == "live" and self.live_aircraft:
            self.selected_index = (self.selected_index + 1) % len(self.live_aircraft)
            self._selected_icao = self.live_aircraft[self.selected_index].get("icao_hex")
        elif self.mode == "history":
            max_page = max(0, (len(self.history_flights) - 1) // 8)
            if self.history_page < max_page:
                self.history_page += 1

    def _toggle_mode(self):
        self.mode = "history" if self.mode == "live" else "live"
        self.selected_index = 0
        self._selected_icao = None
        self.history_page   = 0

    # ------------------------------------------------------------------
    # Update (main loop calls once per frame)
    # ------------------------------------------------------------------

    def update(self, live_aircraft, history_flights, notification, summary,
               fast_mode, new_aircraft=None):
        dr = self._set_display_range
        self.live_aircraft   = [ac for ac in live_aircraft if ac.get("distance", 0) <= dr]
        self.history_flights = history_flights
        self._notification   = notification
        self._summary        = summary
        self._fast_mode      = fast_mode

        if new_aircraft and self._switch_pending is None and self.mode == "live":
            self._switch_pending  = new_aircraft[0]
            self._switch_deadline = time.time() + self.AUTO_SWITCH_DELAY

        if self.live_aircraft:
            if self._selected_icao:
                icao_list = [ac.get("icao_hex") for ac in self.live_aircraft]
                if self._selected_icao in icao_list:
                    self.selected_index = icao_list.index(self._selected_icao)
                else:
                    self.selected_index = 0
                    self._selected_icao = self.live_aircraft[0].get("icao_hex")
                    self._last_rotate   = time.time()
            else:
                self.selected_index = 0
                self._selected_icao = self.live_aircraft[0].get("icao_hex")
                self._last_rotate   = time.time()
        else:
            self.selected_index = 0
            self._selected_icao = None

        if self.auto_rotate and self.mode == "live" and self.live_aircraft:
            interval = (
                self.config.get("fast_mode_interval", 30) if fast_mode
                else self.config.get("auto_rotate_interval", 300)
            )
            if time.time() - self._last_rotate >= interval:
                self.selected_index = (self.selected_index + 1) % len(self.live_aircraft)
                self._selected_icao = self.live_aircraft[self.selected_index].get("icao_hex")
                self._last_rotate   = time.time()

    # ------------------------------------------------------------------
    # Draw
    # ------------------------------------------------------------------

    def draw(self):
        # Promote pending PIL bytes → pygame Surfaces (must be main thread)
        if self._photo_pending:
            for icao, (raw, w, h) in list(self._photo_pending.items()):
                print(f"[photo] CREATING SURFACE {icao}  bytes={len(raw)}", flush=True)
                try:
                    surf = pygame.image.fromstring(raw, (w, h), "RGB")
                    self._photo_cache[icao] = surf
                    print(f"[photo] SURFACE OK {icao}", flush=True)
                except Exception as e:
                    print(f"[photo] SURFACE FAILED {icao}: {e}", flush=True)
                    self._photo_failed.add(icao)
                del self._photo_pending[icao]

        # Auto-switch countdown
        if self._switch_pending is not None and time.time() >= self._switch_deadline:
            self._do_auto_switch()

        self._screen.fill(DARK_GRAY)

        # Header bar (always shown)
        self._render_header()

        if self._settings_open:
            self._render_settings()
        elif self.mode == "live":
            self._render_live()
        else:
            self._render_history()

        self._render_buttons()

        # Overlays (only when not in settings)
        if not self._settings_open:
            if self._switch_pending is not None:
                self._render_auto_switch_banner()
            elif self._summary:
                self._render_summary_overlay()
            elif self._notification:
                self._render_brief_popup()

        if self._fast_mode:
            pygame.draw.rect(self._screen, ORANGE,
                             (0, BUTTON_Y - FAST_BAR_H, SCREEN_W, FAST_BAR_H))

        pygame.display.flip()
        self._clock.tick(30)

    # ------------------------------------------------------------------
    # Header bar
    # ------------------------------------------------------------------

    def _render_header(self):
        pygame.draw.rect(self._screen, HEADER_BG, (0, 0, SCREEN_W, HEADER_H))

        f   = self._fonts
        now = _dt.datetime.now().strftime("%H:%M:%S")

        if self.mode == "live":
            n   = len(self.live_aircraft)
            label = f"{n} aircraft" if n != 1 else "1 aircraft"
            icon  = ICON["flight"]
        else:
            label = f"History — {len(self.history_flights)} flights"
            icon  = ICON["history"]

        cy = HEADER_H // 2
        if self._icon_font_hdr:
            icon_surf = self._icon_font_hdr.render(icon, True, _N8)
            self._screen.blit(icon_surf, (12, cy - icon_surf.get_height() // 2))
            left = f["sm"].render(label, True, WHITE)
            self._screen.blit(left, (12 + icon_surf.get_width() + 6,
                                     cy - left.get_height() // 2))
        else:
            left = f["sm"].render(("✈  " if self.mode == "live" else "📋  ") + label, True, WHITE)
            self._screen.blit(left, (12, cy - left.get_height() // 2))

        cy = HEADER_H // 2
        if self._icon_font_hdr:
            clk_ic = self._icon_font_hdr.render("\ue192", True, _N9)  # schedule (clock)
            time_surf = f["sm"].render(now, True, WHITE)
            total_w = clk_ic.get_width() + 4 + time_surf.get_width()
            rx = SCREEN_W - total_w - 12
            self._screen.blit(clk_ic,    (rx, cy - clk_ic.get_height() // 2))
            self._screen.blit(time_surf, (rx + clk_ic.get_width() + 4,
                                          cy - time_surf.get_height() // 2))
        else:
            time_surf = f["sm"].render(now, True, WHITE)
            self._screen.blit(time_surf, (SCREEN_W - time_surf.get_width() - 12,
                                          cy - time_surf.get_height() // 2))

    # ------------------------------------------------------------------
    # Live mode
    # ------------------------------------------------------------------

    def _render_live(self):
        if not self.live_aircraft:
            self._draw_waiting()
            return

        ac = self.live_aircraft[self.selected_index]

        # Left column
        self._render_photo(ac, PHOTO_X, PHOTO_Y, PHOTO_W, PHOTO_H)
        self._render_registration(ac)
        self._render_map(ac, MAP_X, MAP_Y, MAP_W, MAP_H)

        # Right column
        self._render_flight_info_header(ac)
        self._render_data_grid(ac)

        # Aircraft counter (bottom-left in left column)
        n   = len(self.live_aircraft)
        idx = self.selected_index + 1
        ct  = self._fonts["xs"].render(f"{idx} / {n}", True, LIGHT_GRAY)
        self._screen.blit(ct, (MAP_X, BUTTON_Y - ct.get_height() - 4))

    def _render_registration(self, ac):
        reg = ac.get("registration") or ""
        if not reg:
            return
        label = self._fonts["xs"].render("REG", True, LIGHT_GRAY)
        value = self._fonts["sm"].render(reg, True, ACCENT)
        self._screen.blit(label, (PHOTO_X, REG_Y))
        self._screen.blit(value, (PHOTO_X + label.get_width() + 6, REG_Y))

    def _render_flight_info_header(self, ac):
        """88 px tall flight-info section at top of right column."""
        f  = self._fonts
        s  = self._screen
        x  = RIGHT_X + 8
        y0 = GRID_INFO_Y + 4

        callsign = (ac.get("callsign") or ac.get("icao_hex", "??????")).upper()
        airline  = ac.get("airline", "")
        origin   = ac.get("origin") or "???"
        dest     = ac.get("destination") or "???"
        ac_type  = ac.get("aircraft_type") or ac.get("model") or ""
        reg      = ac.get("registration") or ""

        # Row 1: callsign [+ airline]
        headline = callsign + (f"  ({airline})" if airline else "")
        s.blit(f["lg"].render(headline, True, WHITE), (x, y0))

        # Row 2: route
        route_color = ACCENT if origin != "???" else LIGHT_GRAY
        s.blit(f["md"].render(f"{origin}  →  {dest}", True, route_color), (x, y0 + 28))

        # Row 3: type · reg
        type_line = "  ·  ".join(filter(None, [ac_type, reg]))
        s.blit(f["sm"].render(type_line, True, LIGHT_GRAY), (x, y0 + 54))

        # Divider
        pygame.draw.line(s, MID_GRAY,
                         (RIGHT_X, GRID_Y - 2), (SCREEN_W, GRID_Y - 2), 1)

    def _render_data_grid(self, ac):
        """4×4 grid of data cells starting at y=GRID_Y."""
        f = self._fonts
        s = self._screen

        alt     = ac.get("altitude", 0)
        speed   = ac.get("speed", 0)
        gspd    = ac.get("gs", 0) or 0          # ground speed in knots from dump1090
        heading = ac.get("track", 0) or 0
        vspeed  = ac.get("baro_rate", 0) or 0
        dist    = ac.get("distance", 0) or 0.0
        bearing = ac.get("bearing", 0) or 0
        track   = ac.get("track", 0) or 0
        squawk  = ac.get("squawk") or "----"
        on_gnd  = ac.get("on_ground", False)
        seen    = ac.get("seen", 0) or 0
        signal  = ac.get("rssi") or ac.get("signal_power") or "—"
        icao    = ac.get("icao_hex", "").upper()
        cat     = ac.get("category") or "—"
        msgs    = ac.get("messages", 0) or 0
        last_seen = ac.get("last_seen", time.time())
        tracking_age = int(time.time() - ac.get("first_seen", time.time()))

        trend = ac.get("vert_trend", "level")
        vspeed_color = {"climbing": GREEN, "descending": RED}.get(trend, WHITE)
        alt_str   = f"{int(alt):,} ft" if alt else "—"
        speed_str = f"{int(speed)} kt" if speed else "—"
        gspd_str  = f"{int(gspd * 1.15078):.0f} mph" if gspd else "—"
        hdg_str   = f"{int(heading)}°" if heading else "—"
        vr_str    = f"{vspeed:+,} fpm" if vspeed else "0 fpm"
        dist_str  = f"{dist:.1f} mi"
        brg_str   = f"{int(bearing)}°"
        trk_str   = f"{int(track)}°"
        gnd_str   = "Yes" if on_gnd else "No"
        trking_str = _fmt_duration(tracking_age)
        sig_str   = f"{signal} dBm" if isinstance(signal, (int, float)) else str(signal)
        seen_str  = f"{int(seen)}s"

        rows = [
            [("ALT",     alt_str,    WHITE),
             ("SPEED",   speed_str,  WHITE),
             ("GND SPD", gspd_str,   WHITE),
             ("HEADING", hdg_str,    WHITE)],
            [("V/RATE",  vr_str,     vspeed_color),
             ("DIST",    dist_str,   WHITE),
             ("BEARING", brg_str,    WHITE),
             ("TRACK",   trk_str,    WHITE)],
            [("SQUAWK",  squawk,     YELLOW if squawk not in ("----","7700","7600","7500") else RED),
             ("GROUND",  gnd_str,    ORANGE if on_gnd else WHITE),
             ("TRACKED", trking_str, WHITE),
             ("SIGNAL",  sig_str,    WHITE)],
            [("ICAO",    icao,       ACCENT),
             ("CAT",     cat,        WHITE),
             ("MSGS",    str(msgs),  WHITE),
             ("SEEN",    seen_str,   WHITE)],
        ]

        # "Last updated" age colour
        age = time.time() - last_seen
        if age < 3:
            upd_str, upd_color = "Live", GREEN
        elif age < 10:
            upd_str, upd_color = f"Updated {age:.0f}s ago", LIGHT_GRAY
        else:
            upd_str, upd_color = f"Updated {age:.0f}s ago", ORANGE

        for ri, row_cells in enumerate(rows):
            for ci, (label, value, color) in enumerate(row_cells):
                cx  = RIGHT_X + ci * GRID_COL_W
                cy  = GRID_Y  + ri * GRID_ROW_H
                cw  = GRID_COL_W - 2
                ch  = GRID_ROW_H - 2

                pygame.draw.rect(s, MID_GRAY, (cx + 1, cy + 1, cw, ch), border_radius=4)

                # Label — small but bright, top of cell
                lbl_surf = f["xs"].render(label, True, _N4)
                s.blit(lbl_surf, (cx + 6, cy + 5))

                # Value — large bold, fits or shrinks
                val_surf = f["val"].render(value, True, color)
                if val_surf.get_width() > cw - 8:
                    val_surf = f["md"].render(value, True, color)
                if val_surf.get_width() > cw - 8:
                    val_surf = f["sm"].render(value, True, color)
                s.blit(val_surf, (cx + 6, cy + 22))

        # "Last updated" — shown in the flight-info header area, top-right of right column
        upd = f["xs"].render(upd_str, True, upd_color)
        s.blit(upd, (SCREEN_W - upd.get_width() - 8, GRID_INFO_Y + GRID_INFO_H - upd.get_height() - 4))

    # ------------------------------------------------------------------
    # Photo
    # ------------------------------------------------------------------

    def _render_photo(self, ac, x, y, w, h):
        icao = ac.get("icao_hex", "")

        if icao in self._photo_cache:
            self._screen.blit(self._photo_cache[icao], (x, y))
            return
        if icao in self._photo_failed:
            self._placeholder(x, y, w, h, "No Photo")
            return
        if icao in self._photo_fetching or icao in self._photo_pending:
            self._placeholder(x, y, w, h, "Loading…")
            return

        # Never attempted
        photo_url = ac.get("photo_url")
        print(f"[photo] FIRST ATTEMPT {icao}  photo_url={photo_url!r}", flush=True)
        if photo_url:
            self._photo_fetching.add(icao)
            threading.Thread(
                target=self._fetch_photo,
                args=(icao, photo_url, w, h),
                daemon=True,
            ).start()
            self._placeholder(x, y, w, h, "Loading…")
        else:
            self._photo_failed.add(icao)
            self._placeholder(x, y, w, h, "No Photo")

    def _fetch_photo(self, icao, url, w, h):
        print(f"[photo] START {icao}  url={url}", flush=True)
        try:
            from api_client import fetch_photo_bytes
            data = fetch_photo_bytes(url)
            if data:
                print(f"[photo] DOWNLOADED {icao}  {len(data)} bytes", flush=True)
                img = Image.open(io.BytesIO(data)).convert("RGB").resize(
                    (w, h), Image.LANCZOS
                )
                self._photo_pending[icao] = (img.tobytes(), w, h)
                print(f"[photo] PENDING SET {icao}", flush=True)
                return
            print(f"[photo] NO DATA {icao}", flush=True)
        except Exception as e:
            print(f"[photo] EXCEPTION {icao}: {e}", flush=True)
        finally:
            self._photo_fetching.discard(icao)
        self._photo_failed.add(icao)

    def _placeholder(self, x, y, w, h, text):
        pygame.draw.rect(self._screen, MID_GRAY, (x, y, w, h), border_radius=4)
        surf = self._fonts["sm"].render(text, True, LIGHT_GRAY)
        r    = surf.get_rect(center=(x + w // 2, y + h // 2))
        self._screen.blit(surf, r)

    # ------------------------------------------------------------------
    # Map
    # ------------------------------------------------------------------

    def _render_map(self, ac, x, y, w, h):
        icao     = ac.get("icao_hex", "")
        home_lat = self.config.get("lat",  47.6062)
        home_lon = self.config.get("lon", -122.3321)
        ac_lat   = ac.get("lat", home_lat)
        ac_lon   = ac.get("lon", home_lon)

        now         = time.time()
        have_surf   = icao in self._map_cache and self._map_cache[icao] is not None
        is_pending  = icao in self._map_pending
        last_fetch  = self._map_last_fetch.get(icao, 0)
        due_refresh = (now - last_fetch) >= self.MAP_REFRESH_INTERVAL

        if have_surf:
            self._screen.blit(self._map_cache[icao], (x, y))
        else:
            self._placeholder(x, y, w, h,
                              "Loading map…" if HAS_STATICMAP else "staticmap N/A")

        if HAS_STATICMAP and not is_pending and (not have_surf or due_refresh):
            self._map_pending.add(icao)
            self._map_last_fetch[icao] = now
            threading.Thread(
                target=self._fetch_map,
                args=(icao, home_lat, home_lon, ac_lat, ac_lon, w, h),
                daemon=True,
            ).start()

    def _fetch_map(self, icao, home_lat, home_lon, ac_lat, ac_lon, w, h):
        try:
            m = _sm.StaticMap(w, h)
            m.add_marker(_sm.CircleMarker((home_lon, home_lat), "white",   8))
            m.add_marker(_sm.CircleMarker((ac_lon,   ac_lat),   "#00C8FF", 10))
            m.add_line(_sm.Line([(home_lon, home_lat), (ac_lon, ac_lat)], "#00C8FF", 2))
            img  = m.render(zoom=None)
            surf = pygame.image.fromstring(img.convert("RGB").tobytes(), (w, h), "RGB")
            self._map_cache[icao] = surf
        except Exception:
            pass
        finally:
            self._map_pending.discard(icao)

    # ------------------------------------------------------------------
    # History mode
    # ------------------------------------------------------------------

    def _render_history(self):
        f       = self._fonts
        flights = self.history_flights

        if not flights:
            surf = f["lg"].render("No flight history yet", True, LIGHT_GRAY)
            r    = surf.get_rect(center=(SCREEN_W // 2, CONTENT_Y + CONTENT_H // 2))
            self._screen.blit(surf, r)
            return

        total_pages  = max(1, (len(flights) + 7) // 8)
        header = f["sm"].render(
            f"Flight History  —  Page {self.history_page + 1} of {total_pages}",
            True, ACCENT,
        )
        self._screen.blit(header, (10, CONTENT_Y + 4))

        row_h        = CONTENT_H // 8
        page_flights = flights[self.history_page * 8 : (self.history_page + 1) * 8]

        for i, fl in enumerate(page_flights):
            fy         = CONTENT_Y + i * row_h
            global_idx = self.history_page * 8 + i
            selected   = global_idx == self.selected_index

            bg = BLUE_ACCENT if selected else (MID_GRAY if i % 2 == 0 else DARK_GRAY)
            pygame.draw.rect(self._screen, bg, (0, fy, SCREEN_W, row_h - 1))

            callsign = (fl.get("callsign") or fl.get("icao_hex", "?")).ljust(8)
            origin   = fl.get("origin") or "???"
            dest     = fl.get("destination") or "???"
            alt      = fl.get("altitude") or 0
            dist     = fl.get("distance") or 0.0
            ac_type  = fl.get("aircraft_type") or fl.get("model") or "?"
            ts       = fl.get("first_seen", 0)
            ts_str   = _dt.datetime.fromtimestamp(ts).strftime("%H:%M")

            line  = f"{ts_str}  {callsign}  {origin}→{dest}  {alt:,}ft  {dist:.0f}mi  {ac_type}"
            color = BLACK if selected else WHITE
            self._screen.blit(f["sm"].render(line, True, color),
                              (8, fy + (row_h - 14) // 2))

    # ------------------------------------------------------------------
    # Buttons
    # ------------------------------------------------------------------

    # Button definitions: (icon_key, short_label, x, width, default_colour)
    _BTN_ICONS = [
        ("prev",     "PREV",    10,  135, BLUE_ACCENT),
        ("auto",     "AUTO",   155,  165, GREEN_BTN),
        ("next",     "NEXT",   330,  135, BLUE_ACCENT),
        ("history",  "HIST",   475,  155, BLUE_ACCENT),
        ("settings", "SET",    640,  150, PURPLE_BTN),
    ]

    def _render_buttons(self):
        f = self._fonts

        for i, (icon_key, label, bx, bw, color) in enumerate(self._BTN_ICONS):
            # State-dependent overrides
            if i == 1:  # AUTO
                if self._settings_open:
                    color = MID_GRAY
                elif not self.auto_rotate:
                    color    = ORANGE_BTN
                    icon_key = "pause"
                    label    = "PAUSED"
                else:
                    color = GREEN_BTN
            elif i == 3 and self.mode == "history":
                icon_key = "live"
                label    = "LIVE"
            elif i == 4 and self._settings_open:
                icon_key = "close"
                label    = "CLOSE"

            # Button background
            pygame.draw.rect(self._screen, color,
                             (bx + 2, BUTTON_Y + 2, bw - 4, BUTTON_H - 4),
                             border_radius=6)

            cx = bx + bw // 2
            cy = BUTTON_Y + BUTTON_H // 2

            if self._icon_font:
                # Icon + label stacked: icon takes upper 60%, label lower 40%
                icon_surf  = self._icon_font_sm.render(ICON[icon_key], True, WHITE)
                label_surf = f["xxs"].render(label, True, WHITE)
                total_h    = icon_surf.get_height() + 1 + label_surf.get_height()
                iy = cy - total_h // 2
                ly = iy + icon_surf.get_height() + 1
                self._screen.blit(icon_surf,  icon_surf.get_rect(centerx=cx, top=iy))
                self._screen.blit(label_surf, label_surf.get_rect(centerx=cx, top=ly))
            else:
                # Fallback: text only
                surf = f["xs"].render(label, True, WHITE)
                self._screen.blit(surf, surf.get_rect(center=(cx, cy)))

    # ------------------------------------------------------------------
    # Notifications
    # ------------------------------------------------------------------

    def _render_brief_popup(self):
        ac       = self._notification
        callsign = (ac.get("callsign") or ac.get("icao_hex", "")).strip()
        origin   = ac.get("origin") or "N/A"
        dest     = ac.get("destination") or "N/A"

        pw, ph = 230, 78
        px = SCREEN_W - pw - 6
        py = HEADER_H + 6

        surf = pygame.Surface((pw, ph), pygame.SRCALPHA)
        surf.fill((*_N10, 210))
        self._screen.blit(surf, (px, py))
        pygame.draw.rect(self._screen, _N8, (px, py, pw, ph), 2, border_radius=6)

        f  = self._fonts
        tx = px + 8

        # Row 1: icon + callsign
        row1_y = py + 10
        if self._icon_font_hdr:
            ic = self._icon_font_hdr.render(ICON["flight"], True, _N8)
            self._screen.blit(ic, (tx, row1_y + (f["sm"].get_height() - ic.get_height()) // 2))
            tx2 = tx + ic.get_width() + 5
        else:
            tx2 = tx
        self._screen.blit(f["sm"].render(callsign, True, WHITE), (tx2, row1_y))

        # Row 2: origin → dest
        route = f"{origin}  →  {dest}"
        self._screen.blit(f["xs"].render(route, True, ACCENT), (tx, py + 38))

        # Row 3: "New aircraft" label
        self._screen.blit(f["xxs"].render("New aircraft detected", True, LIGHT_GRAY), (tx, py + 58))

    def _render_summary_overlay(self):
        aircraft_list, countdown = self._summary
        overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        overlay.fill(SEMI_BLACK)
        self._screen.blit(overlay, (0, 0))

        title = self._fonts["lg"].render(
            f"{len(aircraft_list)} New Aircraft   ({countdown}s)", True, WHITE)
        r = title.get_rect(center=(SCREEN_W // 2, HEADER_H + 28))
        self._screen.blit(title, r)

        for i, ac in enumerate(aircraft_list[:8]):
            callsign = (ac.get("callsign") or ac.get("icao_hex", "")).strip()
            dest     = ac.get("destination") or ""
            alt      = ac.get("altitude", 0)
            dist     = ac.get("distance", 0)
            line     = f"{callsign}   {alt:,} ft   {dist:.0f} mi"
            if dest:
                line += f"   → {dest}"
            surf = self._fonts["sm"].render(line, True, ACCENT)
            self._screen.blit(surf, (80, HEADER_H + 64 + i * 38))

    # ------------------------------------------------------------------
    # Auto-switch banner
    # ------------------------------------------------------------------

    def _do_auto_switch(self):
        if self._switch_pending and self.live_aircraft:
            icao      = self._switch_pending.get("icao_hex")
            icao_list = [ac.get("icao_hex") for ac in self.live_aircraft]
            if icao in icao_list:
                self.selected_index = icao_list.index(icao)
                self._selected_icao = icao
        self._switch_pending = None

    def _render_auto_switch_banner(self):
        remaining = max(0.0, self._switch_deadline - time.time())
        ac        = self._switch_pending
        if ac is None:
            return

        callsign = (ac.get("callsign") or ac.get("icao_hex", "")).strip()
        origin   = ac.get("origin") or "N/A"
        dest     = ac.get("destination") or "N/A"
        route    = f"{origin} → {dest}"

        bh = 36
        by = BUTTON_Y - bh
        surf = pygame.Surface((SCREEN_W, bh), pygame.SRCALPHA)
        surf.fill((*_N10, 220))
        self._screen.blit(surf, (0, by))

        f  = self._fonts
        cx = 10  # left cursor, advances right

        # Icon
        if self._icon_font_hdr:
            ic = self._icon_font_hdr.render(ICON["flight"], True, _N8)
            self._screen.blit(ic, (cx, by + (bh - ic.get_height()) // 2))
            cx += ic.get_width() + 6

        # "New:" label
        new_lbl = f["sm"].render("New:", True, _N8)
        self._screen.blit(new_lbl, (cx, by + (bh - new_lbl.get_height()) // 2))
        cx += new_lbl.get_width() + 6

        # Callsign (bright)
        cs_surf = f["sm"].render(callsign, True, WHITE)
        self._screen.blit(cs_surf, (cx, by + (bh - cs_surf.get_height()) // 2))
        cx += cs_surf.get_width() + 10

        # Route: origin → dest (accent colour)
        rt_surf = f["sm"].render(route, True, ACCENT)
        self._screen.blit(rt_surf, (cx, by + (bh - rt_surf.get_height()) // 2))

        # Countdown + [Stay] on the right
        timer_str = f"switching in {remaining:.0f}s"
        timer_surf = f["xs"].render(timer_str, True, LIGHT_GRAY)
        stay_surf  = f["sm"].render("[Stay]", True, YELLOW)
        stay_x  = SCREEN_W - stay_surf.get_width() - 12
        timer_x = stay_x - timer_surf.get_width() - 14
        self._screen.blit(timer_surf, (timer_x, by + (bh - timer_surf.get_height()) // 2))
        self._screen.blit(stay_surf,  (stay_x,  by + (bh - stay_surf.get_height()) // 2))
        self._stay_zone = pygame.Rect(stay_x - 8, by, stay_surf.get_width() + 20, bh)

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def _render_settings(self):
        if self._settings_sub == "location":
            self._render_location_input()
        else:
            self._render_settings_main()

    def _render_settings_main(self):
        f = self._fonts
        s = self._screen

        # Settings header bar
        pygame.draw.rect(s, _N1, (0, CONTENT_Y, SCREEN_W, CONTENT_H))
        pygame.draw.rect(s, _N2, (0, CONTENT_Y, SCREEN_W, 40))
        if self._icon_font_hdr:
            ic = self._icon_font_hdr.render(ICON["settings"], True, _N8)
            s.blit(ic, (14, CONTENT_Y + (40 - ic.get_height()) // 2))
            s.blit(f["md"].render("Settings", True, WHITE),
                   (14 + ic.get_width() + 6, CONTENT_Y + 10))
        else:
            s.blit(f["md"].render("⚙  Settings", True, WHITE), (14, CONTENT_Y + 10))

        y = CONTENT_Y + 52

        # ── Section: Location ──
        y = self._settings_section_header(s, f, y, "LOCATION")
        lat = self.config.get("lat",  47.6062)
        lon = self.config.get("lon", -122.3321)
        y = self._settings_row(s, f, y, "Home Location",
                               f"{lat:.4f}°,  {lon:.4f}°", "Tap to edit address ›",
                               tap_zone_id="location")

        # ── Section: Display ──
        y = self._settings_section_header(s, f, y + 6, "DISPLAY")
        rot = self._set_rotate_interval
        y = self._settings_spinbox(s, f, y, "Auto-rotate interval",
                                   _fmt_duration(rot), "rotate")
        idle = self._set_idle_timeout
        y = self._settings_spinbox(s, f, y, "Idle timeout (min)",
                                   f"{idle} min", "idle")
        dr = self._set_display_range
        dr_str = "All" if dr >= DIST_STEPS[-1] else f"{dr} mi"
        y = self._settings_spinbox(s, f, y, "Display range",
                                   dr_str, "range")

        # ── Section: Advanced ──
        y = self._settings_section_header(s, f, y + 6, "ADVANCED")
        y = self._settings_advanced_buttons(s, f, y)

        # ── Section: System Status ──
        if y + 30 < BUTTON_Y - 10:
            y = self._settings_section_header(s, f, y + 6, "SYSTEM STATUS")
            self._settings_sysinfo(s, f, y)

        # Status message
        if self._settings_status:
            s.blit(f["xs"].render(self._settings_status, True, self._settings_scolor),
                   (14, BUTTON_Y - 18))

    def _settings_section_header(self, s, f, y, title):
        s.blit(f["xxs"].render(title, True, LIGHT_GRAY), (14, y))
        pygame.draw.line(s, MID_GRAY, (14, y + 14), (SCREEN_W - 14, y + 14), 1)
        return y + 20

    def _settings_row(self, s, f, y, label, value, hint, tap_zone_id=None):
        rh = 50
        pygame.draw.rect(s, _N2, (10, y, SCREEN_W - 20, rh), border_radius=6)
        s.blit(f["sm"].render(label, True, WHITE),      (24, y + 8))
        s.blit(f["xs"].render(value, True, ACCENT),     (24, y + 28))
        s.blit(f["xs"].render(hint,  True, LIGHT_GRAY), (SCREEN_W - f["xs"].size(hint)[0] - 24, y + 28))

        # Register tap zone
        if tap_zone_id == "location":
            self._loc_row_rect = pygame.Rect(10, y, SCREEN_W - 20, rh)

        return y + rh + 4

    def _settings_spinbox(self, s, f, y, label, value_str, key):
        rh = 44
        pygame.draw.rect(s, _N2, (10, y, SCREEN_W - 20, rh), border_radius=6)
        s.blit(f["sm"].render(label,     True, WHITE),      (24, y + 14))
        s.blit(f["md"].render(value_str, True, ACCENT),     (SCREEN_W // 2 - 40, y + 12))

        # [−] and [+] buttons
        for sym, bx in [("−", SCREEN_W - 80), ("+", SCREEN_W - 36)]:
            pygame.draw.rect(s, BLUE_ACCENT, (bx, y + 10, 28, 24), border_radius=4)
            lbl = f["sm"].render(sym, True, WHITE)
            s.blit(lbl, lbl.get_rect(center=(bx + 14, y + 22)))

        # Register tap zones
        if key == "rotate":
            self._spin_rotate_minus = pygame.Rect(SCREEN_W - 80, y + 10, 28, 24)
            self._spin_rotate_plus  = pygame.Rect(SCREEN_W - 36, y + 10, 28, 24)
        elif key == "idle":
            self._spin_idle_minus = pygame.Rect(SCREEN_W - 80, y + 10, 28, 24)
            self._spin_idle_plus  = pygame.Rect(SCREEN_W - 36, y + 10, 28, 24)
        elif key == "range":
            self._spin_range_minus = pygame.Rect(SCREEN_W - 80, y + 10, 28, 24)
            self._spin_range_plus  = pygame.Rect(SCREEN_W - 36, y + 10, 28, 24)

        return y + rh + 4

    def _settings_sysinfo(self, s, f, y):
        lines = []
        if HAS_PSUTIL:
            cpu  = psutil.cpu_percent(interval=None)
            ram  = psutil.virtual_memory()
            lines.append(f"CPU {cpu:.0f}%   RAM {ram.percent:.0f}%  ({ram.available//1024//1024} MB free)")
            try:
                temps = psutil.sensors_temperatures()
                if temps:
                    t = next(iter(temps.values()))[0].current
                    lines.append(f"Temp {t:.1f} °C")
            except Exception:
                pass
        lines.append(f"Live aircraft: {len(self.live_aircraft)}   History: {len(self.history_flights)}")

        for line in lines:
            s.blit(f["xs"].render(line, True, LIGHT_GRAY), (14, y))
            y += 18
        return y

    def _settings_advanced_buttons(self, s, f, y):
        btns = [("wifi",     "WI-FI",         BLUE_ACCENT,  10,  160),
                ("delete",   "CLEAR HISTORY", RED,          180,  200),
                ("download", "EXPORT CSV",    GREEN_BTN,    390,  180)]
        for icon_key, label, color, bx, bw in btns:
            pygame.draw.rect(s, color, (bx, y, bw, 36), border_radius=6)
            cx = bx + bw // 2
            cy = y + 18
            if self._icon_font:
                icon_surf  = self._icon_font_sm.render(ICON[icon_key], True, WHITE)
                label_surf = f["xxs"].render(label, True, WHITE)
                # side by side: icon then label
                total_w = icon_surf.get_width() + 4 + label_surf.get_width()
                ix = cx - total_w // 2
                s.blit(icon_surf,  (ix, cy - icon_surf.get_height() // 2))
                s.blit(label_surf, (ix + icon_surf.get_width() + 4,
                                    cy - label_surf.get_height() // 2))
            else:
                lbl = f["xs"].render(label, True, WHITE)
                s.blit(lbl, lbl.get_rect(center=(cx, cy)))

        # Register tap zones
        self._adv_wifi_rect    = pygame.Rect(10,  y, 160, 36)
        self._adv_clear_rect   = pygame.Rect(180, y, 200, 36)
        self._adv_export_rect  = pygame.Rect(390, y, 180, 36)
        return y + 40

    def _render_location_input(self):
        f = self._fonts
        s = self._screen

        pygame.draw.rect(s, _N1, (0, CONTENT_Y, SCREEN_W, CONTENT_H))
        pygame.draw.rect(s, _N2, (0, CONTENT_Y, SCREEN_W, 40))
        if self._icon_font_hdr:
            ic = self._icon_font_hdr.render(ICON["location"], True, _N8)
            s.blit(ic, (14, CONTENT_Y + (40 - ic.get_height()) // 2))
            s.blit(f["md"].render("Home Address", True, WHITE),
                   (14 + ic.get_width() + 6, CONTENT_Y + 10))
        else:
            s.blit(f["md"].render("📍  Home Address", True, WHITE), (14, CONTENT_Y + 10))
        back = f["sm"].render("← Back", True, ACCENT)
        s.blit(back, (SCREEN_W - back.get_width() - 14, CONTENT_Y + 12))

        # Input field
        field_y = CONTENT_Y + 50
        pygame.draw.rect(s, _N2, (10, field_y, SCREEN_W - 20, 40), border_radius=6)
        pygame.draw.rect(s, ACCENT,       (10, field_y, SCREEN_W - 20, 40), 2, border_radius=6)
        cursor  = "│"
        txt = f["md"].render(self._settings_address + cursor, True, WHITE)
        max_w = SCREEN_W - 40
        if txt.get_width() > max_w:
            txt = txt.subsurface(pygame.Rect(txt.get_width() - max_w, 0,
                                             max_w, txt.get_height()))
        s.blit(txt, (20, field_y + (40 - txt.get_height()) // 2))

        if self._settings_status:
            s.blit(f["xs"].render(self._settings_status, True, self._settings_scolor),
                   (14, field_y + 46))

        # Keyboard
        for key in self._settings_keys:
            action = key["action"]
            rect   = key["rect"]
            if action == "⇧" and self._settings_shift:
                bg = ACCENT
            elif action in ("⌫", "⇧", "SEARCH"):
                bg = _N3
            else:
                bg = MID_GRAY
            pygame.draw.rect(s, bg, rect, border_radius=4)
            lbl_text = key["label"]
            if action.isalpha() and len(action) == 1:
                lbl_text = action.upper() if self._settings_shift else action.lower()
            lbl = f["sm"].render(lbl_text, True, WHITE)
            s.blit(lbl, lbl.get_rect(center=rect.center))

    # ------------------------------------------------------------------
    # Settings touch handling
    # ------------------------------------------------------------------

    def _handle_settings_touch(self, pos):
        x, y = pos

        if self._settings_sub == "location":
            # Back button
            if CONTENT_Y <= y <= CONTENT_Y + 40 and x >= SCREEN_W - 120:
                self._settings_sub    = "main"
                self._settings_status = ""
                return
            # Keyboard keys
            for key in self._settings_keys:
                if key["rect"].collidepoint(pos):
                    self._settings_key_press(key["action"])
                    return
            return

        # Main settings sub-screen
        # Location row tap
        if hasattr(self, "_loc_row_rect") and self._loc_row_rect.collidepoint(pos):
            self._settings_sub     = "location"
            self._settings_address = ""
            self._settings_status  = ""
            return

        # Spinbox taps
        if hasattr(self, "_spin_rotate_minus") and self._spin_rotate_minus.collidepoint(pos):
            self._set_rotate_interval = max(30, self._set_rotate_interval - 30)
        elif hasattr(self, "_spin_rotate_plus") and self._spin_rotate_plus.collidepoint(pos):
            self._set_rotate_interval = min(3600, self._set_rotate_interval + 30)
        elif hasattr(self, "_spin_idle_minus") and self._spin_idle_minus.collidepoint(pos):
            self._set_idle_timeout = max(1, self._set_idle_timeout - 1)
        elif hasattr(self, "_spin_idle_plus") and self._spin_idle_plus.collidepoint(pos):
            self._set_idle_timeout = min(60, self._set_idle_timeout + 1)
        elif hasattr(self, "_spin_range_minus") and self._spin_range_minus.collidepoint(pos):
            idx = DIST_STEPS.index(self._set_display_range) if self._set_display_range in DIST_STEPS else len(DIST_STEPS) - 1
            self._set_display_range = DIST_STEPS[max(0, idx - 1)]
        elif hasattr(self, "_spin_range_plus") and self._spin_range_plus.collidepoint(pos):
            idx = DIST_STEPS.index(self._set_display_range) if self._set_display_range in DIST_STEPS else 0
            self._set_display_range = DIST_STEPS[min(len(DIST_STEPS) - 1, idx + 1)]

        # Advanced button taps
        elif hasattr(self, "_adv_wifi_rect") and self._adv_wifi_rect.collidepoint(pos):
            self._open_wifi_from_settings()
        elif hasattr(self, "_adv_clear_rect") and self._adv_clear_rect.collidepoint(pos):
            self._clear_history()
        elif hasattr(self, "_adv_export_rect") and self._adv_export_rect.collidepoint(pos):
            self._export_csv()

    def _settings_key_press(self, action):
        if action == "⌫":
            if self._settings_address:
                self._settings_address = self._settings_address[:-1]
        elif action == "⇧":
            self._settings_shift = not self._settings_shift
        elif action == "SEARCH":
            self._geocode_address()
        else:
            ch = action.upper() if (self._settings_shift and action.isalpha()) else action
            if len(self._settings_address) < 120:
                self._settings_address += ch
            if self._settings_shift and action.isalpha():
                self._settings_shift = False

    def _geocode_address(self):
        if not self._settings_address.strip():
            self._settings_status = "Please enter an address first."
            self._settings_scolor = ORANGE
            return
        self._settings_status = "Searching…"
        self._settings_scolor = ACCENT
        threading.Thread(target=self._geocode_thread, daemon=True).start()

    def _geocode_thread(self):
        from api_client import geocode_address
        result = geocode_address(self._settings_address)
        if result:
            lat, lon, name = result
            self.config["lat"] = lat
            self.config["lon"] = lon
            import config as cfg_module
            cfg_module.save_config(self.config)
            self._map_cache.clear()
            self._map_last_fetch.clear()
            short = name.split(",")[0]
            self._settings_status = f"✓  Set to {short}  ({lat:.4f}, {lon:.4f})"
            self._settings_scolor = GREEN
        else:
            self._settings_status = "Address not found.  Try a more specific address."
            self._settings_scolor = RED

    def _open_wifi_from_settings(self):
        from wifi_setup import WifiSetupScreen
        WifiSetupScreen(self._screen, self._fonts).run()

    def _clear_history(self):
        try:
            import database
            database.clear_history()
            self.history_flights = []
            self._settings_status = "History cleared."
            self._settings_scolor = GREEN
        except Exception as e:
            self._settings_status = f"Error: {e}"
            self._settings_scolor = RED

    def _export_csv(self):
        try:
            import database, csv, os
            path = os.path.expanduser("~/flight_history.csv")
            flights = database.get_history(hours=8760)  # all time
            with open(path, "w", newline="") as fh:
                if flights:
                    writer = csv.DictWriter(fh, fieldnames=flights[0].keys())
                    writer.writeheader()
                    writer.writerows(flights)
            self._settings_status = f"Exported {len(flights)} rows to {path}"
            self._settings_scolor = GREEN
        except Exception as e:
            self._settings_status = f"Export failed: {e}"
            self._settings_scolor = RED

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _draw_waiting(self):
        f  = self._fonts
        cx = SCREEN_W // 2
        cy = CONTENT_Y + CONTENT_H // 2
        t1 = f["lg"].render("Listening for aircraft…", True, LIGHT_GRAY)
        t2 = f["sm"].render("Waiting for ADS-B signal…", True, MID_GRAY)
        self._screen.blit(t1, t1.get_rect(center=(cx, cy - 18)))
        self._screen.blit(t2, t2.get_rect(center=(cx, cy + 18)))


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _fmt_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    m = seconds // 60
    s = seconds % 60
    if m < 60:
        return f"{m}m {s:02d}s"
    h = m // 60
    m = m % 60
    return f"{h}h {m:02d}m"
