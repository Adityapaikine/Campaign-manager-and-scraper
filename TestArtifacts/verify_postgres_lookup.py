"""Exercise the connector against a disposable loopback PostgreSQL cluster."""
from contextlib import closing
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
folder = Path(tempfile.mkdtemp(prefix="postgres-lookup-check-", dir=ROOT / "TestArtifacts"))
os.environ["LEAD_WORKSPACE_DATA_DIR"] = str(folder / "app-data")
from suite_bootstrap import configure
configure()
import psycopg
from app.core.database_connections import DatabaseConfig, DatabaseError, RemoteLeadSource
from app.core.lead_reference import COMPANY_KEY, PROSPECT_KEY

bin_dir = Path(r"C:\Program Files\PostgreSQL\18\bin")
with socket.socket() as probe:
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
data = folder / "cluster"
def run(*args):
    # A background postmaster must not inherit a captured pipe and keep communicate() waiting.
    with (folder / "setup.log").open("a", encoding="utf-8") as log:
        result = subprocess.run([str(arg) for arg in args], stdout=log, stderr=log,
                                timeout=50, creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        raise RuntimeError((folder / "setup.log").read_text(encoding="utf-8"))
    return result

started = False
try:
    run(bin_dir / "initdb.exe", "-D", data, "-U", "lead_lookup_test", "-A", "trust", "--no-locale", "--encoding=UTF8")
    run(bin_dir / "pg_ctl.exe", "-D", data, "-l", folder / "server.log", "-o", f"-h 127.0.0.1 -p {port} -F", "-w", "start")
    started = True
    with psycopg.connect(host="127.0.0.1", port=port, dbname="postgres", user="lead_lookup_test", autocommit=True) as admin:
        admin.execute('CREATE SCHEMA lookup_test')
        admin.execute('CREATE TABLE lookup_test."Prospect Source" ("person profile" TEXT, "company domain" TEXT, "work email" TEXT, "business name" TEXT, "role title" TEXT)')
        with admin.cursor() as cursor:
            cursor.executemany('INSERT INTO lookup_test."Prospect Source" VALUES (%s,%s,%s,%s,%s)', [
                ("https://linkedin.com/in/person-a", "https://www.acme.example/", "a@acme.example", "Acme", "Director"),
                ("linkedin.com/in/person-b", "acme.example", "b@acme.example", "Acme", "Engineer"),
            ])
    config = DatabaseConfig(engine="postgres", host="127.0.0.1", port=port, database="postgres",
        username="lead_lookup_test", sslmode="disable", schema="lookup_test", table="Prospect Source",
        mapping={PROSPECT_KEY: "person profile", COMPANY_KEY: "company domain", "Business Email ID": "work email",
                 "Company Name": "business name", "Job Title": "role title"})
    source = RemoteLeadSource(config, "synthetic-test-value")
    assert ("lookup_test", "Prospect Source") in source.tables()
    info = source.info()
    target = [{PROSPECT_KEY: "www.linkedin.com/in/person-a/", COMPANY_KEY: "acme.example"}]
    plan = source.plan(target, ["Business Email ID", "Company Name", "Job Title"], [0], workspace_key="general")
    assert plan.edits == {(0, "Business Email ID"): "a@acme.example", (0, "Company Name"): "Acme", (0, "Job Title"): "Director"}
    with source.connect() as connection:
        assert connection.execute("SHOW transaction_read_only").fetchone()[0] == "on"
    with psycopg.connect(host="127.0.0.1", port=port, dbname="postgres", user="lead_lookup_test", autocommit=True) as admin:
        assert admin.execute('SELECT COUNT(*) FROM lookup_test."Prospect Source"').fetchone()[0] == 2
        admin.execute('ALTER TABLE lookup_test."Prospect Source" RENAME COLUMN "work email" TO "new email"')
    try:
        source.info()
    except DatabaseError as exc:
        assert "headers have changed" in str(exc)
    else:
        raise AssertionError("Schema change was not detected")
    report = {"engine": "PostgreSQL 18", "isolated_loopback_cluster": True, "discovery": "passed",
              "mapped_headers_with_spaces": "passed", "prospect_and_company_matching": "passed",
              "read_only_transaction": "passed", "source_rows_unchanged": True,
              "schema_change_requires_remapping": "passed", "cluster_stopped": False}
finally:
    if (data / "postmaster.pid").exists():
        run(bin_dir / "pg_ctl.exe", "-D", data, "-m", "fast", "-w", "stop")
if started:
    report["cluster_stopped"] = True
    (ROOT / "TestArtifacts" / "postgres_live_lookup_verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
