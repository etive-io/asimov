"""
Asimov database interface
-------------------------

This module implements the asimov database and its interfaces.

The database backend supports multiple implementations:
- TinyDB: Simple document-based database (good for single-user scenarios)
- SQLAlchemy: Robust SQL database with transaction support (recommended for production)

Implementation
--------------

The default implementation uses SQLAlchemy with SQLite for simplicity,
but can be configured to use PostgreSQL, MySQL, or other databases
for production deployments with better concurrency handling.

"""

import os
import threading
from contextlib import contextmanager
from typing import Dict, List, Optional, Any

from tinydb import Query, TinyDB
from sqlalchemy import create_engine, and_, or_
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool, NullPool

from asimov import config
from asimov.models import (
    Base,
    EventModel,
    ProductionModel,
    ProjectAnalysisModel,
    EventSchema,
    ProductionSchema,
    ProjectAnalysisSchema,
)


class AsimovDatabase:
    """Base class for asimov database backends."""

    def insert(self, table: str, data: Dict[str, Any]) -> Any:
        """Insert a record into the database."""
        raise NotImplementedError

    def query(self, table: str, filters: Optional[Dict[str, Any]] = None) -> List[Dict]:
        """Query records from the database."""
        raise NotImplementedError

    def update(self, table: str, identifier: Any, data: Dict[str, Any]) -> bool:
        """Update a record in the database."""
        raise NotImplementedError

    def delete(self, table: str, identifier: Any) -> bool:
        """Delete a record from the database."""
        raise NotImplementedError


class AsimovTinyDatabase(AsimovDatabase):
    """TinyDB-based document database implementation."""

    def __init__(self):
        database_path = config.get("ledger", "location")
        self.db = TinyDB(database_path)
        self.tables = {
            "event": self.db.table("event"),
            "production": self.db.table("production"),
        }
        self.Q = Query()

    @classmethod
    def _create(cls):
        db_object = cls()
        db_object.db.table("event")
        return db_object

    def insert(self, table, dictionary, doc_id=None):
        """
        Store an entire model in the dictionary.

        Parameters
        ----------
        table : str
           The name of the table which the document should be stored in.
        dictionary: dict
           The dictionary containing the model.
        """
        doc_id = self.tables[table].insert(dictionary)
        return doc_id

    def query(self, table, parameter, value):
        pages = self.tables[table].search(Query()[parameter] == value)
        return pages


class AsimovSQLDatabase(AsimovDatabase):
    """
    SQLAlchemy-based database implementation with transaction support.

    This implementation provides:
    - ACID transactions
    - Thread-safe operations
    - Advanced querying capabilities
    - Support for multiple database backends (SQLite, PostgreSQL, MySQL, etc.)
    """

    def __init__(self, database_url: Optional[str] = None, echo: bool = False):
        """
        Initialize the SQL database backend.

        Parameters
        ----------
        database_url : str, optional
            SQLAlchemy database URL. If not provided, uses config or defaults to SQLite.
        echo : bool, optional
            Whether to log SQL statements. Default is False.
        """
        if database_url is None:
            # Get from config or use default SQLite
            database_path = config.get("ledger", "location", fallback=".asimov/ledger.db")
            # Ensure directory exists
            db_dir = os.path.dirname(database_path)
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir, exist_ok=True)
            database_url = f"sqlite:///{database_path}"

        # Configure engine based on database type
        if "sqlite" in database_url.lower():
            # SQLite-specific configuration for better concurrency
            self.engine = create_engine(
                database_url,
                echo=echo,
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
            )
        else:
            # For other databases (PostgreSQL, MySQL, etc.)
            self.engine = create_engine(
                database_url,
                echo=echo,
                pool_pre_ping=True,  # Verify connections before use
                pool_size=10,
                max_overflow=20,
            )

        # Create session factory
        self.SessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=self.engine
        )

        # Thread-local storage for sessions
        self._thread_local = threading.local()

    @contextmanager
    def get_session(self) -> Session:
        """
        Context manager for database sessions.

        Provides automatic transaction handling and session cleanup.

        Yields
        ------
        Session
            SQLAlchemy session with transaction support.
        """
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def create_tables(self):
        """Create all database tables."""
        Base.metadata.create_all(bind=self.engine)

    @classmethod
    def _create(cls, database_url: Optional[str] = None):
        """
        Create a new database with tables.

        Parameters
        ----------
        database_url : str, optional
            SQLAlchemy database URL.

        Returns
        -------
        AsimovSQLDatabase
            Initialized database instance.
        """
        db_object = cls(database_url=database_url)
        db_object.create_tables()
        return db_object

    def insert_event(self, data: Dict[str, Any]) -> EventModel:
        """
        Insert an event into the database.

        Parameters
        ----------
        data : dict
            Event data including name, repository, meta, etc.

        Returns
        -------
        EventModel
            The created event.
        """
        with self.get_session() as session:
            # Validate with Pydantic
            event_schema = EventSchema(**data)
            
            # Create ORM model
            event = EventModel(
                name=event_schema.name,
                repository=event_schema.repository,
                working_directory=event_schema.working_directory,
                meta=event_schema.meta,
            )
            session.add(event)
            session.flush()
            session.refresh(event)
            return event

    def insert_production(self, data: Dict[str, Any]) -> ProductionModel:
        """
        Insert a production into the database.

        Parameters
        ----------
        data : dict
            Production data including name, pipeline, event, etc.

        Returns
        -------
        ProductionModel
            The created production.
        """
        with self.get_session() as session:
            # Validate with Pydantic
            production_schema = ProductionSchema(**data)
            
            # Create ORM model
            production = ProductionModel(
                name=production_schema.name,
                event_name=production_schema.event_name,
                pipeline=production_schema.pipeline,
                status=production_schema.status,
                comment=production_schema.comment,
                meta=production_schema.meta,
            )
            session.add(production)
            session.flush()
            session.refresh(production)
            return production

    def insert_project_analysis(self, data: Dict[str, Any]) -> ProjectAnalysisModel:
        """
        Insert a project analysis into the database.

        Parameters
        ----------
        data : dict
            Project analysis data.

        Returns
        -------
        ProjectAnalysisModel
            The created project analysis.
        """
        with self.get_session() as session:
            # Validate with Pydantic
            analysis_schema = ProjectAnalysisSchema(**data)
            
            # Create ORM model
            analysis = ProjectAnalysisModel(
                name=analysis_schema.name,
                pipeline=analysis_schema.pipeline,
                status=analysis_schema.status,
                comment=analysis_schema.comment,
                meta=analysis_schema.meta,
            )
            session.add(analysis)
            session.flush()
            session.refresh(analysis)
            return analysis

    def insert(self, table: str, data: Dict[str, Any]) -> Any:
        """
        Generic insert method for backward compatibility.

        Parameters
        ----------
        table : str
            Table name ('event', 'production', or 'project_analysis').
        data : dict
            Record data.

        Returns
        -------
        int
            The ID of the inserted record.
        """
        if table == "event":
            result = self.insert_event(data)
            return result.id
        elif table == "production":
            result = self.insert_production(data)
            return result.id
        elif table == "project_analysis":
            result = self.insert_project_analysis(data)
            return result.id
        else:
            raise ValueError(f"Unknown table: {table}")

    def query_events(
        self, filters: Optional[Dict[str, Any]] = None
    ) -> List[EventModel]:
        """
        Query events from the database.

        Parameters
        ----------
        filters : dict, optional
            Filter conditions (e.g., {'name': 'GW150914'}).

        Returns
        -------
        list of EventModel
            Matching events.
        """
        with self.get_session() as session:
            query = session.query(EventModel)
            
            if filters:
                for key, value in filters.items():
                    if key == "name":
                        query = query.filter(EventModel.name == value)
                    elif hasattr(EventModel, key):
                        query = query.filter(getattr(EventModel, key) == value)
            
            return query.all()

    def query_productions(
        self, filters: Optional[Dict[str, Any]] = None
    ) -> List[ProductionModel]:
        """
        Query productions from the database.

        Parameters
        ----------
        filters : dict, optional
            Filter conditions (e.g., {'event_name': 'GW150914', 'status': 'ready'}).

        Returns
        -------
        list of ProductionModel
            Matching productions.
        """
        with self.get_session() as session:
            query = session.query(ProductionModel)
            
            if filters:
                for key, value in filters.items():
                    if key == "event":
                        # Support both 'event' and 'event_name'
                        query = query.filter(ProductionModel.event_name == value)
                    elif hasattr(ProductionModel, key):
                        query = query.filter(getattr(ProductionModel, key) == value)
            
            return query.all()

    def query_project_analyses(
        self, filters: Optional[Dict[str, Any]] = None
    ) -> List[ProjectAnalysisModel]:
        """
        Query project analyses from the database.

        Parameters
        ----------
        filters : dict, optional
            Filter conditions.

        Returns
        -------
        list of ProjectAnalysisModel
            Matching project analyses.
        """
        with self.get_session() as session:
            query = session.query(ProjectAnalysisModel)
            
            if filters:
                for key, value in filters.items():
                    if hasattr(ProjectAnalysisModel, key):
                        query = query.filter(getattr(ProjectAnalysisModel, key) == value)
            
            return query.all()

    def query(
        self, table: str, parameter: Optional[str] = None, value: Optional[Any] = None
    ) -> List[Dict]:
        """
        Generic query method for backward compatibility.

        Parameters
        ----------
        table : str
            Table name.
        parameter : str, optional
            Parameter to filter on.
        value : any, optional
            Value to match.

        Returns
        -------
        list of dict
            Matching records as dictionaries.
        """
        filters = {parameter: value} if parameter and value else None
        
        if table == "event":
            results = self.query_events(filters)
            return [event.to_dict() for event in results]
        elif table == "production":
            results = self.query_productions(filters)
            return [prod.to_dict() for prod in results]
        elif table == "project_analysis":
            results = self.query_project_analyses(filters)
            return [analysis.to_dict() for analysis in results]
        else:
            raise ValueError(f"Unknown table: {table}")

    def update_event(self, name: str, data: Dict[str, Any]) -> bool:
        """
        Update an event in the database.

        Parameters
        ----------
        name : str
            Event name.
        data : dict
            Updated data.

        Returns
        -------
        bool
            True if successful.
        """
        with self.get_session() as session:
            event = session.query(EventModel).filter(EventModel.name == name).first()
            if not event:
                raise ValueError(f"Event '{name}' not found")
            
            # Update fields
            if "repository" in data:
                event.repository = data["repository"]
            if "working_directory" in data or "working directory" in data:
                event.working_directory = data.get("working_directory") or data.get("working directory")
            if "meta" in data:
                event.meta = data["meta"]
            
            return True

    def update_production(
        self, event_name: str, production_name: str, data: Dict[str, Any]
    ) -> bool:
        """
        Update a production in the database.

        Parameters
        ----------
        event_name : str
            Parent event name.
        production_name : str
            Production name.
        data : dict
            Updated data.

        Returns
        -------
        bool
            True if successful.
        """
        with self.get_session() as session:
            production = (
                session.query(ProductionModel)
                .filter(
                    and_(
                        ProductionModel.event_name == event_name,
                        ProductionModel.name == production_name,
                    )
                )
                .first()
            )
            if not production:
                raise ValueError(
                    f"Production '{production_name}' not found for event '{event_name}'"
                )
            
            # Update fields
            if "status" in data:
                production.status = data["status"]
            if "comment" in data:
                production.comment = data["comment"]
            if "meta" in data:
                production.meta = data["meta"]
            
            return True

    def delete_event(self, name: str) -> bool:
        """
        Delete an event from the database.

        Parameters
        ----------
        name : str
            Event name.

        Returns
        -------
        bool
            True if successful.
        """
        with self.get_session() as session:
            event = session.query(EventModel).filter(EventModel.name == name).first()
            if not event:
                raise ValueError(f"Event '{name}' not found")
            
            session.delete(event)
            return True
