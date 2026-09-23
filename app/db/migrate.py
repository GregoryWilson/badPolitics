import argparse
import ast
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect

from app.core.config import settings
from app.db.base import Base
import app.models.entities  # noqa: F401

ROOT=Path(__file__).resolve().parents[2]
BASELINE_REVISION="0001"

def alembic_config(database_url:str|None=None):
    cfg=Config(str(ROOT/"alembic.ini"))
    url=database_url or settings.database_url
    cfg.set_main_option("sqlalchemy.url",url.replace("%","%%"))
    return cfg

def head_revision(database_url:str|None=None):
    return ScriptDirectory.from_config(alembic_config(database_url)).get_current_head()

def current_revision(database_url:str|None=None):
    url=database_url or settings.database_url
    engine=create_engine(url,pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            return MigrationContext.configure(connection).get_current_revision()
    finally:
        engine.dispose()

def assert_schema_current(database_url:str|None=None):
    current=current_revision(database_url)
    head=head_revision(database_url)
    if current!=head:
        raise RuntimeError(
            f"Database schema revision is {current or 'unmanaged'}; expected {head}. "
            "Run 'alembic upgrade head'. For a pre-MVP-17 database created by "
            "SQLAlchemy create_all, run 'python -m app.db.migrate adopt-legacy' first."
        )
    return current

def upgrade(database_url:str|None=None,revision:str="head"):
    command.upgrade(alembic_config(database_url),revision)

def _legacy_baseline_manifest():
    path=ROOT/"migrations"/"versions"/"0001_baseline.py"
    tree=ast.parse(path.read_text())
    manifest={}
    for node in ast.walk(tree):
        if not isinstance(node,ast.Call) or not isinstance(node.func,ast.Attribute):
            continue
        if node.func.attr!="create_table" or not node.args:
            continue
        first=node.args[0]
        if not isinstance(first,ast.Constant) or not isinstance(first.value,str):
            continue
        columns=set()
        for arg in node.args[1:]:
            if not isinstance(arg,ast.Call) or not isinstance(arg.func,ast.Attribute) or arg.func.attr!="Column" or not arg.args:
                continue
            name=arg.args[0]
            if isinstance(name,ast.Constant) and isinstance(name.value,str):
                columns.add(name.value)
        manifest[first.value]=columns
    if not manifest:
        raise RuntimeError("Unable to read frozen legacy baseline manifest from migration 0001")
    return manifest

def _validate_legacy_schema(engine):
    inspector=inspect(engine)
    actual_tables=set(inspector.get_table_names())
    if "alembic_version" in actual_tables:
        raise RuntimeError("Database is already Alembic-managed; use 'alembic upgrade head'.")
    manifest=_legacy_baseline_manifest()
    expected_tables=set(manifest)
    present=expected_tables & actual_tables
    if not present:
        raise RuntimeError("No LegisWatch legacy tables were found; use 'alembic upgrade head' for a fresh database.")
    missing_tables=sorted(expected_tables-actual_tables)
    missing_columns={}
    for table_name in sorted(expected_tables & actual_tables):
        expected=manifest[table_name]
        actual={c["name"] for c in inspector.get_columns(table_name)}
        missing=sorted(expected-actual)
        if missing:
            missing_columns[table_name]=missing
    if missing_tables or missing_columns:
        details=[]
        if missing_tables:
            details.append("missing tables: "+", ".join(missing_tables))
        if missing_columns:
            details.append(
                "missing columns: "+
                "; ".join(f"{table}({', '.join(cols)})" for table,cols in missing_columns.items())
            )
        raise RuntimeError(
            "Legacy schema does not match the MVP-16 baseline; refusing to stamp it. "
            + " ".join(details)
        )
    return {
        "table_count":len(expected_tables),
        "extra_tables":sorted(actual_tables-expected_tables),
    }

def adopt_legacy(database_url:str|None=None):
    url=database_url or settings.database_url
    engine=create_engine(url,pool_pre_ping=True)
    try:
        validation=_validate_legacy_schema(engine)
    finally:
        engine.dispose()
    cfg=alembic_config(url)
    command.stamp(cfg,BASELINE_REVISION)
    command.upgrade(cfg,"head")
    return {
        **validation,
        "baseline_revision":BASELINE_REVISION,
        "current_revision":current_revision(url),
    }

def main():
    parser=argparse.ArgumentParser(description="LegisWatch database migration helper")
    parser.add_argument("action",choices=["upgrade","current","check","adopt-legacy"])
    parser.add_argument("--database-url",default=None)
    parser.add_argument("--revision",default="head")
    args=parser.parse_args()
    if args.action=="upgrade":
        upgrade(args.database_url,args.revision)
        print(current_revision(args.database_url))
    elif args.action=="current":
        print(current_revision(args.database_url) or "unmanaged")
    elif args.action=="check":
        print(assert_schema_current(args.database_url))
    else:
        result=adopt_legacy(args.database_url)
        print(result)

if __name__=="__main__":
    main()
