"""SQL Server/PostgreSQL lookup sources and non-secret connection preferences."""
from __future__ import annotations

from contextlib import closing, contextmanager
from dataclasses import asdict, dataclass, field
import hashlib
import json
import re
import time

from app.constants import STANDARD_HEADERS
from app.core.lead_reference import (
    COMPANY_FIELDS, COMPANY_KEY, POPULATABLE_FIELDS, PROSPECT_FIELDS, PROSPECT_KEY,
    LeadLookup, ReferenceInfo,
)


ENGINES = {"local": "Local database", "mssql": "SQL Server", "postgres": "PostgreSQL"}
ODBC_DOWNLOAD_URL = "https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server"


class DatabaseError(ValueError):
    """User-facing message containing no raw driver error or connection string."""


@dataclass
class DatabaseConfig:
    engine: str = "local"
    host: str = ""
    port: int = 0
    database: str = ""
    username: str = ""
    auth: str = "password"
    sslmode: str = "verify-full"
    sslrootcert: str = ""
    encrypt: bool = True
    trust_certificate: bool = False
    timeout: int = 15
    schema: str = ""
    table: str = ""
    mapping: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data):
        # Whitelist fields: passwords/connection strings never enter saved profiles.
        return cls(**{key: value for key, value in data.items() if key in cls.__dataclass_fields__})

    def validate(self, *, require_table=False):
        if self.engine not in ENGINES:
            raise DatabaseError("Choose Local database, SQL Server, or PostgreSQL.")
        if self.engine == "local":
            return
        if not self.host.strip() or not self.database.strip():
            raise DatabaseError("Enter the server and database name.")
        if any("\x00" in value for value in (self.host, self.database, self.username, self.sslrootcert)):
            raise DatabaseError("Connection fields cannot contain null characters.")
        if not 0 <= self.port <= 65535 or not 1 <= self.timeout <= 60:
            raise DatabaseError("Use a valid port and a timeout between 1 and 60 seconds.")
        if self.auth not in {"password", "windows"} or (self.engine == "postgres" and self.auth != "password"):
            raise DatabaseError("Select a supported authentication method.")
        if self.auth == "password" and not self.username.strip():
            raise DatabaseError("Enter a database username.")
        if self.sslmode not in {"verify-full", "require", "disable"}:
            raise DatabaseError("Choose a supported PostgreSQL SSL mode.")
        if require_table:
            if not self.schema or not self.table:
                raise DatabaseError("Connect and choose a database table or view.")
            if any(key not in STANDARD_HEADERS for key in self.mapping):
                raise DatabaseError("The saved mapping contains an unknown application header.")
            values = list(self.mapping.values())
            if len(values) != len(set(values)):
                raise DatabaseError("Map each database column to only one application header.")
            if not self.available_fields():
                raise DatabaseError("Map a lookup key and at least one field in its group: Prospect LinkedIn Link for prospect fields, or Company Website for company fields.")

    def available_fields(self):
        return tuple(column for column in POPULATABLE_FIELDS if column in self.mapping
                     and (PROSPECT_KEY if column in PROSPECT_FIELDS else COMPANY_KEY) in self.mapping)

    def credential_key(self):
        values = asdict(self)
        for key in ("schema", "table", "mapping"):
            values.pop(key)
        return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()

    def source_label(self):
        return ENGINES[self.engine] if self.engine == "local" else f"{ENGINES[self.engine]} · {self.database} · {self.schema}.{self.table}"


class DatabaseProfiles:
    def __init__(self, settings):
        self.settings = settings
        self._passwords = {}

    def load(self, engine=None):
        engine = engine or self.settings.get("lead_database_source", "local")
        data = self.settings.get("lead_database_profiles", {}).get(engine, {})
        return DatabaseConfig.from_dict({**data, "engine": engine})

    def save(self, config, password=""):
        config.validate(require_table=config.engine != "local")
        profiles = self.settings.get("lead_database_profiles", {})
        profiles[config.engine] = asdict(config)
        self.settings.update_many({"lead_database_profiles": profiles, "lead_database_source": config.engine})
        if config.engine != "local" and config.auth == "password":
            self._passwords[config.credential_key()] = password

    def password(self, config):
        return self._passwords.get(config.credential_key())

    def remember_session_password(self, config, password):
        self._passwords[config.credential_key()] = password


def suggested_mapping(columns, saved=None):
    """Only suggest unambiguous spelling matches; the user confirms all mappings."""
    def normalized(text):
        return re.sub(r"[^a-z0-9]", "", text.casefold())
    aliases = {"Business Email ID": {"email", "businessemail", "emailaddress"},
               PROSPECT_KEY: {"linkedin", "linkedinurl", "profileurl", "prospectlinkedinurl"},
               COMPANY_KEY: {"website", "companyurl", "domain", "companydomain"}}
    result, used = {}, set()
    for header, column in (saved or {}).items():
        if header in STANDARD_HEADERS and column in columns and column not in used:
            result[header] = column
            used.add(column)
    for header in STANDARD_HEADERS:
        if header in result:
            continue
        options = [column for column in columns if column not in used and normalized(column) in {normalized(header), *aliases.get(header, set())}]
        if len(options) == 1:
            result[header] = options[0]
            used.add(options[0])
    return result


def _safe_error(exc):
    # Driver diagnostics can echo passwords or connection strings. Never display/log them.
    text = str(exc).casefold()
    if "certificate" in text or "ssl" in text or "tls" in text:
        return "The encrypted database connection failed. Check the server certificate and the SSL/TLS options."
    if "login failed" in text or "authentication" in text or "password" in text:
        return "Database sign-in failed. Check the authentication method, username, and password."
    if "permission" in text or "denied" in text:
        return "The account cannot read this database table or its columns. Check its SELECT permissions."
    if "timeout" in text or "timed out" in text:
        return "The database request timed out. Check the server address, network access, and table size."
    return "The database request failed. Check the server, port, database, credentials, and table permissions, then reconnect."


def _identifier(name, engine):
    if not name or "\x00" in name:
        raise DatabaseError("A database schema, table, or column name is invalid. Reconnect and select the table again.")
    return "[" + name.replace("]", "]]") + "]" if engine == "mssql" else '"' + name.replace('"', '""') + '"'


def _odbc_value(value):
    return "{" + str(value).replace("}", "}}") + "}"


class RemoteLeadSource(LeadLookup):
    def __init__(self, config, password=""):
        self.config = DatabaseConfig.from_dict(asdict(config))
        self.password = password

    @contextmanager
    def connect(self):
        config = self.config
        config.validate()
        connection = None
        try:
            if config.engine == "postgres":
                try:
                    import psycopg
                except ImportError:
                    raise DatabaseError("PostgreSQL support is missing. Run Setup_Combined.bat to install psycopg.") from None
                kwargs = dict(host=config.host, port=config.port or 5432, dbname=config.database,
                              user=config.username, password=self.password, connect_timeout=config.timeout,
                              sslmode=config.sslmode, application_name="Lead Workspace lookup",
                              options="-c statement_timeout=60000 -c default_transaction_read_only=on")
                if config.sslrootcert:
                    kwargs["sslrootcert"] = config.sslrootcert
                connection = psycopg.connect(**kwargs)
                connection.read_only = True
                connection.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
            elif config.engine == "mssql":
                try:
                    import pyodbc
                except ImportError:
                    raise DatabaseError("SQL Server support is missing. Run Setup_Combined.bat to install pyodbc.") from None
                drivers = pyodbc.drivers()
                driver = next((name for name in ("ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server") if name in drivers), None)
                if driver is None:
                    raise DatabaseError("Install Microsoft ODBC Driver 18 for SQL Server (64-bit), then reconnect. The download link is in the connection window.")
                server = config.host + (f",{config.port}" if config.port else "")
                values = {"DRIVER": driver, "SERVER": server, "DATABASE": config.database,
                          "Encrypt": "yes" if config.encrypt else "no",
                          "TrustServerCertificate": "yes" if config.trust_certificate else "no",
                          "ApplicationIntent": "ReadOnly", "APP": "Lead Workspace lookup"}
                if config.auth == "windows":
                    values["Trusted_Connection"] = "yes"
                else:
                    values.update(UID=config.username, PWD=self.password)
                connection_string = ";".join(key + "=" + _odbc_value(value) for key, value in values.items())
                connection = pyodbc.connect(connection_string, timeout=config.timeout, autocommit=False)
                connection.timeout = 60
            else:
                raise DatabaseError("Select a SQL Server or PostgreSQL connection.")
            yield connection
        except DatabaseError:
            raise
        except Exception as exc:
            raise DatabaseError(_safe_error(exc)) from None
        finally:
            if connection is not None:
                # A read session never commits or issues data/schema writes.
                try:
                    connection.close()
                except Exception:
                    pass

    def tables(self):
        with self.connect() as connection, closing(connection.cursor()) as cursor:
            cursor.execute("SELECT TABLE_SCHEMA, TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
                           "WHERE TABLE_TYPE IN ('BASE TABLE', 'VIEW') AND TABLE_SCHEMA NOT IN ('pg_catalog', 'information_schema', 'sys') "
                           "ORDER BY TABLE_SCHEMA, TABLE_NAME")
            return [(str(row[0]), str(row[1])) for row in cursor.fetchall()]

    def _columns(self, connection):
        config = self.config
        token = "?" if config.engine == "mssql" else "%s"
        with closing(connection.cursor()) as cursor:
            cursor.execute(f"SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA={token} AND TABLE_NAME={token} ORDER BY ORDINAL_POSITION",
                           (config.schema, config.table))
            columns = [str(row[0]) for row in cursor.fetchall()]
            if not columns:
                raise DatabaseError("No readable columns were found. Select a table/view and check its permissions.")
            # Confirm SELECT access without fetching lead data.
            cursor.execute(f"SELECT * FROM {self._table()} WHERE 1=0")
            return columns

    def columns(self):
        with self.connect() as connection:
            return self._columns(connection)

    def _table(self):
        return ".".join(_identifier(name, self.config.engine) for name in (self.config.schema, self.config.table))

    def _check_mapping(self, columns):
        self.config.validate(require_table=True)
        if any(source not in columns for source in self.config.mapping.values()):
            raise DatabaseError("The database headers have changed. Open Database connection & column mapping, reconnect, and review the mapping again.")

    def info(self):
        columns = self.columns()
        self._check_mapping(columns)
        config = self.config
        return ReferenceInfo(f"{config.host} / {config.database}", None, label=ENGINES[config.engine],
                             table=f"{config.schema}.{config.table}", available_fields=config.available_fields())

    def plan(self, records, columns, row_indices, *, workspace_key, overwrite=False):
        if any(column not in self.config.available_fields() for column in columns):
            raise DatabaseError("Map the selected fields and their lookup keys before populating them.")
        return super().plan(records, columns, row_indices, workspace_key=workspace_key, overwrite=overwrite)

    @contextmanager
    def read_session(self):
        with self.connect() as connection:
            self._check_mapping(self._columns(connection))
            started = time.monotonic()
            def read_rows(columns):
                names = [_identifier(self.config.mapping[column], self.config.engine) for column in columns]
                # Server-side PostgreSQL cursors and bounded fetches avoid loading the whole source table.
                kwargs = {"name": "lead_lookup_" + str(time.monotonic_ns())} if self.config.engine == "postgres" else {}
                with closing(connection.cursor(**kwargs)) as cursor:
                    cursor.execute(f"SELECT {', '.join(names)} FROM {self._table()}")
                    while True:
                        if time.monotonic() - started > 120:
                            raise DatabaseError("Lookup exceeded two minutes. Use a smaller database table/view and try again. No lead values were applied.")
                        batch = cursor.fetchmany(1000)
                        if not batch:
                            break
                        yield from batch
            yield read_rows
