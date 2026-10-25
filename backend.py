import sqlite3
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

app = FastAPI(title="ParkEZ Enterprise API - Shree Pant Nagari")

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = "parkez.db"

# ---------------------------------------------------------
# DATABASE INITIALIZATION
# ---------------------------------------------------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Slot Status Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS room_status (
            room_number TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'free',
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 2. Activity Audit Log Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS occupancy_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_number TEXT NOT NULL,
            event_type TEXT NOT NULL,
            user_id TEXT DEFAULT 'SYSTEM',
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 3. Visitor Approvals Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS visitors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            plate TEXT NOT NULL,
            flat TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 4. Gate Control Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS gate_status (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            state TEXT NOT NULL DEFAULT 'CLOSED',
            last_action_by TEXT DEFAULT 'SYSTEM',
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Seed initial slot records (Slots 1, 2, 3)
    for slot in ["1", "2", "3"]:
        cursor.execute("INSERT OR IGNORE INTO room_status (room_number, status) VALUES (?, 'free')", (slot,))

    # Seed gate status initial state
    cursor.execute("INSERT OR IGNORE INTO gate_status (id, state) VALUES (1, 'CLOSED')")

    conn.commit()
    conn.close()

init_db()

# ---------------------------------------------------------
# PYDANTIC SCHEMAS
# ---------------------------------------------------------
class PrebookPayload(BaseModel):
    slot_id: str
    resident_id: Optional[str] = "A-302"

class SensorPayload(BaseModel):
    slot_id: str
    status: str

class VisitorPayload(BaseModel):
    name: str
    plate: str
    flat: str

class GatePayload(BaseModel):
    state: str
    action_by: Optional[str] = "GUARD"

# ---------------------------------------------------------
# API ENDPOINTS
# ---------------------------------------------------------

# --- PARKING SLOTS ---
@app.get("/api/status")
def get_parking_status():
    """Fetch real-time parking slot statuses."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT room_number, status FROM room_status")
    rows = cursor.fetchall()
    conn.close()
    return {"slots": {row[0]: row[1] for row in rows}}

@app.post("/api/prebook")
def prebook_slot(payload: PrebookPayload):
    """Pre-book an available parking slot."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT status FROM room_status WHERE room_number = ?", (payload.slot_id,))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Slot not found")
    if row[0] != "free":
        conn.close()
        raise HTTPException(status_code=400, detail="Slot is not vacant")

    cursor.execute(
        "UPDATE room_status SET status = 'reserved', last_updated = CURRENT_TIMESTAMP WHERE room_number = ?", 
        (payload.slot_id,)
    )
    cursor.execute(
        "INSERT INTO occupancy_records (room_number, event_type, user_id) VALUES (?, 'PREBOOK', ?)", 
        (payload.slot_id, payload.resident_id)
    )
    conn.commit()
    conn.close()
    return {"message": f"Slot {payload.slot_id} reserved successfully", "pass_code": f"PASS-{payload.resident_id}-SLOT0{payload.slot_id}"}

@app.post("/api/update_slot")
def update_slot(payload: SensorPayload):
    """Update slot status via sensor trigger."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE room_status SET status = ?, last_updated = CURRENT_TIMESTAMP WHERE room_number = ?", 
        (payload.status, payload.slot_id)
    )
    cursor.execute(
        "INSERT INTO occupancy_records (room_number, event_type) VALUES (?, ?)", 
        (payload.slot_id, payload.status.upper())
    )
    conn.commit()
    conn.close()
    return {"status": "success", "slot_id": payload.slot_id, "state": payload.status}

# --- VISITOR REGISTRATION ---
@app.get("/api/visitors")
def get_visitors():
    """Fetch registered visitors for security portal."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, plate, flat, status FROM visitors ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "name": r[1], "plate": r[2], "flat": r[3], "status": r[4]} for r in rows]

@app.post("/api/visitors/register")
def register_visitor(payload: VisitorPayload):
    """Register guest vehicle."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO visitors (name, plate, flat, status) VALUES (?, ?, ?, 'PENDING')",
        (payload.name, payload.plate, payload.flat)
    )
    conn.commit()
    conn.close()
    return {"message": "Visitor registered successfully"}

@app.post("/api/visitors/approve/{visitor_id}")
def approve_visitor(visitor_id: int):
    """Approve visitor entry."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE visitors SET status = 'APPROVED' WHERE id = ?", (visitor_id,))
    cursor.execute("UPDATE gate_status SET state = 'OPEN', last_action_by = 'VISITOR_APPROVAL' WHERE id = 1")
    conn.commit()
    conn.close()
    return {"message": "Visitor approved & gate opened"}

# --- GATE BARRIER CONTROL ---
@app.post("/api/gate")
def set_gate_status(payload: GatePayload):
    """Actuate SG90 gate barrier servo state."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE gate_status SET state = ?, last_action_by = ? WHERE id = 1", (payload.state, payload.action_by))
    conn.commit()
    conn.close()
    return {"gate_status": payload.state}
