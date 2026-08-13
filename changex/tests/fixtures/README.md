# Listing photo test fixtures

Real binary fixtures for GÖREV 02 upload validation:

| File | Purpose |
|------|---------|
| `sample.png` | Valid 1×1 PNG |
| `sample2.png` | Second valid PNG (multi-photo) |
| `sample.jpg` | Valid minimal JPEG |
| `corrupt.png` | PNG magic header without IEND (rejected) |
| `not_image.txt` | Plain text (rejected) |
| `too_large.bin` | ~5 MiB non-image blob |
