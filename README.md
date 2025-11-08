# DeDoppelgaenger

**DeDoppelgaenger** is a high-performance image duplicate and similarity finder.  
It identifies *visually identical or near-identical* images using perceptual hashing - even across large photo collections or multiple storage locations.

Unlike traditional tools, DeDoppelgaenger can **precompute hashes on separate machines** and later compare them - avoiding heavy network transfers of the actual image files.

## Features

- Supports both standard image formats (`.jpg`, `.png`, `.tiff`, `.bmp`, etc.) **and RAW formats** (`.nef`, `.cr2`, `.arw`, `.dng`, …).
- Multithreaded hash computation using `ThreadPoolExecutor`.
- **Distributed mode:** precompute hashes on multiple systems, merge them, and compare without moving large image files.
- Adjustable **Hamming distance** threshold for near-duplicate detection.
- JSON-based output for easy integration and automation.
- CLI-friendly, composable, and easy to script.

---

## Installation

```bash
git clone https://github.com/yourusername/DeDoppelgaenger.git
cd DeDoppelgaenger
pip install -r requirements.txt
```


## Usage

### Generate Hashes (locally)

Compute image hashes in one or more folders and save them to a JSON file:

```bash
python dedoppelgaenger.py -r photos/ --only-hash -o hashes.json
```

### Compare Hashes (distributed or local)

Compare a reference set of hashes with another folder or precomputed hash file:

```bash
python dedoppelgaenger.py -r hashes.json images_to_check/ -d 5 -o matches.json
```

**Arguments:**

| Option            | Description                                         |
| ----------------- | --------------------------------------------------- |
| `-r, --reference` | Reference folder(s) or JSON file(s) (repeatable)    |
| `--only-hash`     | Stop after computing hashes and write them to JSON  |
| `-t, --threads`   | Number of threads (default: 4)                      |
| `-d, --distance`  | Maximum Hamming distance (default: 0 = exact match) |
| `-o, --output`    | Optional JSON output file (default: stdout)         |
| `inputs`          | Folders or JSON files to compare against            |


## Example Workflow

Imagine you have two photo collections on different machines:

**Machine A:**

```bash
python dedoppelgaenger.py -r /mnt/drive_a/photos --only-hash -o drive_a_hashes.json
```

**Machine B:**

```bash
python dedoppelgaenger.py -r /mnt/drive_b/photos --only-hash -o drive_b_hashes.json
```

Now, move only the small `.json` files to a central system and compare them:

```bash
python dedoppelgaenger.py -r drive_a_hashes.json drive_b_hashes.json -d 3 -o duplicates.json
```

This avoids transferring gigabytes of images - only hashes.

---

## Output Format

Example JSON (simplified):

```json
{
  "photos/img001.jpg": ["photos/img001_copy.png", "backup/img001.tiff"],
  "photos/holiday1.jpg": ["backup/holiday1_denoised.png"]
}
```

Each key represents a *reference image*; values are *similar matches* within the given Hamming distance.



## Exit Codes

| Code | Meaning               |
| ---- | --------------------- |
| `0`  | Success               |
| `1`  | Error or interruption |

---

## License

MIT License © 2025 Alexander Schieweck 

