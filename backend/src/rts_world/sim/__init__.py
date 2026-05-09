"""Background world simulation.

Layout (see roadmap.txt §7):

    state       -- RegionState / PendingEvent / TickContext (pure data)
    regions     -- load/write region working set, query due regions  (only DB)
    clock       -- read/advance world_clock                          (only DB)
    events      -- bulk-append world_events                          (only DB)
    tick        -- tick_region(region_id) orchestrator (pure middle)
    scheduler   -- heap-based "next due region" loop
    runner      -- CLI entry: `python -m rts_world.sim.runner ...`
    systems/    -- pure functions over RegionState; one file per concern

Invariants:
    * Only regions / clock / events touch psycopg.
    * tick.py and everything under systems/ are pure Python over in-memory state.
    * One BEGIN/COMMIT per region tick. No per-entity transactions.
    * Region loads are wide SELECTs filtered by region_id. Never N+1.
"""
