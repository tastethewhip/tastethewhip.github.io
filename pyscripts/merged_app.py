#!/usr/bin/env ~/venv/bin/python3
"""
merged_app.py

Combines Meld (plotting/interactive) and SaturdayViewer (CSV search/table) into a
single Tkinter application with tabs. Adds:
 - "Include all horses from matched race(s)" option in the SaturdayViewer tab.
 - Persist column show/hide settings per CSV file (saved to ~/.merged_app_settings.json).
 - Allow user to pick which CSV column should be treated as the race identifier
   (persisted per CSV file).
Usage:
    python merged_app.py
"""
import os
import io
import sys
import csv
import re
import json
import platform
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
import tkinter.font as tkfont
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from PIL import Image, ImageTk
import multiprocessing
import webbrowser

# Try import pywebview lazily; used only when embedding interactive view
try:
    import webview  # pywebview
    _HAS_PYWEBVIEW = True
except Exception:
    webview = None
    _HAS_PYWEBVIEW = False

# --- mappings (kept from original meld_orig) ---
DISTANCE_MAP = {
    '5f': 50,
    '5½f':55,
    '6f': 60,
    '6½f': 65,
    '7f': 70,
    '7½f': 75,
    '1m': 80,
    '1m½f': 85,
    '1m1f': 90,
    '1m1½f':95,
    '1m2f': 100,
    '1m2½f': 105,
    '1m3f': 110,
    '1m3½f': 115,
    '1m4f': 120,
    '1m4½f': 125,
    '1m5f': 130,
    '1m5½f': 135,
    '1m6f': 140,
    '1m7f': 150,
    '1m7½f': 155,
    '2m': 160,
    '2m½f': 165,
    '2m1f': 170,
    '2m1½f': 175,
    '2m2f': 180,
    '2m2½f': 185,
    '2m3f': 190,
    '2m3½f': 195,
    '2m4f': 200,
    '2m4½f': 205,
    '2m5f': 210,
    '2m5½f': 215,
    '2m6f': 220,
    '2m6½f': 225,
    '2m7f': 230,
    '2m7½f': 235,
    '3m': 240,
    '3m½f': 245,
    '3m1f': 250,
    '3m1½f': 255,
    '3m2f': 260
}

GOING_MAP = {
    'Good': 100,
    'Good To Firm': 110,
    'Firm': 120,
    'Good To Soft': 90,
    'Good To Yielding': 90,
    'Soft': 80,
    'Yielding': 80,
    'Very Soft': 85,
    'Heavy': 70,
    'Standard': 100,
    'Standard To Slow': 80
}

DEFAULT_CSV = "recent.csv"
DEFAULT_SAT_CSV = "today.csv"

# Settings persistence ---------------------------------------------------------
class SettingsManager:
    """
    Simple JSON-backed settings store in the user's home directory.
    Stores visible columns per CSV file path:
      {
        "visible_columns": { "/full/path/to/file.csv": ["col1", "col2", ...], ... },
        "race_id_column": { "/full/path/to/file.csv": "race_id", ... }
      }
    """
    def __init__(self, filename=None):
        if filename:
            self.path = filename
        else:
            self.path = os.path.join(os.path.expanduser("~"), ".merged_app_settings.json")
        self._data = {}
        self._load()

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as fh:
                    self._data = json.load(fh) or {}
            except Exception:
                self._data = {}
        else:
            self._data = {}

    def _save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh, indent=2, ensure_ascii=False)
        except Exception:
            # best-effort; don't crash the app for settings save failures
            pass

    def get_visible_columns(self, csv_path):
        if not csv_path:
            return None
        vc = self._data.get("visible_columns", {})
        return vc.get(os.path.abspath(csv_path))

    def set_visible_columns(self, csv_path, columns):
        if not csv_path:
            return
        if "visible_columns" not in self._data:
            self._data["visible_columns"] = {}
        self._data["visible_columns"][os.path.abspath(csv_path)] = list(columns)
        self._save()

    def get_race_column(self, csv_path):
        """Return the persisted race-id column name for this CSV (or None)."""
        if not csv_path:
            return None
        rcmap = self._data.get("race_id_column", {})
        return rcmap.get(os.path.abspath(csv_path))

    def set_race_column(self, csv_path, column_name):
        """Persist the race-id column name for this CSV."""
        if not csv_path:
            return
        if "race_id_column" not in self._data:
            self._data["race_id_column"] = {}
        # store actual string or None
        self._data["race_id_column"][os.path.abspath(csv_path)] = column_name if column_name else None
        self._save()

# instantiate global settings manager
SETTINGS = SettingsManager()

# --- Meld helpers (mostly from meld_orig) ---
def safe_read_csv(path):
    try:
        df = pd.read_csv(path, engine='python', on_bad_lines='skip')
        return df
    except Exception as e:
        raise RuntimeError(f"Failed to read CSV '{path}': {e}")

def prepare_numeric_columns(df):
    for col in ['or', 'rpr', 'ts', 'num', 'draw']:
        if col in df.columns:
            df.loc[:, col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
        else:
            df.loc[:, col] = 0
    return df

def map_distance_going(df):
    if 'dist' not in df.columns:
        df['dist'] = ""
    if 'going' not in df.columns:
        df['going'] = ""
    df['dist_numeric'] = df['dist'].map(DISTANCE_MAP).fillna(0)
    df['going_numeric'] = df['going'].map(GOING_MAP).fillna(0)
    return df

def build_horse_figure(filtered_df):
    fig = go.Figure()
    if filtered_df.empty:
        return fig
    for index, row in filtered_df.iterrows():
        hover_texts = [
            f"or: {row.get('or','')}",
            f"{row.get('course','')},{row.get('dist','')},{row.get('race_name','')}",
            f"going: {row.get('going','')}",
            f"rpr: {row.get('rpr','')},{row.get('comment','')},{row.get('sp','')},£{row.get('prize','')}",
            f"ts: {row.get('ts','')},{row.get('pos','')}/{row.get('ran','')} runners",
            f"or: {row.get('or','')}"
        ]
        rvals = [
            row.get('or', 0),
            row.get('dist_numeric', 0),
            row.get('going_numeric', 0),
            row.get('rpr', 0),
            row.get('ts', 0),
            row.get('or', 0)
        ]
        fig.add_trace(go.Scatterpolar(
            r=rvals,
            theta=['or', 'dist', 'going', 'rpr', 'ts', 'or'],
            mode='lines+markers',
            name=f"Race {row.get('race_id','')},{row.get('course','')},{row.get('dist','')},{row.get('class','')},{row.get('pattern','')}",
            hoverinfo='text',
            text=hover_texts
        ))

    max_val = int(filtered_df[['or', 'dist_numeric', 'going_numeric', 'rpr', 'ts']].max().max()) if not filtered_df.empty else 100
    fig.update_layout(
        title=filtered_df.iloc[-1]['horse'] if not filtered_df.empty and 'horse' in filtered_df.columns else "Horse",
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, max_val]
            )
        ),
        autosize=True,
        margin=dict(l=30, r=30, t=50, b=30)
    )
    return fig

def build_race_figure(filtered_df):
    fig = go.Figure()
    if filtered_df.empty:
        return fig
    for index, row in filtered_df.iterrows():
        hover_texts = [
            f"or: {row.get('or','')}",
            f"rpr: {row.get('rpr','')},{row.get('comment','')},{row.get('sp','')},£{row.get('prize','')}",
            f"ts: {row.get('ts','')},{row.get('pos','')}/{row.get('ran','')} runners",
            f"or: {row.get('or','')},{row.get('horse','')}"
        ]
        rvals = [row.get('or', 0), row.get('rpr', 0), row.get('ts', 0), row.get('or', 0)]
        fig.add_trace(go.Scatterpolar(
            r=rvals,
            theta=['or', 'rpr', 'ts', 'or'],
            mode='lines+markers',
            name=f"{row.get('horse','')},{row.get('pos','')}",
            hoverinfo='text',
            text=hover_texts
        ))

    max_val = int(filtered_df[['or', 'rpr', 'ts']].max().max()) if not filtered_df.empty else 100
    title = ""
    first = filtered_df.iloc[0] if not filtered_df.empty else None
    if first is not None:
        title = f"{first.get('race_name','')},{first.get('class','')},{first.get('pattern','')},{first.get('dist','')},{first.get('going','')}"
    fig.update_layout(
        title=title,
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, max_val]
            )
        ),
        autosize=True,
        margin=dict(l=30, r=30, t=50, b=30)
    )
    return fig

def figure_to_photoimage(fig, width=900, height=500):
    """
    Convert a plotly figure to a Tk PhotoImage using kaleido backend.
    This produces a static PNG image of the interactive plot, which can be displayed inside Tkinter.
    Requires: pip install kaleido pillow
    """
    try:
        img_bytes = pio.to_image(fig, format='png', width=width, height=height, scale=1)
    except Exception as e:
        raise RuntimeError(f"Failed to render figure to image. Make sure 'kaleido' is installed. Original error: {e}")
    image = Image.open(io.BytesIO(img_bytes))
    return ImageTk.PhotoImage(image)

def _start_webview_process(html_path: str):
    """
    Run pywebview in a separate process so webview.start() runs on that
    process's main thread. This function must be top-level so it is picklable
    for multiprocessing on Windows.
    """
    try:
        # local import inside child process to avoid requiring pywebview in parent
        import webview as _webview
        url = f'file://{os.path.abspath(html_path)}'
        _webview.create_window("Meld - Interactive Plot", url, width=1000, height=700, resizable=True)
        _webview.start()
    except Exception as e:
        # Child process can't call self.log(); print to stderr so it shows up in console/logs.
        print(f"pywebview (child) error: {e}", file=sys.stderr)


# --- SaturdayViewer (adapted to include the checkbox and settings persistence) ---
class SaturdayViewer:
    def __init__(self, parent, default_csv=DEFAULT_SAT_CSV):
        self.root = parent
        self.filename = None
        self.rows = []
        self.headers = []
        self.last_matches = []
        self.visible_columns = []    # currently displayed columns (displaycolumns)
        self.hidden_columns = []     # columns hidden by user
        self.default_csv = default_csv

        # New option: include all horses from the same race(s)
        self.include_race_var = tk.BooleanVar(value=False)

        # Race id column selection (persisted per CSV)
        self.race_col_var = tk.StringVar(value="")  # holds the selected header name (exact)

        self._build_ui()
        # attempt to load default csv if present
        if os.path.exists(self.default_csv):
            self.load_csv(self.default_csv)

    def _build_ui(self):
        frm_top = ttk.Frame(self.root)
        frm_top.pack(fill="x", padx=8, pady=6)

        ttk.Label(frm_top, text="CSV file:").pack(side="left")
        self.lbl_file = ttk.Label(frm_top, text="(no file loaded)", width=48)
        self.lbl_file.pack(side="left", padx=(6, 12))

        btn_change = ttk.Button(frm_top, text="Choose file...", command=self.choose_file)
        btn_change.pack(side="left")

        btn_manage = ttk.Button(frm_top, text="Manage columns...", command=self.manage_columns)
        btn_manage.pack(side="left", padx=(6, 6))

        sep = ttk.Separator(self.root, orient="horizontal")
        sep.pack(fill="x", padx=8, pady=6)

        # --- SEARCH AREA ---
        frm_search = ttk.Frame(self.root)
        frm_search.pack(fill="x", padx=8)

        lbl_text = ("Search (regex) horse name(s) — separate patterns with "
                    "comma/semicolon/pipe/newline:")
        ttk.Label(frm_search, text=lbl_text).pack(anchor="w", pady=(0, 4))

        frm_controls = ttk.Frame(frm_search)
        frm_controls.pack(fill="x")

        # Entry expands to take available horizontal space
        self.entry_re = ttk.Entry(frm_controls, width=60)
        self.entry_re.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.entry_re.bind("<Return>", lambda e: self.run_search())

        btn_search = ttk.Button(frm_controls, text="Search", command=self.run_search)
        btn_search.pack(side="left", padx=(0, 6))

        btn_clear = ttk.Button(frm_controls, text="Clear", command=self.clear_search)
        btn_clear.pack(side="left", padx=(0, 6))

        # Checkbox: include all horses from the same race(s)
        chk_include_race = ttk.Checkbutton(
            frm_controls,
            text="Include all horses from matched race(s)",
            variable=self.include_race_var
        )
        chk_include_race.pack(side="left", padx=(6, 6))

        # Combobox: pick which column to treat as race identifier
        # (only exact header names are accepted)
        frm_racecol = ttk.Frame(frm_controls)
        frm_racecol.pack(side="left", padx=(6, 0))
        ttk.Label(frm_racecol, text="Race id column:").pack(side="left", padx=(0, 4))
        self.cmb_race_col = ttk.Combobox(frm_racecol, textvariable=self.race_col_var, state="readonly", width=20)
        self.cmb_race_col['values'] = []  # populated when CSV loaded
        self.cmb_race_col.pack(side="left")
        # When user changes selection, persist it for this CSV
        self.race_col_var.trace_add("write", lambda *a: self._on_race_col_changed())

        self.btn_export = ttk.Button(frm_controls, text="Export matches...", command=self.export_matches, state="disabled")
        self.btn_export.pack(side="left", padx=(6, 0))

        self.btn_resize_all = ttk.Button(frm_controls, text="Auto-resize columns", command=self.auto_resize_all_columns)
        self.btn_resize_all.pack(side="left", padx=(6, 0))

        frm_count = ttk.Frame(frm_search)
        frm_count.pack(fill="x", pady=(6, 0))
        self.lbl_count = ttk.Label(frm_count, text="")
        self.lbl_count.pack(side="right")

        # Frame for table + scrollbars (grid so horizontal scrollbar sits under the tree)
        frame_tbl = ttk.Frame(self.root)
        frame_tbl.pack(fill="both", expand=True, padx=8, pady=(6, 0))

        # Treeview - columns configured after loading a CSV
        self.tree = ttk.Treeview(frame_tbl, columns=(), show="headings", selectmode="browse")

        # Scrollbars
        self.vsb = ttk.Scrollbar(frame_tbl, orient="vertical", command=self.tree.yview)
        self.hsb = ttk.Scrollbar(frame_tbl, orient="horizontal", command=self.tree.xview)

        # attach scroll commands to the tree
        self.tree.configure(yscrollcommand=self.vsb.set, xscrollcommand=self.hsb.set)

        # Place widgets using grid so the horizontal scrollbar sits under the tree
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.vsb.grid(row=0, column=1, sticky="ns")
        self.hsb.grid(row=1, column=0, columnspan=2, sticky="ew")

        # Make the tree expand with the frame
        frame_tbl.rowconfigure(0, weight=1)
        frame_tbl.columnconfigure(0, weight=1)

        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.tree.bind("<Button-3>", self._on_right_click)
        self.tree.bind("<Button-2>", self._on_right_click)  # some systems use Button-2 for right-click

        # Lower frame for full row details
        frame_details = ttk.Frame(self.root)
        frame_details.pack(fill="both", expand=False, padx=8, pady=6)

        ttk.Label(frame_details, text="Full row details:").pack(anchor="w")
        self.txt_details = tk.Text(frame_details, height=10, wrap="word")
        self.txt_details.pack(fill="both", expand=True)
        self.txt_details.configure(state="disabled")

        # Optional: allow Shift+MouseWheel to scroll horizontally
        self._bind_horizontal_scroll()

        # Context menu for header interactions
        self.header_menu = tk.Menu(self.root, tearoff=0)
        self.header_menu.add_command(label="Hide this column", command=self._hide_column_from_menu)
        self.header_menu.add_command(label="Resize this column to contents", command=self._resize_column_from_menu)
        self.header_menu.add_command(label="Resize all columns to contents", command=self.auto_resize_all_columns)
        self.header_menu.add_separator()
        self.header_menu.add_command(label="Show all columns", command=self._reset_columns_from_menu)

        # Track which column was right-clicked (store the column name)
        self._rc_column = None

    def _on_race_col_changed(self):
        # Persist selection for this CSV when user picks a race column
        try:
            SETTINGS.set_race_column(self.filename, self.race_col_var.get())
        except Exception:
            pass

    def _bind_horizontal_scroll(self):
        system = platform.system()
        if system == "Windows":
            self.tree.bind_all("<Shift-MouseWheel>", self._on_shift_mousewheel_windows)
        elif system == "Darwin":
            self.tree.bind_all("<Shift-MouseWheel>", self._on_shift_mousewheel_mac)
        else:
            self.tree.bind_all("<Shift-Button-4>", lambda e: self._scroll_x(-1))
            self.tree.bind_all("<Shift-Button-5>", lambda e: self._scroll_x(1))
            self.tree.bind_all("<Shift-MouseWheel>", lambda e: self._scroll_x(-int(e.delta / 120)))

    def _on_shift_mousewheel_windows(self, event):
        steps = -int(event.delta / 120)
        self._scroll_x(steps)

    def _on_shift_mousewheel_mac(self, event):
        steps = -int(event.delta)
        self._scroll_x(steps)

    def _scroll_x(self, steps):
        try:
            self.tree.xview_scroll(steps, "units")
        except Exception:
            pass

    def _on_right_click(self, event):
        # If right-click is on a heading, show header context menu
        region = self.tree.identify_region(event.x, event.y)
        if region == "heading":
            col_id = self.tree.identify_column(event.x)
            try:
                idx = int(col_id.replace("#", "")) - 1
                all_cols = list(self.tree["columns"])
                if 0 <= idx < len(all_cols):
                    colname = all_cols[idx]
                else:
                    colname = None
            except Exception:
                colname = None
            self._rc_column = colname
            try:
                self.header_menu.tk_popup(event.x_root, event.y_root)
            finally:
                self.header_menu.grab_release()
        else:
            return

    def _hide_column_from_menu(self):
        if not self._rc_column:
            return
        self.hide_column(self._rc_column)

    def _resize_column_from_menu(self):
        if not self._rc_column:
            return
        self.auto_resize_column(self._rc_column)

    def _reset_columns_from_menu(self):
        self.reset_columns()

    def choose_file(self):
        f = filedialog.askopenfilename(title="Select CSV file", filetypes=[("CSV files", "* .csv"), ("All files", "*.*")])
        if f:
            self.load_csv(f)

    def load_csv(self, path):
        if not os.path.isfile(path):
            self.lbl_file.configure(text=f"File not found: {path}")
            messagebox.showinfo("File not found", f"Could not find {path}. Please choose the CSV file.")
            return

        try:
            with open(path, newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                self.headers = reader.fieldnames or []
                self.rows = [row for row in reader]
        except Exception as e:
            messagebox.showerror("Error reading CSV", f"Failed to read CSV file:\n{e}")
            return

        self.filename = path
        display_name = os.path.basename(path)
        self.lbl_file.configure(text=display_name)

        # Use ALL headers as tree columns (preserve CSV order)
        cols = list(self.headers) if self.headers else []
        if not cols:
            cols = ["(no columns)"]

        # Reconfigure tree to show all CSV columns
        self.tree.config(columns=cols)
        for col in cols:
            self.tree.heading(col, text=col)
            # set a reasonable initial width; final width will be computed by auto-resize
            self.tree.column(col, width=120, anchor="w", stretch=False)

        # Reset visibility state (loading a new file shows all columns by default)
        # but read saved settings for this CSV (if any)
        saved = SETTINGS.get_visible_columns(path)
        if saved:
            # only keep columns that still exist in the file
            self.visible_columns = [c for c in saved if c in cols]
            # ensure there's at least one visible column
            if not self.visible_columns:
                self.visible_columns = list(cols)
        else:
            self.visible_columns = list(cols)

        self.hidden_columns = [c for c in cols if c not in self.visible_columns]
        self.tree["displaycolumns"] = self.visible_columns

        # Populate race column combobox values and restore saved selection (if any)
        try:
            self.cmb_race_col['values'] = cols
            # prefer persisted selection for this CSV, else pick exact 'race_id' if present
            saved_race_col = SETTINGS.get_race_column(path)
            if saved_race_col and saved_race_col in cols:
                self.race_col_var.set(saved_race_col)
            else:
                # default best-effort
                if any(h.lower() == "race_id" for h in cols):
                    # use the header that exactly matches case-insensitive "race_id"
                    for h in cols:
                        if h.lower() == "race_id":
                            self.race_col_var.set(h)
                            break
                else:
                    # leave empty (user can pick)
                    self.race_col_var.set("")
        except Exception:
            pass

        # Clear current results and details
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self.txt_details.configure(state="normal")
        self.txt_details.delete("1.0", "end")
        self.txt_details.configure(state="disabled")
        self.lbl_count.configure(text=f"Rows loaded: {len(self.rows)}")
        self.btn_export.config(state="disabled")
        self.last_matches = []

        # Auto-resize after the UI has had a chance to update (ensure fonts are available)
        self.root.update_idletasks()
        self.auto_resize_all_columns()

    def clear_search(self):
        self.entry_re.delete(0, "end")
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self.lbl_count.configure(text=f"Rows loaded: {len(self.rows)}")
        self.txt_details.configure(state="normal")
        self.txt_details.delete("1.0", "end")
        self.txt_details.configure(state="disabled")
        self.last_matches = []
        self.btn_export.config(state="disabled")
        self.tree["displaycolumns"] = self.visible_columns

    def _parse_patterns(self, raw_text):
        parts = [p.strip() for p in re.split(r'[,\n;|]+', raw_text) if p.strip()]
        return parts

    def run_search(self):
        raw = self.entry_re.get().strip()
        if not raw:
            messagebox.showinfo("No pattern", "Please enter one or more regex patterns (e.g. Vintage, ^Venture|Clarets).")
            return

        patterns = self._parse_patterns(raw)
        if not patterns:
            messagebox.showinfo("No pattern", "Please enter at least one non-empty pattern.")
            return

        compiled = []
        try:
            for p in patterns:
                compiled.append(re.compile(p, re.IGNORECASE))
        except re.error as e:
            messagebox.showerror("Regex error", f"Invalid regular expression '{p}':\n{e}")
            return

        name_col = None
        for h in self.headers:
            if h.lower() == "name":
                name_col = h
                break
        if not name_col:
            messagebox.showerror("No 'name' column", "CSV does not contain a 'name' column.")
            return

        # First-pass: rows matching the name regex patterns
        base_matches = []
        for row in self.rows:
            val = row.get(name_col, "") or ""
            for rx in compiled:
                if rx.search(val):
                    base_matches.append(row)
                    break

        if not base_matches:
            # populate tree with ALL columns (the tree's columns are the CSV headers) but no rows
            for iid in self.tree.get_children():
                self.tree.delete(iid)
            self.lbl_count.configure(text="No matches found.")
            self.last_matches = []
            self.btn_export.config(state="disabled")
            self.txt_details.configure(state="normal")
            self.txt_details.delete("1.0", "end")
            self.txt_details.insert("1.0", "No matches found.")
            self.txt_details.configure(state="disabled")
            return

        # If user wants to include all horses from the same race(s), expand the result set:
        expanded_matches = None
        included_race_count = 0
        if self.include_race_var.get():
            # Use only the column explicitly chosen by the user in the combobox.
            race_col = self.race_col_var.get().strip() if self.race_col_var.get() else None

            if not race_col:
                # cannot expand by race if no race column selected
                messagebox.showinfo("Race column not selected", "No race identifier column selected. Please choose a column from the 'Race id column' dropdown to expand matches by race. Returning only direct matches.")
                expanded_matches = base_matches
            else:
                # gather all race ids present in matched rows
                race_ids = set()
                for r in base_matches:
                    val = r.get(race_col, "")
                    race_ids.add(val)
                # include all rows whose race_col value is in race_ids
                expanded = []
                seen = set()
                for idx, row in enumerate(self.rows):
                    key = (idx,)  # unique per-row key because CSV rows may not have unique content
                    if row.get(race_col, "") in race_ids:
                        if key not in seen:
                            expanded.append(row)
                            seen.add(key)
                expanded_matches = expanded
                included_race_count = len(race_ids)
        else:
            expanded_matches = base_matches

        # populate tree with ALL columns (the tree's columns are the CSV headers)
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        cols = list(self.tree["columns"])
        for i, row in enumerate(expanded_matches):
            values = [self._shorten(row.get(c, "")) for c in cols]
            self.tree.insert("", "end", iid=str(i), values=values)

        # update labels and state
        if self.include_race_var.get() and included_race_count:
            self.lbl_count.configure(text=f"Matches: {len(base_matches)} (expanded to {len(expanded_matches)} rows from {included_race_count} race(s))")
        else:
            self.lbl_count.configure(text=f"Matches: {len(expanded_matches)} (patterns: {', '.join(patterns)})")

        self.last_matches = expanded_matches
        self.btn_export.config(state="normal" if expanded_matches else "disabled")

        # Ensure the UI updates before resizing (so font metrics are stable)
        self.root.update_idletasks()
        if expanded_matches:
            # Resize only visible columns to content (this measures actual data)
            self.auto_resize_all_columns()
            first_iid = self.tree.get_children()[0]
            self.tree.selection_set(first_iid)
            self.tree.focus(first_iid)
            self.on_select(None)
        else:
            self.txt_details.configure(state="normal")
            self.txt_details.delete("1.0", "end")
            self.txt_details.insert("1.0", "No matches found.")
            self.txt_details.configure(state="disabled")

    def _shorten(self, s, maxlen=200):
        if s is None:
            return ""
        s = str(s)
        if len(s) > maxlen:
            return s[: maxlen - 2] + "…"
        return s

    def on_select(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        iid = sel[0]
        try:
            idx = int(iid)
        except Exception:
            idx = 0
        if idx < 0 or idx >= len(self.last_matches):
            return

        row = self.last_matches[idx]
        details = []
        for h in self.headers:
            val = row.get(h, "")
            details.append(f"{h}: {val}")
        txt = "\n".join(details)
        self.txt_details.configure(state="normal")
        self.txt_details.delete("1.0", "end")
        self.txt_details.insert("1.0", txt)
        self.txt_details.configure(state="disabled")

    def export_matches(self):
        if not getattr(self, "last_matches", None):
            messagebox.showinfo("No matches", "There are no matches to export.")
            return

        default_name = "matches.csv"
        if self.filename:
            base = os.path.splitext(os.path.basename(self.filename))[0]
            default_name = f"{base}-matches.csv"

        path = filedialog.asksaveasfilename(title="Export matches to CSV",
                                            defaultextension=".csv",
                                            initialfile=default_name,
                                            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if not path:
            return

        try:
            headers = self.headers[:] if self.headers else []
            if not headers and self.last_matches:
                headers = sorted(self.last_matches[0].keys())

            with open(path, "w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=headers, extrasaction="ignore")
                writer.writeheader()
                for row in self.last_matches:
                    writer.writerow({k: (v if v is not None else "") for k, v in row.items()})
        except Exception as e:
            messagebox.showerror("Export error", f"Failed to export matches:\n{e}")
            return

        messagebox.showinfo("Export complete", f"Exported {len(self.last_matches)} rows to:\n{path}")

    # Column visibility / management functions -------------------------------------------------
    def hide_column(self, colname):
        if colname not in list(self.tree["columns"]):
            return
        if colname in self.hidden_columns:
            return
        if colname in self.visible_columns:
            self.visible_columns.remove(colname)
        if colname not in self.hidden_columns:
            self.hidden_columns.append(colname)
        self.tree["displaycolumns"] = self.visible_columns
        # Persist
        SETTINGS.set_visible_columns(self.filename, self.visible_columns)

    def show_column(self, colname):
        if colname not in list(self.tree["columns"]):
            return
        if colname in self.visible_columns:
            return
        self.visible_columns.append(colname)
        ordered = [c for c in list(self.tree["columns"]) if c in self.visible_columns]
        self.visible_columns = ordered
        if colname in self.hidden_columns:
            self.hidden_columns.remove(colname)
        self.tree["displaycolumns"] = self.visible_columns
        # Persist
        SETTINGS.set_visible_columns(self.filename, self.visible_columns)

    def reset_columns(self):
        all_cols = list(self.tree["columns"])
        self.visible_columns = list(all_cols)
        self.hidden_columns = []
        self.tree["displaycolumns"] = self.visible_columns
        self.root.update_idletasks()
        self.auto_resize_all_columns()
        SETTINGS.set_visible_columns(self.filename, self.visible_columns)

    def manage_columns(self):
        if not self.tree["columns"]:
            messagebox.showinfo("No columns", "No columns available.")
            return

        dlg = tk.Toplevel(self.root)
        dlg.title("Manage columns")
        dlg.geometry("420x400")
        dlg.transient(self.root)
        dlg.grab_set()

        frm = ttk.Frame(dlg)
        frm.pack(fill="both", expand=True, padx=8, pady=8)

        lbl = ttk.Label(frm, text="Toggle columns to display:")
        lbl.pack(anchor="w")

        canvas = tk.Canvas(frm)
        scrollbar = ttk.Scrollbar(frm, orient="vertical", command=canvas.yview)
        scroll_frame = ttk.Frame(canvas)

        scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        chk_vars = {}
        for col in self.tree["columns"]:
            var = tk.BooleanVar(value=(col in self.visible_columns))
            chk = ttk.Checkbutton(scroll_frame, text=col, variable=var)
            chk.pack(anchor="w", pady=2)
            chk_vars[col] = var

        def on_apply():
            self.visible_columns = [c for c in self.tree["columns"] if chk_vars[c].get()]
            self.hidden_columns = [c for c in self.tree["columns"] if not chk_vars[c].get()]
            if not self.visible_columns:
                messagebox.showwarning("No columns", "At least one column must be visible.")
                return
            self.tree["displaycolumns"] = self.visible_columns
            dlg.destroy()
            self.root.update_idletasks()
            self.auto_resize_all_columns()
            # Persist
            SETTINGS.set_visible_columns(self.filename, self.visible_columns)

        btn_frame = ttk.Frame(dlg)
        btn_frame.pack(fill="x", padx=8, pady=8)
        ttk.Button(btn_frame, text="Apply", command=on_apply).pack(side="right", padx=(6, 0))
        ttk.Button(btn_frame, text="Cancel", command=dlg.destroy).pack(side="right")

    # Auto-resize helpers ---------------------------------------------------------------------
    def auto_resize_all_columns(self):
        # Resize all visible columns to fit content (headers + visible rows)
        self.root.update_idletasks()
        for col in list(self.tree["displaycolumns"]):
            self.auto_resize_column(col)
        self.tree.update_idletasks()

    def auto_resize_column(self, column):
        # Make sure geometry and fonts are settled
        self.root.update_idletasks()

        # Try to get Treeview font from style; fallback to a known font name
        style = ttk.Style()
        tree_font_name = style.lookup("Treeview", "font")
        try:
            if tree_font_name:
                font = tkfont.nametofont(tree_font_name)
            else:
                font = tkfont.nametofont("TkDefaultFont")
        except Exception:
            font = tkfont.nametofont("TkDefaultFont")

        header_text = str(self.tree.heading(column).get("text", column))
        max_width = font.measure(header_text)

        sample_rows = self.last_matches if self.last_matches else self.rows
        if not sample_rows:
            padding = 24
            new_width = max_width + padding
            new_width = max(60, min(1000, new_width))
            try:
                self.tree.column(column, width=new_width)
            except Exception:
                pass
            return

        max_sample = 1000
        count = 0
        for r in sample_rows:
            if count >= max_sample:
                break
            text = ""
            if isinstance(r, dict):
                text = r.get(column, "") or ""
            else:
                text = str(r)
            if isinstance(text, str):
                text = " ".join(text.split())
            w = font.measure(text)
            if w > max_width:
                max_width = w
            count += 1

        padding = 26
        new_width = max_width + padding
        min_w = 60
        max_w = 1400
        new_width = max(min_w, min(max_w, new_width))
        try:
            self.tree.column(column, width=new_width)
        except Exception:
            pass
        self.tree.update_idletasks()


# --- MeldFrame (adapted from MeldApp but as a Frame so it can be embedded in Notebook) ---
class MeldFrame(ttk.Frame):
    def __init__(self, parent, default_csv=DEFAULT_CSV):
        super().__init__(parent)
        self.parent = parent
        self.csv_path = tk.StringVar(value=default_csv)
        self._current_photo = None
        self._last_fig = None
        self._last_html_path = None

        # Controls frame
        ctrl = ttk.Frame(self)
        ctrl.pack(side=tk.TOP, fill=tk.X, padx=8, pady=8)

        # CSV chooser
        ttk.Label(ctrl, text="CSV:").grid(row=0, column=0, sticky=tk.W)
        self.csv_entry = ttk.Entry(ctrl, textvariable=self.csv_path, width=60)
        self.csv_entry.grid(row=0, column=1, padx=4, sticky=tk.W)
        ttk.Button(ctrl, text="Browse...", command=self.browse_csv).grid(row=0, column=2, padx=4)

        # Mode selection
        self.mode = tk.StringVar(value="horse")
        ttk.Radiobutton(ctrl, text="Horse Name", variable=self.mode, value="horse").grid(row=1, column=0, sticky=tk.W, pady=6)
        ttk.Radiobutton(ctrl, text="Race No.", variable=self.mode, value="race").grid(row=1, column=1, sticky=tk.W, pady=6)

        # Input
        ttk.Label(ctrl, text="Search:").grid(row=2, column=0, sticky=tk.W)
        self.search_entry = ttk.Entry(ctrl, width=60)
        self.search_entry.grid(row=2, column=1, columnspan=2, sticky=tk.W, padx=4, pady=4)

        # Run & buttons
        ttk.Button(ctrl, text="Run", command=self.on_run).grid(row=3, column=0, pady=6)
        ttk.Button(ctrl, text="Open interactive in browser", command=self.open_last_html).grid(row=3, column=1, pady=6)
        #ttk.Button(ctrl, text="Embed interactive (pywebview)", command=self.embed_interactive).grid(row=3, column=2, pady=6)
        ttk.Button(ctrl, text="Save plot as PNG", command=self.save_png).grid(row=3, column=3, pady=6)

        # Panes: left for logs, right for image
        panes = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        panes.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)

        # Left pane - text log
        left = ttk.Frame(panes, width=480)
        panes.add(left, weight=1)
        out_frame = ttk.LabelFrame(left, text="Output")
        out_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self.output = scrolledtext.ScrolledText(out_frame, wrap=tk.WORD, state=tk.NORMAL, width=60)
        self.output.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        # Right pane - image / plot display
        right = ttk.Frame(panes, width=600)
        panes.add(right, weight=2)
        plot_frame = ttk.LabelFrame(right, text="Plot (static preview)")
        plot_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        # Canvas to display image
        self.canvas = tk.Canvas(plot_frame, bg="white")
        self.canvas.pack(fill=tk.BOTH, expand=True)

    def browse_csv(self):
        path = filedialog.askopenfilename(
            title="Select recent.csv",
            filetypes=[("CSV Files", "*.csv"), ("All files", "*.*")],
            initialfile=self.csv_path.get()
        )
        if path:
            self.csv_path.set(path)

    def log(self, text):
        self.output.insert(tk.END, text + "\n")
        self.output.see(tk.END)

    def clear_log(self):
        self.output.delete('1.0', tk.END)

    def on_run(self):
        self.clear_log()
        path = self.csv_path.get() or DEFAULT_CSV
        if not os.path.exists(path):
            messagebox.showerror("CSV not found", f"CSV file not found: {path}")
            return

        search_term = self.search_entry.get().strip()
        if not search_term:
            messagebox.showwarning("Input needed", "Please enter a search string (horse name or race id).")
            return

        try:
            df = safe_read_csv(path)
        except Exception as e:
            messagebox.showerror("Error reading CSV", str(e))
            return

        mode = self.mode.get()
        if mode == "horse":
            self.run_horse(df, search_term)
        else:
            self.run_race(df, search_term)

    def run_horse(self, df, horse_name):
        try:
            filtered_df = df[df['horse'].astype(str).str.contains(horse_name, regex=True, case=False)].copy()
        except Exception as e:
            messagebox.showerror("Filter Error", f"Error filtering by horse name: {e}")
            return

        if filtered_df.empty:
            messagebox.showinfo("No results", f"No rows found for horse search: {horse_name}")
            return

        try:
            race_ids_by_horse = filtered_df.groupby('horse')['race_id'].apply(lambda x: x.tail(10).tolist())
            self.log("race_ids_by_horse:")
            self.log(str(race_ids_by_horse.to_dict()))
        except Exception as e:
            self.log(f"Could not group race ids: {e}")

        self.log("Filtered DataFrame preview:")
        self.log(filtered_df.to_string())

        filtered_df = prepare_numeric_columns(filtered_df)
        filtered_df = map_distance_going(filtered_df)

        fig = build_horse_figure(filtered_df)
        self._last_fig = fig

        # save interactive HTML to temp file for webview/browser
        try:
            html_path = os.path.join(os.getcwd(), "meld_last_plot.html")
            pio.write_html(fig, file=html_path, include_plotlyjs='cdn', auto_open=False)
            self._last_html_path = html_path
            self.log(f"Interactive HTML saved to {html_path}. Use 'Embed interactive (pywebview)' to open it inside a pywebview window.")
        except Exception as e:
            self.log(f"Could not save interactive HTML: {e}")
            self._last_html_path = None

        # Convert to image (static) and show inside Tkinter
        try:
            photo = figure_to_photoimage(fig, width=900, height=500)
            self._current_photo = photo  # keep reference
            self.canvas.delete("all")
            # make canvas match image size if possible
            self.canvas.configure(width=photo.width(), height=photo.height())
            self.canvas.create_image(0, 0, anchor='nw', image=photo)
            self.log("Plot rendered and embedded in GUI (static image).")
        except Exception as e:
            self.log(f"Failed to embed static plot inside GUI: {e}")
            self.log("Attempting to open interactive plot in browser instead...")
            try:
                fig.show()
                self.log("Plot opened in your default web browser.")
            except Exception as e2:
                self.log(f"Also failed to open in browser: {e2}")

    def run_race(self, df, race_id):
        try:
            df['race_id'] = df['race_id'].astype(str)
            filtered_df = df[df['race_id'].str.contains(race_id, regex=False, case=False)].copy()
        except Exception as e:
            messagebox.showerror("Filter Error", f"Error filtering by race id: {e}")
            return

        if filtered_df.empty:
            messagebox.showinfo("No results", f"No rows found for race id: {race_id}")
            return

        try:
            race_ids_by_horse = filtered_df.groupby('horse')['race_id'].apply(lambda x: x.tail(10).tolist())
            self.log("race_ids_by_horse:")
            self.log(str(race_ids_by_horse.to_dict()))
        except Exception as e:
            self.log(f"Could not group race ids: {e}")

        self.log("Filtered DataFrame preview:")
        self.log(filtered_df.to_string())

        filtered_df = prepare_numeric_columns(filtered_df)

        fig = build_race_figure(filtered_df)
        self._last_fig = fig

        # save interactive HTML
        try:
            html_path = os.path.join(os.getcwd(), "meld_last_plot.html")
            pio.write_html(fig, file=html_path, include_plotlyjs='cdn', auto_open=False)
            self._last_html_path = html_path
            self.log(f"Interactive HTML saved to {html_path}. Use 'Embed interactive (pywebview)' to open it inside a pywebview window.")
        except Exception as e:
            self.log(f"Could not save interactive HTML: {e}")
            self._last_html_path = None

        # embed static PNG
        try:
            photo = figure_to_photoimage(fig, width=900, height=500)
            self._current_photo = photo
            self.canvas.delete("all")
            self.canvas.configure(width=photo.width(), height=photo.height())
            self.canvas.create_image(0, 0, anchor='nw', image=photo)
            self.log("Plot rendered and embedded in GUI (static image).")
        except Exception as e:
            self.log(f"Failed to embed static plot inside GUI: {e}")
            try:
                fig.show()
                self.log("Plot opened in your default web browser.")
            except Exception as e2:
                self.log(f"Also failed to open in browser: {e2}")

    def open_last_html(self):
        if self._last_html_path and os.path.exists(self._last_html_path):
            webbrowser.open(f"file://{os.path.abspath(self._last_html_path)}")
            self.log(f"Opened interactive plot in browser: {self._last_html_path}")
        else:
            messagebox.showinfo("No interactive HTML", "No saved interactive HTML available. Run a search first or check permissions.")

    def embed_interactive(self):
        """
        Launch a pywebview window showing the last saved interactive HTML.
        Run pywebview in a separate process so Tk's mainloop (running in the current
        process main thread) is not blocked and pywebview is executed on the
        process main thread (required by pywebview).
        """
        if not _HAS_PYWEBVIEW:
            messagebox.showerror("pywebview not installed", "pywebview is required for embedding. Install it with:\n\npip install pywebview")
            return

        if not self._last_html_path or not os.path.exists(self._last_html_path):
            messagebox.showinfo("No interactive HTML", "No saved interactive HTML found. Run a search first to generate the interactive HTML.")
            return

        # Start pywebview in a separate process (so webview.start runs on that process's main thread)
        try:
            p = multiprocessing.Process(target=_start_webview_process, args=(self._last_html_path,), daemon=False)
            p.start()
            self.log("Launched pywebview in a separate process (non-blocking).")
        except Exception as e:
            self.log(f"Failed to launch pywebview process: {e}")
            # fallback: open in default browser
            try:
                webbrowser.open(f"file://{os.path.abspath(self._last_html_path)}")
                self.log("Opened interactive plot in default web browser as fallback.")
            except Exception as e2:
                self.log(f"Also failed to open fallback browser: {e2}")

    def save_png(self):
        if self._last_fig is None:
            messagebox.showinfo("No plot", "No plot to save. Run a search first.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG image","*.png")])
        if not path:
            return
        try:
            img_bytes = pio.to_image(self._last_fig, format='png', width=1200, height=700, scale=1)
            with open(path, 'wb') as f:
                f.write(img_bytes)
            self.log(f"Saved PNG to {path}")
        except Exception as e:
            messagebox.showerror("Save failed", f"Could not save PNG: {e}")


# --- main: create root, notebook, and embed both UIs ---
def main():
    root = tk.Tk()
    root.title("Combined: Saturday Viewer + Meld Visualiser")
    root.geometry("1280x820")

    nb = ttk.Notebook(root)
    nb.pack(fill="both", expand=True)

    # Saturday Viewer tab
    tab1 = ttk.Frame(nb)
    nb.add(tab1, text="Saturday Viewer (CSV Search)")
    # instantiate SaturdayViewer inside tab1
    sat = SaturdayViewer(tab1)

    # Meld tab
    tab2 = ttk.Frame(nb)
    nb.add(tab2, text="Meld (Plots)")
    meld_frame = MeldFrame(tab2)
    meld_frame.pack(fill="both", expand=True)

    # Select the first tab
    nb.select(0)

    root.mainloop()


if __name__ == "__main__":
    try:
        multiprocessing.freeze_support()
    except Exception:
        pass
    main()
