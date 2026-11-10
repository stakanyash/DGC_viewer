# DGC Viewer

**DGC Viewer** is a lightweight GUI utility (built on PyQt6) for viewing and exporting map metadata created by the [DisplaceBox](https://github.com/stakanyash/displacebin_gui_converter) application.

The tool is designed for map developers and modders who need to look "under the hood" of the metadata, verify original height values, or export them for further editing in third-party software.



## Features

*   **Format support:** Reads the new binary `.dgc` format as well as the legacy text-based `.json` format.
*   **Detailed dump:** Displays the file header, generator version (`DGCVer`), flags, height ranges (`Min`, `Max`, `Delta`), and the original range (`OriginalMin/Max/Delta`).
*   **OriginalValues analysis:** Shows the number of points, compressed and decompressed data size, as well as the first and last values of the array.
*   **Visualization:** Allows enabling a grayscale heightmap preview (provided the number of points forms a perfect square).
*   **Data export:**
    *   **RAW (float32)** — export of original heights in raw format (convenient for importing into other editors).
    *   **CSV** — export of values in `index,value` format (convenient for analysis in Excel or Python).
    *   **PNG** — saving the heightmap visualization as an image.
*   **Convenience:** Drag & Drop support (drag a file directly into the application window).

## Installation and Running

Running the tool requires **Python 3.11** or newer, as well as [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/stakanyash/DGC_viewer.git
cd DGC_viewer
uv run dgc_viewer.py
```

## What are .dgc files?

`.dgc` (DisplaceBox Metadata) files are replacing the old `.json` metadata. It is a compact binary format that stores the original map heights as a compressed `float32` array (zlib). This significantly reduces file size and speeds up reading during reverse conversion to `.bin`.

Despite the binary format, DGC Viewer makes it easy to look inside and verify data integrity.

## License

This project is distributed under the MIT License.
