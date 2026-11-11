import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import ImportTemplate, StagedFile, User
from ..parsers import MAX_BYTES, SOURCES, ParseError, parse_file
from ..security import audit, current_user
from .settings import company_settings

router = APIRouter(prefix="/api/files", tags=["arquivos"])


def _summary(sf: StagedFile | None, parsed: dict, template: ImportTemplate | None) -> dict:
    recs = parsed["records"]
    return {
        "staged_id": sf.id if sf else None, "source": parsed["source"], "source_label": SOURCES[parsed["source"]],
        "filename": parsed["filename"], "size": parsed["size"], "format": parsed["format"],
        "sha256": parsed["sha256"], "needs_mapping": parsed["needs_mapping"], "missing": parsed.get("missing", []),
        "columns": parsed.get("columns", []), "mapping": parsed.get("mapping", {}),
        "header_row": parsed.get("header_row"), "fields": parsed.get("fields", []),
        "preview": parsed.get("preview", []), "raw_grid_head": parsed.get("raw_grid_head", []),
        "signature": parsed.get("signature"), "warnings": parsed.get("warnings", []), "meta": parsed.get("meta", {}),
        "template": {"id": template.id, "name": template.name} if template else None,
        "records_preview": [{k: v for k, v in r.items() if k != "raw"} for r in recs[:15]],
        "count": len(recs),
    }


@router.post("/parse")
async def parse(source: str = Form(...), file: UploadFile = File(...), mapping: str | None = Form(None),
                header_row: int | None = Form(None), save_template: bool = Form(False),
                template_name: str | None = Form(None), replace_staged_id: int | None = Form(None),
                user: User = Depends(current_user), db: Session = Depends(get_db)):
    if source not in SOURCES:
        raise HTTPException(422, "Origem inválida.")
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Arquivo maior que o limite de 10 MB.")
    settings = company_settings(db, user.company_id)
    name = (file.filename or "arquivo").replace("\\", "/").split("/")[-1][:250]
    mp = None
    if mapping:
        try:
            mp = {k: int(v) for k, v in json.loads(mapping).items() if v not in (None, "", -1)}
        except (ValueError, AttributeError):
            raise HTTPException(422, "Mapeamento de colunas inválido.")
    template = None
    try:
        parsed = parse_file(name, data, source, settings, mp, header_row)
        if mp is None and parsed.get("signature"):
            template = db.scalar(select(ImportTemplate).where(
                ImportTemplate.company_id == user.company_id, ImportTemplate.source == source,
                ImportTemplate.signature == parsed["signature"]))
            if template:
                parsed = parse_file(name, data, source, settings, template.mapping, template.header_row)
    except ParseError as exc:
        audit(db, user, "arquivo_rejeitado", "file", "", source=source, arquivo=name, motivo=str(exc))
        db.commit()
        raise HTTPException(422, str(exc))
    if save_template and mp and parsed.get("signature") and not parsed["needs_mapping"]:
        existing = db.scalar(select(ImportTemplate).where(
            ImportTemplate.company_id == user.company_id, ImportTemplate.source == source,
            ImportTemplate.signature == parsed["signature"]))
        if existing:
            existing.mapping, existing.header_row = mp, parsed["header_row"]
            existing.name = template_name or existing.name
            template = existing
        else:
            template = ImportTemplate(company_id=user.company_id, source=source, signature=parsed["signature"],
                                      name=(template_name or f"Modelo {SOURCES[source]}")[:200],
                                      header_row=parsed["header_row"], mapping=mp)
            db.add(template)
        audit(db, user, "salvar_modelo_importacao", "template", "", source=source, nome=template.name)
    sf = None
    if not parsed["needs_mapping"]:
        if replace_staged_id:
            old = db.get(StagedFile, replace_staged_id)
            if old and old.company_id == user.company_id:
                db.delete(old)
        sf = StagedFile(company_id=user.company_id, user_id=user.id, source=source, filename=name, size=len(data),
                        sha256=parsed["sha256"], format=parsed["format"], meta=parsed["meta"],
                        records=parsed["records"])
        db.add(sf)
        db.flush()
        audit(db, user, "arquivo_validado", "staged_file", sf.id, source=source, arquivo=name,
              registros=len(parsed["records"]), sha256=parsed["sha256"])
    db.commit()
    return _summary(sf, parsed, template)


@router.get("/staged/{sid}")
def staged(sid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    sf = db.get(StagedFile, sid)
    if not sf or sf.company_id != user.company_id:
        raise HTTPException(404, "Arquivo não encontrado ou já processado.")
    return {"id": sf.id, "source": sf.source, "filename": sf.filename, "meta": sf.meta, "count": len(sf.records),
            "records": [{k: v for k, v in r.items() if k != "raw"} for r in sf.records[:500]]}


@router.delete("/staged/{sid}")
def remove(sid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    sf = db.get(StagedFile, sid)
    if sf and sf.company_id == user.company_id:
        db.delete(sf)
        db.commit()
    return {"ok": True}
