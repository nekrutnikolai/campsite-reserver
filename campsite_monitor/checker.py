import logging

import requests

LOG = logging.getLogger(__name__)


def check_connectivity():
    """Quick connectivity check. Returns True if network is reachable."""
    try:
        requests.head("https://www.google.com", timeout=5)
        return True
    except Exception:
        return False


def check_all(recgov_campgrounds, reserveca_campgrounds, checkin, checkout, recgov_mod, reserveca_mod):
    """Check all campgrounds across both APIs. Returns (results, errors).

    recgov_campgrounds: list of {"name", "id"} dicts
    reserveca_campgrounds: list of campground dicts from discover_all_facilities()
    checkin, checkout: date objects
    recgov_mod, reserveca_mod: the api.recgov and api.reserveca modules
    """
    results = []
    errors = []

    for cg in recgov_campgrounds:
        try:
            available = recgov_mod.check_availability(cg, checkin, checkout)
            results.extend(available)
        except Exception:
            LOG.exception("Error checking %s", cg["name"])
            errors.append(cg["name"])

    for cg in reserveca_campgrounds:
        try:
            site_type_filter = cg.get("filters", {}).get("site_types") if isinstance(cg.get("filters"), dict) else None
            available = reserveca_mod.check_availability(cg, checkin, checkout, site_type_filter=site_type_filter)
            results.extend(available)
        except Exception:
            LOG.exception("Error checking %s", cg["name"])
            errors.append(cg["name"])

    return results, errors
