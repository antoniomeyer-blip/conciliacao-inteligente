from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..defaults import DEFAULT_SETTINGS, merged_settings
from ..models import AuditLog, Company, ImportTemplate, User
from ..security import audit, current_user, require_admin

router = APIRouter(prefix="/api", tags=["configuracoes"])


def company_settings(db: Session, company_id: int) -> dict:
    c = db.get(Company, company_id)
    return merged_settings(c.settings if c else {})


def _validate(s: dict):
    for k in ("tolerancia_valor_centavos", "tolerancia_dias", "tolerancia_taxa_centavos", "max_itens_agrupamento"):
        v = s.get(k)
        if not isinstance(v, int) or v < 0 or v > 100000:
            raise HTTPException(422, f"Valor inválido para '{k}'.")
    if s["tolerancia_dias"] > 60:
        raise HTTPException(422, "Tolerância de dias deve ser no máximo 60.")
    if s["max_itens_agrupamento"] > 60:
        raise HTTPException(422, "Máximo de itens por agrupamento deve ser no máximo 60.")
    try:
        if not 0 <= float(s["divergencia_valor_max_percentual"]) <= 50:
            raise ValueError
        for t in s.get("taxas", []):
            if not 0 <= float(t["taxa"]) <= 30:
                raise ValueError
            if t.get("modalidade") not in ("debito", "credito", "voucher", "pix", "prepago"):
                raise ValueError
    except (ValueError, KeyError, TypeError):
        raise HTTPException(422, "Revise percentuais e taxas: valores fora do intervalo permitido.")


@router.get("/settings")
def get_settings(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return {"settings": company_settings(db, user.company_id), "defaults": DEFAULT_SETTINGS}


@router.put("/settings")
def put_settings(body: dict, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    new = merged_settings({k: v for k, v in body.items() if k in DEFAULT_SETTINGS})
    _validate(new)
    c = db.get(Company, admin.company_id)
    old = c.settings or {}
    c.settings = new
    audit(db, admin, "alterar_configuracoes", "company", c.id,
          alteradas=[k for k in new if old.get(k) != new[k]])
    db.commit()
    return {"settings": new}


@router.get("/templates")
def list_templates(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(ImportTemplate).where(ImportTemplate.company_id == user.company_id)
                      .order_by(ImportTemplate.source, ImportTemplate.name)).all()
    return [{"id": t.id, "source": t.source, "name": t.name, "signature": t.signature, "header_row": t.header_row,
             "mapping": t.mapping, "created_at": t.created_at.isoformat()} for t in rows]


@router.delete("/templates/{tid}")
def delete_template(tid: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    t = db.get(ImportTemplate, tid)
    if not t or t.company_id != admin.company_id:
        raise HTTPException(404, "Modelo não encontrado.")
    db.delete(t)
    audit(db, admin, "excluir_modelo_importacao", "template", tid)
    db.commit()
    return {"ok": True}


@router.get("/audit")
def audit_log(limit: int = 200, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.scalars(select(AuditLog).where(AuditLog.company_id == admin.company_id)
                      .order_by(AuditLog.id.desc()).limit(min(limit, 1000))).all()
    names = {u.id: u.name for u in db.scalars(select(User).where(User.company_id == admin.company_id))}
    return [{"id": r.id, "action": r.action, "entity": r.entity, "entity_id": r.entity_id, "details": r.details,
             "user": names.get(r.user_id, "-"), "created_at": r.created_at.isoformat()} for r in rows]
