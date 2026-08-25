#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RCShure - Shure Axient Digital (AD4D / AD4Q) Real-Time Monitor & Simulator
Standalone Windows Application (Zero external dependencies, Python Standard Library only)

Protocol Specifications:
- TCP/IP Port: 2202
- Shure Command Strings: < COMMAND PARAMETERS >\n
- Message Types: < REP ... >, < SAMPLE ... >, < GET ... >, < SET ... >
"""

import sys
import os
import socket
import threading
import queue
import time
import math
import random
import re
from typing import Dict, Any, Optional

import tkinter as tk
from tkinter import ttk, messagebox

# ==============================================================================
# COLOR PALETTE - Broadcast Dark Control Room Theme
# ==============================================================================
THEME = {
    "bg_root": "#0E1117",
    "bg_header": "#151922",
    "bg_card": "#1C212D",
    "bg_card_border": "#2C3446",
    "bg_card_inner": "#12161F",
    "text_main": "#ECEFF4",
    "text_muted": "#8A93A6",
    "text_accent": "#00E5FF",
    "accent_primary": "#00B4D8",
    "accent_hover": "#0077B6",
    "status_connected": "#00E676",
    "status_sim": "#B388FF",
    "status_error": "#FF3D00",
    "status_disconnected": "#78909C",
    
    # Meter Colors
    "meter_green": "#00E676",
    "meter_yellow": "#FFEA00",
    "meter_orange": "#FF9100",
    "meter_red": "#FF1744",
    "meter_bg": "#181D26",
    "meter_grid": "#242C3A",
    "meter_peak": "#FFFFFF",
    
    # RF Colors
    "rf_high": "#00E5FF",
    "rf_med": "#FFEA00",
    "rf_low": "#FF3D00",
    "rf_bg": "#181D26",
    
    # Battery Colors
    "batt_normal": "#00E676",
    "batt_med": "#FFB300",
    "batt_low": "#FF1744",
    
    # LED Indicator Colors
    "led_off": "#2A3140",
    "led_mute": "#FF3D00",
    "led_interf": "#FF1744",
    "led_enc": "#00E5FF",
    "led_rf_active": "#00E676",
    "led_peak": "#FF1744",
}

DEFAULT_SHURE_PORT = 2202


# ==============================================================================
# PROTOCOL PARSER & DATA STRUCTURES
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
            # Format: < SAMPLE <ch> <field1> <val1> <field2> <val2> ... >
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
            # Format: < REP <ch> <COMMAND> <VALUE...> > or < REP <COMMAND> <VALUE...> >
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
            
            # Remove enclosing quotes if any
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
    """
    Native offline simulator generating realistic Shure AD4Q telemetry.
    Produces believable voice/music audio peak dynamics, RF link fluctuations,
    battery drainage, and intermittent alerts.
    """
    def __init__(self, output_queue: queue.Queue):
        super().__init__(daemon=True)
        self.output_queue = output_queue
        self.running = threading.Event()
        self.running.set()
        
        # Channel baseline state
        self.channels = {
            1: {
                "name": "VOCAL LEAD",
                "freq": "512.450",
                "audio_level": 15,
                "audio_target": 75,
                "audio_phase": 0.0,
                "rf_qual": 245,
                "antenna": "A",
                "batt_mins": 480,
                "batt_bars": 5,
                "batt_type": "SB900A",
                "mute": False,
                "interf": False,
                "enc": True,
                "talking": True,
            },
            2: {
                "name": "VOCAL BACKING",
                "freq": "528.125",
                "audio_level": 10,
                "audio_target": 65,
                "audio_phase": 1.2,
                "rf_qual": 230,
                "antenna": "B",
                "batt_mins": 390,
                "batt_bars": 4,
                "batt_type": "SB900A",
                "mute": False,
                "interf": False,
                "enc": True,
                "talking": True,
            },
            3: {
                "name": "BASS GUITAR",
                "freq": "554.800",
                "audio_level": 20,
                "audio_target": 85,
                "audio_phase": 2.5,
                "rf_qual": 215,
                "antenna": "A",
                "batt_mins": 110,
                "batt_bars": 2,
                "batt_type": "SB900A",
                "mute": False,
                "interf": False,
                "enc": False,
                "talking": True,
            },
            4: {
                "name": "GUEST / SPARE",
                "freq": "580.375",
                "audio_level": 5,
                "audio_target": 10,
                "audio_phase": 4.0,
                "rf_qual": 250,
                "antenna": "A",
                "batt_mins": 540,
                "batt_bars": 5,
                "batt_type": "SB900A",
                "mute": True,
                "interf": False,
                "enc": True,
                "talking": False,
            }
        }
        self.step_counter = 0

    def stop(self):
        self.running.clear()

    def run(self):
        # 1. Send initial setup reports (< REP ... >)
        self.output_queue.put({"type": "STATUS", "status": "CONNECTED", "msg": "Simulator Mode (AD4Q 4-Ch)"})
        
        # Announce receiver model
        self.output_queue.put({
            "type": "REP", "channel": None, "command": "MODEL", "value": "AD4Q"
        })
        
        # Initial Channel configuration
        for ch, data in self.channels.items():
            self.output_queue.put({
                "type": "REP", "channel": ch, "command": "CHAN_NAME", "value": data["name"]
            })
            self.output_queue.put({
                "type": "REP", "channel": ch, "command": "FREQUENCY", "value": data["freq"].replace(".", "") + "0"
            })
            self.output_queue.put({
                "type": "REP", "channel": ch, "command": "ENCRYPTION", "value": "ON" if data["enc"] else "OFF"
            })
            self.output_queue.put({
                "type": "REP", "channel": ch, "command": "AUDIO_MUTE", "value": "ON" if data["mute"] else "OFF"
            })
            self.output_queue.put({
                "type": "REP", "channel": ch, "command": "TX_BATT_MINS", "value": str(data["batt_mins"])
            })
            self.output_queue.put({
                "type": "REP", "channel": ch, "command": "TX_BATT_BARS", "value": str(data["batt_bars"])
            })

        # 2. Main periodic telemetry loop (100ms interval)
        while self.running.is_set():
            time.sleep(0.10)
            self.step_counter += 1
            
            # Every 10 seconds, drain 1 minute of battery
            if self.step_counter % 100 == 0:
                for ch in self.channels:
                    if self.channels[ch]["batt_mins"] > 0:
                        self.channels[ch]["batt_mins"] -= 1
                        mins = self.channels[ch]["batt_mins"]
                        bars = min(5, max(0, int(mins / 100)))
                        self.channels[ch]["batt_bars"] = bars
                        self.output_queue.put({
                            "type": "REP", "channel": ch, "command": "TX_BATT_MINS", "value": str(mins)
                        })
                        self.output_queue.put({
                            "type": "REP", "channel": ch, "command": "TX_BATT_BARS", "value": str(bars)
                        })

            # Rare interference event simulation (every ~35 seconds on Channel 2 or 3)
            if self.step_counter % 350 == 150:
                target_ch = random.choice([2, 3])
                self.channels[target_ch]["interf"] = True
                self.channels[target_ch]["rf_qual"] = random.randint(40, 90)
                self.output_queue.put({
                    "type": "REP", "channel": target_ch, "command": "INTERFERENCE_STATUS", "value": "DETECTED"
                })
            elif self.step_counter % 350 == 210:
                for ch in self.channels:
                    if self.channels[ch]["interf"]:
                        self.channels[ch]["interf"] = False
                        self.channels[ch]["rf_qual"] = 230
                        self.output_queue.put({
                            "type": "REP", "channel": ch, "command": "INTERFERENCE_STATUS", "value": "NONE"
                        })

            # Generate Sample frame for each channel
            for ch, state in self.channels.items():
                # Audio dynamics calculation
                if state["mute"]:
                    audio_val = 0
                else:
                    state["audio_phase"] += 0.15
                    # Speech envelope with pauses
                    speech_burst = math.sin(state["audio_phase"] * 0.7) * math.cos(state["audio_phase"] * 0.3)
                    if speech_burst > 0.1:
                        raw_level = state["audio_target"] + (math.sin(state["audio_phase"] * 3.1) * 20) + (random.gauss(0, 8))
                    else:
                        raw_level = 10 + random.uniform(0, 8)  # Ambient floor
                        
                    # Audio Peak 000 - 120 (where 120 = 0 dBFS clip, 090 = -10dBFS, 060 = -24dBFS)
                    audio_val = max(0, min(120, int(raw_level)))
                
                state["audio_level"] = audio_val

                # RF link micro-jitter and antenna diversity
                if not state["interf"]:
                    state["rf_qual"] = max(120, min(255, state["rf_qual"] + random.randint(-4, 4)))
                    if random.random() < 0.04:
                        state["antenna"] = "B" if state["antenna"] == "A" else "A"
                
                # Format Shure SAMPLE payload
                # Axient sample format: AUDIO_PEAK (000-120), RF_QUAL (000-255), RF_ANTENNA
                sample_data = {
                    "type": "SAMPLE",
                    "channel": ch,
                    "fields": {
                        "AUDIO_PEAK": f"{audio_val:03d}",
                        "RF_QUAL": f"{state['rf_qual']:03d}",
                        "RF_ANTENNA": state["antenna"],
                        "AUDIO_LEVEL": f"{audio_val:03d}",
                        "TX_BATT_BARS": str(state["batt_bars"]),
                        "TX_BATT_MINS": str(state["batt_mins"]),
                    }
                }
                self.output_queue.put(sample_data)


# ==============================================================================
# NETWORK CLIENT THREAD (Real Hardware TCP Connection)
# ==============================================================================
class ShureClient(threading.Thread):
    """Handles non-blocking TCP socket communication with Shure Axient Receiver."""
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
        """Sends a Shure command string, wrapping with < and > if needed."""
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
            self.output_queue.put({"type": "STATUS", "status": "CONNECTING", "msg": f"Connecting to {self.host}:{self.port}..."})
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.settimeout(5.0)
                self.sock.connect((self.host, self.port))
                self.connected = True
                self.output_queue.put({"type": "STATUS", "status": "CONNECTED", "msg": f"Connected to {self.host}:{self.port}"})
                
                # Send Handshake / Discovery Queries
                # Query receiver model and channels (1 to 4)
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
                    # Start continuous fast metering (100ms)
                    self.send_cmd(f"< SET {ch} METER_RATE 00100 >")
                
                # Global meter rate command fallback
                self.send_cmd("< SET 0 METER_RATE 00100 >")

                # Receive Loop
                buffer = ""
                self.sock.settimeout(1.0)
                while self.running.is_set():
                    try:
                        data = self.sock.recv(4096)
                        if not data:
                            raise ConnectionResetError("Connection closed by remote host")
                        
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
                            self.output_queue.put({"type": "STATUS", "status": "ERROR", "msg": f"Socket read error: {e}"})
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
                    
                self.output_queue.put({"type": "STATUS", "status": "DISCONNECTED", "msg": f"Disconnected: {e}"})
                
                if not self.auto_reconnect:
                    break
                
                # Wait 5 seconds before attempting reconnect
                for _ in range(50):
                    if not self.running.is_set():
                        break
                    time.sleep(0.1)


# ==============================================================================
# CUSTOM TKINTER WIDGETS (Broadcast Dark GUI)
# ==============================================================================
class SegmentedVUMeter(tk.Canvas):
    """High performance Canvas-based segmented VU-Meter with Peak Hold."""
    def __init__(self, parent, width=32, height=220, **kwargs):
        super().__init__(parent, width=width, height=height, bg=THEME["meter_bg"], 
                         highlightthickness=1, highlightbackground=THEME["bg_card_border"], **kwargs)
        self.meter_width = width
        self.meter_height = height
        self.current_val = 0.0  # 0 to 120
        self.peak_val = 0.0
        self.peak_hold_ticks = 0
        self.num_segments = 24
        self.draw_meter()

    def set_level(self, val_0_120: float):
        """Update meter value (0 to 120 Shure scale)."""
        self.current_val = max(0.0, min(120.0, float(val_0_120)))
        if self.current_val >= self.peak_val:
            self.peak_val = self.current_val
            self.peak_hold_ticks = 20  # ~2 seconds hold at 100ms
        else:
            if self.peak_hold_ticks > 0:
                self.peak_hold_ticks -= 1
            else:
                self.peak_val = max(0.0, self.peak_val - 2.5)  # Smooth peak decay
        self.draw_meter()

    def draw_meter(self):
        self.delete("all")
        margin_x = 4
        margin_y = 6
        usable_w = self.meter_width - (margin_x * 2)
        usable_h = self.meter_height - (margin_y * 2)
        seg_h = usable_h / self.num_segments
        gap = 2

        # Draw segments bottom-up
        for i in range(self.num_segments):
            # Segment threshold from 0 to 120
            ratio = (i + 1) / self.num_segments
            seg_level = ratio * 120.0
            
            y2 = self.meter_height - margin_y - (i * seg_h)
            y1 = y2 - (seg_h - gap)
            x1 = margin_x
            x2 = margin_x + usable_w

            # Color zones:
            # Top 2 segments (110-120): Red (Overload/Clip)
            # Next 4 segments (90-110): Orange (-6dB to -2dB)
            # Next 6 segments (60-90): Yellow (-18dB to -6dB)
            # Bottom segments (0-60): Green (Normal signal)
            if i >= self.num_segments - 2:
                active_color = THEME["meter_red"]
            elif i >= self.num_segments - 6:
                active_color = THEME["meter_orange"]
            elif i >= self.num_segments - 12:
                active_color = THEME["meter_yellow"]
            else:
                active_color = THEME["meter_green"]

            if self.current_val >= seg_level:
                fill_col = active_color
            else:
                fill_col = THEME["meter_grid"]

            self.create_rectangle(x1, y1, x2, y2, fill=fill_col, outline="", width=0)

        # Draw Peak Hold Marker Line
        if self.peak_val > 5:
            peak_ratio = min(1.0, self.peak_val / 120.0)
            peak_y = self.meter_height - margin_y - (peak_ratio * usable_h)
            self.create_line(margin_x - 1, peak_y, margin_x + usable_w + 1, peak_y, 
                             fill=THEME["meter_peak"], width=2)


class RFQualityBar(tk.Canvas):
    """Horizontal gradient bar for RF Link Quality (0 - 255)."""
    def __init__(self, parent, width=140, height=14, **kwargs):
        super().__init__(parent, width=width, height=height, bg=THEME["rf_bg"], 
                         highlightthickness=1, highlightbackground=THEME["bg_card_border"], **kwargs)
        self.bar_w = width
        self.bar_h = height
        self.value = 0
        self.draw_bar()

    def set_value(self, val_0_255: int):
        self.value = max(0, min(255, int(val_0_255)))
        self.draw_bar()

    def draw_bar(self):
        self.delete("all")
        percent = self.value / 255.0
        fill_w = int((self.bar_w - 4) * percent)
        
        if percent > 0.65:
            col = THEME["rf_high"]
        elif percent > 0.35:
            col = THEME["rf_med"]
        else:
            col = THEME["rf_low"]

        # Background grid ticks
        for i in range(1, 5):
            tx = int((self.bar_w / 5) * i)
            self.create_line(tx, 1, tx, self.bar_h - 1, fill=THEME["bg_card_border"], width=1)

        if fill_w > 0:
            self.create_rectangle(2, 2, 2 + fill_w, self.bar_h - 2, fill=col, outline="")


class BatteryGauge(tk.Canvas):
    """Smart dynamic battery icon with charge percentage and time remaining."""
    def __init__(self, parent, width=44, height=22, **kwargs):
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
        # Battery shell
        bx1, by1, bx2, by2 = 2, 3, self.w - 8, self.h - 3
        self.create_rectangle(bx1, by1, bx2, by2, outline=THEME["text_muted"], width=1)
        # Nipple
        self.create_rectangle(bx2, by1 + 4, self.w - 4, by2 - 4, fill=THEME["text_muted"], outline="")

        # Battery fill color
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
    """Virtual LED indicator for Mute, Interference, Encryption, etc."""
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
        # Glint reflection for realistic LED look
        if self.is_active:
            self.create_oval(pad + 2, pad + 2, pad + 4, pad + 4, fill="#FFFFFF", outline="")


# ==============================================================================
# CHANNEL MONITOR CARD (Reusable Per-Channel Component)
# ==============================================================================
class ChannelCard(tk.Frame):
    """Comprehensive single-channel monitoring card."""
    def __init__(self, parent, channel_num: int):
        super().__init__(parent, bg=THEME["bg_card"], bd=1, relief="solid",
                         highlightbackground=THEME["bg_card_border"], highlightthickness=1)
        self.channel_num = channel_num
        self.last_audio_peak = 0
        
        self.setup_ui()

    def setup_ui(self):
        # 1. Top Channel Header Bar
        header_frame = tk.Frame(self, bg=THEME["bg_card_inner"], padx=10, pady=8)
        header_frame.pack(fill="x", side="top")
        
        ch_badge = tk.Label(header_frame, text=f"CH {self.channel_num}", font=("Segoe UI", 10, "bold"),
                            fg=THEME["bg_root"], bg=THEME["text_accent"], padx=6, pady=1)
        ch_badge.pack(side="left")
        
        self.freq_label = tk.Label(header_frame, text="---.--- MHz", font=("Consolas", 10, "bold"),
                                   fg=THEME["text_accent"], bg=THEME["bg_card_inner"])
        self.freq_label.pack(side="right")

        # 2. Channel Name Banner
        name_frame = tk.Frame(self, bg=THEME["bg_card"], padx=10, pady=6)
        name_frame.pack(fill="x")
        
        self.name_label = tk.Label(name_frame, text=f"CHANNEL {self.channel_num}", font=("Segoe UI", 12, "bold"),
                                   fg=THEME["text_main"], bg=THEME["bg_card"], anchor="w")
        self.name_label.pack(fill="x")

        # 3. Main Body Frame (VU Meter + Telemetry Panel)
        body_frame = tk.Frame(self, bg=THEME["bg_card"], padx=10, pady=4)
        body_frame.pack(fill="both", expand=True)

        # Left: Vertical Segmented VU Meter + dB Labels
        meter_container = tk.Frame(body_frame, bg=THEME["bg_card"])
        meter_container.pack(side="left", fill="y", padx=(0, 10))

        # Scale markings
        scale_frame = tk.Frame(meter_container, bg=THEME["bg_card"])
        scale_frame.pack(side="left", fill="y", padx=(0, 3))
        for db in ["0", "-6", "-12", "-18", "-30", "-60"]:
            lbl = tk.Label(scale_frame, text=db, font=("Consolas", 7), fg=THEME["text_muted"], bg=THEME["bg_card"])
            lbl.pack(side="top", expand=True)

        self.vu_meter = SegmentedVUMeter(meter_container, width=28, height=210)
        self.vu_meter.pack(side="left", fill="y")

        # Right: Telemetry Details (RF, Battery, Status LEDs)
        telemetry_frame = tk.Frame(body_frame, bg=THEME["bg_card_inner"], padx=8, pady=8,
                                   highlightthickness=1, highlightbackground=THEME["bg_card_border"])
        telemetry_frame.pack(side="left", fill="both", expand=True)

        # --- RF SECTION ---
        rf_title_frame = tk.Frame(telemetry_frame, bg=THEME["bg_card_inner"])
        rf_title_frame.pack(fill="x", pady=(0, 2))
        
        tk.Label(rf_title_frame, text="RF LINK", font=("Segoe UI", 8, "bold"),
                 fg=THEME["text_muted"], bg=THEME["bg_card_inner"]).pack(side="left")
        
        self.antenna_badge = tk.Label(rf_title_frame, text="ANT A", font=("Consolas", 8, "bold"),
                                      fg=THEME["status_connected"], bg=THEME["bg_card"], padx=4)
        self.antenna_badge.pack(side="right")

        self.rf_bar = RFQualityBar(telemetry_frame, width=120, height=12)
        self.rf_bar.pack(fill="x", pady=(2, 4))

        self.rf_val_label = tk.Label(telemetry_frame, text="RF: --- %", font=("Consolas", 8),
                                     fg=THEME["text_muted"], bg=THEME["bg_card_inner"])
        self.rf_val_label.pack(anchor="e", pady=(0, 8))

        # --- BATTERY SECTION ---
        batt_title_frame = tk.Frame(telemetry_frame, bg=THEME["bg_card_inner"])
        batt_title_frame.pack(fill="x", pady=(0, 2))
        
        tk.Label(batt_title_frame, text="TRANSMITTER", font=("Segoe UI", 8, "bold"),
                 fg=THEME["text_muted"], bg=THEME["bg_card_inner"]).pack(side="left")

        batt_row = tk.Frame(telemetry_frame, bg=THEME["bg_card_inner"])
        batt_row.pack(fill="x", pady=(2, 4))
        
        self.batt_gauge = BatteryGauge(batt_row, width=38, height=18)
        self.batt_gauge.pack(side="left", padx=(0, 6))

        self.batt_time_label = tk.Label(batt_row, text="--h --m", font=("Consolas", 9, "bold"),
                                        fg=THEME["text_main"], bg=THEME["bg_card_inner"])
        self.batt_time_label.pack(side="left")

        self.batt_alert_label = tk.Label(telemetry_frame, text="BATTERY OK", font=("Segoe UI", 7, "bold"),
                                         fg=THEME["status_connected"], bg=THEME["bg_card_inner"])
        self.batt_alert_label.pack(anchor="w", pady=(0, 8))

        # --- LED STATUS INDICATORS ---
        tk.Label(telemetry_frame, text="STATUS FLAGS", font=("Segoe UI", 8, "bold"),
                 fg=THEME["text_muted"], bg=THEME["bg_card_inner"]).pack(anchor="w", pady=(0, 4))

        led_grid = tk.Frame(telemetry_frame, bg=THEME["bg_card_inner"])
        led_grid.pack(fill="x")

        # Row 1: Mute & Peak
        r1 = tk.Frame(led_grid, bg=THEME["bg_card_inner"])
        r1.pack(fill="x", pady=2)
        self.led_mute = StatusLED(r1, "MUTE", THEME["led_mute"], size=12)
        self.led_mute.pack(side="left", padx=(0, 4))
        tk.Label(r1, text="MUTE", font=("Segoe UI", 8), fg=THEME["text_main"], bg=THEME["bg_card_inner"]).pack(side="left", padx=(0, 8))

        self.led_peak = StatusLED(r1, "CLIP", THEME["led_peak"], size=12)
        self.led_peak.pack(side="left", padx=(0, 4))
        tk.Label(r1, text="PEAK", font=("Segoe UI", 8), fg=THEME["text_main"], bg=THEME["bg_card_inner"]).pack(side="left")

        # Row 2: Interference & Encryption
        r2 = tk.Frame(led_grid, bg=THEME["bg_card_inner"])
        r2.pack(fill="x", pady=2)
        self.led_interf = StatusLED(r2, "INTERF", THEME["led_interf"], size=12)
        self.led_interf.pack(side="left", padx=(0, 4))
        tk.Label(r2, text="INTERF", font=("Segoe UI", 8), fg=THEME["text_main"], bg=THEME["bg_card_inner"]).pack(side="left", padx=(0, 8))

        self.led_enc = StatusLED(r2, "ENC", THEME["led_enc"], size=12)
        self.led_enc.pack(side="left", padx=(0, 4))
        tk.Label(r2, text="ENCR", font=("Segoe UI", 8), fg=THEME["text_main"], bg=THEME["bg_card_inner"]).pack(side="left")

    def update_name(self, name: str):
        clean_name = name.strip()
        self.name_label.config(text=clean_name if clean_name else f"CHANNEL {self.channel_num}")

    def update_frequency(self, freq_str: str):
        # Shure transmits freq in 100Hz or 1kHz units (e.g. 512450 = 512.450 MHz)
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
        # 1. Audio Peak
        if "AUDIO_PEAK" in fields:
            try:
                val = float(fields["AUDIO_PEAK"])
                self.last_audio_peak = val
                self.vu_meter.set_level(val)
                # Overload peak LED if > 115 (approx -2dBFS)
                self.led_peak.set_state(val >= 115)
            except ValueError:
                pass

        # 2. RF Quality & Antenna
        if "RF_QUAL" in fields:
            try:
                rf_val = int(fields["RF_QUAL"])
                self.rf_bar.set_value(rf_val)
                pct = int((rf_val / 255.0) * 100)
                self.rf_val_label.config(text=f"RF: {pct}% ({rf_val})")
            except ValueError:
                pass

        if "RF_ANTENNA" in fields:
            ant = fields["RF_ANTENNA"].upper()
            self.antenna_badge.config(text=f"ANT {ant}")
            if ant == "A":
                self.antenna_badge.config(fg=THEME["status_connected"])
            else:
                self.antenna_badge.config(fg=THEME["text_accent"])

        # 3. Battery minutes & bars
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
        self.batt_gauge.set_battery(mins, bars)
        if mins == 65535 or mins < 0:
            self.batt_time_label.config(text="--h --m", fg=THEME["text_muted"])
            self.batt_alert_label.config(text="DISCONNECTED", fg=THEME["text_muted"])
        else:
            hrs = mins // 60
            m = mins % 60
            self.batt_time_label.config(text=f"{hrs}h {m:02d}m")
            if mins < 30:
                self.batt_time_label.config(fg=THEME["batt_low"])
                self.batt_alert_label.config(text="CRITICAL BATTERY", fg=THEME["batt_low"])
            elif mins < 60:
                self.batt_time_label.config(fg=THEME["batt_med"])
                self.batt_alert_label.config(text="LOW BATTERY", fg=THEME["batt_med"])
            else:
                self.batt_time_label.config(fg=THEME["text_main"])
                self.batt_alert_label.config(text="BATTERY OK", fg=THEME["status_connected"])

    def update_mute(self, is_muted: bool):
        self.led_mute.set_state(is_muted)

    def update_interference(self, is_interf: bool):
        self.led_interf.set_state(is_interf)

    def update_encryption(self, is_enc: bool):
        self.led_enc.set_state(is_enc)


# ==============================================================================
# MAIN APPLICATION WINDOW
# ==============================================================================
class AxientMonitorApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("RCShure - Shure Axient Digital Real-Time Monitor")
        self.root.geometry("1180x640")
        self.root.minsize(860, 520)
        self.root.configure(bg=THEME["bg_root"])
        
        # Application State
        self.queue: queue.Queue = queue.Queue()
        self.network_client: Optional[ShureClient] = None
        self.simulator: Optional[ShureSimulator] = None
        self.is_connected = False
        self.channel_count = 4  # Default AD4Q (can adapt to AD4D 2-ch)
        self.channels: Dict[int, ChannelCard] = {}

        self.setup_ui()
        self.process_queue()

    def setup_ui(self):
        # 1. Top Header Control Bar
        header = tk.Frame(self.root, bg=THEME["bg_header"], padx=18, pady=12,
                          highlightthickness=1, highlightbackground=THEME["bg_card_border"])
        header.pack(fill="x", side="top")

        # Brand / Title
        brand_frame = tk.Frame(header, bg=THEME["bg_header"])
        brand_frame.pack(side="left", padx=(0, 24))
        
        title_lbl = tk.Label(brand_frame, text="RCShure", font=("Segoe UI", 16, "bold"),
                             fg=THEME["text_accent"], bg=THEME["bg_header"])
        title_lbl.pack(side="left")
        
        sub_lbl = tk.Label(brand_frame, text="Axient Digital Monitor", font=("Segoe UI", 9),
                           fg=THEME["text_muted"], bg=THEME["bg_header"])
        sub_lbl.pack(side="left", padx=(8, 0), pady=(4, 0))

        # Connection Controls
        ctrl_frame = tk.Frame(header, bg=THEME["bg_header"])
        ctrl_frame.pack(side="left")

        # IP Input
        tk.Label(ctrl_frame, text="Receiver IP:", font=("Segoe UI", 9, "bold"),
                 fg=THEME["text_main"], bg=THEME["bg_header"]).pack(side="left", padx=(0, 6))
        
        self.ip_var = tk.StringVar(value="192.168.1.50")
        self.ip_entry = tk.Entry(ctrl_frame, textvariable=self.ip_var, font=("Consolas", 10),
                                 bg=THEME["bg_card_inner"], fg=THEME["text_main"],
                                 insertbackground=THEME["text_accent"], width=15, bd=1, relief="solid")
        self.ip_entry.pack(side="left", padx=(0, 10))

        # Port Input
        tk.Label(ctrl_frame, text="Port:", font=("Segoe UI", 9),
                 fg=THEME["text_muted"], bg=THEME["bg_header"]).pack(side="left", padx=(0, 4))
        self.port_var = tk.StringVar(value=str(DEFAULT_SHURE_PORT))
        self.port_entry = tk.Entry(ctrl_frame, textvariable=self.port_var, font=("Consolas", 10),
                                   bg=THEME["bg_card_inner"], fg=THEME["text_main"],
                                   insertbackground=THEME["text_accent"], width=6, bd=1, relief="solid")
        self.port_entry.pack(side="left", padx=(0, 16))

        # Simulation Mode Checkbox
        self.sim_mode_var = tk.BooleanVar(value=False)
        self.sim_check = tk.Checkbutton(ctrl_frame, text="Modalità Simulazione Offline",
                                        variable=self.sim_mode_var, font=("Segoe UI", 9),
                                        fg=THEME["text_accent"], bg=THEME["bg_header"],
                                        selectcolor=THEME["bg_card_inner"],
                                        activebackground=THEME["bg_header"],
                                        activeforeground=THEME["text_accent"])
        self.sim_check.pack(side="left", padx=(0, 16))

        # Connect / Disconnect Button
        self.btn_connect = tk.Button(ctrl_frame, text="CONNETTI", font=("Segoe UI", 10, "bold"),
                                     bg=THEME["accent_primary"], fg="#FFFFFF", activebackground=THEME["accent_hover"],
                                     activeforeground="#FFFFFF", bd=0, padx=16, pady=4, cursor="hand2",
                                     command=self.toggle_connection)
        self.btn_connect.pack(side="left", padx=(0, 20))

        # Right Side: Status Badge & Receiver Model
        status_frame = tk.Frame(header, bg=THEME["bg_header"])
        status_frame.pack(side="right")

        self.model_badge = tk.Label(status_frame, text="MODEL: AD4Q", font=("Consolas", 9, "bold"),
                                    fg=THEME["text_muted"], bg=THEME["bg_card_inner"], padx=6, pady=2)
        self.model_badge.pack(side="right", padx=(8, 0))

        self.status_dot = tk.Canvas(status_frame, width=12, height=12, bg=THEME["bg_header"], highlightthickness=0)
        self.status_dot.pack(side="left", padx=(0, 6))
        self.status_dot_id = self.status_dot.create_oval(1, 1, 11, 11, fill=THEME["status_disconnected"], outline="")

        self.status_text = tk.Label(status_frame, text="DISCONNESSO", font=("Segoe UI", 9, "bold"),
                                    fg=THEME["status_disconnected"], bg=THEME["bg_header"])
        self.status_text.pack(side="left")

        # 2. Main Channels Container
        self.channels_container = tk.Frame(self.root, bg=THEME["bg_root"], padx=16, pady=16)
        self.channels_container.pack(fill="both", expand=True)

        self.build_channel_grid(4)

        # 3. Bottom Status Bar
        self.footer = tk.Frame(self.root, bg=THEME["bg_header"], padx=14, pady=6,
                               highlightthickness=1, highlightbackground=THEME["bg_card_border"])
        self.footer.pack(fill="x", side="bottom")

        self.footer_log = tk.Label(self.footer, text="Pronto. Inserisci IP ricevitore o attiva Simulazione per iniziare.",
                                   font=("Segoe UI", 9), fg=THEME["text_muted"], bg=THEME["bg_header"], anchor="w")
        self.footer_log.pack(side="left", fill="x", expand=True)

        self.footer_info = tk.Label(self.footer, text="Shure Command Protocol v1.0 | Standalone Zero-Conf",
                                    font=("Consolas", 8), fg=THEME["text_muted"], bg=THEME["bg_header"])
        self.footer_info.pack(side="right")

    def build_channel_grid(self, count: int):
        """Builds or rebuilds channel cards grid (2 or 4 channels)."""
        # Clear existing cards
        for widget in self.channels_container.winfo_children():
            widget.destroy()
        self.channels.clear()
        self.channel_count = count

        for ch in range(1, count + 1):
            card = ChannelCard(self.channels_container, ch)
            card.pack(side="left", fill="both", expand=True, padx=6)
            self.channels[ch] = card

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
        else:  # DISCONNECTED / ERROR
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
        # 1. Simulator Mode
        if self.sim_mode_var.get():
            self.simulator = ShureSimulator(self.queue)
            self.simulator.start()
            self.set_status_ui("SIMULATOR", "Modalità simulazione offline Shure AD4Q avviata.")
            return

        # 2. Hardware TCP Socket Mode
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
        """Polls background network/simulator thread queue and updates GUI."""
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

            # Global Receiver Model (AD4D or AD4Q)
            if cmd == "MODEL":
                self.model_badge.config(text=f"MODEL: {val}")
                if "AD4D" in val.upper() and self.channel_count != 2:
                    self.build_channel_grid(2)
                elif "AD4Q" in val.upper() and self.channel_count != 4:
                    self.build_channel_grid(4)

            # Per-Channel attributes
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


# ==============================================================================
# ENTRY POINT
# ==============================================================================
def main():
    root = tk.Tk()
    
    # Try enabling high DPI awareness on Windows
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
