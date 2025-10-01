"""
Asimov databse interface
------------------------

This module implements the asimov database and its interfaces.

Note that this approach to the database is a departure from what I set
up initially for the database backed logger, and I think it would be
better to use a document database going forward.

Implementation
--------------

Initially the implementation is designed to use TinyDB but that's
just because I want something I can work with easily on a laptop.
MongoDB would be a better long-term solution.

"""

from tinydb import Query, TinyDB

from asimov import config


class AsimovDatabase:
    pass


class AsimovTinyDatabase(AsimovDatabase):
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
           The dicitonary containing the model.
        """
        doc_id = self.tables[table].insert(dictionary)
        return doc_id

    def query(self, table, parameter, value):
        pages = self.tables[table].search(Query()[parameter] == value)
        return pages
