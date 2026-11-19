"""Disposable ARU-70 decoder comparison; never changes a user project.

Use the isolated map-preflight-venv. Qt mode accepts --qt-site for the existing
locked Qt environment. Run each mode in a fresh process to compare peak RSS.
"""
import argparse
import json
import os
import sys
import threading
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["generate", "vips", "qt", "smoke", "compat"])
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--qt-site")
    parser.add_argument("--edge", type=int, default=10000)
    parser.add_argument("--qt-allocation-mib", type=int, default=256)
    args = parser.parse_args()
    os.environ.setdefault("VIPS_CONCURRENCY", "2")
    import psutil
    process = psutil.Process()
    peak = [process.memory_info().rss]
    stop = threading.Event()
    def monitor():
        while not stop.wait(.01):
            peak[0] = max(peak[0], process.memory_info().rss)
    thread = threading.Thread(target=monitor)
    thread.start()
    start = time.perf_counter()
    details = {}
    try:
        if args.mode == "qt":
            if args.qt_site:
                sys.path.insert(0, args.qt_site)
            from PySide6.QtCore import QRect
            from PySide6.QtGui import QGuiApplication, QImageIOHandler, QImageReader
            app = QGuiApplication([])
            reader = QImageReader(str(args.source))
            reader.setAllocationLimit(args.qt_allocation_mib)
            details["clip_supported"] = reader.supportsOption(QImageIOHandler.ImageOption.ClipRect)
            reader.setClipRect(QRect(0, 0, 256, 256))
            image = reader.read()
            details.update(width=image.width(), height=image.height(), error=reader.errorString())
            del app
        else:
            if args.mode == "compat":
                if args.qt_site:
                    sys.path.insert(0, args.qt_site)
                from PySide6.QtWidgets import QApplication, QWidget
                from PySide6QtAds import CDockManager
                app = QApplication([])
                shell = QWidget()
                manager = CDockManager(shell)
                details["qt_ads_created"] = manager is not None
            import pyvips
            pyvips.cache_set_max_mem(32 * 1024**2)
            pyvips.cache_set_max(100)
            pyvips.cache_set_max_files(16)
            details["vips"] = ".".join(str(pyvips.version(i)) for i in range(3))
            if args.mode == "generate":
                xy = pyvips.Image.xyz(args.edge, args.edge)
                image = (xy[0] % 256).bandjoin([(xy[1] % 256), (xy[0] + xy[1]) % 256])
                image.cast("uchar").write_to_file(str(args.source))
            elif args.mode in {"smoke", "compat"}:
                image = pyvips.Image.black(1100, 700, bands=3) + [60, 110, 180]
                image.cast("uchar").dzsave(str(args.source), tile_size=256, overlap=0,
                                          suffix=".png", keep="none")
                assert args.source.with_suffix(".dzi").is_file()
                if args.mode == "compat":
                    from PySide6.QtGui import QImage
                    tile = args.source.parent / (args.source.name + "_files/11/0_0.png")
                    decoded = QImage(str(tile))
                    assert decoded.width() == 256 and decoded.pixelColor(0, 0).red() == 60
                    details["qt_decoded_tile"] = True
            else:
                image = pyvips.Image.new_from_file(str(args.source), access="sequential",
                                                  fail_on="warning")
                details.update(width=image.width, height=image.height, bands=image.bands)
                image.dzsave(str(args.output), tile_size=256, overlap=0,
                             suffix=".png", keep="none")
    finally:
        stop.set()
        thread.join()
        peak[0] = max(peak[0], process.memory_info().rss)
    details.update(mode=args.mode, elapsed_s=round(time.perf_counter() - start, 3),
                   peak_rss_mib=round(peak[0] / 1024**2, 2))
    print(json.dumps(details), flush=True)


if __name__ == "__main__":
    main()
