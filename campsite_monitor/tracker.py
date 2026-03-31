import time


class AvailabilityTracker:
    """Tracks site availability across cycles, detecting new and gone sites."""

    def __init__(self, db=None):
        self.previously_available = {}  # (campground, site, checkin_str, checkout_str) -> site dict
        self.total_found = set()  # all-time set of keys
        self.sites_found_today = 0
        self.db = db  # optional SiteDB for persistence

    def update(self, available_sites, checkin, checkout):
        """Process one cycle's results. Returns (new_sites: list, gone_sites: list).

        Each site dict has: campground, site, url, park_url, and optionally site_type.
        """
        checkin_str = str(checkin)
        checkout_str = str(checkout)

        now_available = {}
        for site in available_sites:
            key = (site["campground"], site["site"], checkin_str, checkout_str)
            now_available[key] = site

        # Detect NEW sites
        new_sites = []
        for key, site in now_available.items():
            if key not in self.previously_available:
                # If db provided, check if we've seen this across restarts
                if self.db and not self.db.record_find(
                    site["campground"],
                    site["site"],
                    checkin_str,
                    checkout_str,
                    site.get("url", ""),
                ):
                    continue  # Already known from before restart
                self.total_found.add(key)
                self.sites_found_today += 1
                new_sites.append(site)

        # Detect GONE sites
        gone_sites = []
        for key, site in self.previously_available.items():
            if (
                key[2] == checkin_str
                and key[3] == checkout_str
                and key not in now_available
            ):
                gone_sites.append(site)
                if self.db:
                    self.db.record_gone(
                        site["campground"], site["site"], checkin_str, checkout_str
                    )

        # Update previously_available: remove old keys for this date range, add new
        self.previously_available = {
            k: v
            for k, v in self.previously_available.items()
            if not (k[2] == checkin_str and k[3] == checkout_str)
        }
        self.previously_available.update(now_available)

        return new_sites, gone_sites

    def reset_daily(self):
        """Reset daily counters (called at daily summary time)."""
        self.sites_found_today = 0

    @property
    def total_tracked(self):
        return len(self.total_found)


class FailureTracker:
    """Tracks consecutive API failures per source, triggers alerts at threshold."""

    def __init__(self, threshold=3):
        self.consecutive = {}  # name -> count
        self.alerted = set()  # names we've sent failure alerts for
        self.threshold = threshold

    def update(self, errors, all_names):
        """Process one cycle. Returns (newly_failed: list[str], recovered: list[str])."""
        error_set = set(errors)
        newly_failed = []
        recovered = []

        for name in all_names:
            if name in error_set:
                self.consecutive[name] = self.consecutive.get(name, 0) + 1
                if (
                    self.consecutive[name] == self.threshold
                    and name not in self.alerted
                ):
                    self.alerted.add(name)
                    newly_failed.append(name)
            else:
                if name in self.alerted:
                    self.alerted.discard(name)
                    recovered.append(name)
                self.consecutive[name] = 0

        return newly_failed, recovered


class NetworkMonitor:
    """Tracks network connectivity, alerts after sustained downtime."""

    def __init__(self, threshold=300):
        self.down_since = None
        self.alerted = False
        self.threshold = threshold  # seconds before alerting

    def check(self, is_up):
        """Process one connectivity check. Returns one of:
        'up'          - network is up, no state change
        'down_silent' - network is down, within threshold
        'down_alert'  - network is down, threshold exceeded (first time)
        'recovered'   - network came back after alert was sent
        """
        if not is_up:
            if self.down_since is None:
                self.down_since = time.monotonic()
                return "down_silent"
            elif not self.alerted and time.monotonic() - self.down_since > self.threshold:
                self.alerted = True
                return "down_alert"
            return "down_silent"
        else:
            if self.alerted:
                self.down_since = None
                self.alerted = False
                return "recovered"
            self.down_since = None
            return "up"
