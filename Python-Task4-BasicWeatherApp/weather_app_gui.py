import threading
from datetime import datetime

import requests
import tkinter as tk
from tkinter import font as tkfont

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
IPINFO_URL = "https://ipinfo.io/json"
REQUEST_TIMEOUT = 8

# WMO weather codes -> (description, emoji)
# https://open-meteo.com/en/docs
WEATHER_CODES = {
    0: ("Clear sky", "☀️"), 1: ("Mainly clear", "🌤️"), 2: ("Partly cloudy", "⛅"), 3: ("Overcast", "☁️"),
    45: ("Fog", "🌫️"), 48: ("Depositing rime fog", "🌫️"),
    51: ("Light drizzle", "🌦️"), 53: ("Moderate drizzle", "🌦️"), 55: ("Dense drizzle", "🌦️"),
    56: ("Light freezing drizzle", "🌦️"), 57: ("Dense freezing drizzle", "🌦️"),
    61: ("Slight rain", "🌧️"), 63: ("Moderate rain", "🌧️"), 65: ("Heavy rain", "🌧️"),
    66: ("Light freezing rain", "🌧️"), 67: ("Heavy freezing rain", "🌧️"),
    71: ("Slight snow fall", "🌨️"), 73: ("Moderate snow fall", "🌨️"), 75: ("Heavy snow fall", "🌨️"),
    77: ("Snow grains", "🌨️"),
    80: ("Slight rain showers", "🌧️"), 81: ("Moderate rain showers", "🌧️"), 82: ("Violent rain showers", "🌧️"),
    85: ("Slight snow showers", "🌨️"), 86: ("Heavy snow showers", "🌨️"),
    95: ("Thunderstorm", "⛈️"), 96: ("Thunderstorm with slight hail", "⛈️"), 99: ("Thunderstorm with heavy hail", "⛈️"),
}


def describe_weather_code(code):
    entry = WEATHER_CODES.get(code)
    return entry if entry else ("Unknown conditions", "🌡️")


# ---------------------------------------------------------------------------
# Color palette (real-app-ish, temperature-reactive)
# ---------------------------------------------------------------------------
THEMES = {
    "cold": {"top": "#3A5DAE", "bottom": "#7FA6DE", "accent": "#2F6FED"},
    "mild": {"top": "#2E8B9E", "bottom": "#7ED0C9", "accent": "#189A8A"},
    "warm": {"top": "#D97B3E", "bottom": "#F2C879", "accent": "#E0692F"},
}
DEFAULT_THEME = THEMES["mild"]

TEXT_DARK = "#1B2A4A"
TEXT_MUTED = "#6B7A99"
CARD_BG = "#FFFFFF"
ERROR_FG = "#B3261E"


def round_rect(canvas, x1, y1, x2, y2, radius=20, **kwargs):
    """Draw a rounded rectangle on a Canvas and return its item id."""
    points = [
        x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
        x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
        x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


def theme_for_temp(temp_c):
    if temp_c is None:
        return DEFAULT_THEME
    if temp_c < 12:
        return THEMES["cold"]
    if temp_c < 26:
        return THEMES["mild"]
    return THEMES["warm"]


class WeatherApp:
    WIDTH = 460
    VISIBLE_HEIGHT = 700  # initial on-screen window height — content can exceed
                          # this; the canvas becomes scrollable so nothing is
                          # ever cut off regardless of platform/display quirks.
    CARD_RADIUS = 20
    CARD_PAD = 20

    def __init__(self, root):
        self.root = root
        self.root.title("Weather")
        self.root.configure(bg="#3A5DAE")

        self.unit = "metric"
        self.place = None          # {"name", "country", "latitude", "longitude"}
        self.forecast_data = None  # raw Open-Meteo forecast JSON
        self.theme = DEFAULT_THEME
        self.content_height = 1200  # generous placeholder; corrected after layout

        self._build_fonts()
        self._build_widgets()

        # Now that every card has been placed we know the *real* content
        # height — resize the gradient + scroll region to match exactly,
        # and only THEN size the window. This sidesteps the macOS tkinter
        # quirk where geometry set too early (or before the true content
        # size is known) locks the window at the wrong size: we no longer
        # depend on guessing a fixed pixel height at all — if content is
        # taller than the visible window, the scrollbar handles it.
        self.content_height = int(self.y_after_error + 20)
        self._draw_gradient(self.theme)
        self.canvas.configure(scrollregion=(0, 0, self.WIDTH, self.content_height))

        self.root.update_idletasks()
        self.root.minsize(self.WIDTH + 18, 400)
        visible_height = min(self.VISIBLE_HEIGHT, self.content_height)
        self.root.geometry(f"{self.WIDTH + 18}x{visible_height}")
        self.root.resizable(True, True)

    # ------------------------------------------------------------------
    # Fonts
    # ------------------------------------------------------------------
    def _build_fonts(self):
        self.f_title = tkfont.Font(family="Segoe UI", size=15, weight="bold")
        self.f_city = tkfont.Font(family="Segoe UI", size=17, weight="bold")
        self.f_temp = tkfont.Font(family="Segoe UI", size=46, weight="bold")
        self.f_desc = tkfont.Font(family="Segoe UI", size=13)
        self.f_meta = tkfont.Font(family="Segoe UI", size=11)
        self.f_card_title = tkfont.Font(family="Segoe UI", size=11, weight="bold")
        self.f_hour = tkfont.Font(family="Segoe UI", size=10, weight="bold")
        self.f_hour_temp = tkfont.Font(family="Segoe UI", size=12, weight="bold")
        self.f_day = tkfont.Font(family="Segoe UI", size=11)
        self.f_day_temp = tkfont.Font(family="Segoe UI", size=11, weight="bold")
        # No explicit family here on purpose: "Segoe UI Emoji" only exists on
        # Windows. Leaving family unset lets Tk fall back to each platform's
        # native color-emoji font (Apple Color Emoji on macOS, Segoe UI Emoji
        # on Windows, Noto Color Emoji on most Linux setups) at the given size.
        self.f_icon_big = tkfont.Font(size=36)
        self.f_icon_small = tkfont.Font(size=18)
        self.f_icon_tiny = tkfont.Font(size=15)

    # ------------------------------------------------------------------
    # Layout construction
    # ------------------------------------------------------------------
    def _build_widgets(self):
        container = tk.Frame(self.root)
        container.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(
            container, width=self.WIDTH, height=self.content_height, highlightthickness=0
        )
        scrollbar = tk.Scrollbar(container, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Mouse wheel / trackpad scrolling (bound to the canvas area only,
        # so it doesn't hijack scrolling elsewhere if this were embedded).
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)       # Windows/macOS
        self.canvas.bind("<Button-4>", lambda e: self.canvas.yview_scroll(-1, "units"))  # Linux
        self.canvas.bind("<Button-5>", lambda e: self.canvas.yview_scroll(1, "units"))   # Linux

        self._draw_gradient(self.theme)

        y = 18
        self.canvas.create_text(
            self.WIDTH / 2, y, text="Weather", font=self.f_title, fill="white", anchor="n"
        )
        y += 34

        # --- Search row ---------------------------------------------------
        search_frame = tk.Frame(self.canvas, bg="white")
        self.canvas.create_window(
            self.WIDTH / 2, y, window=search_frame, width=self.WIDTH - 40, height=44, anchor="n"
        )
        search_frame.pack_propagate(False)

        self.city_entry = tk.Entry(
            search_frame, font=self.f_desc, bd=0, relief="flat",
            fg=TEXT_DARK, highlightthickness=0,
        )
        self.city_entry.pack(side="left", fill="both", expand=True, padx=(14, 4), pady=8)
        self.city_entry.bind("<Return>", lambda _e: self.on_get_weather())

        self.get_weather_btn = tk.Button(
            search_frame, text="Search", font=self.f_meta, bg=self.theme["accent"],
            fg="white", bd=0, relief="flat", activebackground=self.theme["accent"],
            activeforeground="white", cursor="hand2", command=self.on_get_weather,
        )
        self.get_weather_btn.pack(side="right", fill="y", padx=(0, 6), pady=6)

        y += 54

        self.locate_label = tk.Label(
            self.canvas, text="Use my location", fg="white", font=self.f_meta,
            cursor="hand2", bg=self.theme["top"],
        )
        self.canvas.create_window(self.WIDTH / 2, y, window=self.locate_label, anchor="n")
        self.locate_label.bind("<Button-1>", lambda _e: self.on_use_my_location())
        y += 26

        # --- Unit toggle (segmented pill) ----------------------------------
        toggle_frame = tk.Frame(self.canvas, bg="white")
        self.canvas.create_window(
            self.WIDTH / 2, y, window=toggle_frame, width=140, height=32, anchor="n"
        )
        self.c_btn = tk.Label(
            toggle_frame, text="°C", font=self.f_meta, bg=self.theme["accent"], fg="white",
            cursor="hand2",
        )
        self.c_btn.place(x=0, y=0, width=70, height=32)
        self.f_btn = tk.Label(
            toggle_frame, text="°F", font=self.f_meta, bg="white", fg=TEXT_MUTED,
            cursor="hand2",
        )
        self.f_btn.place(x=70, y=0, width=70, height=32)
        self.c_btn.bind("<Button-1>", lambda _e: self._set_unit("C"))
        self.f_btn.bind("<Button-1>", lambda _e: self._set_unit("F"))
        y += 44

        # --- Error banner (reserved space, hidden until needed) ------------
        self.error_text_id = self.canvas.create_text(
            self.WIDTH / 2, y, text="", fill=ERROR_FG, font=self.f_meta,
            width=self.WIDTH - 60, justify="center", anchor="n",
        )
        y += 8
        self.y_after_error = y

        # --- Current conditions card ----------------------------------------
        self.current_frame = self._add_card(height=250)
        top_row = tk.Frame(self.current_frame, bg=CARD_BG)
        top_row.pack(fill="x", pady=(4, 0))

        self.location_var = tk.StringVar(value="Search a city to begin")
        tk.Label(
            top_row, textvariable=self.location_var, font=self.f_city,
            bg=CARD_BG, fg=TEXT_DARK,
        ).pack(side="left")

        self.hilo_var = tk.StringVar(value="")
        tk.Label(
            top_row, textvariable=self.hilo_var, font=self.f_meta,
            bg=CARD_BG, fg=TEXT_MUTED,
        ).pack(side="right")

        mid_row = tk.Frame(self.current_frame, bg=CARD_BG)
        mid_row.pack(fill="x", pady=(6, 0))

        self.icon_var = tk.StringVar(value="🌡️")
        tk.Label(
            mid_row, textvariable=self.icon_var, font=self.f_icon_big, bg=CARD_BG,
        ).pack(side="left")

        temp_col = tk.Frame(mid_row, bg=CARD_BG)
        temp_col.pack(side="left", fill="x", expand=True, padx=(6, 0))

        self.temp_var = tk.StringVar(value="--°")
        tk.Label(
            temp_col, textvariable=self.temp_var, font=self.f_temp,
            bg=CARD_BG, fg=TEXT_DARK,
        ).pack(anchor="w")

        self.desc_var = tk.StringVar(value="No data yet")
        tk.Label(
            temp_col, textvariable=self.desc_var, font=self.f_desc,
            bg=CARD_BG, fg=TEXT_MUTED,
        ).pack(anchor="w")

        bottom_row = tk.Frame(self.current_frame, bg=CARD_BG)
        bottom_row.pack(fill="x", pady=(10, 0))

        self.humidity_var = tk.StringVar(value="Humidity —")
        tk.Label(
            bottom_row, textvariable=self.humidity_var, font=self.f_meta,
            bg=CARD_BG, fg=TEXT_MUTED,
        ).pack(side="left")

        self.wind_var = tk.StringVar(value="Wind —")
        tk.Label(
            bottom_row, textvariable=self.wind_var, font=self.f_meta,
            bg=CARD_BG, fg=TEXT_MUTED,
        ).pack(side="right")

        # --- Hourly forecast card --------------------------------------------
        self.hourly_frame = self._add_card(height=175, title="Next 6 hours")
        hourly_row = tk.Frame(self.hourly_frame, bg=CARD_BG)
        hourly_row.pack(fill="both", expand=True, pady=(10, 12))

        # Grid with 6 equal-width columns avoids the squeeze/overlap that
        # pack(side="left", expand=True) could cause when six items have to
        # share limited width.
        for col in range(6):
            hourly_row.grid_columnconfigure(col, weight=1, uniform="hour")

        self.hourly_slots = []
        for i in range(6):
            slot = tk.Frame(hourly_row, bg=CARD_BG)
            slot.grid(row=0, column=i, sticky="nsew")
            time_lbl = tk.Label(slot, text="--", font=self.f_hour, bg=CARD_BG, fg=TEXT_DARK)
            time_lbl.pack()
            icon_lbl = tk.Label(slot, text="", font=self.f_icon_tiny, bg=CARD_BG)
            icon_lbl.pack(pady=3)
            temp_lbl = tk.Label(slot, text="--°", font=self.f_hour_temp, bg=CARD_BG, fg=TEXT_DARK)
            temp_lbl.pack()
            self.hourly_slots.append({"time": time_lbl, "icon": icon_lbl, "temp": temp_lbl})

        # --- Daily forecast card ---------------------------------------------
        self.daily_frame = self._add_card(height=250, title="5-day forecast")

        self.daily_rows = []
        for _ in range(5):
            row = tk.Frame(self.daily_frame, bg=CARD_BG)
            row.pack(fill="x", pady=3)
            day_lbl = tk.Label(row, text="---", font=self.f_day, bg=CARD_BG, fg=TEXT_DARK, width=8, anchor="w")
            day_lbl.pack(side="left")
            icon_lbl = tk.Label(row, text="", font=self.f_icon_small, bg=CARD_BG)
            icon_lbl.pack(side="left", padx=(4, 8))
            desc_lbl = tk.Label(row, text="--", font=self.f_day, bg=CARD_BG, fg=TEXT_MUTED, anchor="w")
            desc_lbl.pack(side="left", fill="x", expand=True)
            temp_lbl = tk.Label(row, text="--°", font=self.f_day_temp, bg=CARD_BG, fg=TEXT_DARK)
            temp_lbl.pack(side="right")
            self.daily_rows.append(
                {"row": row, "day": day_lbl, "icon": icon_lbl, "desc": desc_lbl, "temp": temp_lbl}
            )

    def _add_card(self, height, title=None):
        x1, x2 = 20, self.WIDTH - 20
        y1 = self.y_after_error
        y2 = y1 + height
        round_rect(self.canvas, x1, y1, x2, y2, radius=self.CARD_RADIUS, fill=CARD_BG, outline="")

        inner = tk.Frame(self.canvas, bg=CARD_BG)
        self.canvas.create_window(
            (x1 + x2) / 2, (y1 + y2) / 2, window=inner,
            width=(x2 - x1) - 2 * self.CARD_PAD, height=(y2 - y1) - 2 * self.CARD_PAD,
        )
        inner.pack_propagate(False)

        if title:
            tk.Label(
                inner, text=title, font=self.f_card_title, bg=CARD_BG, fg=TEXT_MUTED,
            ).pack(anchor="w")

        self.y_after_error = y2 + 16
        return inner

    def _draw_gradient(self, theme):
        self.canvas.delete("bg")
        top = self._hex_to_rgb(theme["top"])
        bottom = self._hex_to_rgb(theme["bottom"])
        for i in range(self.content_height):
            ratio = i / self.content_height
            r = int(top[0] + (bottom[0] - top[0]) * ratio)
            g = int(top[1] + (bottom[1] - top[1]) * ratio)
            b = int(top[2] + (bottom[2] - top[2]) * ratio)
            color = f"#{r:02x}{g:02x}{b:02x}"
            self.canvas.create_line(0, i, self.WIDTH, i, fill=color, tags="bg")
        self.canvas.tag_lower("bg")

    def _on_mousewheel(self, event):
        # event.delta is +/-120 per notch on Windows, a small int on macOS
        # trackpads. Normalizing to +/-1 "unit" per event feels natural on
        # both without needing separate platform branches.
        direction = -1 if event.delta > 0 else 1
        self.canvas.yview_scroll(direction, "units")

    @staticmethod
    def _hex_to_rgb(hex_color):
        hex_color = hex_color.lstrip("#")
        return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))

    def _apply_theme(self, temp_c):
        theme = theme_for_temp(temp_c)
        if theme is self.theme:
            return
        self.theme = theme
        self._draw_gradient(theme)
        self.get_weather_btn.configure(bg=theme["accent"], activebackground=theme["accent"])
        self.locate_label.configure(bg=theme["top"])
        self.c_btn.configure(bg=theme["accent"] if self.unit == "metric" else "white")

    # ------------------------------------------------------------------
    # Error handling (always in the GUI, never printed to terminal)
    # ------------------------------------------------------------------
    def _show_error(self, message):
        self.canvas.itemconfig(self.error_text_id, text=message)

    def _clear_error(self):
        self.canvas.itemconfig(self.error_text_id, text="")

    def _set_loading(self, is_loading):
        self.get_weather_btn.configure(state="disabled" if is_loading else "normal")

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def on_get_weather(self):
        city = self.city_entry.get().strip()
        if not city:
            self._show_error("Please enter a city name.")
            return

        self._clear_error()
        self._set_loading(True)
        threading.Thread(target=self._fetch_and_render, args=(city,), daemon=True).start()

    def on_use_my_location(self):
        self._clear_error()
        self._set_loading(True)
        threading.Thread(target=self._locate_and_render, daemon=True).start()

    def _set_unit(self, which):
        self.unit = "metric" if which == "C" else "imperial"
        self.c_btn.configure(
            bg=self.theme["accent"] if which == "C" else "white",
            fg="white" if which == "C" else TEXT_MUTED,
        )
        self.f_btn.configure(
            bg=self.theme["accent"] if which == "F" else "white",
            fg="white" if which == "F" else TEXT_MUTED,
        )
        if self.place and self.forecast_data:
            self._render_all()

    # ------------------------------------------------------------------
    # Networking (background thread; GUI updates always via root.after)
    # ------------------------------------------------------------------
    def _fetch_and_render(self, city):
        place, error = self._geocode(city)
        if error:
            self.root.after(0, lambda: self._finish_with_error(error))
            return

        forecast, error = self._fetch_forecast(place["latitude"], place["longitude"])
        if error:
            self.root.after(0, lambda: self._finish_with_error(error))
            return

        self.root.after(0, lambda: self._finish(place, forecast))

    def _locate_and_render(self):
        try:
            resp = requests.get(IPINFO_URL, timeout=REQUEST_TIMEOUT)
        except requests.exceptions.RequestException:
            self.root.after(0, lambda: self._finish_with_error(
                "Couldn't detect your location automatically. Enter a city manually."
            ))
            return

        if resp.status_code != 200:
            self.root.after(0, lambda: self._finish_with_error(
                "Location service unavailable. Enter a city manually."
            ))
            return

        try:
            info = resp.json()
        except ValueError:
            self.root.after(0, lambda: self._finish_with_error(
                "Location service returned an invalid response."
            ))
            return

        city = info.get("city")
        if not city:
            self.root.after(0, lambda: self._finish_with_error(
                "Couldn't determine your city from your IP address."
            ))
            return

        self.root.after(0, lambda: self.city_entry.delete(0, tk.END))
        self.root.after(0, lambda: self.city_entry.insert(0, city))
        self._fetch_and_render(city)

    def _geocode(self, city):
        params = {"name": city, "count": 1, "language": "en", "format": "json"}
        try:
            resp = requests.get(GEOCODE_URL, params=params, timeout=REQUEST_TIMEOUT)
        except requests.exceptions.Timeout:
            return None, "Geocoding request timed out."
        except requests.exceptions.ConnectionError:
            return None, "Couldn't connect to the geocoding service."
        except requests.exceptions.RequestException as exc:
            return None, f"Unexpected network error: {exc}"

        if resp.status_code != 200:
            return None, f"Geocoding service error (status {resp.status_code})."
        try:
            data = resp.json()
        except ValueError:
            return None, "Received an invalid response from the geocoding service."

        results = data.get("results")
        if not results:
            return None, f"City '{city}' not found. Check the spelling."

        top = results[0]
        return {
            "latitude": top["latitude"],
            "longitude": top["longitude"],
            "name": top.get("name", city),
            "country": top.get("country", ""),
        }, None

    def _fetch_forecast(self, latitude, longitude):
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code",
            "hourly": "temperature_2m,weather_code",
            "daily": "temperature_2m_max,temperature_2m_min,weather_code",
            "timezone": "auto",
        }
        try:
            resp = requests.get(FORECAST_URL, params=params, timeout=REQUEST_TIMEOUT)
        except requests.exceptions.Timeout:
            return None, "Forecast request timed out."
        except requests.exceptions.ConnectionError:
            return None, "Couldn't connect to the forecast service."
        except requests.exceptions.RequestException as exc:
            return None, f"Unexpected network error: {exc}"

        if resp.status_code != 200:
            return None, f"Weather service error (status {resp.status_code})."
        try:
            return resp.json(), None
        except ValueError:
            return None, "Received an invalid response from the weather service."

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------
    def _finish(self, place, forecast):
        self._set_loading(False)
        self._clear_error()
        self.place = place
        self.forecast_data = forecast
        self._render_all()

    def _finish_with_error(self, message):
        self._set_loading(False)
        self._show_error(message)

    def _convert_temp(self, celsius):
        if celsius is None:
            return None, ""
        if self.unit == "metric":
            return celsius, "°"
        return (celsius * 9 / 5) + 32, "°"

    def _render_all(self):
        self._render_current()
        self._render_hourly()
        self._render_daily()

    def _render_current(self):
        place = self.place
        data = self.forecast_data
        country = place.get("country", "")
        self.location_var.set(f"{place['name']}, {country}" if country else place["name"])

        current = data.get("current", {})
        temp_c = current.get("temperature_2m")
        humidity = current.get("relative_humidity_2m")
        wind_kmh = current.get("wind_speed_10m")
        code = current.get("weather_code")

        self._apply_theme(temp_c)

        temp_val, unit_label = self._convert_temp(temp_c)
        self.temp_var.set(f"{temp_val:.0f}{unit_label}" if temp_val is not None else "--°")

        description, emoji = describe_weather_code(code) if code is not None else ("N/A", "🌡️")
        self.desc_var.set(description)
        self.icon_var.set(emoji)

        self.humidity_var.set(f"Humidity {humidity}%" if humidity is not None else "Humidity —")

        if wind_kmh is not None:
            if self.unit == "metric":
                self.wind_var.set(f"Wind {wind_kmh:.1f} km/h")
            else:
                self.wind_var.set(f"Wind {wind_kmh * 0.621371:.1f} mph")
        else:
            self.wind_var.set("Wind —")

        # Today's high/low from the daily array (index 0 = today)
        daily = data.get("daily", {})
        highs = daily.get("temperature_2m_max", [])
        lows = daily.get("temperature_2m_min", [])
        if highs and lows:
            hi_v, unit = self._convert_temp(highs[0])
            lo_v, _ = self._convert_temp(lows[0])
            self.hilo_var.set(f"H:{hi_v:.0f}{unit}  L:{lo_v:.0f}{unit}")
        else:
            self.hilo_var.set("")

    def _render_hourly(self):
        data = self.forecast_data
        hourly = data.get("hourly", {})
        times = hourly.get("time", [])
        temps = hourly.get("temperature_2m", [])
        codes = hourly.get("weather_code", [])
        current_time_str = data.get("current", {}).get("time", "")

        start_index = 0
        if current_time_str and times:
            try:
                current_dt = datetime.fromisoformat(current_time_str)
                for i, t in enumerate(times):
                    if datetime.fromisoformat(t) >= current_dt:
                        start_index = i
                        break
            except ValueError:
                start_index = 0

        entries = list(zip(times[start_index:], temps[start_index:], codes[start_index:]))[:6]

        for i, slot in enumerate(self.hourly_slots):
            if i >= len(entries):
                slot["time"].configure(text="--")
                slot["temp"].configure(text="--°")
                slot["icon"].configure(text="")
                continue

            time_str, temp_c, code = entries[i]
            try:
                dt = datetime.fromisoformat(time_str)
                label = dt.strftime("%H:%M")
            except ValueError:
                label = time_str
            slot["time"].configure(text=label)

            _desc, emoji = describe_weather_code(code) if code is not None else ("", "")
            slot["icon"].configure(text=emoji)

            temp_val, unit_label = self._convert_temp(temp_c)
            slot["temp"].configure(text=f"{temp_val:.0f}{unit_label}" if temp_val is not None else "--°")

    def _render_daily(self):
        data = self.forecast_data
        daily = data.get("daily", {})
        dates = daily.get("time", [])
        highs = daily.get("temperature_2m_max", [])
        lows = daily.get("temperature_2m_min", [])
        codes = daily.get("weather_code", [])

        entries = list(zip(dates, highs, lows, codes))[:5]
        today = datetime.now().date()

        for i, row in enumerate(self.daily_rows):
            if i >= len(entries):
                row["day"].configure(text="---")
                row["desc"].configure(text="--")
                row["temp"].configure(text="--°")
                row["icon"].configure(text="")
                continue

            date_str, hi_c, lo_c, code = entries[i]
            try:
                day_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                label = "Today" if day_date == today else day_date.strftime("%a %d")
            except ValueError:
                label = date_str
            row["day"].configure(text=label)

            description, emoji = describe_weather_code(code) if code is not None else ("N/A", "")
            row["icon"].configure(text=emoji)
            row["desc"].configure(text=description)

            hi_v, unit_label = self._convert_temp(hi_c)
            lo_v, _ = self._convert_temp(lo_c)
            if hi_v is not None and lo_v is not None:
                row["temp"].configure(text=f"{hi_v:.0f}{unit_label}/{lo_v:.0f}{unit_label}")
            else:
                row["temp"].configure(text="--°")


def main():
    root = tk.Tk()
    app = WeatherApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()