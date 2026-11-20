"""Browse and audition local TotK BNVIB curves on Windows."""

import argparse
from collections import defaultdict
import csv
import ctypes as ct
import math
import os
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Thread
from time import monotonic
import tkinter as tk
from tkinter import messagebox, ttk


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / 'build/rumble-analysis/totk-v143-romfs-waves.csv'
SDL_DIR = ROOT / 'build/v143'
MODES = {'原始 · 1×': 1, '增强 · 约 2×': 2, '增强 · 约 3×': 3}
NINTENDO_PRO_MODELS = {(0x057E, 0x2009): 'Nintendo Switch Pro Controller',
                       (0x057E, 0x2069): 'Nintendo Switch 2 Pro Controller'}
NEUTRAL = (0, 160, 0, 320)


def load_catalog(path):
    effects = defaultdict(list)
    with path.open(encoding='utf-8-sig', newline='') as source:
        for row in csv.DictReader(source):
            name = row['resource']
            t, low, lf, high, hf = (
                float(row[key]) for key in
                ('time_ms', 'low_amplitude', 'low_hz', 'high_amplitude', 'high_hz')
            )
            samples = effects[name]
            expected_time = samples[-1][0] + 5 if samples else 0
            if not (t == expected_time and 0 <= low <= 1 and 0 <= high <= 1
                    and all(math.isfinite(hz) and 0 <= hz <= 20000 for hz in (lf, hf))):
                raise ValueError(f'曲线数据无效：{name}，{t:g} ms')
            samples.append((t, low, lf, high, hf))
    if not effects:
        raise ValueError('目录没有震动曲线。')
    return dict(sorted(effects.items(), key=lambda entry: entry[0].casefold()))


def scaled_samples(samples, boost):
    if boost == 1:
        return samples
    output = []
    for t, low, lf, high, hf in samples:
        scale = 0.98 * boost / (1 + (boost - 1) * max(low, high))
        output.append((t, low * scale, lf, high * scale, hf))
    return output


class Gamepads:
    def __init__(self, directory):
        self.directory = directory

    def __enter__(self):
        with os.add_dll_directory(str(self.directory)):
            # SDL resolves the libusb backend at runtime, including for Switch 2 Pro USB.
            self.usb = ct.CDLL(str(self.directory / 'libusb-1.0.dll'))
            dll = ct.CDLL(str(self.directory / 'SDL3.dll'))
        uint, ushort = ct.c_uint32, ct.c_uint16
        ptr, string, boolean = ct.c_void_p, ct.c_char_p, ct.c_bool

        def bind(symbol, result, *args):
            fn = getattr(dll, 'SDL_' + symbol)
            fn.restype = result
            fn.argtypes = args
            return fn

        init = bind('Init', boolean, uint)
        hint = bind('SetHint', boolean, string, string)
        self.quit = bind('Quit', None)
        self.error = bind('GetError', string)
        self.update = bind('UpdateGamepads', None)
        self.delay = bind('DelayPrecise', None, ct.c_uint64)
        self.get = bind('GetGamepads', ct.POINTER(uint), ct.POINTER(ct.c_int))
        self.free = bind('free', None, ptr)
        self.name = bind('GetGamepadNameForID', string, uint)
        self.vendor = bind('GetGamepadVendorForID', ushort, uint)
        self.product = bind('GetGamepadProductForID', ushort, uint)
        self.open = bind('OpenGamepad', ptr, uint)
        self.close = bind('CloseGamepad', None, ptr)
        self.connected = bind('GamepadConnected', boolean, ptr)
        self.connection = bind('GetGamepadConnectionState', ct.c_int, ptr)
        self.hd = bind('RumbleGamepadFrequenciesEx', boolean, ptr, *([ct.c_float] * 8), uint)
        self.stop = bind('RumbleGamepad', boolean, ptr, ushort, ushort, uint)
        hint(b'SDL_JOYSTICK_HIDAPI_SWITCH2_EXPERIMENTAL_HD', b'1')
        if not init(0x2000):  # SDL_INIT_GAMEPAD
            detail = self.error_text()
            self.quit()
            raise RuntimeError(detail)
        return self

    def __exit__(self, *_):
        self.quit()

    def error_text(self):
        return (self.error() or b'Unknown SDL error').decode('utf-8', errors='replace')

    def devices(self):
        count = ct.c_int()
        ids = self.get(ct.byref(count))
        if not ids:
            raise RuntimeError(self.error_text())
        try:
            devices = {}
            for device in ids[:count.value]:
                vid, pid = self.vendor(device), self.product(device)
                name = (self.name(device) or b'Gamepad').decode('utf-8', errors='replace')
                name = NINTENDO_PRO_MODELS.get((vid, pid), name)
                devices[device] = f'{name}  [{vid:04X}:{pid:04X} · ID {device}]'
            return devices
        finally:
            self.free(ids)


class Playback:
    def __init__(self, directory):
        self.commands = Queue()
        self.messages = Queue()
        self.closing = Event()
        self.thread = Thread(target=self.run, args=(directory,), daemon=True)
        self.thread.start()

    def run(self, directory):
        try:
            with Gamepads(directory) as pads:
                self.play_loop(pads)
        except (OSError, AttributeError, RuntimeError) as error:
            self.messages.put(('error', f'无法初始化手柄：{error}'))

    def play_loop(self, pads):
        pad = None
        device_id = None
        samples = []
        selection = None
        devices = None
        next_refresh = 0
        started = 0
        previous = None
        last_sent = 0
        last_cursor = 0

        def finish(reason=None):
            nonlocal pad, device_id, samples
            if pad:
                if pads.connected(pad):
                    if not pads.hd(pad, *NEUTRAL, *NEUTRAL, 0):
                        pads.stop(pad, 0, 0, 0)
                    pads.update()
                pads.close(pad)
                pad = None
            device_id = None
            samples = []
            if reason:
                self.messages.put(('stopped', reason))

        try:
            while not self.closing.is_set():
                pads.update()
                now = monotonic()
                if pad and not pads.connected(pad):
                    finish('手柄已断开')
                    next_refresh = 0
                if now >= next_refresh:
                    current_devices = pads.devices()
                    if current_devices != devices:
                        devices = current_devices
                        self.messages.put(('devices', devices))
                    next_refresh = now + 0.4

                while not self.closing.is_set():
                    try:
                        command, value = self.commands.get_nowait()
                    except Empty:
                        break
                    if command == 'refresh':
                        next_refresh = 0
                    elif command == 'select':
                        selection = value
                        if pad and device_id != selection:
                            finish('已切换手柄')
                    elif command == 'stop':
                        if pad:
                            finish('已停止')
                    elif command == 'play':
                        target, wave = value
                        if target != selection or target not in devices:
                            finish('请先选择已连接的手柄')
                            continue
                        finish()
                        pad = pads.open(target)
                        if not pad:
                            self.messages.put(('stopped', f'无法打开手柄：{pads.error_text()}'))
                            continue
                        device_id, samples = target, wave
                        started = monotonic()
                        previous, last_sent, last_cursor = None, 0, 0
                        connection = {1: '有线', 2: '无线'}.get(pads.connection(pad), '')
                        label = devices[device_id]
                        self.messages.put(('playing', f'正在播放 · {label}' + (f' · {connection}' if connection else '')))

                if pad:
                    now = monotonic()
                    elapsed = (now - started) * 1000
                    index = int(elapsed / 5)
                    if index >= len(samples):
                        finish('播放完成')
                    else:
                        channels = samples[index][1:]
                        if channels != previous or now - last_sent >= 0.025:
                            if not pads.hd(pad, *channels, *channels, 50):
                                finish(f'震动发送失败：{pads.error_text()}')
                            else:
                                previous, last_sent = channels, now
                        if pad and now - last_cursor >= 0.03:
                            self.messages.put(('cursor', elapsed))
                            last_cursor = now
                if pad:
                    pads.delay(1_000_000)
                else:
                    self.closing.wait(0.025)
        finally:
            finish()


class Player:
    BG = '#101b26'
    LINE = '#304356'
    TEXT = '#c6d3df'
    LOW = '#5bd9d0'
    HIGH = '#ffc383'

    def __init__(self, root, catalog, player_factory=Playback):
        self.root, self.catalog = root, catalog
        self.worker = player_factory(SDL_DIR)
        self.devices = {}
        self.device_id = None
        self.names = []
        self.current = None
        self.wave = []
        self.cursor = None
        self.plot_frame = None
        self.closing = False

        root.title('王国之泪 · 震动测试')
        dpi = root.winfo_fpixels('1i') / 96
        width = min(round(1120 * dpi), root.winfo_screenwidth() - 70)
        height = min(round(730 * dpi), root.winfo_screenheight() - 120)
        root.geometry(f'{width}x{height}')
        root.minsize(min(850, width), min(570, height))
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.bind('<Escape>', self.stop)
        root.bind('<FocusOut>', self.focus_lost)
        root.bind('<Unmap>', lambda event: self.stop() if event.widget == root else None)

        style = ttk.Style(root)
        style.configure('Title.TLabel', font=('Microsoft YaHei UI', 18, 'bold'))
        style.configure('Effect.TLabel', font=('Microsoft YaHei UI', 12, 'bold'))
        layout = ttk.Frame(root, padding=(16, 12))
        layout.pack(fill='both', expand=True)
        ttk.Label(layout, text='王国之泪 · 震动测试', style='Title.TLabel').pack(anchor='w', pady=(0, 10))
        controls = ttk.Frame(layout)
        controls.pack(fill='x', pady=(0, 12))
        ttk.Label(controls, text='手柄').grid(row=0, column=0)
        self.device = ttk.Combobox(controls, state='readonly')
        self.device.grid(row=0, column=1, sticky='ew', padx=(8, 6))
        self.device.bind('<<ComboboxSelected>>', self.select_device)
        ttk.Button(controls, text='刷新', command=lambda: self.command('refresh')).grid(row=0, column=2)
        ttk.Label(controls, text='强度').grid(row=0, column=3, padx=(14, 5))
        self.mode = ttk.Combobox(controls, state='readonly', values=tuple(MODES), width=15)
        self.mode.current(0)
        self.mode.grid(row=0, column=4)
        self.mode.bind('<<ComboboxSelected>>', self.select_effect)
        self.play_button = ttk.Button(controls, text='播放', command=self.play, state='disabled')
        self.play_button.grid(row=0, column=5, padx=(12, 5))
        ttk.Button(controls, text='停止', command=self.stop).grid(row=0, column=6)
        controls.columnconfigure(1, weight=1)

        panes = ttk.Panedwindow(layout, orient='horizontal')
        panes.pack(fill='both', expand=True)
        left = ttk.Frame(panes, padding=(0, 0, 10, 0))
        right = ttk.Frame(panes, padding=(8, 0, 0, 0))
        panes.add(left, weight=1)
        panes.add(right, weight=4)
        self.search = tk.StringVar()
        ttk.Label(left, text='搜索资源名称').pack(anchor='w')
        ttk.Entry(left, textvariable=self.search, width=28).pack(fill='x', pady=(4, 6))
        self.count = ttk.Label(left)
        self.count.pack(anchor='w', pady=(0, 4))
        listing = ttk.Frame(left)
        listing.pack(fill='both', expand=True)
        self.effects = tk.Listbox(listing, width=30, exportselection=False, activestyle='none')
        scroll = ttk.Scrollbar(listing, orient='vertical', command=self.effects.yview)
        self.effects.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        self.effects.pack(side='left', fill='both', expand=True)
        self.effects.bind('<<ListboxSelect>>', self.select_effect)
        self.search.trace_add('write', self.filter_effects)

        self.title = ttk.Label(right, style='Effect.TLabel')
        self.title.pack(anchor='w')
        self.details = ttk.Label(right)
        self.details.pack(anchor='w', pady=(4, 8))
        self.chart = tk.Canvas(right, background=self.BG, highlightthickness=0, width=540, height=380)
        self.chart.pack(fill='both', expand=True)
        self.chart.bind('<Configure>', self.draw)
        self.status = ttk.Label(layout, text='正在识别手柄…')
        self.status.pack(anchor='w', pady=(8, 0))
        self.filter_effects()
        root.after(25, self.poll)

    def command(self, name, payload=None):
        self.worker.commands.put((name, payload))

    def update_buttons(self):
        can_play = self.current and self.device_id in self.devices and self.worker.thread.is_alive()
        self.play_button.configure(state='normal' if can_play else 'disabled')

    def filter_effects(self, *_):
        query = self.search.get().strip().casefold()
        names = [name for name in self.catalog if query in name.casefold()]
        selected = self.current if self.current in names else (names[0] if names else None)
        self.names = names
        self.effects.delete(0, 'end')
        for name in names:
            self.effects.insert('end', name.removesuffix('.bnvib'))
        if selected is not None:
            index = names.index(selected)
            self.effects.selection_set(index)
            self.effects.see(index)
        self.count.configure(text=f'{len(names)} / {len(self.catalog)} 条曲线')
        self.select_effect()

    def select_effect(self, *_):
        self.stop()
        selected = self.effects.curselection()
        self.current = self.names[selected[0]] if selected else None
        original = self.catalog.get(self.current, [])
        self.wave = scaled_samples(original, MODES[self.mode.get()])
        self.title.configure(text=self.current.removesuffix('.bnvib') if self.current else '没有匹配曲线')
        if self.wave:
            peak = max(max(row[1], row[3]) for row in self.wave)
            self.details.configure(text=f'{len(self.wave)*5/1000:.3f} 秒   ·   200 Hz 采样   ·   播放峰值 {peak:.3f}')
        else:
            self.details.configure(text='')
        self.draw()
        self.update_buttons()

    def select_device(self, *_):
        index = self.device.current()
        self.device_id = list(self.devices)[index] if index >= 0 else None
        self.command('select', self.device_id)
        self.stop()
        if self.device_id is not None:
            self.status.configure(text='已选择手柄，点击播放开始测试')
        self.update_buttons()

    def play(self):
        if self.current and self.device_id in self.devices:
            self.command('play', (self.device_id, self.wave))

    def stop(self, *_):
        self.command('stop')
        self.cursor = None
        self.update_cursor()
        if self.status.cget('text').startswith('正在播放'):
            self.status.configure(text='已停止')

    def focus_lost(self, *_):
        def check():
            if not self.closing and self.root.focus_displayof() is None:
                self.stop()
        self.root.after_idle(check)

    def draw(self, *_):
        c = self.chart
        c.delete('all')
        self.plot_frame = None
        if not self.wave:
            return
        width, height = c.winfo_width(), c.winfo_height()
        if width < 140 or height < 200:
            return
        x0, x1 = 62, width - 27
        duration = len(self.wave) * 5
        top, middle, bottom = 42, height // 2 + 4, height - 37
        plots = ((top, middle - 26, '振幅', 1, (1, 3)),
                 (middle + 15, bottom, '频率（Hz）',
                  max(100, math.ceil(max(max(row[2], row[4]) for row in self.wave) / 100) * 100), (2, 4)))
        self.plot_frame = (x0, x1, top, bottom, duration)
        for y0, y1, name, limit, channels in plots:
            c.create_text(x0, y0 - 15, text=name, fill=self.TEXT, anchor='w')
            for fraction in (0, 0.25, 0.5, 0.75, 1):
                y = y1 - fraction * (y1 - y0)
                c.create_line(x0, y, x1, y, fill=self.LINE)
                c.create_text(x0 - 8, y, text=f'{fraction * limit:g}', fill=self.TEXT, anchor='e')
                x = x0 + fraction * (x1 - x0)
                c.create_line(x, y0, x, y1, fill=self.LINE)
                if y1 == bottom:
                    c.create_text(x, bottom + 12, text=f'{fraction * duration:g}', fill=self.TEXT)
            for channel, color in zip(channels, (self.LOW, self.HIGH)):
                if channels == (1, 3) and MODES[self.mode.get()] > 1:
                    self.line(self.catalog[self.current], channel, color, x0, x1, y0, y1, limit, duration, True)
                self.line(self.wave, channel, color, x0, x1, y0, y1, limit, duration)
        c.create_text(x0, height - 9, text='时间（ms）', fill=self.TEXT, anchor='w')
        c.create_text(x1, 17, text='高频', fill=self.HIGH, anchor='e')
        c.create_text(x1 - 56, 17, text='低频', fill=self.LOW, anchor='e')
        if MODES[self.mode.get()] > 1:
            c.create_text(x1 - 115, 17, text='虚线为原始振幅', fill=self.TEXT, anchor='e')
        self.update_cursor()

    def line(self, wave, channel, color, x0, x1, y0, y1, limit, duration, dashed=False):
        points = []
        for row in wave:
            points.extend((x0 + row[0] / duration * (x1 - x0), y1 - row[channel] / limit * (y1 - y0)))
        points.extend((x1, points[-1]))
        self.chart.create_line(*points, fill=color, width=1 if dashed else 2, dash=(4, 3) if dashed else ())

    def update_cursor(self):
        self.chart.delete('cursor')
        if self.cursor is not None and self.plot_frame:
            x0, x1, y0, y1, duration = self.plot_frame
            x = x0 + min(1, self.cursor / duration) * (x1 - x0)
            self.chart.create_line(x, y0, x, y1, fill='#e8f1fb', tags='cursor')

    def poll(self):
        if self.closing:
            return
        while True:
            try:
                kind, value = self.worker.messages.get_nowait()
            except Empty:
                break
            if kind == 'devices':
                self.devices = value
                self.device.configure(values=tuple(value.values()))
                if self.device_id in value:
                    self.device.current(list(value).index(self.device_id))
                else:
                    self.device_id = None
                    self.device.set('')
                    self.command('select')
                    self.status.configure(text='请选择要测试的手柄' if value else '未发现手柄 · 连接后会自动刷新')
                self.update_buttons()
            elif kind == 'cursor':
                self.cursor = value
                self.update_cursor()
            else:
                self.status.configure(text=value)
                if kind in ('stopped', 'error'):
                    self.cursor = None
                    self.update_cursor()
        self.update_buttons()
        self.root.after(25, self.poll)

    def close(self):
        self.closing = True
        self.worker.closing.set()
        self.root.withdraw()

        def finish():
            if self.worker.thread.is_alive():
                self.root.after(15, finish)
            else:
                self.root.destroy()
        finish()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, default=CATALOG)
    args = parser.parse_args()
    if os.name == 'nt':
        ct.windll.shcore.SetProcessDpiAwareness(1)
    root = tk.Tk()
    try:
        catalog = load_catalog(args.catalog)
    except (OSError, ValueError, KeyError) as error:
        root.withdraw()
        messagebox.showerror('无法读取震动曲线', f'{args.catalog}\n\n{error}', parent=root)
        root.destroy()
        return 1
    Player(root, catalog)
    root.mainloop()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
