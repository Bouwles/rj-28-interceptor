"""RJ-28 build entry point.

    blender --background --python blender/build.py -- <target> [options]

Targets:
    testboard   toolkit test board (Phase 0)
    blockout    proportional blockout, both mount states, G1 sheets (Phase 2)
    model       detailed model. Options: only=leg,foot  noctx  sheets  robot  sweep  save
    export      web model and site data (Phase 8). Options: lod0 lod1 edges stations hdri all  check
                (see rj28/export.py for the whole sequence)
    drawings    the five drawing sheets as SVG, PDF and PNG. Options: sheet=1,3  cache  lines  nopng  nopdf
"""
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import bpy  # noqa: E402


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    target = argv[0] if argv else "testboard"
    opts = set(argv[1:])
    t0 = time.time()
    out = HERE / "out"
    out.mkdir(exist_ok=True)

    if target == "testboard":
        from rj28 import testboard
        testboard.build()
        bpy.ops.wm.save_as_mainfile(filepath=str(out / "testboard.blend"))
        if "norender" not in opts:
            testboard.render_all()
    elif target == "blockout":
        from rj28.assemblies import blockout
        blockout.run(opts)
    elif target == "model":
        from rj28 import modelrun
        modelrun.run(opts)
    elif target == "drawings":
        from rj28 import drawings
        drawings.run(opts)
    elif target == "export":
        from rj28 import export
        export.run(opts)
    else:
        raise SystemExit(f"unknown target {target!r}")
    print(f"BUILD {target} done in {time.time() - t0:.1f} s")


main()
