"""Configuração via variáveis de ambiente."""
import os

DATABASE_URL = (os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or "").strip()
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL[len("postgres://"):]
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL[len("postgresql://"):]
if not DATABASE_URL:
    # Sem PostgreSQL configurado: SQLite local (em /tmp no ambiente serverless). Apenas para testes.
    base = "/tmp" if os.getenv("VERCEL") else os.path.join(os.path.dirname(__file__), "..")
    DATABASE_URL = f"sqlite:///{os.path.abspath(os.path.join(base, 'conciliacao.db'))}"

IS_SQLITE = DATABASE_URL.startswith("sqlite")
JWT_SECRET = os.getenv("JWT_SECRET") or "dev-secret-altere-em-producao"
JWT_DEFAULT = JWT_SECRET == "dev-secret-altere-em-producao"
JWT_HOURS = int(os.getenv("JWT_HOURS", "12"))
ALLOW_REGISTRATION = os.getenv("ALLOW_REGISTRATION", "true").lower() == "true"
AUTO_CREATE_TABLES = os.getenv("AUTO_CREATE_TABLES", "true").lower() == "true"
