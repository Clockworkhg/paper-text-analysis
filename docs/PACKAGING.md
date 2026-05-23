# Packaging

This project has two supported run modes:

- Development mode: run from source with `python research_tool.py ...` or an
  editable install that exposes `cads` and `cads-gui`.
- Release mode: build standalone executables with PyInstaller via
  `build_exe.py`.

## Development Install

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m spacy download en_core_web_sm
cads --help
cads-gui
```

OCR and online features are optional:

```powershell
python -m pip install -e ".[ocr,online]"
```

## Standalone Executables

Install the build extra:

```powershell
python -m pip install -e ".[build]"
```

Preview PyInstaller commands without building:

```powershell
python build_exe.py --dry-run
python build_exe.py --cli --dry-run
python build_exe.py --gui --debug-console --dry-run
```

Build release artifacts:

```powershell
python build_exe.py --clean
python build_exe.py --cli
python build_exe.py --gui
```

Use `--onedir` if one-file startup is slow or antivirus scanning is a problem:

```powershell
python build_exe.py --gui --onedir
```

Use `--debug-console` when diagnosing GUI startup failures:

```powershell
python build_exe.py --gui --debug-console
```

## Release Checklist

1. Run `python research_tool.py test`.
2. Run `python build_exe.py --dry-run` and check that paths point at this repo.
3. Build the needed artifacts.
4. Smoke-test `dist/cads` with `--help`.
5. Smoke-test `dist/cads-gui` by launching the app.

Generated `.spec`, `build/`, and `dist/` files are local artifacts. Keep
PyInstaller configuration in `build_exe.py`.
