import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests

app = FastAPI(
    title="Cell Tower Geolocation Service",
    version="1.0.0",
    description="Resolve MCC/MNC/LAC/CI (hex) via Google Geolocation API",
)

# Read the Google API key from environment
GOOGLE_API_KEY = os.getenv("GOOGLE_GEO_API_KEY")
if not GOOGLE_API_KEY:
    # For Railway, just make sure you set this env var in the dashboard
    raise RuntimeError("GOOGLE_GEO_API_KEY environment variable is not set")

GOOGLE_URL = f"https://www.googleapis.com/geolocation/v1/geolocate?key=AIzaSyA-0TQB0mS1B9Ci7CfnzrH7HQdrG-BIjdo"


class CellLookupRequest(BaseModel):
    # Defaults for your case, but overridable
    mcc: int = 505          # Australia
    mnc: int = 1            # Telstra
    lac_hex: str            # e.g. "3011"
    ci_hex: str             # e.g. "826BC03"
    radio_type: str = "lte" # or "gsm", "wcdma", etc.


class CellLookupResponse(BaseModel):
    lat: float
    lon: float
    accuracy: float
    mcc: int
    mnc: int
    lac_dec: int
    ci_dec: int


def hex_to_dec(value: str) -> int:
    """
    Convert a hex string (with or without '0x' prefix) to decimal int.
    """
    value = value.strip()
    if value.lower().startswith("0x"):
        value = value[2:]
    return int(value, 16)


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/cell-location", response_model=CellLookupResponse)
def cell_location(req: CellLookupRequest):
    # 1. Convert hex -> decimal
    try:
        lac_dec = hex_to_dec(req.lac_hex)
        ci_dec = hex_to_dec(req.ci_hex)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid hex values for LAC or CI")

    # 2. Build payload for Google Geolocation API
    payload = {
        "cellTowers": [
            {
                "mobileCountryCode": req.mcc,
                "mobileNetworkCode": req.mnc,
                "locationAreaCode": lac_dec,
                "cellId": ci_dec,
                "radioType": req.radio_type,
            }
        ]
    }

    # 3. Call Google API
    try:
        r = requests.post(GOOGLE_URL, json=payload, timeout=5)
    except requests.RequestException as e:
        raise HTTPException(
            status_code=502,
            detail=f"Error contacting Google Geolocation API: {e}",
        )

    if r.status_code != 200:
        # Surface Google’s error body so you can debug quota/auth issues
        raise HTTPException(
            status_code=502,
            detail=f"Google API error (status {r.status_code}): {r.text}",
        )

    data = r.json()
    location = data.get("location")
    if not location:
        raise HTTPException(
            status_code=502,
            detail="No 'location' field in Google Geolocation API response",
        )

    return CellLookupResponse(
        lat=location["lat"],
        lon=location["lng"],
        accuracy=data.get("accuracy", 0),
        mcc=req.mcc,
        mnc=req.mnc,
        lac_dec=lac_dec,
        ci_dec=ci_dec,
    )
