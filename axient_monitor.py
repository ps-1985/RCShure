#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RCShure - Shure Axient Digital (AD4D / AD4Q) Real-Time Monitor & Simulator
Standalone Windows Application (Zero external dependencies, Python Standard Library only)

Features:
- Dynamic Responsive Layout with Full Window Resizing
- EDIT LAYOUT Mode: Interactive synchronized resizing of all section heights across all channels (1 to 4)
- Synchronized width divider between VU Meter and Telemetry Panels
- Dual RF Antenna (A & B) Meters + 5 Purple Quality Dots (Axient Digital Standard)
- Full-Height High-Resolution Segmented VU Meter with Peak Hold
- RF Drop Event Logger in each channel (timestamps events when RF Quality <= 1/5)
- Interactive Low-Battery Blinking Alert with Click-to-Acknowledge
"""

import sys
import os
import socket
import threading
import queue
import time
import datetime
import math
import random
import re
from typing import Dict, Any, Optional, List, Callable

import tkinter as tk
from tkinter import ttk, messagebox

# ==============================================================================
# COLOR PALETTE - Broadcast Dark Control Room Theme
# ==============================================================================
THEME = {
    "bg_root": "#0B0E14",
    "bg_header": "#121722",
    "bg_card": "#171D2A",
    "bg_card_border": "#283347",
    "bg_card_inner": "#0E131D",
    "bg_log": "#090C12",
    "text_main": "#F3F6FA",
    "text_muted": "#8A99AD",
    "text_accent": "#00E5FF",
    "accent_primary": "#00B4D8",
    "accent_hover": "#0077B6",
    "status_connected": "#00E676",
    "status_sim": "#C084FC",
    "status_error": "#FF334B",
    "status_disconnected": "#64748B",
    
    # Meter Colors (Audio VU)
    "meter_green": "#00E676",
    "meter_yellow": "#FFD600",
    "meter_orange": "#FF9100",
    "meter_red": "#FF1744",
    "meter_bg": "#090D14",
    "meter_grid": "#1A2230",
    "meter_peak": "#FFFFFF",
    
    # RF Meters & 5 Purple Quality Dots
    "rf_bar_active": "#00E5FF",
    "rf_bar_inactive": "#005577",
    "rf_bar_bg": "#0D121B",
    "rf_qual_purple": "#B829E3",
    "rf_qual_purple_bright": "#D946EF",
    "rf_qual_off": "#221A30",
    
    # Battery Colors & Blinking Alert
    "batt_normal": "#00E676",
    "batt_med": "#FFB300",
    "batt_low": "#FF1744",
    "batt_alert_bg1": "#520D19",
    "batt_alert_bg2": "#1F080D",
    "batt_alert_border": "#FF1744",
    
    # LED Indicator Colors
    "led_off": "#1E2533",
    "led_mute": "#FF3D00",
    "led_interf": "#FF1744",
    "led_enc": "#00E5FF",
    "led_peak": "#FF1744",
    
    # Edit Mode & Divider Colors
    "edit_mode_active": "#FFB300",
    "divider_normal": "#242E40",
    "divider_active": "#00E5FF",
    "divider_grip": "#7E8B9F",
    "divider_grip_active": "#FFFFFF",
}

DEFAULT_SHURE_PORT = 2202


# ==============================================================================
# PROTOCOL PARSER
# ==============================================================================
class ShureParser:
    """Parses Shure Command String protocol messages."""
    
    @staticmethod
    def parse_message(raw_msg: str) -> Optional[Dict[str, Any]]:
        raw_msg = raw_msg.strip()
        if not (raw_msg.startswith("<") and raw_msg.endswith(">")):
            return None
        
        content = raw_msg[1:-1].strip()
        tokens = content.split()
        if not tokens:
            return None
        
        msg_type = tokens[0].upper()
        
        if msg_type == "SAMPLE":
            if len(tokens) < 3:
                return None
            try:
                channel = int(tokens[1])
            except ValueError:
                return None
            
            data = {"type": "SAMPLE", "channel": channel, "fields": {}}
            i = 2
            while i < len(tokens):
                key = tokens[i]
                if i + 1 < len(tokens):
                    val = tokens[i + 1]
                    data["fields"][key] = val
                    i += 2
                else:
                    data["fields"][key] = True
                    i += 1
            return data
            
        elif msg_type == "REP":
            if len(tokens) < 2:
                return None
            
            channel = None
            start_idx = 1
            if tokens[1].isdigit():
                channel = int(tokens[1])
                start_idx = 2
            
            if start_idx >= len(tokens):
                return None
                
            cmd = tokens[start_idx]
            values = tokens[start_idx + 1:]
            val_str = " ".join(values)
            
            if val_str.startswith("{") and val_str.endswith("}"):
                val_str = val_str[1:-1]
            elif val_str.startswith('"') and val_str.endswith('"'):
                val_str = val_str[1:-1]
                
            return {
                "type": "REP",
                "channel": channel,
                "command": cmd,
                "value": val_str,
                "raw_values": values
            }
            
        return {"type": msg_type, "tokens": tokens}


# ==============================================================================
# SHURE SIMULATOR (Offline Native 4-Channel AD4Q Simulator)
# ==============================================================================
class ShureSimulator(threading.Thread):
    def __init__(self, output_queue: queue.Queue):
        super().__init__(daemon=True)
        self.output_queue = output_queue
        self.running = threading.Event()
        self.running.set()
        
        self.channels = {
            1: {
                "name": "VOCAL LEAD",
                "freq": "512.450",
                "audio_level": 15,
                "audio_target": 78,
                "audio_phase": 0.0,
                "rf_a": 230,
                "rf_b": 195,
                "rf_qual": 245,
                "antenna": "A",
                "batt_mins": 480,
                "batt_bars": 5,
                "mute": False,
                "interf": False,
                "enc": True,
            },
            2: {
                "name": "VOCAL BACKING",
                "freq": "528.125",
                "audio_level": 10,
                "audio_target": 68,
                "audio_phase": 1.2,
                "rf_a": 175,
                "rf_b": 235,
                "rf_qual": 215,
                "antenna": "B",
                "batt_mins": 390,
                "batt_bars": 4,
                "mute": False,
                "interf": False,
                "enc": True,
            },
            3: {
                "name": "BASS GUITAR",
                "freq": "554.800",
                "audio_level": 20,
                "audio_target": 86,
                "audio_phase": 2.5,
                "rf_a": 190,
                "rf_b": 165,
                "rf_qual": 155,
                "antenna": "A",
                "batt_mins": 18,
                "batt_bars": 1,
                "mute": False,
                "interf": False,
                "enc": False,
            },
            4: {
                "name": "GUEST / SPARE",
                "freq": "580.375",
                "audio_level": 5,
                "audio_target": 12,
                "audio_phase": 4.0,
                "rf_a": 245,
                "rf_b": 230,
                "rf_qual": 250,
                "antenna": "A",
                "batt_mins": 540,
                "batt_bars": 5,
                "mute": True,
                "interf": False,
                "enc": True,
            }
        }
        self.step_counter = 0

    def stop(self):
        self.running.clear()

    def run(self):
        self.output_queue.put({"type": "STATUS", "status": "CONNECTED", "msg": "Simulator Mode (AD4Q 4-Ch)"})
        self.output_queue.put({"type": "REP", "channel": None, "command": "MODEL", "value": "AD4Q"})
        
        for ch, data in self.channels.items():
            self.output_queue.put({"type": "REP", "channel": ch, "command": "CHAN_NAME", "value": data["name"]})
            self.output_queue.put({"type": "REP", "channel": ch, "command": "FREQUENCY", "value": data["freq"].replace(".", "") + "0"})
            self.output_queue.put({"type": "REP", "channel": ch, "command": "ENCRYPTION", "value": "ON" if data["enc"] else "OFF"})
            self.output_queue.put({"type": "REP", "channel": ch, "command": "AUDIO_MUTE", "value": "ON" if data["mute"] else "OFF"})
            self.output_queue.put({"type": "REP", "channel": ch, "command": "TX_BATT_MINS", "value": str(data["batt_mins"])})
            self.output_queue.put({"type": "REP", "channel": ch, "command": "TX_BATT_BARS", "value": str(data["batt_bars"])})

        while self.running.is_set():
            time.sleep(0.10)
            self.step_counter += 1
            
            if self.step_counter % 320 == 120:
                target_ch = 2
                self.channels[target_ch]["interf"] = True
                self.channels[target_ch]["rf_qual"] = 28
                self.channels[target_ch]["rf_a"] = 45
                self.output_queue.put({"type": "REP", "channel": target_ch, "command": "INTERFERENCE_STATUS", "value": "DETECTED"})
            elif self.step_counter % 320 == 190:
                for ch in self.channels:
                    if self.channels[ch]["interf"]:
                        self.channels[ch]["interf"] = False
                        self.channels[ch]["rf_qual"] = 225
                        self.channels[ch]["rf_a"] = 190
                        self.output_queue.put({"type": "REP", "channel": ch, "command": "INTERFERENCE_STATUS", "value": "NONE"})

            for ch, state in self.channels.items():
                if state["mute"]:
                    audio_val = 0
                else:
                    state["audio_phase"] += 0.15
                    speech_burst = math.sin(state["audio_phase"] * 0.7) * math.cos(state["audio_phase"] * 0.3)
                    if speech_burst > 0.08:
                        raw_level = state["audio_target"] + (math.sin(state["audio_phase"] * 3.1) * 24) + (random.gauss(0, 8))
                    else:
                        raw_level = 12 + random.uniform(0, 8)
                    audio_val = max(0, min(120, int(raw_level)))
                
                state["audio_level"] = audio_val

                if not state["interf"]:
                    state["rf_a"] = max(80, min(255, state["rf_a"] + random.randint(-4, 4)))
                    state["rf_b"] = max(80, min(255, state["rf_b"] + random.randint(-4, 4)))
                    state["rf_qual"] = max(110, min(255, state["rf_qual"] + random.randint(-3, 3)))
                    state["antenna"] = "A" if state["rf_a"] >= state["rf_b"] else "B"
                
                sample_data = {
                    "type": "SAMPLE",
                    "channel": ch,
                    "fields": {
                        "AUDIO_PEAK": f"{audio_val:03d}",
                        "RF_RSSI_A": f"{state['rf_a']:03d}",
                        "RF_RSSI_B": f"{state['rf_b']:03d}",
                        "RF_QUAL": f"{state['rf_qual']:03d}",
                        "RF_ANTENNA": state["antenna"],
                        "TX_BATT_BARS": str(state["batt_bars"]),
                        "TX_BATT_MINS": str(state["batt_mins"]),
                    }
                }
                self.output_queue.put(sample_data)


# ==============================================================================
# NETWORK CLIENT THREAD (Real Hardware TCP Connection)
# ==============================================================================
class ShureClient(threading.Thread):
    def __init__(self, host: str, port: int, output_queue: queue.Queue, auto_reconnect: bool = True):
        super().__init__(daemon=True)
        self.host = host
        self.port = port
        self.output_queue = output_queue
        self.auto_reconnect = auto_reconnect
        self.running = threading.Event()
        self.running.set()
        self.sock: Optional[socket.socket] = None
        self.connected = False

    def stop(self):
        self.running.clear()
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass

    def send_cmd(self, cmd: str):
        if not self.connected or not self.sock:
            return
        if not cmd.startswith("<"):
            cmd = f"< {cmd} >"
        cmd = cmd.strip() + "\n"
        try:
            self.sock.sendall(cmd.encode("ascii"))
        except Exception as e:
            self.output_queue.put({"type": "STATUS", "status": "ERROR", "msg": f"Send Error: {e}"})

    def run(self):
        while self.running.is_set():
            self.output_queue.put({"type": "STATUS", "status": "CONNECTING", "msg": f"Connessione a {self.host}:{self.port}..."})
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.settimeout(5.0)
                self.sock.connect((self.host, self.port))
                self.connected = True
                self.output_queue.put({"type": "STATUS", "status": "CONNECTED", "msg": f"Connesso a {self.host}:{self.port}"})
                
                self.send_cmd("< GET MODEL >")
                self.send_cmd("< GET DEVICE_ID >")
                for ch in range(1, 5):
                    self.send_cmd(f"< GET {ch} CHAN_NAME >")
                    self.send_cmd(f"< GET {ch} FREQUENCY >")
                    self.send_cmd(f"< GET {ch} AUDIO_MUTE >")
                    self.send_cmd(f"< GET {ch} ENCRYPTION >")
                    self.send_cmd(f"< GET {ch} TX_BATT_MINS >")
                    self.send_cmd(f"< GET {ch} TX_BATT_BARS >")
                    self.send_cmd(f"< GET {ch} INTERFERENCE_STATUS >")
                    self.send_cmd(f"< SET {ch} METER_RATE 00100 >")
                
                self.send_cmd("< SET 0 METER_RATE 00100 >")

                buffer = ""
                self.sock.settimeout(1.0)
                while self.running.is_set():
                    try:
                        data = self.sock.recv(4096)
                        if not data:
                            raise ConnectionResetError("Connessione chiusa dal server")
                        
                        buffer += data.decode("ascii", errors="replace")
                        while "<" in buffer and ">" in buffer:
                            start = buffer.find("<")
                            end = buffer.find(">", start)
                            if end != -1:
                                raw_msg = buffer[start : end + 1]
                                buffer = buffer[end + 1 :]
                                parsed = ShureParser.parse_message(raw_msg)
                                if parsed:
                                    self.output_queue.put(parsed)
                            else:
                                break
                    except socket.timeout:
                        continue
                    except (ConnectionResetError, BrokenPipeError) as e:
                        raise e
                    except Exception as e:
                        if self.running.is_set():
                            self.output_queue.put({"type": "STATUS", "status": "ERROR", "msg": f"Errore lettura socket: {e}"})
                        break

            except Exception as e:
                self.connected = False
                if self.sock:
                    try:
                        self.sock.close()
                    except Exception:
                        pass
                if not self.running.is_set():
                    break
                    
                self.output_queue.put({"type": "STATUS", "status": "DISCONNECTED", "msg": f"Disconnesso: {e}"})
                if not self.auto_reconnect:
                    break
                for _ in range(50):
                    if not self.running.is_set():
                        break
                    time.sleep(0.1)


# ==============================================================================
# INTERACTIVE SYNCHRONIZED DRAGGABLE DIVIDERS
# ==============================================================================
class SynchronizedHorizontalDivider(tk.Canvas):
    """
    Horizontal draggable divider between sections in the right panel.
    Dragging any divider in any channel synchronizes the height across ALL channels!
    """
    def __init__(self, parent, section_key: str, app_instance, height=6, **kwargs):
        super().__init__(parent, height=height, bg=THEME["divider_normal"],
                         highlightthickness=0, cursor="sb_v_double_arrow", **kwargs)
        self.section_key = section_key
        self.app = app_instance
        self.div_height = height
        self.start_y = 0
        self.is_dragging = False
        
        self.bind("<Button-1>", self.on_press)
        self.bind("<B1-Motion>", self.on_motion)
        self.bind("<ButtonRelease-1>", self.on_release)
        self.bind("<Enter>", self.on_enter)
        self.bind("<Leave>", self.on_leave)
        self.bind("<Configure>", lambda e: self.draw_divider())
        self.draw_divider()

    def set_edit_mode(self, is_edit: bool):
        bg = THEME["divider_active"] if is_edit else THEME["divider_normal"]
        self.config(bg=bg)
        self.draw_divider()

    def draw_divider(self):
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 10:
            return
        
        is_edit = getattr(self.app, "edit_mode_active", False)
        grip_col = THEME["divider_grip_active"] if is_edit else THEME["divider_grip"]
        
        # Central grip handle dots (3 dots)
        mid_x = w // 2
        mid_y = h // 2
        for offset in [-12, 0, 12]:
            self.create_oval(mid_x + offset - 1, mid_y - 1, mid_x + offset + 1, mid_y + 1, fill=grip_col, outline="")

    def on_press(self, event):
        self.start_y = event.y_root
        self.is_dragging = True
        self.config(bg=THEME["divider_active"])

    def on_motion(self, event):
        if self.is_dragging:
            delta = event.y_root - self.start_y
            if abs(delta) >= 1:
                self.start_y = event.y_root
                self.app.adjust_shared_section_height(self.section_key, delta)

    def on_release(self, event):
        self.is_dragging = False
        is_edit = getattr(self.app, "edit_mode_active", False)
        self.config(bg=THEME["divider_active"] if is_edit else THEME["divider_normal"])
        self.draw_divider()

    def on_enter(self, event):
        self.config(bg=THEME["divider_active"])

    def on_leave(self, event):
        if not self.is_dragging:
            is_edit = getattr(self.app, "edit_mode_active", False)
            self.config(bg=THEME["divider_active"] if is_edit else THEME["divider_normal"])


class SynchronizedVerticalDivider(tk.Canvas):
    """
    Vertical draggable divider between VU Meter and Right Telemetry Panel.
    Dragging adjusts the panel split across ALL channels simultaneously!
    """
    def __init__(self, parent, app_instance, width=6, **kwargs):
        super().__init__(parent, width=width, bg=THEME["divider_normal"],
                         highlightthickness=0, cursor="sb_h_double_arrow", **kwargs)
        self.app = app_instance
        self.start_x = 0
        self.is_dragging = False
        
        self.bind("<Button-1>", self.on_press)
        self.bind("<B1-Motion>", self.on_motion)
        self.bind("<ButtonRelease-1>", self.on_release)
        self.bind("<Enter>", self.on_enter)
        self.bind("<Leave>", self.on_leave)
        self.bind("<Configure>", lambda e: self.draw_divider())
        self.draw_divider()

    def set_edit_mode(self, is_edit: bool):
        bg = THEME["divider_active"] if is_edit else THEME["divider_normal"]
        self.config(bg=bg)
        self.draw_divider()

    def draw_divider(self):
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if h < 10:
            return
        is_edit = getattr(self.app, "edit_mode_active", False)
        grip_col = THEME["divider_grip_active"] if is_edit else THEME["divider_grip"]
        mid_x = w // 2
        mid_y = h // 2
        for offset in [-12, 0, 12]:
            self.create_oval(mid_x - 1, mid_y + offset - 1, mid_x + 1, mid_y + offset + 1, fill=grip_col, outline="")

    def on_press(self, event):
        self.start_x = event.x_root
        self.is_dragging = True
        self.config(bg=THEME["divider_active"])

    def on_motion(self, event):
        if self.is_dragging:
            delta = event.x_root - self.start_x
            if abs(delta) >= 1:
                self.start_x = event.x_root
                self.app.adjust_shared_panel_width(delta)

    def on_release(self, event):
        self.is_dragging = False
        is_edit = getattr(self.app, "edit_mode_active", False)
        self.config(bg=THEME["divider_active"] if is_edit else THEME["divider_normal"])
        self.draw_divider()

    def on_enter(self, event):
        self.config(bg=THEME["divider_active"])

    def on_leave(self, event):
        if not self.is_dragging:
            is_edit = getattr(self.app, "edit_mode_active", False)
            self.config(bg=THEME["divider_active"] if is_edit else THEME["divider_normal"])


# ==============================================================================
# CUSTOM TKINTER WIDGETS
# ==============================================================================
class FullHeightVUMeter(tk.Canvas):
    def __init__(self, parent, width=32, **kwargs):
        super().__init__(parent, width=width, bg=THEME["meter_bg"],
                         highlightthickness=1, highlightbackground=THEME["bg_card_border"], **kwargs)
        self.meter_width = width
        self.meter_height = 340
        self.current_val = 0.0
        self.peak_val = 0.0
        self.peak_hold_ticks = 0
        self.num_segments = 38
        self.bind("<Configure>", self.on_resize)

    def on_resize(self, event):
        if event.height > 20:
            self.meter_height = event.height
            self.meter_width = event.width
            self.draw_meter()

    def set_level(self, val_0_120: float):
        self.current_val = max(0.0, min(120.0, float(val_0_120)))
        if self.current_val >= self.peak_val:
            self.peak_val = self.current_val
            self.peak_hold_ticks = 20
        else:
            if self.peak_hold_ticks > 0:
                self.peak_hold_ticks -= 1
            else:
                self.peak_val = max(0.0, self.peak_val - 2.2)
        self.draw_meter()

    def draw_meter(self):
        self.delete("all")
        margin_x = 4
        margin_y = 6
        usable_w = max(4, self.meter_width - (margin_x * 2))
        usable_h = max(20, self.meter_height - (margin_y * 2))
        seg_h = usable_h / self.num_segments
        gap = 2

        for i in range(self.num_segments):
            ratio = (i + 1) / self.num_segments
            seg_level = ratio * 120.0
            
            y2 = self.meter_height - margin_y - (i * seg_h)
            y1 = y2 - (seg_h - gap)
            x1 = margin_x
            x2 = margin_x + usable_w

            if i >= self.num_segments - 3:
                active_color = THEME["meter_red"]
            elif i >= self.num_segments - 11:
                active_color = THEME["meter_orange"]
            elif i >= self.num_segments - 22:
                active_color = THEME["meter_yellow"]
            else:
                active_color = THEME["meter_green"]

            fill_col = active_color if self.current_val >= seg_level else THEME["meter_grid"]
            self.create_rectangle(x1, y1, x2, y2, fill=fill_col, outline="", width=0)

        if self.peak_val > 6:
            peak_ratio = min(1.0, self.peak_val / 120.0)
            peak_y = self.meter_height - margin_y - (peak_ratio * usable_h)
            self.create_line(margin_x - 1, peak_y, margin_x + usable_w + 1, peak_y,
                             fill=THEME["meter_peak"], width=2)


class DualRFMeter(tk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=THEME["bg_card_inner"], **kwargs)
        self.rf_a_val = 0
        self.rf_b_val = 0
        self.active_ant = "A"
        self.qual_val = 0
        self.num_dots_active = 0
        self.setup_ui()

    def setup_ui(self):
        top_row = tk.Frame(self, bg=THEME["bg_card_inner"])
        top_row.pack(fill="x", pady=(0, 4))
        
        tk.Label(top_row, text="RF LINK", font=("Segoe UI", 9, "bold"),
                 fg=THEME["text_muted"], bg=THEME["bg_card_inner"]).pack(side="left")
        
        qual_box = tk.Frame(top_row, bg=THEME["bg_card_inner"])
        qual_box.pack(side="right")
        
        self.lbl_qual_txt = tk.Label(qual_box, text="QUAL", font=("Segoe UI", 8, "bold"),
                                     fg=THEME["rf_qual_purple_bright"], bg=THEME["bg_card_inner"])
        self.lbl_qual_txt.pack(side="left", padx=(0, 6))
        
        self.qual_canvas = tk.Canvas(qual_box, width=75, height=14, bg=THEME["bg_card_inner"], highlightthickness=0)
        self.qual_canvas.pack(side="left")

        # Antenna A
        row_a = tk.Frame(self, bg=THEME["bg_card_inner"])
        row_a.pack(fill="x", pady=1)
        self.lbl_ant_a = tk.Label(row_a, text="A", font=("Consolas", 9, "bold"),
                                  fg=THEME["rf_bar_active"], bg=THEME["bg_card_inner"], width=2)
        self.lbl_ant_a.pack(side="left", padx=(0, 4))
        self.bar_a = tk.Canvas(row_a, height=10, bg=THEME["rf_bar_bg"], highlightthickness=1, highlightbackground=THEME["bg_card_border"])
        self.bar_a.pack(side="left", fill="x", expand=True)

        # Antenna B
        row_b = tk.Frame(self, bg=THEME["bg_card_inner"])
        row_b.pack(fill="x", pady=1)
        self.lbl_ant_b = tk.Label(row_b, text="B", font=("Consolas", 9, "bold"),
                                  fg=THEME["text_muted"], bg=THEME["bg_card_inner"], width=2)
        self.lbl_ant_b.pack(side="left", padx=(0, 4))
        self.bar_b = tk.Canvas(row_b, height=10, bg=THEME["rf_bar_bg"], highlightthickness=1, highlightbackground=THEME["bg_card_border"])
        self.bar_b.pack(side="left", fill="x", expand=True)

        self.bar_a.bind("<Configure>", lambda e: self.draw_bars())
        self.bar_b.bind("<Configure>", lambda e: self.draw_bars())
        self.draw_purple_dots(0)

    def set_rf_data(self, rf_a: int, rf_b: int, active_ant: str, qual_0_255: int) -> int:
        self.rf_a_val = max(0, min(255, int(rf_a)))
        self.rf_b_val = max(0, min(255, int(rf_b)))
        self.active_ant = active_ant.upper()
        self.qual_val = max(0, min(255, int(qual_0_255)))
        
        if self.active_ant == "A":
            self.lbl_ant_a.config(fg=THEME["status_connected"])
            self.lbl_ant_b.config(fg=THEME["text_muted"])
        else:
            self.lbl_ant_a.config(fg=THEME["text_muted"])
            self.lbl_ant_b.config(fg=THEME["status_connected"])

        if self.qual_val >= 220:
            num_dots = 5
        elif self.qual_val >= 170:
            num_dots = 4
        elif self.qual_val >= 120:
            num_dots = 3
        elif self.qual_val >= 70:
            num_dots = 2
        elif self.qual_val >= 30:
            num_dots = 1
        else:
            num_dots = 0

        self.num_dots_active = num_dots
        self.draw_purple_dots(num_dots)
        self.draw_bars()
        return num_dots

    def draw_purple_dots(self, active_count: int):
        self.qual_canvas.delete("all")
        dot_r = 5
        gap = 14
        start_x = 7
        y = 7
        for i in range(5):
            x = start_x + (i * gap)
            is_lit = (i < active_count)
            col = THEME["rf_qual_purple_bright"] if is_lit else THEME["rf_qual_off"]
            outline_col = THEME["rf_qual_purple"] if is_lit else "#2E243D"
            self.qual_canvas.create_oval(x - dot_r, y - dot_r, x + dot_r, y + dot_r, fill=col, outline=outline_col, width=1)

    def draw_bars(self):
        self.bar_a.delete("all")
        w_a = self.bar_a.winfo_width()
        h_a = self.bar_a.winfo_height()
        if w_a > 10:
            fill_w_a = int((w_a - 4) * (self.rf_a_val / 255.0))
            col_a = THEME["rf_bar_active"] if self.active_ant == "A" else THEME["rf_bar_inactive"]
            if fill_w_a > 0:
                self.bar_a.create_rectangle(2, 2, 2 + fill_w_a, h_a - 2, fill=col_a, outline="")

        self.bar_b.delete("all")
        w_b = self.bar_b.winfo_width()
        h_b = self.bar_b.winfo_height()
        if w_b > 10:
            fill_w_b = int((w_b - 4) * (self.rf_b_val / 255.0))
            col_b = THEME["rf_bar_active"] if self.active_ant == "B" else THEME["rf_bar_inactive"]
            if fill_w_b > 0:
                self.bar_b.create_rectangle(2, 2, 2 + fill_w_b, h_b - 2, fill=col_b, outline="")


class BatteryGauge(tk.Canvas):
    def __init__(self, parent, width=46, height=20, **kwargs):
        super().__init__(parent, width=width, height=height, bg=THEME["bg_card_inner"],
                         highlightthickness=0, **kwargs)
        self.w = width
        self.h = height
        self.bars = 5
        self.mins = 480
        self.draw_battery()

    def set_battery(self, mins: int, bars: Optional[int] = None):
        self.mins = max(0, int(mins))
        if bars is not None:
            self.bars = max(0, min(5, int(bars)))
        else:
            self.bars = min(5, max(0, int(self.mins / 100)))
        self.draw_battery()

    def draw_battery(self):
        self.delete("all")
        bx1, by1, bx2, by2 = 2, 3, self.w - 8, self.h - 3
        self.create_rectangle(bx1, by1, bx2, by2, outline=THEME["text_muted"], width=1)
        self.create_rectangle(bx2, by1 + 4, self.w - 4, by2 - 4, fill=THEME["text_muted"], outline="")

        if self.mins < 60 or self.bars <= 1:
            col = THEME["batt_low"]
        elif self.mins < 180 or self.bars <= 2:
            col = THEME["batt_med"]
        else:
            col = THEME["batt_normal"]

        inner_w = (bx2 - bx1) - 4
        fill_w = int(inner_w * (self.bars / 5.0))
        if fill_w > 0:
            self.create_rectangle(bx1 + 2, by1 + 2, bx1 + 2 + fill_w, by2 - 2, fill=col, outline="")


class StatusLED(tk.Canvas):
    def __init__(self, parent, label: str, active_color: str, size=14, **kwargs):
        super().__init__(parent, width=size, height=size, bg=THEME["bg_card_inner"],
                         highlightthickness=0, **kwargs)
        self.size = size
        self.label_text = label
        self.active_color = active_color
        self.is_active = False
        self.draw_led()

    def set_state(self, active: bool):
        if self.is_active != active:
            self.is_active = active
            self.draw_led()

    def draw_led(self):
        self.delete("all")
        fill_col = self.active_color if self.is_active else THEME["led_off"]
        outline_col = "#444" if not self.is_active else fill_col
        pad = 2
        self.create_oval(pad, pad, self.size - pad, self.size - pad, fill=fill_col, outline=outline_col, width=1)
        if self.is_active:
            self.create_oval(pad + 2, pad + 2, pad + 5, pad + 5, fill="#FFFFFF", outline="")


# ==============================================================================
# CHANNEL MONITOR CARD (With Interactive Section Resizers)
# ==============================================================================
class ChannelCard(tk.Frame):
    def __init__(self, parent, channel_num: int, app_instance):
        super().__init__(parent, bg=THEME["bg_card"], bd=1, relief="solid",
                         highlightbackground=THEME["bg_card_border"], highlightthickness=1)
        self.channel_num = channel_num
        self.app = app_instance
        self.last_audio_peak = 0
        
        self.is_blinking_battery = False
        self.battery_acked = False
        self.blink_phase = False
        self.curr_batt_mins = 480
        
        self.last_rf_qual_dots = 5
        self.in_drop_state = False
        self.drop_event_count = 0
        
        self.dividers: List[SynchronizedHorizontalDivider] = []
        self.vert_divider: Optional[SynchronizedVerticalDivider] = None
        
        self.setup_ui()

    def setup_ui(self):
        # 1. Top Channel Header
        header_frame = tk.Frame(self, bg=THEME["bg_card_inner"], padx=10, pady=6)
        header_frame.pack(fill="x", side="top")
        
        ch_badge = tk.Label(header_frame, text=f"CH {self.channel_num}", font=("Segoe UI", 11, "bold"),
                            fg=THEME["bg_root"], bg=THEME["text_accent"], padx=8, pady=1)
        ch_badge.pack(side="left")
        
        self.freq_label = tk.Label(header_frame, text="---.--- MHz", font=("Consolas", 11, "bold"),
                                   fg=THEME["text_accent"], bg=THEME["bg_card_inner"])
        self.freq_label.pack(side="right")

        # 2. Channel Name Banner
        name_frame = tk.Frame(self, bg=THEME["bg_card"], padx=10, pady=4)
        name_frame.pack(fill="x")
        
        self.name_label = tk.Label(name_frame, text=f"CHANNEL {self.channel_num}", font=("Segoe UI", 13, "bold"),
                                   fg=THEME["text_main"], bg=THEME["bg_card"], anchor="w")
        self.name_label.pack(fill="x")

        # 3. Main Body Frame
        body_frame = tk.Frame(self, bg=THEME["bg_card"], padx=6, pady=4)
        body_frame.pack(fill="both", expand=True)

        # Left: Full-Height Dynamic VU Meter + Scale
        self.meter_container = tk.Frame(body_frame, bg=THEME["bg_card"])
        self.meter_container.pack(side="left", fill="both", expand=True, padx=(0, 2))

        scale_frame = tk.Frame(self.meter_container, bg=THEME["bg_card"])
        scale_frame.pack(side="left", fill="y", padx=(0, 2))
        for db in ["0", "-6", "-12", "-18", "-24", "-36", "-60"]:
            lbl = tk.Label(scale_frame, text=db, font=("Consolas", 8, "bold"), fg=THEME["text_muted"], bg=THEME["bg_card"])
            lbl.pack(side="top", expand=True)

        self.vu_meter = FullHeightVUMeter(self.meter_container, width=28)
        self.vu_meter.pack(side="left", fill="both", expand=True)

        # Vertical Divider (Between VU Meter and Right Panel)
        self.vert_divider = SynchronizedVerticalDivider(body_frame, self.app, width=5)
        self.vert_divider.pack(side="left", fill="y", padx=2)

        # Right: Telemetry Column with 4 Resizable Sections & 3 Horizontal Dividers
        self.right_panel = tk.Frame(body_frame, bg=THEME["bg_card"], width=self.app.shared_right_panel_width)
        self.right_panel.pack(side="right", fill="both", expand=False)
        self.right_panel.pack_propagate(False)

        # SECTION 1: DUAL RF LINK
        self.frame_rf = tk.Frame(self.right_panel, bg=THEME["bg_card_inner"],
                                 height=self.app.shared_section_heights["rf"],
                                 highlightthickness=1, highlightbackground=THEME["bg_card_border"])
        self.frame_rf.pack(fill="x", side="top")
        self.frame_rf.pack_propagate(False)

        self.rf_meter = DualRFMeter(self.frame_rf, padx=6, pady=4)
        self.rf_meter.pack(fill="both", expand=True)

        # DIVIDER 1: RF -> TX
        div1 = SynchronizedHorizontalDivider(self.right_panel, "rf", self.app)
        div1.pack(fill="x", side="top", pady=2)
        self.dividers.append(div1)

        # SECTION 2: TRANSMITTER (TX)
        self.frame_tx = tk.Frame(self.right_panel, bg=THEME["bg_card_inner"],
                                 height=self.app.shared_section_heights["tx"],
                                 highlightthickness=1, highlightbackground=THEME["bg_card_border"], cursor="hand2")
        self.frame_tx.pack(fill="x", side="top")
        self.frame_tx.pack_propagate(False)
        self.frame_tx.bind("<Button-1>", self.on_tx_box_click)

        tx_title_frame = tk.Frame(self.frame_tx, bg=THEME["bg_card_inner"], padx=6, pady=2)
        tx_title_frame.pack(fill="x")
        tx_title_frame.bind("<Button-1>", self.on_tx_box_click)
        
        lbl_tx = tk.Label(tx_title_frame, text="TRANSMITTER (TX)", font=("Segoe UI", 8, "bold"),
                          fg=THEME["text_muted"], bg=THEME["bg_card_inner"])
        lbl_tx.pack(side="left")
        lbl_tx.bind("<Button-1>", self.on_tx_box_click)

        batt_row = tk.Frame(self.frame_tx, bg=THEME["bg_card_inner"], padx=6)
        batt_row.pack(fill="x", pady=(0, 2))
        batt_row.bind("<Button-1>", self.on_tx_box_click)
        
        self.batt_gauge = BatteryGauge(batt_row, width=42, height=18)
        self.batt_gauge.pack(side="left", padx=(0, 4))
        self.batt_gauge.bind("<Button-1>", self.on_tx_box_click)

        self.batt_time_label = tk.Label(batt_row, text="--h --m", font=("Consolas", 9, "bold"),
                                        fg=THEME["text_main"], bg=THEME["bg_card_inner"])
        self.batt_time_label.pack(side="left")
        self.batt_time_label.bind("<Button-1>", self.on_tx_box_click)

        self.batt_alert_label = tk.Label(self.frame_tx, text="BATTERY OK", font=("Segoe UI", 7, "bold"),
                                         fg=THEME["status_connected"], bg=THEME["bg_card_inner"], padx=6)
        self.batt_alert_label.pack(anchor="w")
        self.batt_alert_label.bind("<Button-1>", self.on_tx_box_click)

        self.ack_hint_label = tk.Label(self.frame_tx, text="", font=("Segoe UI", 7, "italic"),
                                       fg=THEME["text_muted"], bg=THEME["bg_card_inner"], padx=6)
        self.ack_hint_label.pack(anchor="w")
        self.ack_hint_label.bind("<Button-1>", self.on_tx_box_click)

        # DIVIDER 2: TX -> FLAGS
        div2 = SynchronizedHorizontalDivider(self.right_panel, "tx", self.app)
        div2.pack(fill="x", side="top", pady=2)
        self.dividers.append(div2)

        # SECTION 3: STATUS FLAGS
        self.frame_flags = tk.Frame(self.right_panel, bg=THEME["bg_card_inner"],
                                    height=self.app.shared_section_heights["flags"],
                                    highlightthickness=1, highlightbackground=THEME["bg_card_border"])
        self.frame_flags.pack(fill="x", side="top")
        self.frame_flags.pack_propagate(False)

        tk.Label(self.frame_flags, text="STATUS FLAGS", font=("Segoe UI", 8, "bold"),
                 fg=THEME["text_muted"], bg=THEME["bg_card_inner"], padx=6, pady=2).pack(anchor="w")

        led_grid = tk.Frame(self.frame_flags, bg=THEME["bg_card_inner"], padx=6)
        led_grid.pack(fill="x")

        # Row 1: Mute & Peak
        r1 = tk.Frame(led_grid, bg=THEME["bg_card_inner"])
        r1.pack(fill="x", pady=1)
        self.led_mute = StatusLED(r1, "MUTE", THEME["led_mute"], size=12)
        self.led_mute.pack(side="left", padx=(0, 3))
        tk.Label(r1, text="MUTE", font=("Segoe UI", 7, "bold"), fg=THEME["text_main"], bg=THEME["bg_card_inner"]).pack(side="left", padx=(0, 8))

        self.led_peak = StatusLED(r1, "CLIP", THEME["led_peak"], size=12)
        self.led_peak.pack(side="left", padx=(0, 3))
        tk.Label(r1, text="PEAK", font=("Segoe UI", 7, "bold"), fg=THEME["text_main"], bg=THEME["bg_card_inner"]).pack(side="left")

        # Row 2: Interference & Encryption
        r2 = tk.Frame(led_grid, bg=THEME["bg_card_inner"])
        r2.pack(fill="x", pady=1)
        self.led_interf = StatusLED(r2, "INTERF", THEME["led_interf"], size=12)
        self.led_interf.pack(side="left", padx=(0, 3))
        tk.Label(r2, text="INTERF", font=("Segoe UI", 7, "bold"), fg=THEME["text_main"], bg=THEME["bg_card_inner"]).pack(side="left", padx=(0, 6))

        self.led_enc = StatusLED(r2, "ENC", THEME["led_enc"], size=12)
        self.led_enc.pack(side="left", padx=(0, 3))
        tk.Label(r2, text="ENCR", font=("Segoe UI", 7, "bold"), fg=THEME["text_main"], bg=THEME["bg_card_inner"]).pack(side="left")

        # DIVIDER 3: FLAGS -> LOG
        div3 = SynchronizedHorizontalDivider(self.right_panel, "flags", self.app)
        div3.pack(fill="x", side="top", pady=2)
        self.dividers.append(div3)

        # SECTION 4: RF DROPS (<=1/5) LOG
        self.frame_log = tk.Frame(self.right_panel, bg=THEME["bg_log"],
                                  height=self.app.shared_section_heights["log"],
                                  highlightthickness=1, highlightbackground=THEME["bg_card_border"])
        self.frame_log.pack(fill="both", expand=True, side="top")

        log_header = tk.Frame(self.frame_log, bg=THEME["bg_log"], padx=4, pady=2)
        log_header.pack(fill="x")
        
        self.lbl_log_title = tk.Label(log_header, text="📉 RF DROPS: 0", font=("Segoe UI", 8, "bold"),
                                      fg=THEME["rf_qual_purple_bright"], bg=THEME["bg_log"])
        self.lbl_log_title.pack(side="left")
        
        btn_clear = tk.Button(log_header, text="CLR", font=("Segoe UI", 7, "bold"),
                              fg=THEME["text_muted"], bg=THEME["bg_card"], bd=0, padx=3, cursor="hand2",
                              command=self.clear_drop_log)
        btn_clear.pack(side="right")

        self.log_list = tk.Listbox(self.frame_log, font=("Consolas", 8), bg=THEME["bg_log"], fg=THEME["text_muted"],
                                   selectbackground=THEME["bg_card_border"], selectforeground="#FFF",
                                   bd=0, highlightthickness=0)
        self.log_list.pack(fill="both", expand=True, padx=2, pady=(0, 2))

    def update_section_heights(self, heights: Dict[str, int]):
        """Synchronously updates the section heights on this channel."""
        self.frame_rf.config(height=heights["rf"])
        self.frame_tx.config(height=heights["tx"])
        self.frame_flags.config(height=heights["flags"])
        self.frame_log.config(height=heights["log"])

    def update_panel_width(self, width: int):
        self.right_panel.config(width=width)

    def set_edit_mode(self, is_edit: bool):
        for div in self.dividers:
            div.set_edit_mode(is_edit)
        if self.vert_divider:
            self.vert_divider.set_edit_mode(is_edit)

    def log_rf_drop(self, dots: int, details: str = ""):
        now_str = datetime.datetime.now().strftime("%H:%M:%S")
        self.drop_event_count += 1
        entry = f"[{now_str}] {dots}/5 {details}"
        self.log_list.insert(0, entry)
        if self.log_list.size() > 60:
            self.log_list.delete("end")
        self.lbl_log_title.config(text=f"📉 RF DROPS: {self.drop_event_count}", fg=THEME["meter_red"])

    def clear_drop_log(self):
        self.log_list.delete(0, "end")
        self.drop_event_count = 0
        self.lbl_log_title.config(text="📉 RF DROPS: 0", fg=THEME["rf_qual_purple_bright"])

    def on_tx_box_click(self, event=None):
        if self.is_blinking_battery:
            self.battery_acked = True
            self.is_blinking_battery = False
            self.ack_hint_label.config(text="[ALLARME SILENZIATO]")
            self.frame_tx.config(bg=THEME["bg_card_inner"], highlightbackground=THEME["batt_low"], highlightthickness=2)
            self.apply_tx_box_bg(THEME["bg_card_inner"])

    def apply_tx_box_bg(self, bg_color: str):
        for widget in [self.frame_tx, self.batt_time_label, self.batt_alert_label, self.ack_hint_label]:
            try:
                widget.config(bg=bg_color)
            except Exception:
                pass

    def update_name(self, name: str):
        clean_name = name.strip()
        self.name_label.config(text=clean_name if clean_name else f"CHANNEL {self.channel_num}")

    def update_frequency(self, freq_str: str):
        try:
            digits = re.sub(r"[^\d]", "", freq_str)
            if len(digits) >= 6:
                mhz = f"{digits[:3]}.{digits[3:6]}"
                self.freq_label.config(text=f"{mhz} MHz")
            elif len(digits) >= 3:
                self.freq_label.config(text=f"{digits} MHz")
            else:
                self.freq_label.config(text=f"{freq_str} MHz")
        except Exception:
            self.freq_label.config(text=f"{freq_str}")

    def update_sample(self, fields: Dict[str, Any]):
        if "AUDIO_PEAK" in fields:
            try:
                val = float(fields["AUDIO_PEAK"])
                self.last_audio_peak = val
                self.vu_meter.set_level(val)
                self.led_peak.set_state(val >= 115)
            except ValueError:
                pass

        rf_a = fields.get("RF_RSSI_A", fields.get("RF_QUAL", 200))
        rf_b = fields.get("RF_RSSI_B", int(int(rf_a) * 0.9) if str(rf_a).isdigit() else 180)
        rf_ant = fields.get("RF_ANTENNA", "A")
        rf_qual = fields.get("RF_QUAL", 230)
        
        try:
            dots = self.rf_meter.set_rf_data(int(rf_a), int(rf_b), str(rf_ant), int(rf_qual))
            if dots <= 1:
                if not self.in_drop_state:
                    self.in_drop_state = True
                    self.log_rf_drop(dots, f"(Ant {rf_ant})")
            else:
                self.in_drop_state = False
            self.last_rf_qual_dots = dots
        except (ValueError, TypeError):
            pass

        mins = None
        bars = None
        if "TX_BATT_MINS" in fields:
            try:
                mins = int(fields["TX_BATT_MINS"])
            except ValueError:
                pass
        if "TX_BATT_BARS" in fields:
            try:
                bars = int(fields["TX_BATT_BARS"])
            except ValueError:
                pass
                
        if mins is not None:
            self.update_battery(mins, bars)

    def update_battery(self, mins: int, bars: Optional[int] = None):
        self.curr_batt_mins = mins
        self.batt_gauge.set_battery(mins, bars)
        
        if mins == 65535 or mins < 0:
            self.batt_time_label.config(text="--h --m", fg=THEME["text_muted"])
            self.batt_alert_label.config(text="DISCONNECTED", fg=THEME["text_muted"])
            self.is_blinking_battery = False
            self.ack_hint_label.config(text="")
        else:
            hrs = mins // 60
            m = mins % 60
            self.batt_time_label.config(text=f"{hrs}h {m:02d}m")
            
            if mins < 60 or (bars is not None and bars <= 1):
                self.batt_time_label.config(fg=THEME["batt_low"])
                self.batt_alert_label.config(text="LOW BATTERY (<20%)", fg=THEME["batt_low"])
                if not self.battery_acked:
                    self.is_blinking_battery = True
                    self.ack_hint_label.config(text="[CLICCA PER TACITARE]")
            else:
                self.battery_acked = False
                self.is_blinking_battery = False
                self.batt_time_label.config(fg=THEME["text_main"])
                self.batt_alert_label.config(text="BATTERY OK", fg=THEME["status_connected"])
                self.ack_hint_label.config(text="")
                self.frame_tx.config(bg=THEME["bg_card_inner"], highlightbackground=THEME["bg_card_border"], highlightthickness=1)
                self.apply_tx_box_bg(THEME["bg_card_inner"])

    def tick_blink(self):
        if self.is_blinking_battery and not self.battery_acked:
            self.blink_phase = not self.blink_phase
            bg_col = THEME["batt_alert_bg1"] if self.blink_phase else THEME["batt_alert_bg2"]
            border_col = THEME["batt_alert_border"] if self.blink_phase else THEME["bg_card_border"]
            self.frame_tx.config(bg=bg_col, highlightbackground=border_col, highlightthickness=2)
            self.apply_tx_box_bg(bg_col)

    def update_mute(self, is_muted: bool):
        self.led_mute.set_state(is_muted)

    def update_interference(self, is_interf: bool):
        self.led_interf.set_state(is_interf)
        if is_interf:
            self.log_rf_drop(self.last_rf_qual_dots, "[INTERFERENZA]")

    def update_encryption(self, is_enc: bool):
        self.led_enc.set_state(is_enc)


# ==============================================================================
# MAIN APPLICATION WINDOW (With Synchronized Section Resizing)
# ==============================================================================
class AxientMonitorApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("RCShure - Shure Axient Digital Real-Time Monitor")
        self.root.geometry("1280x720")
        self.root.minsize(960, 580)
        self.root.configure(bg=THEME["bg_root"])
        
        self.queue: queue.Queue = queue.Queue()
        self.network_client: Optional[ShureClient] = None
        self.simulator: Optional[ShureSimulator] = None
        self.is_connected = False
        self.channel_count = 4
        self.channels: Dict[int, ChannelCard] = {}
        
        # Shared Synchronized Layout Heights & Width
        self.shared_section_heights = {
            "rf": 74,
            "tx": 78,
            "flags": 74,
            "log": 160,
        }
        self.shared_right_panel_width = 190
        self.edit_mode_active = False

        self.setup_ui()
        self.process_queue()
        self.blink_loop()

    def setup_ui(self):
        # 1. Top Header Control Bar
        header = tk.Frame(self.root, bg=THEME["bg_header"], padx=18, pady=10,
                          highlightthickness=1, highlightbackground=THEME["bg_card_border"])
        header.pack(fill="x", side="top")

        brand_frame = tk.Frame(header, bg=THEME["bg_header"])
        brand_frame.pack(side="left", padx=(0, 18))
        
        title_lbl = tk.Label(brand_frame, text="RCShure", font=("Segoe UI", 18, "bold"),
                             fg=THEME["text_accent"], bg=THEME["bg_header"])
        title_lbl.pack(side="left")
        
        sub_lbl = tk.Label(brand_frame, text="Axient Digital Monitor", font=("Segoe UI", 10),
                           fg=THEME["text_muted"], bg=THEME["bg_header"])
        sub_lbl.pack(side="left", padx=(8, 0), pady=(4, 0))

        ctrl_frame = tk.Frame(header, bg=THEME["bg_header"])
        ctrl_frame.pack(side="left")

        tk.Label(ctrl_frame, text="IP:", font=("Segoe UI", 10, "bold"),
                 fg=THEME["text_main"], bg=THEME["bg_header"]).pack(side="left", padx=(0, 6))
        
        self.ip_var = tk.StringVar(value="192.168.1.50")
        self.ip_entry = tk.Entry(ctrl_frame, textvariable=self.ip_var, font=("Consolas", 11),
                                 bg=THEME["bg_card_inner"], fg=THEME["text_main"],
                                 insertbackground=THEME["text_accent"], width=14, bd=1, relief="solid")
        self.ip_entry.pack(side="left", padx=(0, 10))

        tk.Label(ctrl_frame, text="Port:", font=("Segoe UI", 10),
                 fg=THEME["text_muted"], bg=THEME["bg_header"]).pack(side="left", padx=(0, 4))
        self.port_var = tk.StringVar(value=str(DEFAULT_SHURE_PORT))
        self.port_entry = tk.Entry(ctrl_frame, textvariable=self.port_var, font=("Consolas", 11),
                                   bg=THEME["bg_card_inner"], fg=THEME["text_main"],
                                   insertbackground=THEME["text_accent"], width=6, bd=1, relief="solid")
        self.port_entry.pack(side="left", padx=(0, 14))

        self.sim_mode_var = tk.BooleanVar(value=True)
        self.sim_check = tk.Checkbutton(ctrl_frame, text="Simulazione Offline",
                                        variable=self.sim_mode_var, font=("Segoe UI", 10),
                                        fg=THEME["text_accent"], bg=THEME["bg_header"],
                                        selectcolor=THEME["bg_card_inner"],
                                        activebackground=THEME["bg_header"],
                                        activeforeground=THEME["text_accent"])
        self.sim_check.pack(side="left", padx=(0, 14))

        self.btn_connect = tk.Button(ctrl_frame, text="CONNETTI", font=("Segoe UI", 11, "bold"),
                                     bg=THEME["accent_primary"], fg="#FFFFFF", activebackground=THEME["accent_hover"],
                                     activeforeground="#FFFFFF", bd=0, padx=16, pady=4, cursor="hand2",
                                     command=self.toggle_connection)
        self.btn_connect.pack(side="left", padx=(0, 16))

        # EDIT LAYOUT BUTTON
        self.btn_edit_layout = tk.Button(ctrl_frame, text="📐 EDIT LAYOUT", font=("Segoe UI", 10, "bold"),
                                         bg=THEME["bg_card_inner"], fg=THEME["text_main"],
                                         activebackground=THEME["bg_card_border"], activeforeground=THEME["text_accent"],
                                         bd=1, relief="solid", padx=12, pady=4, cursor="hand2",
                                         command=self.toggle_edit_layout)
        self.btn_edit_layout.pack(side="left", padx=(0, 14))

        # Right Side Status
        status_frame = tk.Frame(header, bg=THEME["bg_header"])
        status_frame.pack(side="right")

        self.model_badge = tk.Label(status_frame, text="MODEL: AD4Q", font=("Consolas", 10, "bold"),
                                    fg=THEME["text_muted"], bg=THEME["bg_card_inner"], padx=8, pady=3)
        self.model_badge.pack(side="right", padx=(10, 0))

        self.status_dot = tk.Canvas(status_frame, width=14, height=14, bg=THEME["bg_header"], highlightthickness=0)
        self.status_dot.pack(side="left", padx=(0, 6))
        self.status_dot_id = self.status_dot.create_oval(1, 1, 13, 13, fill=THEME["status_disconnected"], outline="")

        self.status_text = tk.Label(status_frame, text="DISCONNESSO", font=("Segoe UI", 10, "bold"),
                                    fg=THEME["status_disconnected"], bg=THEME["bg_header"])
        self.status_text.pack(side="left")

        # 2. Main Channels Container (PanedWindow for interactive column resizing)
        self.paned_container = tk.PanedWindow(self.root, orient="horizontal", bg=THEME["bg_root"],
                                             bd=0, sashwidth=4, sashrelief="flat", sashpad=2)
        self.paned_container.pack(fill="both", expand=True, padx=10, pady=10)

        self.build_channel_grid(4)

        # 3. Footer Bar
        self.footer = tk.Frame(self.root, bg=THEME["bg_header"], padx=16, pady=6,
                               highlightthickness=1, highlightbackground=THEME["bg_card_border"])
        self.footer.pack(fill="x", side="bottom")

        self.footer_log = tk.Label(self.footer, text="Pronto. In modalità EDIT puoi trascinare qualsiasi divisore per ridimensionare tutte le colonne sincronizzate.",
                                   font=("Segoe UI", 10), fg=THEME["text_muted"], bg=THEME["bg_header"], anchor="w")
        self.footer_log.pack(side="left", fill="x", expand=True)

        self.footer_info = tk.Label(self.footer, text="Synchronized Multi-Zone Heights | Dual RF | 5-Dot Qual",
                                    font=("Consolas", 9), fg=THEME["text_muted"], bg=THEME["bg_header"])
        self.footer_info.pack(side="right")

    def toggle_edit_layout(self):
        self.edit_mode_active = not self.edit_mode_active
        
        if self.edit_mode_active:
            self.btn_edit_layout.config(text="🔒 BLOCCA LAYOUT", bg=THEME["edit_mode_active"], fg="#000000")
            self.paned_container.config(sashwidth=8, sashrelief="raised", bg=THEME["divider_active"])
            self.footer_log.config(text="Modalità EDIT attiva: trascina un qualsiasi divisore orizzontale o verticale. Le altezze si aggiornano su TUTTI i canali contemporaneamente!")
        else:
            self.btn_edit_layout.config(text="📐 EDIT LAYOUT", bg=THEME["bg_card_inner"], fg=THEME["text_main"])
            self.paned_container.config(sashwidth=4, sashrelief="flat", bg=THEME["bg_root"])
            self.footer_log.config(text="Layout bloccato. Modalità operativa broadcast.")

        for card in self.channels.values():
            card.set_edit_mode(self.edit_mode_active)

    def adjust_shared_section_height(self, section_key: str, delta_y: int):
        """
        Adjusts the height of a section across ALL channels synchronously!
        """
        current_h = self.shared_section_heights.get(section_key, 70)
        new_h = max(36, min(240, current_h + delta_y))
        self.shared_section_heights[section_key] = new_h
        
        # Apply updated heights to ALL channels simultaneously
        for card in self.channels.values():
            card.update_section_heights(self.shared_section_heights)

    def adjust_shared_panel_width(self, delta_x: int):
        """
        Adjusts the width of the right telemetry panel across ALL channels synchronously!
        """
        new_w = max(130, min(320, self.shared_right_panel_width + delta_x))
        self.shared_right_panel_width = new_w
        for card in self.channels.values():
            card.update_panel_width(self.shared_right_panel_width)

    def build_channel_grid(self, count: int):
        for pane in self.paned_container.panes():
            self.paned_container.remove(pane)
        self.channels.clear()
        self.channel_count = count

        for ch in range(1, count + 1):
            card = ChannelCard(self.paned_container, ch, self)
            self.paned_container.add(card, minsize=220, stretch="always")
            self.channels[ch] = card

    def blink_loop(self):
        for card in self.channels.values():
            card.tick_blink()
        self.root.after(450, self.blink_loop)

    def set_status_ui(self, status: str, msg: str):
        self.footer_log.config(text=msg)
        if status == "CONNECTED":
            self.status_text.config(text="CONNESSO", fg=THEME["status_connected"])
            self.status_dot.itemconfig(self.status_dot_id, fill=THEME["status_connected"])
            self.btn_connect.config(text="DISCONNETTI", bg=THEME["status_error"])
            self.ip_entry.config(state="disabled")
            self.port_entry.config(state="disabled")
            self.sim_check.config(state="disabled")
            self.is_connected = True
        elif status == "CONNECTING":
            self.status_text.config(text="CONNESSIONE IN CORSO...", fg=THEME["meter_yellow"])
            self.status_dot.itemconfig(self.status_dot_id, fill=THEME["meter_yellow"])
        elif status == "SIMULATOR":
            self.status_text.config(text="SIMULAZIONE ATTIVA", fg=THEME["status_sim"])
            self.status_dot.itemconfig(self.status_dot_id, fill=THEME["status_sim"])
            self.btn_connect.config(text="DISCONNETTI", bg=THEME["status_error"])
            self.ip_entry.config(state="disabled")
            self.port_entry.config(state="disabled")
            self.sim_check.config(state="disabled")
            self.is_connected = True
        else:
            self.status_text.config(text="DISCONNESSO", fg=THEME["status_disconnected"])
            self.status_dot.itemconfig(self.status_dot_id, fill=THEME["status_disconnected"])
            self.btn_connect.config(text="CONNETTI", bg=THEME["accent_primary"])
            self.ip_entry.config(state="normal")
            self.port_entry.config(state="normal")
            self.sim_check.config(state="normal")
            self.is_connected = False

    def toggle_connection(self):
        if self.is_connected:
            self.disconnect()
        else:
            self.connect()

    def connect(self):
        if self.sim_mode_var.get():
            self.simulator = ShureSimulator(self.queue)
            self.simulator.start()
            self.set_status_ui("SIMULATOR", "Modalità simulazione offline Shure AD4Q avviata.")
            return

        ip = self.ip_var.get().strip()
        port_str = self.port_var.get().strip()
        
        if not ip:
            messagebox.showerror("Errore Parametri", "Inserisci un indirizzo IP valido del ricevitore Shure.")
            return
            
        try:
            port = int(port_str)
        except ValueError:
            messagebox.showerror("Errore Parametri", "La porta specificata non è valida.")
            return

        self.set_status_ui("CONNECTING", f"Tentativo di connessione a {ip}:{port}...")
        self.network_client = ShureClient(ip, port, self.queue, auto_reconnect=True)
        self.network_client.start()

    def disconnect(self):
        if self.simulator:
            self.simulator.stop()
            self.simulator = None
            
        if self.network_client:
            self.network_client.stop()
            self.network_client = None
            
        self.set_status_ui("DISCONNECTED", "Disconnesso.")

    def process_queue(self):
        try:
            while True:
                msg = self.queue.get_nowait()
                self.handle_incoming_message(msg)
        except queue.Empty:
            pass
        finally:
            self.root.after(30, self.process_queue)

    def handle_incoming_message(self, msg: Dict[str, Any]):
        msg_type = msg.get("type")
        
        if msg_type == "STATUS":
            st = msg.get("status")
            m = msg.get("msg", "")
            if st == "CONNECTED":
                if self.sim_mode_var.get():
                    self.set_status_ui("SIMULATOR", m)
                else:
                    self.set_status_ui("CONNECTED", m)
            elif st == "DISCONNECTED" or st == "ERROR":
                self.set_status_ui(st, m)
            elif st == "CONNECTING":
                self.set_status_ui("CONNECTING", m)

        elif msg_type == "SAMPLE":
            ch = msg.get("channel")
            if ch in self.channels:
                self.channels[ch].update_sample(msg.get("fields", {}))

        elif msg_type == "REP":
            ch = msg.get("channel")
            cmd = msg.get("command", "").upper()
            val = msg.get("value", "")

            if cmd == "MODEL":
                self.model_badge.config(text=f"MODEL: {val}")
                if "AD4D" in val.upper() and self.channel_count != 2:
                    self.build_channel_grid(2)
                elif "AD4Q" in val.upper() and self.channel_count != 4:
                    self.build_channel_grid(4)

            if ch in self.channels:
                card = self.channels[ch]
                if cmd == "CHAN_NAME":
                    card.update_name(val)
                elif cmd == "FREQUENCY":
                    card.update_frequency(val)
                elif cmd == "AUDIO_MUTE":
                    card.update_mute(val.upper() in ["ON", "MUTE", "YES", "1"])
                elif cmd == "ENCRYPTION":
                    card.update_encryption(val.upper() in ["ON", "YES", "ENABLED", "1"])
                elif cmd == "INTERFERENCE_STATUS":
                    card.update_interference(val.upper() in ["DETECTED", "YES", "1", "TRUE"])
                elif cmd == "TX_BATT_MINS":
                    try:
                        card.update_battery(int(val))
                    except ValueError:
                        pass
                elif cmd == "TX_BATT_BARS":
                    try:
                        card.batt_gauge.set_battery(card.batt_gauge.mins, int(val))
                    except ValueError:
                        pass

    def on_closing(self):
        self.disconnect()
        self.root.destroy()


def main():
    root = tk.Tk()
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    app = AxientMonitorApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()
