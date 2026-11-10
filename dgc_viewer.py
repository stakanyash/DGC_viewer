import sys
import os
import json
import struct
import zlib
import base64
import math

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTextEdit, QLabel, QFileDialog, QMessageBox,
    QSplitter, QCheckBox
)
from PyQt6.QtGui import QFont, QFontDatabase, QImage, QPixmap
from PyQt6.QtCore import Qt


MAGIC = b"DGCB"
FORMAT_VERSION = 1
FLAG_HAS_ORIGINAL_RANGE = 0x01
FLAG_HAS_ORIGINAL_VALUES = 0x02


def _read_exact(f, n):
    buf = f.read(n)
    if len(buf) != n:
        raise ValueError(f"Unexpected EOF: wanted {n} bytes, got {len(buf)}")
    return buf


def parse_metadata(path):
    with open(path, "rb") as f:
        head = f.read(4)
    if head == MAGIC:
        return _parse_dgc(path)
    return _parse_json(path)


def _parse_dgc(path):
    with open(path, "rb") as f:
        magic = _read_exact(f, 4)
        if magic != MAGIC:
            raise ValueError("Bad magic")

        fmt_ver, flags = struct.unpack("<HH", _read_exact(f, 4))
        if fmt_ver != FORMAT_VERSION:
            raise ValueError(f"Unsupported format version: {fmt_ver}")

        mn, mx, dl, omn, omx, odl = struct.unpack("<6d", _read_exact(f, 48))

        dgcver_len, = struct.unpack("<H", _read_exact(f, 2))
        dgcver_bytes = _read_exact(f, dgcver_len) if dgcver_len else b""
        dgcver = dgcver_bytes.decode("utf-8", errors="replace") if dgcver_bytes else ""

        ov_len, = struct.unpack("<I", _read_exact(f, 4))
        ov_bytes = _read_exact(f, ov_len) if ov_len else b""

    result = {
        "_format": "DGC",
        "_format_version": fmt_ver,
        "_flags": flags,
        "_file_size": os.path.getsize(path),
        "Min": mn,
        "Max": mx,
        "Delta": dl,
    }
    if dgcver:
        result["DGCVer"] = dgcver
    if flags & FLAG_HAS_ORIGINAL_RANGE:
        result["OriginalMin"] = omn
        result["OriginalMax"] = omx
        result["OriginalDelta"] = odl
    if flags & FLAG_HAS_ORIGINAL_VALUES:
        result["_original_values_compressed_len"] = len(ov_bytes)
        try:
            packed = zlib.decompress(ov_bytes)
            if len(packed) % 4 != 0:
                result["_original_values_error"] = (
                    f"decompressed size {len(packed)} is not multiple of 4"
                )
            else:
                count = len(packed) // 4
                result["OriginalValues"] = list(struct.unpack(f"{count}f", packed))
        except zlib.error as e:
            result["_original_values_error"] = f"zlib decompress failed: {e}"
    return result


def _parse_json(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    result = dict(data)
    result["_format"] = "legacy JSON"
    result["_file_size"] = os.path.getsize(path)
    ov = result.get("OriginalValues")
    if isinstance(ov, str):
        try:
            compressed = base64.b64decode(ov)
            packed = zlib.decompress(compressed)
            if len(packed) % 4 != 0:
                result["_original_values_error"] = (
                    f"decompressed size {len(packed)} is not multiple of 4"
                )
            else:
                count = len(packed) // 4
                result["OriginalValues"] = list(struct.unpack(f"{count}f", packed))
        except Exception as e:
            result["_original_values_error"] = str(e)
    return result


def make_heightmap_image(values):
    count = len(values)
    if count == 0:
        return None, None
    size = int(round(math.sqrt(count)))
    if size * size != count:
        return None, None

    mn = min(values)
    mx = max(values)
    delta = mx - mn if mx != mn else 1.0

    pixels = bytearray(size * size)
    for i, v in enumerate(values):
        norm = int(round((v - mn) / delta * 255))
        pixels[i] = max(0, min(255, norm))

    image = QImage(bytes(pixels), size, size, size, QImage.Format.Format_Grayscale8)
    return image, size


def format_dump(meta):
    lines = []
    lines.append(f"Format: {meta.get('_format', 'unknown')}")
    if "_format_version" in meta:
        lines.append(f"Format version: {meta['_format_version']}")
        lines.append(f"Flags: 0x{meta['_flags']:04x}")
    if "_file_size" in meta:
        lines.append(f"File size: {meta['_file_size']} bytes")
    if "DGCVer" in meta:
        lines.append(f"DGCVer: {meta['DGCVer']}")
    lines.append("")
    lines.append(f"Min:   {meta.get('Min')}")
    lines.append(f"Max:   {meta.get('Max')}")
    lines.append(f"Delta: {meta.get('Delta')}")
    lines.append("")
    if "OriginalMin" in meta:
        lines.append("Original range:")
        lines.append(f"  OriginalMin:   {meta['OriginalMin']}")
        lines.append(f"  OriginalMax:   {meta['OriginalMax']}")
        lines.append(f"  OriginalDelta: {meta['OriginalDelta']}")
        lines.append("")
    ov = meta.get("OriginalValues")
    if ov:
        lines.append(f"OriginalValues: {len(ov)} floats")
        if "_original_values_compressed_len" in meta:
            lines.append(f"  compressed size: {meta['_original_values_compressed_len']} bytes")
        lines.append(f"  decompressed:    {len(ov) * 4} bytes")
        lines.append(f"  min: {min(ov)}")
        lines.append(f"  max: {max(ov)}")
        root = int(round(math.sqrt(len(ov))))
        if root * root == len(ov):
            lines.append(f"  map size:        {root}x{root}")
        head = ov[:10]
        tail = ov[-10:] if len(ov) > 10 else []
        lines.append(f"  first {len(head)}: {head}")
        if tail:
            lines.append(f"  last {len(tail)}: {tail}")
    elif "_original_values_error" in meta:
        lines.append(f"OriginalValues: ERROR - {meta['_original_values_error']}")
    else:
        lines.append("OriginalValues: absent")
    return "\n".join(lines)


class DgcViewer(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DGC Metadata Viewer")
        self.resize(900, 720)
        self.setAcceptDrops(True)

        self._meta = None
        self._path = None
        self._image = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        bar = QHBoxLayout()
        bar.setSpacing(8)

        self.open_btn = QPushButton("Open...")
        self.open_btn.clicked.connect(self.open_file)
        bar.addWidget(self.open_btn)

        self.export_raw_btn = QPushButton("Export RAW")
        self.export_raw_btn.clicked.connect(self.export_raw)
        self.export_raw_btn.setEnabled(False)
        bar.addWidget(self.export_raw_btn)

        self.export_csv_btn = QPushButton("Export CSV")
        self.export_csv_btn.clicked.connect(self.export_csv)
        self.export_csv_btn.setEnabled(False)
        bar.addWidget(self.export_csv_btn)

        self.export_png_btn = QPushButton("Export PNG")
        self.export_png_btn.clicked.connect(self.export_png)
        self.export_png_btn.setEnabled(False)
        bar.addWidget(self.export_png_btn)

        bar.addStretch()

        self.show_image_cb = QCheckBox("Show heightmap")
        self.show_image_cb.setChecked(False)
        self.show_image_cb.setEnabled(False)
        self.show_image_cb.stateChanged.connect(self._on_show_image_toggled)
        bar.addWidget(self.show_image_cb)

        layout.addLayout(bar)

        self.path_label = QLabel("No file loaded")
        self.path_label.setStyleSheet("color: #888;")
        self.path_label.setWordWrap(True)
        layout.addWidget(self.path_label)

        self.splitter = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(self.splitter, 1)

        self.text = QTextEdit()
        self.text.setReadOnly(True)
        mono = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        mono.setPointSize(10)
        self.text.setFont(mono)
        self.splitter.addWidget(self.text)

        self.image_panel = QWidget()
        image_layout = QVBoxLayout(self.image_panel)
        image_layout.setContentsMargins(0, 0, 0, 0)
        image_layout.setSpacing(4)

        self.image_label = QLabel("No heightmap loaded")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("background: #1a1a1a; color: #888;")
        self.image_label.setMinimumHeight(260)
        image_layout.addWidget(self.image_label, 1)

        self.splitter.addWidget(self.image_panel)
        self.image_panel.setVisible(False)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path and os.path.isfile(path):
                self.load_file(path)
                break

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open metadata file",
            "",
            "Metadata (*.dgc *.json);;DGC (*.dgc);;Legacy JSON (*.json);;All files (*)",
        )
        if path:
            self.load_file(path)

    def load_file(self, path):
        try:
            meta = parse_metadata(path)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to parse file:\n{e}")
            return

        self._meta = meta
        self._path = path
        self._image = None
        self.path_label.setText(path)
        self.text.setPlainText(format_dump(meta))

        has_ov = bool(meta.get("OriginalValues"))
        self.export_raw_btn.setEnabled(has_ov)
        self.export_csv_btn.setEnabled(has_ov)

        self.show_image_cb.blockSignals(True)
        self.show_image_cb.setChecked(False)
        self.show_image_cb.blockSignals(False)
        self.image_panel.setVisible(False)

        self._prepare_image(meta)

    def _prepare_image(self, meta):
        ov = meta.get("OriginalValues")
        if not ov:
            self.export_png_btn.setEnabled(False)
            self.show_image_cb.setEnabled(False)
            self.image_label.setPixmap(QPixmap())
            self.image_label.setText("No OriginalValues in this file")
            return

        image, size = make_heightmap_image(ov)
        if image is None:
            self.export_png_btn.setEnabled(False)
            self.show_image_cb.setEnabled(False)
            self.image_label.setPixmap(QPixmap())
            self.image_label.setText(
                f"Cannot render: {len(ov)} values is not a perfect square"
            )
            return

        self._image = image
        self.export_png_btn.setEnabled(True)
        self.show_image_cb.setEnabled(True)

    def _on_show_image_toggled(self):
        if self.show_image_cb.isChecked():
            if self._image is not None:
                self.image_panel.setVisible(True)
                self._update_image_display()
        else:
            self.image_panel.setVisible(False)

    def _update_image_display(self):
        if self._image is None or not self.image_panel.isVisible():
            return
        target = self.image_label.size()
        if target.width() < 32 or target.height() < 32:
            target = self.image_label.sizeHint()
        pix = QPixmap.fromImage(self._image).scaled(
            target,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.image_label.setPixmap(pix)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_image_display()

    def export_raw(self):
        if not self._meta or not self._meta.get("OriginalValues"):
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export OriginalValues as RAW",
            "",
            "Raw float32 (*.raw);;All files (*)",
        )
        if not path:
            return
        vals = self._meta["OriginalValues"]
        try:
            with open(path, "wb") as f:
                f.write(struct.pack(f"{len(vals)}f", *vals))
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Export failed:\n{e}")
            return
        QMessageBox.information(self, "Done", f"Exported {len(vals)} floats to:\n{path}")

    def export_csv(self):
        if not self._meta or not self._meta.get("OriginalValues"):
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export OriginalValues as CSV",
            "",
            "CSV (*.csv);;All files (*)",
        )
        if not path:
            return
        vals = self._meta["OriginalValues"]
        try:
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write("index,value\n")
                for i, v in enumerate(vals):
                    f.write(f"{i},{v}\n")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Export failed:\n{e}")
            return
        QMessageBox.information(self, "Done", f"Exported {len(vals)} rows to:\n{path}")

    def export_png(self):
        if self._image is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export heightmap as PNG",
            "",
            "PNG (*.png);;All files (*)",
        )
        if not path:
            return
        try:
            if not self._image.save(path, "PNG"):
                raise ValueError("QImage.save returned False")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Export failed:\n{e}")
            return
        QMessageBox.information(self, "Done", f"Heightmap saved to:\n{path}")


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("DGC Viewer")
    viewer = DgcViewer()
    viewer.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()