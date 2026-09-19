"""
The asimov storage API.

Asimov handles the results files for productions using a nested directory layout.
This API helps to make using this easier.


Configuration options
---------------------

Configuration options for the storage API can be found in the `storage` namespace.

```
[storage]
root = /path/to/the/storage/root

```

"""

import hashlib
import os
import pathlib
import stat
import uuid
from shutil import copyfile

import yaml


class NotAStoreError(Exception):
    pass


class AlreadyPresentException(Exception):
    pass


class HashError(Exception):
    pass


class Manifest:
    """
    The storage manifest.

    This object contains details of all of the resources (files) stored
    in a Store, including auditing information such as hashes and UUIDs.

    Parameters
    ----------
    store : `asimov.storage.Store`
       The results store which this should be the manifest of.
    """

    uuid_hash = None

    def __init__(self, store):
        self.root = store.root
        self.store = store

        try:
            with self._open() as f:
                self.data = yaml.safe_load(f)
        except FileNotFoundError:
            raise NotAStoreError

    @property
    def hash_dict(self):
        data = {}
        for event in self.data["events"].values():
            for production in event.values():
                for resource in production.values():
                    data[resource["hash"]] = resource
        return data

    @property
    def uuid_dict(self):
        data = {}
        for e_name, event in self.data["events"].items():
            for p_name, production in event.items():
                for r_name, resource in production.items():
                    # Files are stored on disk under their own name (see
                    # Store.add_file), not renamed to their UUID, so the
                    # path must be built from `r_name`, not from
                    # `resource["uuid"]`.
                    data[resource["uuid"]] = os.path.join(
                        self.root, e_name, p_name, r_name
                    )
        return data

    def get_hash(self, uuid):
        if not self.uuid_hash:
            self.uuid_hash = {}
            for e_name, event in self.data["events"].items():
                for p_name, production in event.items():
                    for r_name, resource in production.items():
                        self.uuid_hash[resource["uuid"]] = resource["hash"]
        return self.uuid_hash[uuid]

    def _open(self):
        """
        Open the manifest file.
        """
        manifest = os.path.join(self.root, ".manifest", "manifest.yaml")
        # Check the manifest exists
        if os.path.isfile(manifest):
            return open(manifest, "r")
        else:
            raise FileNotFoundError

    def update(self):
        """
        Update the manifest file.
        """
        manifest = os.path.join(self.root, ".manifest", "manifest.yaml")
        if os.path.isfile(manifest):
            with open(manifest, "w") as f:
                f.write(yaml.dump(self.data))
        else:
            raise FileNotFoundError

    def get_uuid(self, event, production, filename):
        try:
            return self.data["events"][event][production][filename]["uuid"]
        except KeyError:
            raise FileNotFoundError

    @classmethod
    def create(cls, store):
        """
        Create the manifest.
        This should only be run on a new store, and will fail if a `.manifest` directory exists
        in the Store already.
        """
        contents = {"name": store["name"], "events": {}}
        manifest = os.path.join(store["root"], ".manifest", "manifest.yaml")

        if not os.path.isfile(manifest):
            with open(manifest, "w") as f:
                f.write(yaml.dump(contents))
        else:
            raise FileExistsError

    def _verify(self, hash):
        """
        Verify the manifest directory's hash.

        Parameters
        ----------
        hash : str
           The hash of the manifest directory itself.
        """
        pass

    def list_resources(self, event, production):
        """
        List all of the resources available for a production.
        """
        return self.data["events"][event][production]

    def add_record(self, event, production, resource, hash, resource_uuid):
        """
        Add a resource record to the manifest.

        Parameters
        ----------
        event : `asimov.events.Event` or str
           The event which this file is for.
           Can be either an event object, or the name of the event.
        production : `asimov.events.Production` or str
           Can be either a production object or the name of the production.
        resource : str
           The path to the resource to be recorded.
        hash : str
           The hash of the resource being recorded.
        uuid : UUID
           The UUID of the object being recorded.
        """
        # This function should store the name, location, event, production of the file
        # then calculate the hash and uuid for the file, and store them in the manifest

        if event not in self.data["events"]:
            self.data["events"][event] = {}
        if production not in self.data["events"][event]:
            self.data["events"][event][production] = {}

        if resource in self.data["events"][event][production]:
            raise FileExistsError

        self.data["events"][event][production][resource] = {
            "uuid": resource_uuid.hex,
            "hash": hash,
        }


class Store:
    """
    The results store.

    Parameters
    ----------
    root : str, optional
       The path to the results store.
       If not provided defaults to the value of `storage>root` in the configuration file.
    """

    def __init__(self, root=None):
        """
        Initiate an asimov store.
        """
        self.root = root

        self.manifest = Manifest(self)

    @classmethod
    def create(cls, root, name):
        """
        Create this results store.

        Parameters
        ----------
        root : str
           The path to the results store.
        name : str
           A name for this Store.
        """
        pathlib.Path(root).mkdir(parents=False, exist_ok=False)
        manifest_dir = os.path.join(root, ".manifest")
        pathlib.Path(manifest_dir).mkdir(parents=False, exist_ok=False)
        store = {}
        store["name"] = name
        store["root"] = root
        _ = Manifest.create(store)

    def _check(self):
        """
        Check the integrity of the results store.
        """
        pass

    def _exists(self):
        """
        Check if the store exists.
        """
        pass

    def _hash(self, path):
        """
        Calculate the hash of a file.

        Parameters
        ----------
        path : str
           The filepath of the file to be hashed.
        """
        hasher = hashlib.md5()
        with open(path, "rb") as afile:
            buf = afile.read()
            hasher.update(buf)
        return hasher.hexdigest()

    def add_file(self, event, production, file, new_name=None):
        """
        Add a file to the store.

        Parameters
        ----------
        event : `asimov.events.Event` or str
           The event which this file is for.
           Can be either an event object, or the name of the event.
        production : `asimov.events.Production` or str
           Can be either a production object or the name of the production.
        file : str
           The path to the origin file to be stored.
        new_name : str
           The new name of the file once it's stored.

        Returns
        -------
        hash : str
           The MD5 hash of the stored file.
        """
        hash = self._hash(file)
        if hash in self.manifest.hash_dict:
            raise AlreadyPresentException

        pathlib.Path(os.path.join(self.root, event, production)).mkdir(
            parents=True, exist_ok=True
        )

        this_uuid = uuid.uuid4()

        name = new_name if new_name else os.path.basename(file)

        self.manifest.add_record(event, production, name, hash, this_uuid)

        destination = os.path.join(self.root, event, production, name)

        copyfile(file, destination)

        os.chmod(destination, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)

        self.manifest.update()

        # `.hex`, not `.urn`: the manifest itself records `resource_uuid.hex`
        # (see Manifest.add_record), so returning `.urn` here made the
        # returned uuid useless for a subsequent `fetch_uuid()`/`get_hash()`
        # call - it would never match what's actually stored.
        return {"file": name, "hash": self._hash(destination), "uuid": this_uuid.hex}

    def fetch_file(self, event, production, file, hash=None):
        """
        Retrieve a file from the store.

        Parameters
        ----------
        event : `asimov.events.Event` or str
           The event which this file is for.
           Can be either an event object, or the name of the event.
        production : `asimov.events.Production` or str
           Can be either a production object or the name of the production.
        file : str
           The name of the file to be retrieved.
        hash : str, optional
           The expected MD5 hash of the file.
           If this is not provided the file will be verified against the store's manifest
           before being returned, but if a hash is provided it will be checked against
           the provided value.

        Returns
        -------
        path : str
           The path to the file.
        """
        this_uuid = self.manifest.get_uuid(event, production, file)
        resource = self.fetch_uuid(this_uuid)
        stored_hash = self.manifest.get_hash(this_uuid)
        file_hash = self._hash(resource)

        if file_hash != stored_hash:
            raise HashError(
                "The file in the file store's hash does not match the manifest."
            )

        if hash:
            if hash != stored_hash:
                raise HashError("The manifest hash does not match the check hash.")

        return resource

    def fetch_uuid(self, uuid):
        """
        Retrieve a file from the store from its uuid.

        Parameters
        ----------
        uuid : str
           The uuid of the requested resource.

        Returns
        -------
        file : str
           The path to the file.
        """
        return self.manifest.uuid_dict[uuid]
