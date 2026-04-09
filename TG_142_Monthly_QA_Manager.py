"""
TG-142 Linac QA Manager
-----------------------
A single-file desktop application for tracking C-arm linac QA in a way that
feels more structured than spreadsheets while still staying simple enough to
run locally in Spyder.

Reference basis:
AAPM TG-142, Klein et al., Medical Physics 36(9), 4197-4212 (2009)

Technical notes:
- Python 3.7+
- tkinter (standard library)
- sqlite3 (standard library)
- matplotlib (optional, for trend plots)

Run:
    python tg142_qa_manager.py
"""

import csv
import os
import sqlite3
import sys
import tkinter as tk
from datetime import date, datetime
from tkinter import filedialog, messagebox, ttk

# Optional plotting support
try:
    import matplotlib
    matplotlib.use("TkAgg")
    import matplotlib.dates as mdates
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure
    HAS_MPL = True
except ImportError:
    HAS_MPL = False


# ------------------------------------------------------------
# Database location
# ------------------------------------------------------------
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tg142_qa.db")


# ------------------------------------------------------------
# TG-142 test catalog
# ------------------------------------------------------------
# Each test dictionary contains:
#   name       : label shown in the GUI
#   category   : Dosimetry / Mechanical / Safety / Imaging
#   unit       : %, mm, deg, Functional, Baseline, etc.
#   tolerance  : allowed deviation (None for functional checks)
#   tol_type   : how the result should be interpreted
#   frequency  : Daily / Monthly / Annual
#   notes      : short guidance shown as tooltip

DAILY_TESTS = [
    {"name": "X-ray Output Constancy", "category": "Dosimetry", "unit": "%", "tolerance": 3.0, "tol_type": "pct", "frequency": "Daily", "notes": "All energies, % deviation from baseline"},
    {"name": "Electron Output Constancy", "category": "Dosimetry", "unit": "%", "tolerance": 3.0, "tol_type": "pct", "frequency": "Daily", "notes": "Weekly for most; daily if unique e-monitoring"},
    {"name": "Laser Localization", "category": "Mechanical", "unit": "mm", "tolerance": 2.0, "tol_type": "mm", "frequency": "Daily", "notes": "Non-IMRT: 2 mm, IMRT: 1.5 mm, SRS: 1 mm. Adjust locally if needed."},
    {"name": "ODI Distance Indicator @ Iso", "category": "Mechanical", "unit": "mm", "tolerance": 2.0, "tol_type": "mm", "frequency": "Daily", "notes": "ODI at isocenter"},
    {"name": "Collimator Size Indicator", "category": "Mechanical", "unit": "mm", "tolerance": 2.0, "tol_type": "mm", "frequency": "Daily", "notes": "2 mm non-SRS, 1 mm SRS"},
    {"name": "Door Interlock (Beam Off)", "category": "Safety", "unit": "Functional", "tolerance": None, "tol_type": "functional", "frequency": "Daily", "notes": "Beam must terminate when door opens"},
    {"name": "Door Closing Safety", "category": "Safety", "unit": "Functional", "tolerance": None, "tol_type": "functional", "frequency": "Daily", "notes": ""},
    {"name": "Audiovisual Monitors", "category": "Safety", "unit": "Functional", "tolerance": None, "tol_type": "functional", "frequency": "Daily", "notes": ""},
    {"name": "Radiation Area Monitor", "category": "Safety", "unit": "Functional", "tolerance": None, "tol_type": "functional", "frequency": "Daily", "notes": "If used"},
    {"name": "Beam On Indicator", "category": "Safety", "unit": "Functional", "tolerance": None, "tol_type": "functional", "frequency": "Daily", "notes": ""},
    {"name": "kV/MV Imaging Collision Interlocks", "category": "Imaging", "unit": "Functional", "tolerance": None, "tol_type": "functional", "frequency": "Daily", "notes": "Planar kV and MV (EPID)"},
    {"name": "kV/MV Imaging Positioning Accuracy", "category": "Imaging", "unit": "mm", "tolerance": 2.0, "tol_type": "mm", "frequency": "Daily", "notes": "Repositioning accuracy; 1 mm for SRS"},
    {"name": "Imaging-Tx Coordinate Coincidence", "category": "Imaging", "unit": "mm", "tolerance": 2.0, "tol_type": "mm", "frequency": "Daily", "notes": "Single gantry angle; 1 mm for SRS"},
    {"name": "CBCT Collision Interlocks", "category": "Imaging", "unit": "Functional", "tolerance": None, "tol_type": "functional", "frequency": "Daily", "notes": "Cone-beam CT kV and MV"},
    {"name": "CBCT Imaging-Tx Coincidence", "category": "Imaging", "unit": "mm", "tolerance": 2.0, "tol_type": "mm", "frequency": "Daily", "notes": "2 mm non-SRS, 1 mm SRS"},
]

MONTHLY_TESTS = [
    {"name": "X-ray Output Constancy (Monthly)", "category": "Dosimetry", "unit": "%", "tolerance": 2.0, "tol_type": "pct", "frequency": "Monthly", "notes": "2% from baseline"},
    {"name": "Electron Output Constancy (Monthly)", "category": "Dosimetry", "unit": "%", "tolerance": 2.0, "tol_type": "pct", "frequency": "Monthly", "notes": "2% from baseline"},
    {"name": "Backup Monitor Chamber Constancy", "category": "Dosimetry", "unit": "%", "tolerance": 2.0, "tol_type": "pct", "frequency": "Monthly", "notes": ""},
    {"name": "Photon Beam Profile Constancy (Flatness)", "category": "Dosimetry", "unit": "%", "tolerance": 1.0, "tol_type": "pct", "frequency": "Monthly", "notes": "1% from baseline off-axis factors"},
    {"name": "Photon Beam Profile Constancy (Symmetry)", "category": "Dosimetry", "unit": "%", "tolerance": 1.0, "tol_type": "pct", "frequency": "Monthly", "notes": "1% from baseline (signed)"},
    {"name": "Electron Beam Profile Constancy", "category": "Dosimetry", "unit": "%", "tolerance": 1.0, "tol_type": "pct", "frequency": "Monthly", "notes": "1% from baseline"},
    {"name": "Electron Beam Energy Constancy", "category": "Dosimetry", "unit": "mm", "tolerance": 2.0, "tol_type": "mm", "frequency": "Monthly", "notes": "2% / 2 mm"},
    {"name": "IC Profiler Flatness", "category": "Dosimetry", "unit": "%", "tolerance": 1.0, "tol_type": "pct", "frequency": "Monthly", "notes": "Flatness from IC Profiler vs baseline"},
    {"name": "IC Profiler Symmetry (GT)", "category": "Dosimetry", "unit": "%", "tolerance": 1.0, "tol_type": "pct", "frequency": "Monthly", "notes": "Gun-Target symmetry from IC Profiler"},
    {"name": "IC Profiler Symmetry (LR)", "category": "Dosimetry", "unit": "%", "tolerance": 1.0, "tol_type": "pct", "frequency": "Monthly", "notes": "Left-Right symmetry from IC Profiler"},
    {"name": "Light/Radiation Field Coincidence (Sym)", "category": "Mechanical", "unit": "mm", "tolerance": 2.0, "tol_type": "mm", "frequency": "Monthly", "notes": "2 mm or 1% on a side"},
    {"name": "Light/Radiation Field Coincidence (Asym)", "category": "Mechanical", "unit": "mm", "tolerance": 1.0, "tol_type": "mm", "frequency": "Monthly", "notes": "1 mm or 1% on a side"},
    {"name": "Laser vs Front Pointer Distance", "category": "Mechanical", "unit": "mm", "tolerance": 1.0, "tol_type": "mm", "frequency": "Monthly", "notes": "Distance-check device"},
    {"name": "Gantry Angle Indicator", "category": "Mechanical", "unit": "deg", "tolerance": 1.0, "tol_type": "deg", "frequency": "Monthly", "notes": "Cardinal angles, digital only"},
    {"name": "Collimator Angle Indicator", "category": "Mechanical", "unit": "deg", "tolerance": 1.0, "tol_type": "deg", "frequency": "Monthly", "notes": "Cardinal angles"},
    {"name": "Jaw Position Indicators (Symmetric)", "category": "Mechanical", "unit": "mm", "tolerance": 2.0, "tol_type": "mm", "frequency": "Monthly", "notes": "Summation of total width/length"},
    {"name": "Jaw Position Indicators (Asymmetric)", "category": "Mechanical", "unit": "mm", "tolerance": 1.0, "tol_type": "mm", "frequency": "Monthly", "notes": "At 0.0 and 10.0 cm settings"},
    {"name": "Cross-Hair Centering (Walkout)", "category": "Mechanical", "unit": "mm", "tolerance": 1.0, "tol_type": "mm", "frequency": "Monthly", "notes": ""},
    {"name": "Couch Vertical Position", "category": "Mechanical", "unit": "mm", "tolerance": 2.0, "tol_type": "mm", "frequency": "Monthly", "notes": "Treatment couch position indicators"},
    {"name": "Couch Lateral Position", "category": "Mechanical", "unit": "mm", "tolerance": 2.0, "tol_type": "mm", "frequency": "Monthly", "notes": ""},
    {"name": "Couch Longitudinal Position", "category": "Mechanical", "unit": "mm", "tolerance": 2.0, "tol_type": "mm", "frequency": "Monthly", "notes": ""},
    {"name": "Couch Rotation", "category": "Mechanical", "unit": "deg", "tolerance": 1.0, "tol_type": "deg", "frequency": "Monthly", "notes": "1 degree non-SRS, 0.5 degree SRS"},
    {"name": "Wedge Placement Accuracy", "category": "Mechanical", "unit": "mm", "tolerance": 2.0, "tol_type": "mm", "frequency": "Monthly", "notes": ""},
    {"name": "Localizing Lasers", "category": "Mechanical", "unit": "mm", "tolerance": 2.0, "tol_type": "mm", "frequency": "Monthly", "notes": "2 mm non-IMRT, 1 mm IMRT/SRS"},
    {"name": "Accessory Tray Position", "category": "Mechanical", "unit": "mm", "tolerance": 2.0, "tol_type": "mm", "frequency": "Monthly", "notes": "Port film graticle tray"},
    {"name": "Latching of Wedges/Blocking Tray", "category": "Safety", "unit": "Functional", "tolerance": None, "tol_type": "functional", "frequency": "Monthly", "notes": "Check with latch facing floor at the test angle"},
    {"name": "Laser Guard Interlock", "category": "Safety", "unit": "Functional", "tolerance": None, "tol_type": "functional", "frequency": "Monthly", "notes": ""},
    {"name": "EPID Imaging-Tx Coincidence (4 angles)", "category": "Imaging", "unit": "mm", "tolerance": 2.0, "tol_type": "mm", "frequency": "Monthly", "notes": "Four cardinal gantry angles"},
    {"name": "EPID Scaling", "category": "Imaging", "unit": "mm", "tolerance": 2.0, "tol_type": "mm", "frequency": "Monthly", "notes": "At clinical SSD"},
    {"name": "kV Imaging-Tx Coincidence (4 angles)", "category": "Imaging", "unit": "mm", "tolerance": 2.0, "tol_type": "mm", "frequency": "Monthly", "notes": "Four cardinal gantry angles"},
    {"name": "CBCT Geometric Distortion", "category": "Imaging", "unit": "mm", "tolerance": 2.0, "tol_type": "mm", "frequency": "Monthly", "notes": "2 mm non-SRS, 1 mm SRS"},
    {"name": "Winston-Lutz Isocenter (WL)", "category": "Mechanical", "unit": "mm", "tolerance": 1.0, "tol_type": "mm", "frequency": "Monthly", "notes": "Radiation-mechanical isocenter coincidence; SRS <= 1 mm"},
]

ANNUAL_TESTS = [
    {"name": "X-ray Flatness (Annual)", "category": "Dosimetry", "unit": "%", "tolerance": 1.0, "tol_type": "baseline_pct", "frequency": "Annual", "notes": "Change from commissioning baseline"},
    {"name": "X-ray Symmetry (Annual)", "category": "Dosimetry", "unit": "%", "tolerance": 1.0, "tol_type": "baseline_pct", "frequency": "Annual", "notes": "Change from commissioning baseline (signed)"},
    {"name": "Electron Flatness (Annual)", "category": "Dosimetry", "unit": "%", "tolerance": 1.0, "tol_type": "baseline_pct", "frequency": "Annual", "notes": "Change from commissioning baseline"},
    {"name": "Electron Symmetry (Annual)", "category": "Dosimetry", "unit": "%", "tolerance": 1.0, "tol_type": "baseline_pct", "frequency": "Annual", "notes": "Change from commissioning baseline"},
    {"name": "X-ray/Electron Output Calibration (TG-51)", "category": "Dosimetry", "unit": "%", "tolerance": 1.0, "tol_type": "pct", "frequency": "Annual", "notes": "Absolute, 1% per TG-51"},
    {"name": "Field Size Output Factors (Spot Check)", "category": "Dosimetry", "unit": "%", "tolerance": 2.0, "tol_type": "pct", "frequency": "Annual", "notes": "2% for FS < 4x4, 1% for >= 4x4 cm2"},
    {"name": "X-ray Beam Quality (PDD10 or TMR)", "category": "Dosimetry", "unit": "%", "tolerance": 1.0, "tol_type": "baseline_pct", "frequency": "Annual", "notes": "1% from baseline"},
    {"name": "Electron Beam Quality (R50)", "category": "Dosimetry", "unit": "mm", "tolerance": 1.0, "tol_type": "baseline_mm", "frequency": "Annual", "notes": "1 mm from baseline"},
    {"name": "Physical Wedge Transmission Factor", "category": "Dosimetry", "unit": "%", "tolerance": 2.0, "tol_type": "pct", "frequency": "Annual", "notes": "2% constancy"},
    {"name": "X-ray MU Linearity (>=5 MU)", "category": "Dosimetry", "unit": "%", "tolerance": 2.0, "tol_type": "pct", "frequency": "Annual", "notes": "2% for >= 5 MU"},
    {"name": "X-ray Output vs Dose Rate", "category": "Dosimetry", "unit": "%", "tolerance": 2.0, "tol_type": "baseline_pct", "frequency": "Annual", "notes": "2% from baseline"},
    {"name": "X-ray Output vs Gantry Angle", "category": "Dosimetry", "unit": "%", "tolerance": 1.0, "tol_type": "baseline_pct", "frequency": "Annual", "notes": "1% from baseline"},
    {"name": "Electron Output vs Gantry Angle", "category": "Dosimetry", "unit": "%", "tolerance": 1.0, "tol_type": "baseline_pct", "frequency": "Annual", "notes": "1% from baseline"},
    {"name": "Collimator Rotation Isocenter", "category": "Mechanical", "unit": "mm", "tolerance": 1.0, "tol_type": "baseline_mm", "frequency": "Annual", "notes": "1 mm from baseline"},
    {"name": "Gantry Rotation Isocenter", "category": "Mechanical", "unit": "mm", "tolerance": 1.0, "tol_type": "baseline_mm", "frequency": "Annual", "notes": "1 mm from baseline"},
    {"name": "Couch Rotation Isocenter", "category": "Mechanical", "unit": "mm", "tolerance": 1.0, "tol_type": "baseline_mm", "frequency": "Annual", "notes": "1 mm from baseline"},
    {"name": "Radiation-Mechanical Isocenter Coincidence", "category": "Mechanical", "unit": "mm", "tolerance": 2.0, "tol_type": "baseline_mm", "frequency": "Annual", "notes": "2 mm non-SRS, 1 mm SRS"},
    {"name": "Table Top Sag", "category": "Mechanical", "unit": "mm", "tolerance": 2.0, "tol_type": "baseline_mm", "frequency": "Annual", "notes": "2 mm from baseline"},
    {"name": "Table Angle", "category": "Mechanical", "unit": "deg", "tolerance": 1.0, "tol_type": "deg", "frequency": "Annual", "notes": "1 degree"},
    {"name": "Table Travel (All Directions)", "category": "Mechanical", "unit": "mm", "tolerance": 2.0, "tol_type": "mm", "frequency": "Annual", "notes": "Maximum range 2 mm"},
    {"name": "Manufacturer Safety Procedures", "category": "Safety", "unit": "Functional", "tolerance": None, "tol_type": "functional", "frequency": "Annual", "notes": "Follow vendor-defined safety checks"},
    {"name": "EPID Full Range of Travel (SDD)", "category": "Imaging", "unit": "mm", "tolerance": 5.0, "tol_type": "mm", "frequency": "Annual", "notes": "5 mm"},
    {"name": "kV Beam Quality/Energy", "category": "Imaging", "unit": "Baseline", "tolerance": None, "tol_type": "functional", "frequency": "Annual", "notes": "Consistent with ATP baseline"},
    {"name": "CBCT Imaging Dose", "category": "Imaging", "unit": "Baseline", "tolerance": None, "tol_type": "functional", "frequency": "Annual", "notes": "Consistent with ATP baseline"},
]

ALL_TESTS = DAILY_TESTS + MONTHLY_TESTS + ANNUAL_TESTS


# ------------------------------------------------------------
# Database helpers
# ------------------------------------------------------------
def init_db(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS machines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            model TEXT,
            serial_number TEXT,
            institution TEXT,
            machine_type TEXT DEFAULT 'IMRT',
            energies TEXT,
            created_date TEXT,
            notes TEXT
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS baselines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            machine_id INTEGER NOT NULL,
            test_name TEXT NOT NULL,
            baseline_value REAL,
            baseline_date TEXT,
            notes TEXT,
            FOREIGN KEY (machine_id) REFERENCES machines(id)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS qa_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            machine_id INTEGER NOT NULL,
            test_name TEXT NOT NULL,
            frequency TEXT NOT NULL,
            measurement_date TEXT NOT NULL,
            measured_value REAL,
            functional_result TEXT,
            deviation REAL,
            tolerance REAL,
            status TEXT,
            operator TEXT,
            notes TEXT,
            FOREIGN KEY (machine_id) REFERENCES machines(id)
        )
        """
    )

    conn.commit()
    conn.close()


def get_machines():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, model, machine_type FROM machines ORDER BY name")
    rows = cursor.fetchall()
    conn.close()
    return rows


def save_machine(name, model, serial_number, institution, machine_type, energies, notes):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO machines (name, model, serial_number, institution, machine_type, energies, created_date, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            name,
            model,
            serial_number,
            institution,
            machine_type,
            energies,
            datetime.now().strftime("%Y-%m-%d"),
            notes,
        ),
    )
    conn.commit()
    machine_id = cursor.lastrowid
    conn.close()
    return machine_id


def get_baseline(machine_id, test_name):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT baseline_value, baseline_date FROM baselines WHERE machine_id=? AND test_name=?",
        (machine_id, test_name),
    )
    row = cursor.fetchone()
    conn.close()
    return row


def save_baseline(machine_id, test_name, value, notes=""):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    existing = get_baseline(machine_id, test_name)

    if existing:
        cursor.execute(
            """
            UPDATE baselines
            SET baseline_value=?, baseline_date=?, notes=?
            WHERE machine_id=? AND test_name=?
            """,
            (value, datetime.now().strftime("%Y-%m-%d"), notes, machine_id, test_name),
        )
    else:
        cursor.execute(
            """
            INSERT INTO baselines (machine_id, test_name, baseline_value, baseline_date, notes)
            VALUES (?, ?, ?, ?, ?)
            """,
            (machine_id, test_name, value, datetime.now().strftime("%Y-%m-%d"), notes),
        )

    conn.commit()
    conn.close()


def save_qa_record(machine_id, test_name, frequency, measured_value, functional_result, deviation, tolerance, status, operator, notes):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO qa_records (
            machine_id, test_name, frequency, measurement_date, measured_value,
            functional_result, deviation, tolerance, status, operator, notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            machine_id,
            test_name,
            frequency,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            measured_value,
            functional_result,
            deviation,
            tolerance,
            status,
            operator,
            notes,
        ),
    )
    conn.commit()
    conn.close()


def get_qa_history(machine_id, test_name, limit=200):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT measurement_date, measured_value, deviation, status, operator, notes
        FROM qa_records
        WHERE machine_id=? AND test_name=?
        ORDER BY measurement_date DESC
        LIMIT ?
        """,
        (machine_id, test_name, limit),
    )
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_all_qa_for_machine(machine_id, frequency=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    if frequency:
        cursor.execute(
            """
            SELECT measurement_date, test_name, measured_value, deviation, tolerance, status, operator
            FROM qa_records
            WHERE machine_id=? AND frequency=?
            ORDER BY measurement_date DESC
            """,
            (machine_id, frequency),
        )
    else:
        cursor.execute(
            """
            SELECT measurement_date, test_name, measured_value, deviation, tolerance, status, operator
            FROM qa_records
            WHERE machine_id=?
            ORDER BY measurement_date DESC
            """,
            (machine_id,),
        )

    rows = cursor.fetchall()
    conn.close()
    return rows


# ------------------------------------------------------------
# Result evaluation
# ------------------------------------------------------------
def evaluate_result(test_def, measured_value, functional_result, baseline_value):
    """
    Returns:
        (deviation, status)

    deviation:
        Numeric difference from baseline/reference, or None for functional checks.

    status:
        PASS / FAIL / WARN / Functional-PASS / Functional-FAIL / etc.
    """
    tol_type = test_def["tol_type"]
    tolerance = test_def["tolerance"]

    if tol_type == "functional":
        if functional_result and functional_result.strip().upper() in ("PASS", "P", "OK", "YES", "FUNCTIONAL", "FUNC"):
            return None, "Functional-PASS"
        if functional_result and functional_result.strip().upper() in ("FAIL", "F", "NO", "NOT FUNCTIONAL"):
            return None, "Functional-FAIL"
        return None, "Functional-?"

    if measured_value is None:
        return None, "No Data"

    if tol_type in ("pct", "mm", "deg"):
        if baseline_value is not None:
            deviation = abs(measured_value - baseline_value)
        else:
            deviation = abs(measured_value)
        status = "PASS" if deviation <= tolerance else "FAIL"
        return round(deviation, 4), status

    if tol_type in ("baseline_pct", "baseline_mm"):
        if baseline_value is None:
            return None, "No Baseline"
        deviation = abs(measured_value - baseline_value)
        status = "PASS" if deviation <= tolerance else "FAIL"
        return round(deviation, 4), status

    return None, "Unknown"


# ------------------------------------------------------------
# Status colors
# ------------------------------------------------------------
STATUS_COLORS = {
    "PASS": "#d4edda",
    "FAIL": "#f8d7da",
    "Functional-PASS": "#d4edda",
    "Functional-FAIL": "#f8d7da",
    "WARN": "#fff3cd",
    "No Baseline": "#e2e3e5",
    "No Data": "#e2e3e5",
    "Functional-?": "#fff3cd",
    "Unknown": "#e2e3e5",
}

STATUS_FG = {
    "PASS": "#155724",
    "FAIL": "#721c24",
    "Functional-PASS": "#155724",
    "Functional-FAIL": "#721c24",
    "WARN": "#856404",
    "No Baseline": "#383d41",
    "No Data": "#383d41",
    "Functional-?": "#856404",
    "Unknown": "#383d41",
}


# ------------------------------------------------------------
# Main application
# ------------------------------------------------------------
class TG142App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("TG-142 Linac QA Manager")
        self.geometry("1280x820")
        self.minsize(1100, 700)
        self.configure(bg="#f0f0f0")

        self.current_machine_id = None
        self.current_machine_name = tk.StringVar(value="-- Select Machine --")

        self._build_menu()
        self._build_toolbar()
        self._build_main_area()
        self._refresh_machine_list()

    def _build_menu(self):
        menubar = tk.Menu(self)
        self.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Add Machine / Linac...", command=self.show_add_machine)
        file_menu.add_command(label="Export QA Records to CSV...", command=self.export_csv)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.quit)

        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Tools", menu=tools_menu)
        tools_menu.add_command(label="Set Commissioning Baselines...", command=self.show_baseline_editor)
        tools_menu.add_command(label="View QA History...", command=self.show_history)
        tools_menu.add_command(label="Trend Plots...", command=self.show_trend_plots)

        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="TG-142 Tolerance Summary", command=self.show_tg142_summary)
        help_menu.add_command(label="About", command=self.show_about)

    def _build_toolbar(self):
        toolbar = tk.Frame(self, bg="#3c4a5a", height=48)
        toolbar.pack(side=tk.TOP, fill=tk.X)

        tk.Label(
            toolbar,
            text="TG-142 Linac QA Manager",
            bg="#3c4a5a",
            fg="white",
            font=("Helvetica", 14, "bold"),
        ).pack(side=tk.LEFT, padx=16, pady=10)

        tk.Label(toolbar, text="Active Machine:", bg="#3c4a5a", fg="#adb5bd").pack(side=tk.LEFT, padx=(30, 4), pady=10)

        self.machine_combo = ttk.Combobox(toolbar, textvariable=self.current_machine_name, state="readonly", width=30)
        self.machine_combo.pack(side=tk.LEFT, pady=10)
        self.machine_combo.bind("<<ComboboxSelected>>", self._on_machine_select)

        ttk.Button(toolbar, text="+ Add Machine", command=self.show_add_machine).pack(side=tk.LEFT, padx=8, pady=8)
        ttk.Button(toolbar, text="Set Baselines", command=self.show_baseline_editor).pack(side=tk.LEFT, padx=4, pady=8)
        ttk.Button(toolbar, text="Trend Plots", command=self.show_trend_plots).pack(side=tk.LEFT, padx=4, pady=8)
        ttk.Button(toolbar, text="History", command=self.show_history).pack(side=tk.LEFT, padx=4, pady=8)

    def _build_main_area(self):
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        self.daily_frame = self._build_qa_tab("Daily QA", DAILY_TESTS, "Daily")
        self.monthly_frame = self._build_qa_tab("Monthly QA", MONTHLY_TESTS, "Monthly")
        self.annual_frame = self._build_qa_tab("Annual QA", ANNUAL_TESTS, "Annual")
        self.summary_frame = self._build_summary_tab()

        self.notebook.add(self.daily_frame, text="  Daily QA  ")
        self.notebook.add(self.monthly_frame, text="  Monthly QA  ")
        self.notebook.add(self.annual_frame, text="  Annual QA  ")
        self.notebook.add(self.summary_frame, text="  Summary / History  ")

    def _build_qa_tab(self, title, tests, frequency):
        outer = tk.Frame(self.notebook, bg="#f0f0f0")

        header = tk.Frame(outer, bg="#dce3ea", pady=6)
        header.pack(fill=tk.X, side=tk.TOP)

        tk.Label(header, text=f"{title}  —  AAPM TG-142", bg="#dce3ea", font=("Helvetica", 11, "bold")).pack(side=tk.LEFT, padx=12)

        tk.Label(header, text="Operator:").pack(side=tk.LEFT, padx=(30, 2))
        operator_var = tk.StringVar()
        tk.Entry(header, textvariable=operator_var, width=18).pack(side=tk.LEFT)

        tk.Label(header, text="Date:").pack(side=tk.LEFT, padx=(12, 2))
        date_var = tk.StringVar(value=date.today().strftime("%Y-%m-%d"))
        tk.Entry(header, textvariable=date_var, width=12).pack(side=tk.LEFT)

        entries_by_test = {}
        result_widgets = {}

        ttk.Button(
            header,
            text="💾  Save All Results",
            command=lambda: self._save_all_results(tests, frequency, entries_by_test, operator_var, result_widgets),
        ).pack(side=tk.RIGHT, padx=12)

        canvas = tk.Canvas(outer, bg="#f0f0f0")
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        form_frame = tk.Frame(canvas, bg="#f0f0f0")

        form_frame.bind("<Configure>", lambda event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=form_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4, pady=4)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        canvas.bind_all("<MouseWheel>", lambda event, active_canvas=canvas: active_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units"))

        headers = ["#", "Test Name (TG-142)", "Category", "Unit", "Tolerance", "Baseline", "Measured Value / Result", "Deviation", "Status", "Notes"]
        widths = [3, 32, 10, 8, 9, 9, 20, 9, 14, 20]
        for col_idx, (header_text, width) in enumerate(zip(headers, widths)):
            tk.Label(
                form_frame,
                text=header_text,
                bg="#3c4a5a",
                fg="white",
                font=("Helvetica", 9, "bold"),
                width=width,
                anchor="w",
                padx=4,
            ).grid(row=0, column=col_idx, sticky="ew", padx=1, pady=1)

        seen_categories = set()

        for row_idx, test in enumerate(tests, start=1):
            category = test["category"]

            if category not in seen_categories:
                seen_categories.add(category)
                category_colors = {
                    "Dosimetry": "#e8f4f8",
                    "Mechanical": "#f0f4e8",
                    "Safety": "#f8f0e8",
                    "Imaging": "#f4e8f8",
                }
                row_bg = category_colors.get(category, "#f0f0f0")
            else:
                row_bg = "#fafafa" if row_idx % 2 == 0 else "#ffffff"

            tk.Label(form_frame, text=str(row_idx), bg=row_bg, width=3, anchor="center", font=("Helvetica", 8)).grid(row=row_idx, column=0, sticky="ew", padx=1, pady=1)

            test_name_label = tk.Label(
                form_frame,
                text=test["name"],
                bg=row_bg,
                width=32,
                anchor="w",
                font=("Helvetica", 9),
                wraplength=220,
                justify="left",
                padx=4,
            )
            test_name_label.grid(row=row_idx, column=1, sticky="ew", padx=1, pady=1)
            if test.get("notes"):
                self._add_tooltip(test_name_label, test["notes"])

            tk.Label(form_frame, text=category[:10], bg=row_bg, width=10, anchor="w", font=("Helvetica", 8)).grid(row=row_idx, column=2, sticky="ew", padx=1, pady=1)
            tk.Label(form_frame, text=test["unit"], bg=row_bg, width=8, anchor="center", font=("Helvetica", 8)).grid(row=row_idx, column=3, sticky="ew", padx=1, pady=1)

            tolerance_text = f"±{test['tolerance']}" if test["tolerance"] is not None else "Functional"
            if test["unit"] not in ("%", "mm", "deg", "Functional", "Baseline"):
                tolerance_text = str(test["tolerance"])
            tk.Label(form_frame, text=tolerance_text, bg=row_bg, width=9, anchor="center", font=("Helvetica", 8)).grid(row=row_idx, column=4, sticky="ew", padx=1, pady=1)

            baseline_label = tk.Label(form_frame, text="--", bg=row_bg, width=9, anchor="center", font=("Helvetica", 8), fg="#555")
            baseline_label.grid(row=row_idx, column=5, sticky="ew", padx=1, pady=1)

            functional_var = None
            if test["tol_type"] == "functional":
                functional_var = tk.StringVar(value="")
                input_frame = tk.Frame(form_frame, bg=row_bg)
                input_frame.grid(row=row_idx, column=6, sticky="ew", padx=1, pady=1)
                ttk.Radiobutton(input_frame, text="PASS", variable=functional_var, value="PASS").pack(side=tk.LEFT)
                ttk.Radiobutton(input_frame, text="FAIL", variable=functional_var, value="FAIL").pack(side=tk.LEFT)
                value_entry = None
            else:
                value_entry = tk.Entry(form_frame, width=20, font=("Helvetica", 9))
                value_entry.grid(row=row_idx, column=6, sticky="ew", padx=1, pady=1)
                value_entry.bind(
                    "<FocusOut>",
                    lambda event, current_test=test, entry_widget=value_entry, baseline_widget=baseline_label, result_map=result_widgets: self._live_evaluate(current_test, entry_widget, baseline_widget, result_map),
                )

            deviation_label = tk.Label(form_frame, text="--", bg=row_bg, width=9, anchor="center", font=("Helvetica", 8))
            deviation_label.grid(row=row_idx, column=7, sticky="ew", padx=1, pady=1)

            status_label = tk.Label(form_frame, text="--", bg=row_bg, width=14, anchor="center", font=("Helvetica", 8, "bold"))
            status_label.grid(row=row_idx, column=8, sticky="ew", padx=1, pady=1)

            notes_entry = tk.Entry(form_frame, width=20, font=("Helvetica", 8))
            notes_entry.grid(row=row_idx, column=9, sticky="ew", padx=1, pady=1)

            entries_by_test[test["name"]] = (value_entry, notes_entry, functional_var, baseline_label)
            result_widgets[test["name"]] = (deviation_label, status_label)

        outer._entries_dict = entries_by_test
        outer._tests = tests
        outer._frequency = frequency
        outer._operator_var = operator_var
        return outer

    def _live_evaluate(self, test, value_entry, baseline_lbl, result_labels):
        if self.current_machine_id is None:
            return

        raw_value = value_entry.get().strip()
        if not raw_value:
            return

        try:
            numeric_value = float(raw_value)
        except ValueError:
            return

        baseline_row = get_baseline(self.current_machine_id, test["name"])
        baseline_value = baseline_row[0] if baseline_row else None

        deviation, status = evaluate_result(test, numeric_value, None, baseline_value)

        deviation_label, status_label = result_labels.get(test["name"], (None, None))
        if deviation_label:
            deviation_label.config(text=f"{deviation:.3f}" if deviation is not None else "--")
        if status_label:
            status_label.config(text=status, bg=STATUS_COLORS.get(status, "#e2e3e5"), fg=STATUS_FG.get(status, "black"))

    def _save_all_results(self, tests, frequency, entries_dict, operator_var, result_labels):
        if self.current_machine_id is None:
            messagebox.showwarning("No Machine", "Please select a machine first.")
            return

        operator_name = operator_var.get().strip() or "Unknown"
        saved_count = 0
        invalid_tests = []

        for test in tests:
            widgets = entries_dict.get(test["name"])
            if not widgets:
                continue

            value_entry, notes_entry, functional_var, baseline_lbl = widgets
            notes_text = notes_entry.get().strip() if notes_entry else ""

            if test["tol_type"] == "functional":
                functional_result = functional_var.get() if functional_var else ""
                if not functional_result:
                    continue

                _, status = evaluate_result(test, None, functional_result, None)
                save_qa_record(
                    self.current_machine_id,
                    test["name"],
                    frequency,
                    None,
                    functional_result,
                    None,
                    test["tolerance"],
                    status,
                    operator_name,
                    notes_text,
                )

                _, status_label = result_labels.get(test["name"], (None, None))
                if status_label:
                    status_label.config(text=status, bg=STATUS_COLORS.get(status, "#e2e3e5"), fg=STATUS_FG.get(status, "black"))
                saved_count += 1
                continue

            if not value_entry:
                continue

            raw_value = value_entry.get().strip()
            if not raw_value:
                continue

            try:
                numeric_value = float(raw_value)
            except ValueError:
                invalid_tests.append(test["name"])
                continue

            baseline_row = get_baseline(self.current_machine_id, test["name"])
            baseline_value = baseline_row[0] if baseline_row else None
            deviation, status = evaluate_result(test, numeric_value, None, baseline_value)

            save_qa_record(
                self.current_machine_id,
                test["name"],
                frequency,
                numeric_value,
                None,
                deviation,
                test["tolerance"],
                status,
                operator_name,
                notes_text,
            )

            deviation_label, status_label = result_labels.get(test["name"], (None, None))
            if deviation_label:
                deviation_label.config(text=f"{deviation:.3f}" if deviation is not None else "--")
            if status_label:
                status_label.config(text=status, bg=STATUS_COLORS.get(status, "#e2e3e5"), fg=STATUS_FG.get(status, "black"))
            saved_count += 1

        message = f"Saved {saved_count} result(s) for {frequency} QA."
        if invalid_tests:
            message += f"\nSkipped (invalid input): {', '.join(invalid_tests)}"
        messagebox.showinfo("Saved", message)

    def _build_summary_tab(self):
        frame = tk.Frame(self.notebook, bg="#f0f0f0")

        top_bar = tk.Frame(frame, bg="#dce3ea", pady=6)
        top_bar.pack(fill=tk.X)
        tk.Label(top_bar, text="QA Summary & History", bg="#dce3ea", font=("Helvetica", 11, "bold")).pack(side=tk.LEFT, padx=12)
        ttk.Button(top_bar, text="Refresh", command=self._refresh_summary).pack(side=tk.LEFT, padx=8)

        self._summary_freq_var = tk.StringVar(value="All")
        for option in ("All", "Daily", "Monthly", "Annual"):
            ttk.Radiobutton(top_bar, text=option, variable=self._summary_freq_var, value=option, command=self._refresh_summary).pack(side=tk.LEFT, padx=4)

        columns = ("Date", "Test", "Measured", "Deviation", "Tolerance", "Status", "Operator")
        tree = ttk.Treeview(frame, columns=columns, show="headings", height=30)
        for col_name in columns:
            tree.heading(col_name, text=col_name)
            tree.column(col_name, width=180 if col_name == "Test" else 100, minwidth=60)

        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4, pady=4)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=4)

        tree.tag_configure("PASS", background="#d4edda")
        tree.tag_configure("FAIL", background="#f8d7da")
        tree.tag_configure("WARN", background="#fff3cd")
        tree.tag_configure("FuncPASS", background="#d4edda")
        tree.tag_configure("FuncFAIL", background="#f8d7da")

        self._summary_tree = tree
        return frame

    def _refresh_summary(self):
        if self.current_machine_id is None:
            return

        selected_frequency = self._summary_freq_var.get()
        frequency_filter = None if selected_frequency == "All" else selected_frequency
        rows = get_all_qa_for_machine(self.current_machine_id, frequency_filter)

        for item in self._summary_tree.get_children():
            self._summary_tree.delete(item)

        for row in rows:
            date_str, test_name, measured_value, deviation, tolerance, status, operator = row
            measured_text = f"{measured_value:.4f}" if measured_value is not None else "--"
            deviation_text = f"{deviation:.4f}" if deviation is not None else "--"
            tolerance_text = f"{tolerance:.4f}" if tolerance is not None else "Functional"

            tag = ""
            if status == "PASS":
                tag = "PASS"
            elif status == "FAIL":
                tag = "FAIL"
            elif status == "Functional-PASS":
                tag = "FuncPASS"
            elif status == "Functional-FAIL":
                tag = "FuncFAIL"

            self._summary_tree.insert(
                "",
                "end",
                values=(date_str[:16], test_name, measured_text, deviation_text, tolerance_text, status, operator),
                tags=(tag,),
            )

    def _refresh_machine_list(self):
        machines = get_machines()
        self._machines_raw = machines
        self.machine_combo["values"] = [f"{machine[0]}: {machine[1]} ({machine[2] or 'N/A'})" for machine in machines]

    def _on_machine_select(self, event):
        selected_index = self.machine_combo.current()
        if selected_index < 0 or selected_index >= len(self._machines_raw):
            return

        machine = self._machines_raw[selected_index]
        self.current_machine_id = machine[0]
        self.title(f"TG-142 QA Manager — {machine[1]}")
        self._refresh_baseline_labels()
        self._refresh_summary()

    def _refresh_baseline_labels(self):
        if self.current_machine_id is None:
            return

        for tab_frame in (self.daily_frame, self.monthly_frame, self.annual_frame):
            entries = getattr(tab_frame, "_entries_dict", {})
            for test_name, widgets in entries.items():
                _, _, _, baseline_label = widgets
                baseline = get_baseline(self.current_machine_id, test_name)
                baseline_label.config(text=f"{baseline[0]:.3f}" if baseline else "--")

    def show_add_machine(self):
        window = tk.Toplevel(self)
        window.title("Add / Edit Machine")
        window.geometry("500x440")
        window.grab_set()

        fields = [
            ("Machine Name *", "name"),
            ("Model", "model"),
            ("Serial Number", "serial_number"),
            ("Institution", "institution"),
            ("Energies (e.g. 6MV,10MV,6e)", "energies"),
            ("Notes", "notes"),
        ]

        entries = {}
        for row_idx, (label_text, key) in enumerate(fields):
            tk.Label(window, text=label_text).grid(row=row_idx, column=0, sticky="e", padx=12, pady=6)
            entry = tk.Entry(window, width=36)
            entry.grid(row=row_idx, column=1, sticky="ew", padx=8, pady=6)
            entries[key] = entry

        tk.Label(window, text="Machine Type *").grid(row=len(fields), column=0, sticky="e", padx=12, pady=6)
        machine_type_var = tk.StringVar(value="IMRT")
        machine_type_combo = ttk.Combobox(window, textvariable=machine_type_var, values=["Non-IMRT", "IMRT", "IMRT/SRS/SBRT"], state="readonly", width=34)
        machine_type_combo.grid(row=len(fields), column=1, sticky="ew", padx=8, pady=6)

        def do_save():
            machine_name = entries["name"].get().strip()
            if not machine_name:
                messagebox.showerror("Error", "Machine name is required.", parent=window)
                return

            machine_id = save_machine(
                name=machine_name,
                model=entries["model"].get().strip(),
                serial_number=entries["serial_number"].get().strip(),
                institution=entries["institution"].get().strip(),
                machine_type=machine_type_var.get(),
                energies=entries["energies"].get().strip(),
                notes=entries["notes"].get().strip(),
            )
            self._refresh_machine_list()
            messagebox.showinfo("Saved", f"Machine '{machine_name}' saved (ID={machine_id}).", parent=window)
            window.destroy()

        ttk.Button(window, text="Save Machine", command=do_save).grid(row=len(fields) + 1, column=0, columnspan=2, pady=16)

    def show_baseline_editor(self):
        if self.current_machine_id is None:
            messagebox.showwarning("No Machine", "Please select a machine first.")
            return

        window = tk.Toplevel(self)
        window.title("Commissioning Baseline Values")
        window.geometry("820x680")
        window.grab_set()

        tk.Label(
            window,
            text=(
                "Enter commissioning/reference baseline values for each test.\n"
                "These are used to calculate deviations during routine QA."
            ),
            justify="left",
        ).pack(anchor="w", padx=12, pady=8)

        filter_bar = tk.Frame(window)
        filter_bar.pack(fill=tk.X, padx=8)
        tk.Label(filter_bar, text="Filter:").pack(side=tk.LEFT)
        filter_var = tk.StringVar(value="All")
        for option in ("All", "Daily", "Monthly", "Annual"):
            ttk.Radiobutton(filter_bar, text=option, variable=filter_var, value=option, command=lambda: refresh_list()).pack(side=tk.LEFT, padx=4)

        canvas = tk.Canvas(window)
        scrollbar = ttk.Scrollbar(window, orient="vertical", command=canvas.yview)
        form_frame = tk.Frame(canvas)
        form_frame.bind("<Configure>", lambda event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=form_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4, pady=4)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        canvas.bind_all("<MouseWheel>", lambda event, active_canvas=canvas: active_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units"))

        baseline_entries = {}

        def refresh_list():
            for widget in form_frame.winfo_children():
                widget.destroy()

            headers = ["Test Name", "Freq", "Unit", "Baseline Value", "Last Set"]
            widths = [36, 8, 8, 16, 14]
            for col_idx, (header_text, width) in enumerate(zip(headers, widths)):
                tk.Label(
                    form_frame,
                    text=header_text,
                    bg="#3c4a5a",
                    fg="white",
                    width=width,
                    font=("Helvetica", 9, "bold"),
                    anchor="w",
                    padx=4,
                ).grid(row=0, column=col_idx, sticky="ew", padx=1, pady=1)

            selected_frequency = filter_var.get()
            for row_idx, test in enumerate(ALL_TESTS, start=1):
                if selected_frequency != "All" and test["frequency"] != selected_frequency:
                    continue
                if test["tol_type"] == "functional":
                    continue

                row_bg = "#fafafa" if row_idx % 2 == 0 else "#ffffff"
                tk.Label(form_frame, text=test["name"], bg=row_bg, width=36, anchor="w", font=("Helvetica", 8), padx=4, wraplength=260).grid(row=row_idx, column=0, sticky="ew", padx=1, pady=1)
                tk.Label(form_frame, text=test["frequency"][:7], bg=row_bg, width=8, anchor="center", font=("Helvetica", 8)).grid(row=row_idx, column=1, sticky="ew", padx=1, pady=1)
                tk.Label(form_frame, text=test["unit"], bg=row_bg, width=8, anchor="center", font=("Helvetica", 8)).grid(row=row_idx, column=2, sticky="ew", padx=1, pady=1)

                entry = tk.Entry(form_frame, width=16, font=("Helvetica", 9))
                baseline = get_baseline(self.current_machine_id, test["name"])
                if baseline:
                    entry.insert(0, str(baseline[0]))
                entry.grid(row=row_idx, column=3, sticky="ew", padx=4, pady=1)
                baseline_entries[test["name"]] = entry

                last_set_text = baseline[1] if baseline else "Not set"
                tk.Label(form_frame, text=last_set_text, bg=row_bg, width=14, anchor="center", font=("Helvetica", 7), fg="#555").grid(row=row_idx, column=4, sticky="ew", padx=1, pady=1)

        refresh_list()

        def save_all_baselines():
            saved_count = 0
            for test_name, entry in baseline_entries.items():
                raw_value = entry.get().strip()
                if not raw_value:
                    continue
                try:
                    numeric_value = float(raw_value)
                    save_baseline(self.current_machine_id, test_name, numeric_value)
                    saved_count += 1
                except ValueError:
                    pass

            self._refresh_baseline_labels()
            messagebox.showinfo("Saved", f"Saved {saved_count} baseline values.", parent=window)

        ttk.Button(window, text="Save All Baselines", command=save_all_baselines).pack(pady=8)

    def show_history(self):
        if self.current_machine_id is None:
            messagebox.showwarning("No Machine", "Please select a machine first.")
            return

        window = tk.Toplevel(self)
        window.title("QA Record History")
        window.geometry("900x600")

        top_bar = tk.Frame(window)
        top_bar.pack(fill=tk.X, padx=8, pady=6)
        tk.Label(top_bar, text="Test:").pack(side=tk.LEFT)

        numeric_tests = [test["name"] for test in ALL_TESTS if test["tol_type"] != "functional"]
        test_var = tk.StringVar(value=numeric_tests[0] if numeric_tests else "")
        ttk.Combobox(top_bar, textvariable=test_var, values=numeric_tests, state="readonly", width=50).pack(side=tk.LEFT, padx=8)
        ttk.Button(top_bar, text="Load", command=lambda: load_history()).pack(side=tk.LEFT)

        columns = ("Date", "Measured", "Deviation", "Status", "Operator", "Notes")
        tree = ttk.Treeview(window, columns=columns, show="headings", height=25)
        for col_name in columns:
            tree.heading(col_name, text=col_name)
            tree.column(col_name, width=130)
        tree.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        tree.tag_configure("PASS", background="#d4edda")
        tree.tag_configure("FAIL", background="#f8d7da")

        def load_history():
            for item in tree.get_children():
                tree.delete(item)
            rows = get_qa_history(self.current_machine_id, test_var.get())
            for row in rows:
                date_str, measured_value, deviation, status, operator, notes = row
                tree.insert(
                    "",
                    "end",
                    values=(
                        date_str[:16],
                        f"{measured_value:.4f}" if measured_value is not None else "--",
                        f"{deviation:.4f}" if deviation is not None else "--",
                        status or "--",
                        operator or "--",
                        notes or "",
                    ),
                    tags=(("PASS",) if status == "PASS" else ("FAIL",) if status == "FAIL" else ()),
                )

    def show_trend_plots(self):
        if not HAS_MPL:
            messagebox.showerror("Missing Library", "matplotlib is not installed.\nRun: pip install matplotlib")
            return
        if self.current_machine_id is None:
            messagebox.showwarning("No Machine", "Please select a machine first.")
            return

        window = tk.Toplevel(self)
        window.title("QA Trend Plots")
        window.geometry("1000x700")

        top_bar = tk.Frame(window)
        top_bar.pack(fill=tk.X, padx=8, pady=6)

        tk.Label(top_bar, text="Test:").pack(side=tk.LEFT)
        numeric_tests = [test["name"] for test in ALL_TESTS if test["tol_type"] != "functional"]
        test_var = tk.StringVar(value=numeric_tests[0] if numeric_tests else "")
        ttk.Combobox(top_bar, textvariable=test_var, values=numeric_tests, state="readonly", width=48).pack(side=tk.LEFT, padx=6)

        tk.Label(top_bar, text="View:").pack(side=tk.LEFT, padx=(12, 2))
        view_var = tk.StringVar(value="Measured Value")
        ttk.Combobox(top_bar, textvariable=view_var, values=["Measured Value", "Deviation"], state="readonly", width=16).pack(side=tk.LEFT)

        figure = Figure(figsize=(10, 5), dpi=96)
        axis = figure.add_subplot(111)
        canvas_plot = FigureCanvasTkAgg(figure, master=window)
        canvas_plot.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        def do_plot():
            test_name = test_var.get()
            rows = get_qa_history(self.current_machine_id, test_name, limit=500)
            if not rows:
                messagebox.showinfo("No Data", f"No QA records found for:\n{test_name}", parent=window)
                return

            plot_dates = []
            plot_values = []
            plot_deviations = []
            plot_statuses = []

            for row in reversed(rows):
                date_str, measured_value, deviation, status, _, _ = row
                if measured_value is None:
                    continue
                try:
                    plot_dates.append(datetime.strptime(date_str[:16], "%Y-%m-%d %H:%M"))
                    plot_values.append(measured_value)
                    plot_deviations.append(deviation if deviation is not None else 0)
                    plot_statuses.append(status)
                except Exception:
                    pass

            if not plot_dates:
                messagebox.showinfo("No Data", "No numeric data to plot.", parent=window)
                return

            axis.clear()

            test_def = next((test for test in ALL_TESTS if test["name"] == test_name), None)
            tolerance = test_def["tolerance"] if test_def else None

            y_data = plot_deviations if view_var.get() == "Deviation" else plot_values
            point_colors = ["#28a745" if status == "PASS" else "#dc3545" for status in plot_statuses]

            axis.scatter(plot_dates, y_data, c=point_colors, s=40, zorder=5)
            axis.plot(plot_dates, y_data, color="#6c757d", linewidth=0.8, alpha=0.7)

            if tolerance is not None and view_var.get() == "Deviation":
                axis.axhline(tolerance, color="red", linestyle="--", linewidth=1, label=f"Tolerance ±{tolerance}")
                axis.axhline(-tolerance, color="red", linestyle="--", linewidth=1)

            baseline = get_baseline(self.current_machine_id, test_name)
            if baseline and view_var.get() == "Measured Value":
                axis.axhline(baseline[0], color="blue", linestyle=":", linewidth=1.2, label=f"Baseline: {baseline[0]}")

            axis.set_title(f"{test_name}\n(Machine ID {self.current_machine_id})", fontsize=10)
            axis.set_xlabel("Date")
            axis.set_ylabel(view_var.get())
            axis.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
            figure.autofmt_xdate(rotation=30)
            axis.grid(True, alpha=0.3)

            from matplotlib.patches import Patch
            legend_items = [Patch(facecolor="#28a745", label="PASS"), Patch(facecolor="#dc3545", label="FAIL")]
            handles, labels = axis.get_legend_handles_labels()
            axis.legend(legend_items + handles, ["PASS", "FAIL"] + labels, fontsize=8)

            canvas_plot.draw()

        def save_plot():
            filepath = filedialog.asksaveasfilename(
                defaultextension=".png",
                filetypes=[("PNG", "*.png"), ("PDF", "*.pdf"), ("SVG", "*.svg")],
                parent=window,
            )
            if filepath:
                figure.savefig(filepath, dpi=150, bbox_inches="tight")
                messagebox.showinfo("Saved", f"Plot saved to:\n{filepath}", parent=window)

        ttk.Button(top_bar, text="Plot", command=do_plot).pack(side=tk.LEFT, padx=10)
        ttk.Button(top_bar, text="Save Plot...", command=save_plot).pack(side=tk.LEFT)

    def export_csv(self):
        if self.current_machine_id is None:
            messagebox.showwarning("No Machine", "Please select a machine first.")
            return

        filepath = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            initialfile=f"linac_qa_{datetime.now().strftime('%Y%m%d')}.csv",
        )
        if not filepath:
            return

        rows = get_all_qa_for_machine(self.current_machine_id)
        with open(filepath, "w", newline="") as file_handle:
            writer = csv.writer(file_handle)
            writer.writerow(["Date", "Test Name", "Measured Value", "Deviation", "Tolerance", "Status", "Operator"])
            for row in rows:
                writer.writerow(row)

        messagebox.showinfo("Exported", f"Exported {len(rows)} records to:\n{filepath}")

    def show_tg142_summary(self):
        window = tk.Toplevel(self)
        window.title("TG-142 Tolerance Summary")
        window.geometry("900x620")

        columns = ("Frequency", "Category", "Test Name", "Tolerance", "Unit", "Notes")
        tree = ttk.Treeview(window, columns=columns, show="headings", height=30)
        for col_name, width in zip(columns, [70, 90, 280, 80, 70, 200]):
            tree.heading(col_name, text=col_name)
            tree.column(col_name, width=width)

        scrollbar = ttk.Scrollbar(window, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4, pady=4)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=4)

        tree.tag_configure("Daily", background="#e8f4f8")
        tree.tag_configure("Monthly", background="#f0f4e8")
        tree.tag_configure("Annual", background="#f8f0e8")

        for test in ALL_TESTS:
            tolerance_text = f"±{test['tolerance']}" if test["tolerance"] is not None else "Functional"
            tree.insert(
                "",
                "end",
                values=(test["frequency"], test["category"], test["name"], tolerance_text, test["unit"], test.get("notes", "")),
                tags=(test["frequency"],),
            )

    def show_about(self):
        messagebox.showinfo(
            "About",
            "TG-142 Linac QA Manager\n"
            "─────────────────────────────\n"
            "Based on AAPM TG-142:\n"
            "Klein et al., Med. Phys. 36(9), 4197-4212 (2009)\n\n"
            "Single-file Python/Tkinter + SQLite application.\n"
            "Run in Spyder or any Python 3 environment.\n\n"
            "Features:\n"
            "• Commissioning baseline storage\n"
            "• Daily / Monthly / Annual QA entry\n"
            "• Pass/Fail evaluation vs TG-142 tolerances\n"
            "• Trend plots (matplotlib)\n"
            "• CSV export\n\n"
            "No web frameworks. Pure Python.",
        )

    def _add_tooltip(self, widget, text):
        tooltip_window = None

        def show_tooltip(event):
            nonlocal tooltip_window
            x = widget.winfo_rootx() + 20
            y = widget.winfo_rooty() + 20
            tooltip_window = tk.Toplevel(widget)
            tooltip_window.wm_overrideredirect(True)
            tooltip_window.wm_geometry(f"+{x}+{y}")
            tk.Label(
                tooltip_window,
                text=text,
                background="#ffffe0",
                relief="solid",
                borderwidth=1,
                font=("Helvetica", 8),
                wraplength=300,
            ).pack()

        def hide_tooltip(event):
            nonlocal tooltip_window
            if tooltip_window:
                tooltip_window.destroy()
                tooltip_window = None

        widget.bind("<Enter>", show_tooltip)
        widget.bind("<Leave>", hide_tooltip)


if __name__ == "__main__":
    init_db()

    if not HAS_MPL:
        print("WARNING: matplotlib not found. Trend plots will be disabled.")
        print("Install with: pip install matplotlib")

    app = TG142App()
    app.mainloop()
