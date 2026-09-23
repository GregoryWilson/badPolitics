import pytest
from sqlalchemy import create_engine, inspect

from app.db.base import Base
import app.models.entities  # noqa: F401
from app.db.migrate import adopt_legacy, assert_schema_current, current_revision, head_revision, upgrade

def sqlite_url(path):
    return "sqlite:///"+str(path)

def explicit_model_indexes():
    return {
        (table.name,index.name)
        for table in Base.metadata.tables.values()
        for index in table.indexes
        if index.name
    }

def test_fresh_database_upgrades_to_head(tmp_path):
    url=sqlite_url(tmp_path/"fresh.db")
    upgrade(url)
    assert current_revision(url)==head_revision(url)=="0003"
    assert assert_schema_current(url)=="0003"

    engine=create_engine(url)
    try:
        inspector=inspect(engine)
        actual_tables=set(inspector.get_table_names())
        assert set(Base.metadata.tables) <= actual_tables
        for table_name,table in Base.metadata.tables.items():
            actual_columns={row["name"] for row in inspector.get_columns(table_name)}
            assert {column.name for column in table.columns}==actual_columns

        actual_indexes={
            (table_name,row["name"])
            for table_name in Base.metadata.tables
            for row in inspector.get_indexes(table_name)
        }
        assert explicit_model_indexes() <= actual_indexes
    finally:
        engine.dispose()

def test_legacy_create_all_schema_can_be_adopted(tmp_path):
    url=sqlite_url(tmp_path/"legacy.db")
    upgrade(url,"0001")
    engine=create_engine(url)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("DROP TABLE alembic_version")
    finally:
        engine.dispose()

    assert current_revision(url) is None
    result=adopt_legacy(url)
    assert result["baseline_revision"]=="0001"
    assert result["current_revision"]=="0003"
    assert result["table_count"] < len(Base.metadata.tables)
    assert assert_schema_current(url)=="0002"

def test_incomplete_legacy_schema_is_refused(tmp_path):
    url=sqlite_url(tmp_path/"partial.db")
    engine=create_engine(url)
    try:
        Base.metadata.tables["bills"].create(engine)
    finally:
        engine.dispose()

    with pytest.raises(RuntimeError,match="refusing to stamp"):
        adopt_legacy(url)

def test_application_no_longer_creates_schema_at_import():
    source=(__import__("pathlib").Path(__file__).resolve().parents[1]/"app/main.py").read_text()
    assert "metadata.create_all" not in source
