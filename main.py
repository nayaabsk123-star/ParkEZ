from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="ParkEZ API")

# Enable CORS so your index.html can communicate with this backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-Memory State for Parking Slots & Gate
system_state = {
    "slots": {"1": "free", "2": "free", "3": "free"},
    "gate_status": "CLOSED"
}

class SensorPayload(BaseModel):
    slot_id: str
    is_occupied: bool

class PrebookPayload(BaseModel):
    slot_id: str

# Endpoint 1: Frontend fetches slot & gate status
@app.get("/api/status")
def get_system_status():
    return system_state

# Endpoint 2: ESP32 updates IR sensor states
@app.post("/api/hardware/sensor")
def update_sensor(payload: SensorPayload):
    if payload.slot_id not in system_state["slots"]:
        raise HTTPException(status_code=404, detail="Slot not found")
    
    system_state["slots"][payload.slot_id] = "occupied" if payload.is_occupied else "free"
    return {"status": "success", "updated_slot": payload.slot_id, "state": system_state["slots"][payload.slot_id]}

# Endpoint 3: Frontend pre-books a parking slot
@app.post("/api/prebook")
def prebook_slot(payload: PrebookPayload):
    if payload.slot_id not in system_state["slots"]:
        raise HTTPException(status_code=404, detail="Slot not found")
    
    if system_state["slots"][payload.slot_id] != "free":
        raise HTTPException(status_code=400, detail="Slot unavailable")
    
    system_state["slots"][payload.slot_id] = "booked"
    system_state["gate_status"] = "OPEN"
    return {"message": f"Slot {payload.slot_id} booked!", "gate_status": system_state["gate_status"]}

# Endpoint 4: ESP32 polls to check if servo gate should open
@app.get("/api/hardware/gate-status")
def get_gate_status():
    return {"gate_status": system_state["gate_status"]}
