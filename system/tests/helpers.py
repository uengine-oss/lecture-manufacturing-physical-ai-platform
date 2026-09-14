from hydops.b3_tsdb import store


def tick_until_event(rt, event_type=None, asset_id="HYD-01", max_s=200):
    for i in range(max_s):
        for ev in rt.tick(1):
            if ev["asset_id"] == asset_id and (event_type is None or ev["event_type"] == event_type):
                return ev
    return None


def run_until_settled(rt, orc, event_id, max_s=200):
    for _ in range(max_s):
        rt.tick(1)
        orc.poll()
        st = store.get_event(event_id)["status"]
        if st in ("CLOSED", "ESCALATED", "REJECTED") or (st == "VERIFY_HOLD" and not orc.snapshot(event_id)["interrupts"]):
            return st
    return store.get_event(event_id)["status"]
