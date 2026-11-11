import hashlib
import time
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..engine import LEVEL_LABELS, SOURCE_LABELS, STATUS_LABELS, reconcile, summarize
from ..models import Match, Reconciliation, StagedFile, Transaction, User
from ..reports import exporters
from ..security import audit, current_user
from .settings import company_settings

router = APIRouter(prefix="/api", tags=["conciliacoes"])


class ProcessIn(BaseModel):
    files: dict[str, int]
    force: bool = False


class DecisionIn(BaseModel):
    decision: str  # aprovar | rejeitar
    note: str = ""


class NoteIn(BaseModel):
    note: str


def _own(db: Session, rid: int, user: User) -> Reconciliation:
    r = db.get(Reconciliation, rid)
    if not r or r.company_id != user.company_id:
        raise HTTPException(404, "Conciliação não encontrada.")
    return r


def _num(v):
    return str(Decimal(str(v)).quantize(Decimal("0.01"))) if v is not None else None


def tx_dict(t: Transaction) -> dict:
    return {"id": t.id, "uid": t.uid, "source": t.source, "row": t.row, "date": t.date, "settle_date": t.settle_date,
            "identifier": t.identifier, "description": t.description, "counterparty": t.counterparty,
            "amount": _num(t.amount), "found_amount": _num(t.found_amount), "difference": _num(t.difference),
            "gross": _num(t.gross), "fee": _num(t.fee), "kind": t.kind, "brand": t.brand, "modality": t.modality,
            "status": t.status, "status_label": STATUS_LABELS.get(t.status, t.status),
            "justification": t.justification, "level": t.level, "confidence": t.confidence,
            "match_ids": t.match_ids, "note": t.note}


def match_dict(m: Match) -> dict:
    return {"id": m.id, "code": m.code, "level": m.level, "level_label": LEVEL_LABELS.get(m.level), "rule": m.rule,
            "confidence": m.confidence, "state": m.state, "status": m.status,
            "status_label": STATUS_LABELS.get(m.status), "left": m.left, "right": m.right,
            "left_total": _num(m.left_total), "right_total": _num(m.right_total), "difference": _num(m.difference),
            "justification": m.justification, "note": m.note,
            "decided_at": m.decided_at.isoformat() if m.decided_at else None}


def rec_dict(r: Reconciliation) -> dict:
    return {"id": r.id, "code": r.code, "version": r.version, "parent_id": r.parent_id, "group_key": r.group_key,
            "period_start": r.period_start, "period_end": r.period_end, "files": r.files, "totals": r.totals,
            "status": r.status, "duration_ms": r.duration_ms, "created_at": r.created_at.isoformat(),
            "user": r.user.name if r.user else "-", "settings_snapshot": r.settings_snapshot}


def _run_and_store(db: Session, user: User, records: dict, files_info: list, group_key: str,
                   period, parent: Reconciliation | None) -> Reconciliation:
    settings = company_settings(db, user.company_id)
    t0 = time.perf_counter()
    result = reconcile(records, settings, period)
    duration = int((time.perf_counter() - t0) * 1000)
    version = 1 + (db.scalar(select(func.max(Reconciliation.version)).where(
        Reconciliation.company_id == user.company_id, Reconciliation.group_key == group_key)) or 0)
    p = result["period"] or [None, None]
    rec = Reconciliation(company_id=user.company_id, user_id=user.id, code="", group_key=group_key, version=version,
                         parent_id=parent.id if parent else None, period_start=p[0], period_end=p[1],
                         files=files_info, settings_snapshot=settings, duration_ms=duration)
    db.add(rec)
    db.flush()
    rec.code = f"CI-{datetime.now().strftime('%Y%m%d')}-{rec.id:05d}"
    code_map = {}
    for m in result["matches"]:
        code_map[m["id"]] = m["id"]
        db.add(Match(reconciliation_id=rec.id, code=m["id"], level=m["level"], rule=m["rule"],
                     confidence=m["confidence"], state=m["state"], status=m["status"], left=m["left"],
                     right=m["right"], left_total=m["left_total"], right_total=m["right_total"],
                     difference=m["difference"], justification=m["justification"]))
    for t in result["transactions"]:
        db.add(Transaction(
            reconciliation_id=rec.id, uid=t["uid"], source=t["source"], row=t["row"], date=t["date"],
            settle_date=t["settle_date"], identifier=(t["identifier"] or "")[:120], description=t["description"] or "",
            counterparty=(t["counterparty"] or "")[:300], amount=t["amount"], found_amount=t["found_amount"],
            difference=t["difference"], gross=t["gross"], fee=t["fee"], kind=t["kind"], brand=t["brand"],
            modality=t["modality"], status=t["status"], justification=t["justification"],
            unmatched_status=t["unmatched_status"], unmatched_justification=t["unmatched_justification"],
            level=t["level"], confidence=t["confidence"], match_ids=t["match_ids"], data=t["data"]))
    rec.totals = summarize(result["transactions"], result["matches"])
    return rec


@router.post("/reconciliations")
def process(body: ProcessIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    files = {k: v for k, v in body.files.items() if v}
    if "bank" not in files:
        raise HTTPException(422, "O extrato bancário é obrigatório para conciliar.")
    if len(files) < 2:
        raise HTTPException(422, "Envie o extrato bancário e pelo menos mais um arquivo (ERP, máquina ou adquirente).")
    staged = {}
    for source, sid in files.items():
        sf = db.get(StagedFile, sid)
        if not sf or sf.company_id != user.company_id or sf.source != source:
            raise HTTPException(404, f"Arquivo de '{SOURCE_LABELS.get(source, source)}' não encontrado. Envie novamente.")
        staged[source] = sf
    group_key = hashlib.sha256("|".join(f"{s}:{staged[s].sha256}" for s in sorted(staged)).encode()).hexdigest()
    existing = db.scalars(select(Reconciliation).where(
        Reconciliation.company_id == user.company_id, Reconciliation.group_key == group_key)
        .order_by(Reconciliation.version.desc())).first()
    if existing and not body.force:
        raise HTTPException(409, {"message": "Estes mesmos arquivos já foram processados. Deseja criar uma nova versão?",
                                  "existing": {"id": existing.id, "code": existing.code, "version": existing.version,
                                               "created_at": existing.created_at.isoformat()}})
    period = None
    bm = staged["bank"].meta or {}
    if bm.get("periodo_inicio") and bm.get("periodo_fim"):
        period = (date.fromisoformat(bm["periodo_inicio"]), date.fromisoformat(bm["periodo_fim"]))
    records = {s: sf.records for s, sf in staged.items()}
    files_info = [{"source": s, "filename": sf.filename, "sha256": sf.sha256, "size": sf.size, "format": sf.format,
                   "registros": len(sf.records), "meta": sf.meta} for s, sf in staged.items()]
    rec = _run_and_store(db, user, records, files_info, group_key, period, existing)
    for sf in staged.values():  # não manter dados de arquivos além do necessário
        db.delete(sf)
    audit(db, user, "processar_conciliacao", "reconciliation", rec.id, codigo=rec.code, versao=rec.version,
          arquivos=[f["filename"] for f in files_info], tempo_ms=rec.duration_ms,
          percentual=rec.totals.get("percentual_conciliacao"))
    db.commit()
    return rec_dict(rec)


@router.post("/reconciliations/{rid}/reprocess")
def reprocess(rid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    old = _own(db, rid, user)
    txs = db.scalars(select(Transaction).where(Transaction.reconciliation_id == old.id).order_by(Transaction.id)).all()
    records: dict[str, list] = {}
    for t in sorted(txs, key=lambda x: (x.source, int(x.uid.split(":")[1]))):
        records.setdefault(t.source, []).append(t.data)
    period = (date.fromisoformat(old.period_start), date.fromisoformat(old.period_end)) \
        if old.period_start and old.period_end else None
    bank_meta = next((f.get("meta", {}) for f in old.files if f["source"] == "bank"), {})
    if bank_meta.get("periodo_inicio"):
        period = (date.fromisoformat(bank_meta["periodo_inicio"]), date.fromisoformat(bank_meta["periodo_fim"]))
    rec = _run_and_store(db, user, records, old.files, old.group_key, period, old)
    audit(db, user, "reprocessar_conciliacao", "reconciliation", rec.id, origem=old.code, versao=rec.version)
    db.commit()
    return rec_dict(rec)


@router.get("/reconciliations")
def list_recs(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Reconciliation).where(Reconciliation.company_id == user.company_id)
                      .order_by(Reconciliation.id.desc()).limit(500)).all()
    out = []
    for r in rows:
        d = rec_dict(r)
        d.pop("settings_snapshot")
        out.append(d)
    return out


@router.get("/reconciliations/{rid}")
def get_rec(rid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = _own(db, rid, user)
    d = rec_dict(r)
    d["versions"] = [{"id": x.id, "code": x.code, "version": x.version, "created_at": x.created_at.isoformat()}
                     for x in db.scalars(select(Reconciliation).where(
                         Reconciliation.company_id == user.company_id, Reconciliation.group_key == r.group_key)
                         .order_by(Reconciliation.version))]
    d["suggestions"] = [match_dict(m) for m in db.scalars(select(Match).where(
        Match.reconciliation_id == r.id, Match.state == "sugerido"))]
    return d


SORTABLE = {"date": Transaction.date, "amount": Transaction.amount, "difference": Transaction.difference,
            "status": Transaction.status, "source": Transaction.source, "description": Transaction.description,
            "identifier": Transaction.identifier, "found_amount": Transaction.found_amount}


@router.get("/reconciliations/{rid}/transactions")
def list_tx(rid: int, status: list[str] | None = Query(None), source: list[str] | None = Query(None),
            q: str | None = None, match: str | None = None, date_from: str | None = None, date_to: str | None = None,
            sort: str = "date", dir: str = "asc", page: int = 1, size: int = 50,
            user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = _own(db, rid, user)
    stmt = select(Transaction).where(Transaction.reconciliation_id == r.id)
    if status:
        stmt = stmt.where(Transaction.status.in_(status))
    if source:
        stmt = stmt.where(Transaction.source.in_(source))
    if match:
        mt = db.scalar(select(Match).where(Match.reconciliation_id == r.id, Match.code == match))
        stmt = stmt.where(Transaction.uid.in_((mt.left + mt.right) if mt else []))
    if date_from:
        stmt = stmt.where(Transaction.date >= date_from)
    if date_to:
        stmt = stmt.where(Transaction.date <= date_to)
    if q:
        term = q.strip()
        like = f"%{term.lower()}%"
        conds = [func.lower(Transaction.description).like(like), func.lower(Transaction.counterparty).like(like),
                 func.lower(Transaction.identifier).like(like), func.lower(Transaction.note).like(like)]
        num = term.replace("R$", "").replace(" ", "")
        if num.replace(".", "").replace(",", "").replace("-", "").isdigit():
            from ..parsers.common import parse_decimal
            val = parse_decimal(num, ",")
            if val is not None:
                conds += [Transaction.amount == val, Transaction.amount == -val]
        stmt = stmt.where(or_(*conds))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    col = SORTABLE.get(sort, Transaction.date)
    stmt = stmt.order_by(col.desc() if dir == "desc" else col.asc(), Transaction.id)
    size = max(1, min(size, 500))
    rows = db.scalars(stmt.offset((max(page, 1) - 1) * size).limit(size)).all()
    return {"total": total, "page": page, "size": size, "items": [tx_dict(t) for t in rows]}


@router.get("/reconciliations/{rid}/transactions/{tid}")
def tx_detail(rid: int, tid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = _own(db, rid, user)
    t = db.get(Transaction, tid)
    if not t or t.reconciliation_id != r.id:
        raise HTTPException(404, "Lançamento não encontrado.")
    ms = db.scalars(select(Match).where(Match.reconciliation_id == r.id, Match.code.in_(t.match_ids or []))).all()
    uids = {u for m in ms for u in m.left + m.right} - {t.uid}
    related = db.scalars(select(Transaction).where(Transaction.reconciliation_id == r.id,
                                                   Transaction.uid.in_(uids))).all() if uids else []
    d = tx_dict(t)
    d["raw"] = (t.data or {}).get("raw", {})
    d["unmatched_status"] = t.unmatched_status
    return {"transaction": d, "matches": [match_dict(m) for m in ms],
            "related": [tx_dict(x) for x in sorted(related, key=lambda x: (x.source, x.date or ""))]}


def _refresh_totals(db: Session, r: Reconciliation):
    txs = db.scalars(select(Transaction).where(Transaction.reconciliation_id == r.id)).all()
    ms = db.scalars(select(Match).where(Match.reconciliation_id == r.id)).all()
    r.totals = summarize([{**tx_dict(t), "match_ids": t.match_ids} for t in txs],
                         [{"id": m.code, "state": m.state, "level": m.level, "difference": str(m.difference)} for m in ms])


@router.post("/reconciliations/{rid}/matches/{mid}/decision")
def decide(rid: int, mid: int, body: DecisionIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = _own(db, rid, user)
    m = db.get(Match, mid)
    if not m or m.reconciliation_id != r.id:
        raise HTTPException(404, "Vínculo não encontrado.")
    if body.decision not in ("aprovar", "rejeitar"):
        raise HTTPException(422, "Decisão inválida.")
    if m.state in ("aprovado", "rejeitado"):
        raise HTTPException(409, f"Este vínculo já foi {m.state}.")
    stamp = f"{user.name} em {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    m.state = "aprovado" if body.decision == "aprovar" else "rejeitado"
    m.decided_by, m.decided_at, m.note = user.id, datetime.now(timezone.utc), body.note
    other = {x.code: x.state for x in db.scalars(select(Match).where(Match.reconciliation_id == r.id))}
    other[m.code] = m.state
    txs = db.scalars(select(Transaction).where(Transaction.reconciliation_id == r.id,
                                               Transaction.uid.in_(m.left + m.right))).all()
    for t in txs:
        if m.state == "aprovado":
            if t.status == "analise_manual":
                t.status = "conciliado"
            t.justification = f"{t.justification} Aprovado por {stamp}." + (f" Obs.: {body.note}" if body.note else "")
        else:
            active = [c for c in t.match_ids if other.get(c) in ("auto", "aprovado", "sugerido") and c != m.code]
            if not active:
                t.status = t.unmatched_status
                t.justification = (f"{t.unmatched_justification} Sugestão {m.code} rejeitada por {stamp}."
                                   + (f" Motivo: {body.note}" if body.note else ""))
                t.found_amount = t.difference = t.level = t.confidence = None
    _refresh_totals(db, r)
    audit(db, user, f"vinculo_{m.state}", "match", m.id, conciliacao=r.code, vinculo=m.code, obs=body.note)
    db.commit()
    return match_dict(m)


@router.post("/reconciliations/{rid}/transactions/{tid}/note")
def add_note(rid: int, tid: int, body: NoteIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = _own(db, rid, user)
    t = db.get(Transaction, tid)
    if not t or t.reconciliation_id != r.id:
        raise HTTPException(404, "Lançamento não encontrado.")
    note = body.note.strip()[:2000]
    t.note = f"{note} ({user.name}, {datetime.now().strftime('%d/%m/%Y %H:%M')})" if note else ""
    audit(db, user, "observacao", "transaction", t.id, conciliacao=r.code)
    db.commit()
    return tx_dict(t)


@router.get("/reconciliations/{rid}/export")
def export(rid: int, type: str = "xlsx", user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = _own(db, rid, user)
    txs = [tx_dict(t) for t in db.scalars(select(Transaction).where(Transaction.reconciliation_id == r.id)
                                          .order_by(Transaction.date, Transaction.source, Transaction.id))]
    ms = [match_dict(m) for m in db.scalars(select(Match).where(Match.reconciliation_id == r.id).order_by(Match.id))]
    rd = rec_dict(r)
    base = f"conciliacao_{r.code}_v{r.version}"
    if type == "xlsx":
        content = exporters.to_xlsx(rd, txs, ms, exporters.summary_rows(rd, r.totals))
        media, fname = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", f"{base}.xlsx"
    elif type == "csv":
        content, media, fname = exporters.to_csv(txs), "text/csv; charset=utf-8", f"{base}.csv"
    elif type == "pdf":
        content, media, fname = exporters.to_pdf_executive(rd, r.totals, txs), "application/pdf", f"{base}_executivo.pdf"
    elif type == "divergencias":
        content = exporters.to_pdf_divergences(rd, [t for t in txs if t["status"] != "conciliado"],
                                               {m["code"]: m for m in ms})
        media, fname = "application/pdf", f"{base}_divergencias.pdf"
    elif type == "resumo":
        content, media, fname = exporters.summary_csv(rd, r.totals), "text/csv; charset=utf-8", f"{base}_resumo.csv"
    else:
        raise HTTPException(422, "Tipo de exportação inválido.")
    audit(db, user, "exportar", "reconciliation", r.id, tipo=type)
    db.commit()
    return Response(content, media_type=media, headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@router.get("/dashboard")
def dashboard(user: User = Depends(current_user), db: Session = Depends(get_db)):
    latest = db.scalars(select(Reconciliation).where(Reconciliation.company_id == user.company_id)
                        .order_by(Reconciliation.id.desc())).first()
    hist = db.scalars(select(Reconciliation).where(Reconciliation.company_id == user.company_id)
                      .order_by(Reconciliation.id.desc()).limit(12)).all()
    return {"latest": rec_dict(latest) if latest else None,
            "history": [{"id": h.id, "code": h.code, "version": h.version, "period_start": h.period_start,
                         "period_end": h.period_end, "percentual": h.totals.get("percentual_conciliacao"),
                         "conciliado": h.totals.get("total_conciliado"), "created_at": h.created_at.isoformat()}
                        for h in reversed(hist)]}


@router.delete("/reconciliations/{rid}")
def delete_rec(rid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = _own(db, rid, user)
    if user.role != "admin":
        raise HTTPException(403, "Apenas administradores podem excluir conciliações.")
    db.execute(delete(Transaction).where(Transaction.reconciliation_id == r.id))
    db.execute(delete(Match).where(Match.reconciliation_id == r.id))
    for child in db.scalars(select(Reconciliation).where(Reconciliation.parent_id == r.id)):
        child.parent_id = None
    db.delete(r)
    audit(db, user, "excluir_conciliacao", "reconciliation", rid, codigo=r.code)
    db.commit()
    return {"ok": True}
