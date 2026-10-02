import contextlib
import glob
import os
import pathlib
import shutil
import subprocess

import git

from asimov import config, logger
from asimov.utils import set_directory


class AsimovFileNotFound(FileNotFoundError):
    pass


class EventRepo:
    """
    Read a git repository containing event PE information.

    Parameters
    ----------
    directory : str
       The path to the git repository on the filesystem.
    url : str
       The URL of the git repository
    update : bool
        Flag to determine if the repository is updated when loaded.
        Defaults to False.
    """

    def __init__(self, directory, url=None, update=False, pending_init=False):
        self.event = directory.split("/")[-1]
        self.directory = directory
        self.update_needed = update
        self._repo = None
        self._updated = False
        self._pending_init = pending_init
        self.url = url

        self.logger = logger

    @staticmethod
    def git_enabled():
        """
        Whether per-event git repositories are in use.

        Set ``[general] event_git = false`` to skip creating and updating
        git repositories for events (useful for very large projects, where
        a repository per event is slow and uses a lot of file handles).
        Repositories which are explicitly configured with a URL are still
        cloned.
        """
        try:
            return config.getboolean("general", "event_git", fallback=True)
        except ValueError:
            return True

    def _ensure_initialised(self):
        """
        Create the on-disk repository if :meth:`create` deferred doing so.

        Creating a repository means ``git init``, writing a file, and making
        a commit. :meth:`create` is called whenever an Event without a
        repository is constructed, and Events are reconstructed on every
        ledger read, so this is only done when the repository is first
        needed.
        """
        if not self._pending_init:
            return
        self._pending_init = False
        category = config.get("general", "calibration_directory")
        os.makedirs(os.path.join(self.directory, category), exist_ok=True)
        if not self.git_enabled():
            return
        try:
            repo = git.Repo.init(self.directory, initial_branch="main")
        except (TypeError, git.exc.GitCommandError) as exc:
            # Fallback for older git versions that don't support initial_branch
            logger.warning(
                "Git version does not support 'initial_branch' when initializing "
                "repository at %s; falling back to default initial branch. "
                "Original error: %s",
                self.directory,
                exc,
            )
            repo = git.Repo.init(self.directory)
        try:
            with open(os.path.join(self.directory, category, ".gitkeep"), "w") as f:
                f.write(" ")
            repo.git.add(os.path.join(".", category, ".gitkeep"))
            try:
                repo.git.commit("-m", "Initial commit")
            except git.exc.GitCommandError as e:
                if "working tree clean" not in (e.stdout or ""):
                    logger.debug(f"Initial commit in {self.directory} skipped: {e}")
        finally:
            repo.close()

    @contextlib.contextmanager
    def _git(self):
        """
        Open the repository for the duration of a ``with`` block.

        A ``git.Repo`` which has run commands keeps ``git cat-file``
        subprocesses (and their pipes) open until it is closed. With one
        EventRepo per event, holding every handle open exhausts the
        process's file descriptors on large projects, so internal
        operations use a short-lived handle which is closed on exit.
        If a long-lived handle has already been created through
        :attr:`repo` it is reused (and left open).
        """
        self._ensure_initialised()
        if self._repo is not None:
            yield self._repo
            return
        repo = git.Repo(self.directory)
        try:
            yield repo
        finally:
            repo.close()

    def close(self):
        """Release the long-lived handle from :attr:`repo`, if there is one."""
        if self._repo is not None:
            self._repo.close()
            self._repo = None

    @property
    def repo(self):
        """
        A long-lived ``git.Repo`` handle, opened lazily.

        Every Event gets its own EventRepo, and every ledger read
        reconstructs Event objects - opening the repo eagerly here made
        constructing an Event (and therefore just listing events) require
        the checkout to already exist at a resolvable path, which broke as
        soon as it was read from a different working directory than where
        it was created. Deferring this to first actual use means listing
        events never needs to touch git at all.

        Prefer :meth:`_git` inside this class: this handle keeps file
        descriptors open until :meth:`close` is called.
        """
        self._ensure_initialised()
        if self._repo is None:
            self._repo = git.Repo(self.directory)
        return self._repo

    def get_default_branch(self):
        """
        Get the default branch name for this repository.
        
        Returns
        -------
        str
            The name of the default branch (e.g., 'master', 'main')
        """
        with self._git() as repo:
            return self._default_branch(repo)

    def _default_branch(self, repo):
        try:
            # Try to get the remote's default branch
            if repo.remotes:
                remote = repo.remotes[0]
                # Get the symbolic reference for HEAD from the remote
                if hasattr(remote, 'refs'):
                    for ref in remote.refs:
                        ref_name = getattr(ref, "name", "")
                        if ref_name.endswith("HEAD"):
                            # Get what HEAD points to
                            remote_head = getattr(ref, "remote_head", None)
                            if remote_head:
                                return remote_head
                            target_ref = getattr(ref, "ref", None)
                            target_name = getattr(target_ref, "name", None)
                            if target_name:
                                return target_name.split("/")[-1]
            
            # Fallback: check local HEAD or common branch names
            if repo.head.is_valid():
                return repo.head.ref.name
            
            # Final fallback: try common names
            for branch_name in ['main', 'master']:
                try:
                    repo.git.rev_parse('--verify', branch_name)
                    return branch_name
                except git.exc.GitCommandError:
                    continue
                    
            # If all else fails, return 'master' as last resort
            return 'master'
        except (git.exc.GitCommandError, AttributeError) as e:
            # In case of any error, return 'master' as a safe default
            self.logger.warning(f"Could not detect default branch for {self.event}: {e}")
            return 'master'

    def __repr__(self):
        return self.directory

    @classmethod
    def create(cls, location):
        """
        Create a new git repository to store configurations etc.

        The directory is created immediately, but ``git init`` and the
        initial commit are deferred until the repository is first used (and
        skipped altogether if ``[general] event_git`` is false).

        Parameters
        ----------
        location : str
           The location of the directory to be used.
        """
        os.makedirs(location, exist_ok=True)
        # The git init and initial commit are deferred until the repository
        # is first used, see _ensure_initialised().
        return cls(directory=location, url=location, pending_init=True)

    @classmethod
    def from_url(cls, url, name, directory=None, update=False):
        """
        Clone a git repository into a working directory,
        then create an EventRepo object for it.

        Parameters
        ----------
        url : str
           The URL of the git repository
        name : str
           The name for the git repository (probably the event name)
        directory : str, optional
           The location to store the cloned repository.
           If this value isn't provided the repository is
           cloned into the /tmp directory.
        update : bool
           Flag to determine if the repository is updated when loaded.
           Defaults to False.
        """
        if not directory:
            tmp = config.get("general", "git_default")
            directory = f"{tmp}/{name}"

            if os.path.exists(directory):
                return cls(directory, url, update=update)

            pathlib.Path(directory).mkdir(parents=True, exist_ok=True)

        # Replace an https address with an ssh address
        if "https" in url:
            url = url.replace("https://", "git@")
            final = "/".join(url.split("/")[1:])
            start = url.split("/")[0]

            url = f"{start}:{final}"

        try:
            repo = git.Repo.clone_from(url, directory)
        except git.exc.GitCommandError:
            repo = git.Repo(directory)
            try:
                try:
                    repo.git.stash()
                except git.exc.GitCommandError:
                    pass
                if update:
                    try:
                        repo.remotes[0].pull()
                    except git.exc.GitCommandError:
                        pass
            finally:
                repo.close()
        else:
            try:
                repo.git.execute(["git", "lfs", "install"])
                repo.git.execute(["git", "lfs", "fetch"])
                repo.git.execute(["git", "lfs", "pull"])
            except git.exc.GitCommandError:
                pass
            finally:
                repo.close()
        return cls(directory, url, update=update)

    def add_file(self, source, destination, commit_message=None):
        """
        Add a new file to the repository.

        Parameters
        ----------
        source : str, file path
           The path to the file to be added.
        destination : str
           The location to which the file should be copied in
           the repository, relative to the root of the repository.
           Any directories which do not exist already will be created.
        commit_message : str, optional
           The commit message for the git commit.
           Defaults to a description of the file addition.
        """

        self._ensure_initialised()
        destination_dir = os.path.dirname(destination)
        destination_dir = os.path.join(self.directory, destination_dir)
        pathlib.Path(destination_dir).mkdir(parents=True, exist_ok=True)

        destination_d = os.path.join(self.directory, destination)

        try:
            shutil.copyfile(source, destination_d)
        except shutil.SameFileError:
            pass

        if not self.git_enabled():
            return

        if not commit_message:
            commit_message = f"Added {destination}"

        with self._git() as repo:
            repo.git.add(destination)
            repo.git.commit("-m", commit_message)
            try:
                repo.git.push()
            except git.exc.GitCommandError as e:
                if "There is no tracking information for the current branch." in str(e):
                    pass
                elif (
                    "Either specify the URL from the command-line or configure a remote repository using"
                    in str(e)
                ):
                    pass
                else:
                    raise e

    def find_timefile(self, category=config.get("general", "calibration_directory")):
        """
        Find the time file in this repository.
        
        Parameters
        ----------
        category : str, optional
           The category directory to search in.
           Defaults to the value of "general/calibration_directory" from config.
        """

        self._ensure_initialised()
        with set_directory(os.path.join(self.directory, category)):
            try:
                gps_file = glob.glob("*gps*.txt")[0]
                return gps_file
            except IndexError:
                raise AsimovFileNotFound

    def find_coincfile(self, category=config.get("general", "calibration_directory")):
        """
        Find the coinc file for this calibration category in this repository.
        
        Parameters
        ----------
        category : str, optional
           The category directory to search in.
           Defaults to the value of "general/calibration_directory" from config.
        """
        self._ensure_initialised()
        coinc_file = glob.glob(
            os.path.join(os.getcwd(), self.directory, category, "*coinc*.xml")
        )

        if len(coinc_file) > 0:
            return coinc_file[0]
        else:
            raise AsimovFileNotFound

    def find_prods(
        self, name=None, category=config.get("general", "calibration_directory")
    ):
        """
        Find all of the productions for a relevant category of runs
        in the event repository.

        Parameters
        ----------
        name : str, optional
           The name of the production.
           If omitted then all production ini files are returned.
        category : str, optional
           The category of run. Defaults to the value of "general/calibration_directory" from config.
        """

        self.update_once()
        if category is not None:
            path = f"{os.path.join(os.getcwd(), self.directory, category)}/{name}.ini"
        else:
            category = "project_analyses"
            path = f"{os.path.join(os.getcwd(), self.directory)}/{name}.ini"

        return [path]

    def upload_prod(
        self,
        production,
        rundir,
        preferred=False,
        category=config.get("general", "calibration_directory"),
        rootdir="public_html/LVC/projects/O3/C01/",
        rename=False,
    ):
        """
        Upload the results of a PE job to the event repostory.

        Parameters
        ----------
        category : str, optional
           The category of the job.
           Defaults to the value of "general/calibration_directory" from config.
        production : str
           The production name.
        rundir : str
           The run directory of the PE job.
        """

        preferred_list = ["--preferred", "--append_preferred"]
        web_path = os.path.join(
            os.path.expanduser("~"), *rootdir.split("/"), self.event, production
        )  # TODO Make this generic
        if rename:
            prod_name = rename
        else:
            prod_name = production

        command = [
            config.get("pesummary", "location"),
            "--event",
            self.event,
            "--exp",
            prod_name,
            "--rundir",
            rundir,
            "--webdir",
            web_path,
            "--edit_homepage_table",
        ]
        if preferred:
            command += preferred_list
        dagman = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        )
        out, err = dagman.communicate()

        # Check if there was an error or if the push didn't succeed
        # Instead of checking for "master -> master", check for general push success
        if err:
            raise ValueError(f"Sample upload failed.\n{out}\n{err}")
        else:
            return out

    def update_once(self):
        """
        Pull the latest updates, but only the first time this is called.

        Looking up an analysis' files used to pull the repository every
        time, which means a ``checkout``, ``pull`` and ``git lfs fetch``
        (and so network access) per analysis. An EventRepo lives for the
        duration of a command, so one pull per instance is enough.
        """
        if not self._updated:
            self.update()

    def update(self, stash=False, branch=None):
        """
        Pull the latest updates to the repository.

        Does nothing if event git repositories are disabled
        (``[general] event_git = false``).

        Parameters
        ----------
        stash : bool, optional
           If true any changes which are in the local version
           of the repository are first stashed.
           Default is False.
        branch : str, optional
           The branch which should be checked-out.
           If not provided, uses the repository's default branch.
        """
        if not self.git_enabled():
            return

        if branch is None:
            branch = self.get_default_branch()

        with self._git() as repo:
            if stash:
                repo.git.stash()

            repo.git.checkout(branch)
            self._updated = True
            try:
                repo.git.pull()
                repo.git.execute(["git", "lfs", "fetch"])
            except git.exc.GitCommandError as e:
                if "There is no tracking information for the current branch." in str(e):
                    pass
                elif (
                    "Either specify the URL from the command-line or configure a remote repository using"
                    in str(e)
                ):
                    pass
                elif "Temporary failure in name resolution" in str(e):
                    logger.warning(f"Unable to update the repository for {self.event}")
                else:
                    raise e
