import glob
import os
import pathlib
import shutil
import subprocess
import time

import git

from copy import copy

from asimov import config, logger
from asimov.utils import set_directory

from .ini import RunConfiguration


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

    def __init__(self, directory, url=None, update=False):
        self.event = directory.split("/")[-1]
        self.directory = directory
        self.update_needed = update
        self.repo = git.Repo(directory)
        self.url = url

        self.logger = logger

    def get_default_branch(self):
        """
        Get the default branch name for this repository.
        
        Returns
        -------
        str
            The name of the default branch (e.g., 'master', 'main')
        """
        try:
            # Try to get the remote's default branch
            if self.repo.remotes:
                remote = self.repo.remotes[0]
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
            if self.repo.head.is_valid():
                return self.repo.head.ref.name
            
            # Final fallback: try common names
            for branch_name in ['main', 'master']:
                try:
                    self.repo.git.rev_parse('--verify', branch_name)
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

        Parameters
        ----------
        location : str
           The location of the directory to be used.
        """
        directory = config.get("general", "calibration_directory")
        os.makedirs(location, exist_ok=True)
        try:
            # Try to create with 'main' as the initial branch (modern convention)
            repo = git.Repo.init(location, initial_branch="main")
        except (TypeError, git.exc.GitCommandError) as exc:
            # Fallback for older git versions that don't support initial_branch
            logger.warning(
                "Git version does not support 'initial_branch' when initializing "
                "repository at %s; falling back to default initial branch. "
                "Original error: %s",
                location,
                exc,
            )
            repo = git.Repo.init(location)
        os.makedirs(os.path.join(location, directory), exist_ok=True)
        with open(os.path.join(location, directory, ".gitkeep"), "w") as f:
            f.write(" ")
        repo.git.add(os.path.join(".", directory, ".gitkeep"))
        try:
            repo.git.commit("-m", "Initial commit")
        except git.exc.GitCommandError as e:
            if "working tree clean" in e.stdout:
                pass
        return cls(directory=location, url=location)

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
            repo.git.execute(["git", "lfs", "install"])
            repo.git.execute(["git", "lfs", "fetch"])
            repo.git.execute(["git", "lfs", "pull"])
        except git.exc.GitCommandError:
            repo = git.Repo(directory)
            try:
                repo.git.stash()
            except git.exc.GitCommandError:
                pass

        if update:
            try:
                repo.remotes[0].pull()
            except git.exc.GitCommandError:
                pass
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

        destination_dir = os.path.dirname(destination)
        destination_dir = os.path.join(self.directory, destination_dir)
        pathlib.Path(destination_dir).mkdir(parents=True, exist_ok=True)

        destination_d = os.path.join(self.directory, destination)

        try:
            shutil.copyfile(source, destination_d)
        except shutil.SameFileError:
            pass

        if not commit_message:
            commit_message = f"Added {destination}"

        self.repo.git.add(destination)
        self.repo.git.commit("-m", commit_message)
        try:
            self.repo.git.push()
            time.sleep(15)
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

        self.update()
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

    def upload_preferred(self, event, prods):
        """
        Prepare the preferred PESummary file by combining all of the
        productions for an event which are marked as `Preferred`
        or `Finalised`.

        Parameters
        ----------
        event : `asimov.event.Event`
           The event which the preferred upload is being prepared for.
        prods : list
           A list of all of the productions which should be included in the preferred file.
        """

        samples = []
        labels = []
        configs = []

        for prod in prods:
            samples.append(
                glob.glob(
                    str(
                        os.path.join(event.data[f"{prod}_rundir"], "posterior_samples"),
                    )
                    + "/*.hdf5"
                )[0]
            )
            run_ini = os.path.join(event.data[f"{prod}_rundir"], "config.ini")
            actual_config = RunConfiguration(run_ini)
            engine_data = actual_config.get_engine()
            labels.append(f"C01:{engine_data['approx']}")
            configs.append(
                str(os.path.join(event.data[f"{prod}_rundir"], "config.ini"))
            )

        with set_directory(
            os.path.join(self.directory, "Preferred", "PESummary_metafile")
        ):

            command = [
                "summarycombine",
                "--webdir",
                f"/home/daniel.williams/public_html/LVC/projects/O3/preferred/{event.title}",
                "--samples",
            ]
            command += samples
            command += ["--labels"]
            command += labels
            command += ["--config"]
            command += configs
            command += ["--gw"]

            dagman = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
            )
            out, err = dagman.communicate()

            self.logger.info(out)
            self.logger.error(err)

            copy(
                "/home/daniel.williams/public_html/LVC/projects/O3/"
                + f"preferred/{event.title}/samples/posterior_samples.h5",
                os.path.join(self.directory, "Preferred", "PESummary_metafile"),
            )
            self.repo.git.add("Preferred/PESummary_metafile/posterior_samples.h5")
            self.repo.git.commit("-m", "Updated the preferred sample metafile.")
            self.repo.git.push()
            time.sleep(15)

            event.labels += ["Preferred cleaned"]
            event.issue_object.save()

        return True

    def update(self, stash=False, branch=None):
        """
        Pull the latest updates to the repository.

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
        if stash:
            self.repo.git.stash()

        if branch is None:
            branch = self.get_default_branch()
            
        self.repo.git.checkout(branch)
        try:
            self.repo.git.pull()
            self.repo.git.execute(["git", "lfs", "fetch"])
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
