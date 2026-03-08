#!/usr/bin/env python3
"""
A simple Tkinter GUI wrapper around the original json_to_csv.py logic.

Features:
- Select input JSON file
- Select output CSV file (suggested name auto-filled)
- Optional custom comma-separated field order (leave blank to use built-in example order)
- Convert button (runs in a background thread so the UI stays responsive)
- Log / status area and progress bar
- Error handling with message boxes

Save this file and run:
    python json_to_csv_tk.py
"""
import json
import csv
import threading
import traceback
import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# --- Flattening / conversion logic (adapted from your original script) ---

def flatten_quotes(quotes):
    if not quotes:
        return ""
    return "||".join([
        f"{q.get('date','')} | {q.get('horse','')} | {q.get('horse_id','')} | {q.get('race','')} | {q.get('race_id','')} | {q.get('course','')} | {q.get('course_id','')} | {q.get('distance_f','')} | {q.get('distance_y','')} | {q.get('quote','')}"
        for q in quotes
    ])

def flatten_stable_tour(stable_tour):
    if not stable_tour:
        return ""
    return "||".join([
        f"{t.get('horse','')} | {t.get('horse_id','')} | {t.get('quote','')}"
        for t in stable_tour
    ])

def flatten_prev_owners(prev_owners):
    if not prev_owners:
        return ""
    return "||".join([
        f"{o.get('owner','')} ({o.get('change_date','')})"
        for o in prev_owners
    ])

def flatten_stats(stats: dict, prefix: str):
    out = {}
    for key, value in stats.items():
        if isinstance(value, dict):
            for k2, v2 in value.items():
                out[f"{prefix}_{key}_{k2}"] = v2
        else:
            out[f"{prefix}_{key}"] = value
    return out

def flatten_runner(runner: dict):
    flat = {}
    for k, v in runner.items():
        if k == "quotes":
            flat["quotes"] = flatten_quotes(v)
        elif k == "stable_tour":
            flat["stable_tour"] = flatten_stable_tour(v)
        elif k == "prev_owners":
            flat["prev_owners"] = flatten_prev_owners(v)
        elif k == "stats":
            flat.update(flatten_stats(v, "stats"))
        elif isinstance(v, dict):
            for k2, v2 in v.items():
                flat[f"{k}_{k2}"] = v2
        else:
            flat[k] = v
    return flat

def flatten_race(race: dict):
    # All keys except runners
    flat = {k: v for k, v in race.items() if k != "runners"}
    return flat

def find_races(data: dict):
    # Assumes structure is country > course > time > race
    # It's defensive: iterates nested dicts to find 'runners' containing races.
    # If the structure differs, user should inspect/adjust.
    for country in data.values():
        if not isinstance(country, dict):
            continue
        for course in country.values():
            if not isinstance(course, dict):
                continue
            for time, race in course.items():
                # race may be a dict; yield if so
                if isinstance(race, dict):
                    yield race

# Default example order used if user does not specify a custom order
DEFAULT_EXAMPLE_ORDER = [
    "course", "going_detailed", "off_time",  "race_name","pattern", "distance_round","race_class", "age_band", "rating_band", "prize", "field_size",
     "name","age", "sex","number", "draw",  "trainer","jockey","headgear", "headgear_first", "lbs", "ofr", "rpr", "ts",
     "last_run", "form", "comment", "spotlight", "quotes", "stable_tour","trainer_rtf", "stats_course_runs", "stats_course_wins", "stats_distance_runs",
]

def convert_json_to_csv(json_file: str, csv_file: str, custom_order_csv: str = None, log_fn=None):
    """
    Convert JSON to CSV using the flattening rules.
    - custom_order_csv: optional string of comma-separated fieldnames that will be used at the front of CSV columns.
    - log_fn: optional function to receive log lines (log_fn(str))
    """
    def log(msg=""):
        if log_fn:
            log_fn(msg)

    log(f"Loading JSON file: {json_file}")
    with open(json_file, encoding="utf-8") as f:
        data = json.load(f)

    rows = []
    for race in find_races(data):
        race_flat = flatten_race(race)
        for runner in race.get('runners', []):
            row = {}
            row.update(race_flat)
            row.update(flatten_runner(runner))
            rows.append(row)

    if not rows:
        log("Warning: No rows found in JSON structure. The CSV will be empty.")
    else:
        log(f"Found {len(rows)} rows to write to CSV.")

    # Collect all fieldnames
    fieldnames = set()
    for r in rows:
        fieldnames.update(r.keys())

    # Determine ordered fields
    custom_order = []
    if custom_order_csv:
        # Parse user-provided comma-separated order
        # Remove empty tokens, strip whitespace
        custom_order = [f.strip() for f in custom_order_csv.split(",") if f.strip()]
        log(f"Custom order specified ({len(custom_order)} fields).")

    # Build ordered_fields list:
    if custom_order:
        ordered_fields = [f for f in custom_order if f in fieldnames] + [f for f in fieldnames if f not in custom_order]
    else:
        ordered_fields = [f for f in DEFAULT_EXAMPLE_ORDER if f in fieldnames] + [f for f in fieldnames if f not in DEFAULT_EXAMPLE_ORDER]

    log(f"Writing CSV to: {csv_file}")
    os.makedirs(os.path.dirname(csv_file) or ".", exist_ok=True)
    with open(csv_file, "w", encoding="utf-8", newline='') as f:
        writer = csv.DictWriter(f, fieldnames=ordered_fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    log("Finished writing CSV.")

# --- Tkinter GUI ---

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("JSON → CSV Converter")
        self.minsize(700, 400)
        self.create_widgets()

        # State
        self.json_path = ""
        self.csv_path = ""

    def create_widgets(self):
        pad = 8
        frm = ttk.Frame(self)
        frm.pack(fill="both", expand=True, padx=pad, pady=pad)

        # Input file selection
        in_row = ttk.Frame(frm)
        in_row.pack(fill="x", pady=(0, 6))
        ttk.Label(in_row, text="JSON input:").pack(side="left")
        self.in_label = ttk.Label(in_row, text="(not selected)", width=60, anchor="w")
        self.in_label.pack(side="left", padx=(6, 8))
        ttk.Button(in_row, text="Select JSON...", command=self.select_json).pack(side="right")

        # Output file selection
        out_row = ttk.Frame(frm)
        out_row.pack(fill="x", pady=(0, 6))
        ttk.Label(out_row, text="CSV output:").pack(side="left")
        self.out_label = ttk.Label(out_row, text="(not selected)", width=60, anchor="w")
        self.out_label.pack(side="left", padx=(6, 8))
        ttk.Button(out_row, text="Select CSV...", command=self.select_csv).pack(side="right")

        # Custom order entry
        order_row = ttk.Frame(frm)
        order_row.pack(fill="x", pady=(0, 6))
        ttk.Label(order_row, text="Optional column order (comma-separated):").pack(side="left")
        self.order_entry = ttk.Entry(order_row)
        self.order_entry.pack(fill="x", expand=True, side="left", padx=(6, 8))
        ttk.Button(order_row, text="Use default", command=self.clear_order).pack(side="right")

        # Controls row
        controls = ttk.Frame(frm)
        controls.pack(fill="x", pady=(0, 6))
        self.convert_btn = ttk.Button(controls, text="Convert", command=self.start_conversion_thread)
        self.convert_btn.pack(side="left")
        self.open_after_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(controls, text="Open CSV when done", variable=self.open_after_var).pack(side="left", padx=(8,0))

        # Progress bar
        self.progress = ttk.Progressbar(controls, mode="determinate")
        self.progress.pack(fill="x", expand=True, side="left", padx=(12, 0))

        # Log text area
        log_label = ttk.Label(frm, text="Log / status:")
        log_label.pack(anchor="w")
        self.log_text = tk.Text(frm, height=12, wrap="none")
        self.log_text.pack(fill="both", expand=True)
        # Add scrollbars
        scroll_y = ttk.Scrollbar(self.log_text.master, orient="vertical", command=self.log_text.yview)
        scroll_x = ttk.Scrollbar(self.log_text.master, orient="horizontal", command=self.log_text.xview)
        self.log_text['yscrollcommand'] = scroll_y.set
        self.log_text['xscrollcommand'] = scroll_x.set
        scroll_y.pack(side="right", fill="y")
        scroll_x.pack(side="bottom", fill="x")

        # Menu (basic)
        menubar = tk.Menu(self)
        filemenu = tk.Menu(menubar, tearoff=0)
        filemenu.add_command(label="Select JSON...", command=self.select_json)
        filemenu.add_command(label="Select CSV...", command=self.select_csv)
        filemenu.add_separator()
        filemenu.add_command(label="Exit", command=self.quit)
        menubar.add_cascade(label="File", menu=filemenu)
        helpmenu = tk.Menu(menubar, tearoff=0)
        helpmenu.add_command(label="About", command=self.show_about)
        menubar.add_cascade(label="Help", menu=helpmenu)
        self.config(menu=menubar)

    def log(self, message=""):
        # Append message to log_text in the main thread
        def append():
            self.log_text.insert("end", message + "\n")
            self.log_text.see("end")
        self.after(0, append)

    def select_json(self):
        path = filedialog.askopenfilename(title="Select JSON file", filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if path:
            self.json_path = path
            self.in_label.config(text=os.path.basename(path) + " — " + path)
            # Suggest an output CSV file next to input if none set
            if not self.csv_path:
                base = os.path.splitext(path)[0]
                suggested = base + ".csv"
                self.csv_path = suggested
                self.out_label.config(text=os.path.basename(suggested) + " — " + suggested)

    def select_csv(self):
        path = filedialog.asksaveasfilename(title="Select output CSV file", defaultextension=".csv", filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if path:
            self.csv_path = path
            self.out_label.config(text=os.path.basename(path) + " — " + path)

    def clear_order(self):
        self.order_entry.delete(0, "end")

    def start_conversion_thread(self):
        if not self.json_path:
            messagebox.showwarning("Missing input", "Please select an input JSON file.")
            return
        if not self.csv_path:
            messagebox.showwarning("Missing output", "Please select an output CSV file.")
            return

        # disable UI controls
        self.convert_btn.config(state="disabled")
        self.progress.config(mode="indeterminate")
        self.progress.start(10)
        self.log_text.delete("1.0", "end")
        self.log("Starting conversion...")

        thread = threading.Thread(target=self._run_conversion, daemon=True)
        thread.start()

    def _run_conversion(self):
        try:
            custom_order = self.order_entry.get().strip()
            # define a logger function to send logs to UI
            def logger(msg=""):
                self.log(msg)

            convert_json_to_csv(self.json_path, self.csv_path, custom_order_csv=custom_order or None, log_fn=logger)
            self.log("Conversion completed successfully.")
            if self.open_after_var.get():
                try:
                    self.open_file_with_default_app(self.csv_path)
                except Exception as e:
                    self.log(f"Could not open file automatically: {e}")
            messagebox.showinfo("Done", f"CSV written to:\n{self.csv_path}")
        except Exception as e:
            tb = traceback.format_exc()
            self.log("ERROR: " + str(e))
            self.log(tb)
            messagebox.showerror("Error", f"An error occurred during conversion:\n{e}\n\nSee log for details.")
        finally:
            # re-enable UI
            def reset_ui():
                self.convert_btn.config(state="normal")
                self.progress.stop()
                self.progress.config(mode="determinate", value=0)
            self.after(0, reset_ui)

    @staticmethod
    def open_file_with_default_app(path):
        if sys.platform.startswith("darwin"):
            os.system(f"open {shlex_quote(path)}")
        elif os.name == "nt":
            os.startfile(path)
        else:
            # Linux and others
            os.system(f"xdg-open {shlex_quote(path)}")

    def show_about(self):
        messagebox.showinfo("About", "JSON → CSV Converter\nTkinter app\nBased on a conversion script.")

def shlex_quote(s):
    # simple quoting helper for opening files via os.system
    return '"' + s.replace('"', '\\"') + '"'

def main():
    app = App()
    app.mainloop()

if __name__ == "__main__":
    main()
