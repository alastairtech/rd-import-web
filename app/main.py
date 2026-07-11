from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from . import db, importer
from .config import IMPORT_ROOT
from .rdconf import RdConfError, load_db_creds

app = FastAPI(title="Rivendell Import")

BASE_DIR = Path(__file__).parent
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        request, "index.html", {"import_root": str(IMPORT_ROOT)}
    )


@app.get("/api/groups")
def api_groups():
    try:
        creds = load_db_creds()
        groups = db.list_groups(creds)
    except RdConfError as e:
        raise HTTPException(status_code=500, detail=f"rd.conf error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

    return [
        {
            "name": g.name,
            "description": g.description,
            "low_cart": g.low_cart,
            "high_cart": g.high_cart,
        }
        for g in groups
    ]


@app.get("/api/scheduler-codes")
def api_scheduler_codes():
    try:
        creds = load_db_creds()
        codes = db.list_scheduler_codes(creds)
    except RdConfError as e:
        raise HTTPException(status_code=500, detail=f"rd.conf error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

    return [{"code": c.code, "description": c.description} for c in codes]


@app.post("/api/upload")
async def api_upload(files: List[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="No files were uploaded")

    pairs = []
    for f in files:
        data = await f.read()
        pairs.append((f.filename or "", data))

    try:
        staging_rel, saved_rel_paths = importer.save_uploaded_files(pairs)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"staging_dir": staging_rel, "paths": saved_rel_paths}


@app.get("/api/cart-check")
def api_cart_check(number: int):
    try:
        creds = load_db_creds()
        existing_group = db.cart_exists(creds, number)
    except RdConfError as e:
        raise HTTPException(status_code=500, detail=f"rd.conf error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

    return {"exists": existing_group is not None, "group": existing_group}


@app.get("/api/browse")
def api_browse(path: str = ""):
    try:
        entries = importer.browse(path)
    except importer.PathSecurityError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except (FileNotFoundError, NotADirectoryError) as e:
        raise HTTPException(status_code=404, detail=str(e))

    return {
        "path": path,
        "entries": [
            {"name": e.name, "is_dir": e.is_dir, "rel_path": e.rel_path} for e in entries
        ],
    }


class ImportRequest(BaseModel):
    group: str
    paths: List[str]
    recursive: bool = False
    cart_mode: str = "auto"  # "auto" or "manual"
    cart_number: Optional[int] = None
    existing_cart_action: Optional[str] = None  # "add_cut" or "delete_cuts", only used if the cart already exists
    delete_source: bool = False
    scheduler_codes: List[str] = []
    normalization_level: Optional[int] = None
    autotrim_level: Optional[int] = None
    segue_level: Optional[int] = None
    fix_broken_formats: bool = False
    startdate_offset: Optional[int] = None
    enddate_offset: Optional[int] = None


@app.post("/api/import")
def api_import(req: ImportRequest):
    if not req.paths:
        raise HTTPException(status_code=400, detail="No files or folder selected")

    delete_cuts = False

    if req.cart_mode == "manual":
        if not req.cart_number or req.cart_number <= 0:
            raise HTTPException(status_code=400, detail="Manual mode requires a cart number > 0")
        try:
            creds = load_db_creds()
            existing_group = db.cart_exists(creds, req.cart_number)
        except RdConfError as e:
            raise HTTPException(status_code=500, detail=f"rd.conf error: {e}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Database error: {e}")

        if existing_group is not None:
            if req.existing_cart_action == "delete_cuts":
                delete_cuts = True
            elif req.existing_cart_action == "add_cut":
                delete_cuts = False
            else:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Cart {req.cart_number} already exists in group '{existing_group}'. "
                        "Choose whether to add this as a new cut or delete the existing "
                        "cuts first, then try again."
                    ),
                )
        cart_number = req.cart_number
    else:
        cart_number = 0

    try:
        files = importer.collect_audio_files(req.paths, req.recursive)
    except importer.PathSecurityError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    if cart_number != 0 and len(files) > 1:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Manual cart number given but {len(files)} files were selected. "
                "Manual cart numbers only apply to a single-file import."
            ),
        )

    result = importer.run_rdimport(
        group=req.group,
        files=files,
        cart_number=cart_number,
        delete_source=req.delete_source,
        delete_cuts=delete_cuts,
        scheduler_codes=req.scheduler_codes,
        normalization_level=req.normalization_level,
        autotrim_level=req.autotrim_level,
        segue_level=req.segue_level,
        fix_broken_formats=req.fix_broken_formats,
        startdate_offset=req.startdate_offset,
        enddate_offset=req.enddate_offset,
    )

    # rdimport can exit 0 while still having silently skipped files it
    # couldn't open, so treat that as a failure too, not just relying on
    # a nonzero exit code.
    success = result.returncode == 0 and result.skipped_count == 0

    # Any files that came from the web upload picker live in a transient
    # staging dir under _uploads/. Only clean those up once rdimport has
    # actually succeeded with them — on failure we leave them in place so
    # the person can retry (e.g. after fixing a group/cart issue) without
    # needing to re-pick and re-upload the same file.
    if success:
        staging_dirs = {
            f"{importer.UPLOAD_SUBDIR}/{p.split('/')[1]}"
            for p in req.paths
            if p.startswith(f"{importer.UPLOAD_SUBDIR}/")
        }
        for staging_dir in staging_dirs:
            importer.cleanup_staging_dir(staging_dir)

    return {
        "command": " ".join(result.command),
        "files_imported": [str(f) for f in files],
        "returncode": result.returncode,
        "skipped_count": result.skipped_count,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "success": success,
    }
