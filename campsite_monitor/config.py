import logging
import os

import yaml

LOG = logging.getLogger(__name__)


def load_config(path):
    """Load campground configuration from a YAML file.

    Returns dict with keys:
        "recgov": list of {"name": str, "id": str}
        "reserveca": list of {"name": str, "place_id": str, optional "facility_ids": list, optional "filters": dict}

    Raises SystemExit on missing file or invalid config.
    """
    if not os.path.exists(path):
        print(f"Error: config file not found: {path}")
        raise SystemExit(1)

    with open(path) as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        print(f"Error: config file must be a YAML mapping: {path}")
        raise SystemExit(1)

    recgov = []
    for item in data.get("recgov", []):
        if "id" not in item or "name" not in item:
            print(f"Error: recgov entry missing 'id' or 'name': {item}")
            raise SystemExit(1)
        recgov.append({"name": item["name"], "id": str(item["id"])})

    reserveca = []
    for item in data.get("reserveca", []):
        if "place_id" not in item or "name" not in item:
            print(f"Error: reserveca entry missing 'place_id' or 'name': {item}")
            raise SystemExit(1)
        entry = {"name": item["name"], "place_id": str(item["place_id"])}
        if "facility_ids" in item:
            entry["facility_ids"] = [str(fid) for fid in item["facility_ids"]]
        if "filters" in item:
            entry["filters"] = item["filters"]
        reserveca.append(entry)

    return {"recgov": recgov, "reserveca": reserveca}
