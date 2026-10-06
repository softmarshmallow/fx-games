"""Every test talks to the FX engine offline, with this interpreter as its node host.

A scratch copy of a game project has no ``.venv``, so the engine is told which Python runs
node bodies; no test reads a ``.env``, and none reaches the network.
"""

import os
import sys

os.environ.setdefault("GRIDA_FX_PYTHON", sys.executable)
os.environ["GRIDA_FX_DISABLE_DOTENV"] = "1"
os.environ["GRIDA_FX_NETWORK"] = "off"
