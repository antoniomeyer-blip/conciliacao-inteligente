import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import ALLOW_REGISTRATION
from ..db import get_db
from ..models import Company, User
from ..security import audit, create_token, current_user, hash_password, require_admin, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])
users_router = APIRouter(prefix="/api/users", tags=["usuarios"])


class RegisterIn(BaseModel):
    company: str
    name: str
    email: str
    password: str


class LoginIn(BaseModel):
    email: str
    password: str


class UserIn(BaseModel):
    name: str
    email: str
    password: str
    role: str = "analista"


def _validate(email: str, password: str):
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HTTPException(422, "E-mail inválido.")
    if len(password) < 8:
        raise HTTPException(422, "A senha deve ter pelo menos 8 caracteres.")


def user_out(u: User) -> dict:
    return {"id": u.id, "name": u.name, "email": u.email, "role": u.role,
            "company": {"id": u.company_id, "name": u.company.name if u.company else ""}}


@router.post("/register")
def register(body: RegisterIn, db: Session = Depends(get_db)):
    if not ALLOW_REGISTRATION:
        raise HTTPException(403, "Cadastro desabilitado. Solicite acesso ao administrador.")
    email = body.email.strip().lower()
    _validate(email, body.password)
    if not body.company.strip() or not body.name.strip():
        raise HTTPException(422, "Informe empresa e nome.")
    if db.scalar(select(User).where(func.lower(User.email) == email)):
        raise HTTPException(409, "Já existe um usuário com este e-mail.")
    company = Company(name=body.company.strip(), settings={})
    db.add(company)
    db.flush()
    user = User(company_id=company.id, email=email, name=body.name.strip(),
                password_hash=hash_password(body.password), role="admin")
    db.add(user)
    db.flush()
    audit(db, user, "cadastro_empresa", "company", company.id)
    db.commit()
    db.refresh(user)
    return {"token": create_token(user, db), "user": user_out(user)}


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(func.lower(User.email) == body.email.strip().lower()))
    if not user or not verify_password(body.password, user.password_hash) or not user.active:
        raise HTTPException(401, "E-mail ou senha incorretos.")
    audit(db, user, "login", "user", user.id)
    db.commit()
    return {"token": create_token(user, db), "user": user_out(user)}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return user_out(user)


@users_router.get("")
def list_users(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(User).where(User.company_id == user.company_id).order_by(User.name)).all()
    return [user_out(u) for u in rows]


@users_router.post("")
def create_user(body: UserIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    _validate(email, body.password)
    if body.role not in ("admin", "analista"):
        raise HTTPException(422, "Papel inválido.")
    if db.scalar(select(User).where(func.lower(User.email) == email)):
        raise HTTPException(409, "Já existe um usuário com este e-mail.")
    u = User(company_id=admin.company_id, email=email, name=body.name.strip(),
             password_hash=hash_password(body.password), role=body.role)
    db.add(u)
    db.flush()
    audit(db, admin, "criar_usuario", "user", u.id, email=email, role=body.role)
    db.commit()
    db.refresh(u)
    return user_out(u)
