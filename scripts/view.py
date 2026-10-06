"""The viewer over FX run folders; it only reads.

    uv run python scripts/view.py [runs ...] [--port N] [--no-open]

Without a folder it shows the ``runs`` folder of the nearest ``fx.yaml`` (``out/runs`` here).
It keeps each run's view fresh in the user cache while it serves them (docs/viewer.md).
"""

from stage_gen.viewer import main

raise SystemExit(main())
