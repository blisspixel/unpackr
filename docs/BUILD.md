# Build And Install Modes

## Supported Runtime

- Windows
- Python `3.11+`

## Recommended Install (Editable)

```powershell
pip install -e .
unpackr-doctor
```

This provides console entry points:
- `unpackr`
- `unpackr-doctor`
- `vhealth`

## Batch Wrapper Mode

You can also run via the included wrappers:
- `unpackr.bat`
- `vhealth.bat`

If needed, place wrappers in a directory that is already on your `PATH`.

## Standalone EXE

A first-party EXE release pipeline is not currently maintained.
For historical packaging notes and scripts, see `docs/archive/`.

## Verification

```powershell
unpackr-doctor
unpackr --help
vhealth --help
```
