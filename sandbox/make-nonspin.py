from supervisor import gitlab, mattermost
from supervisor import config
from supervisor import condor, git
from supervisor.ini import RunConfiguration
import re, os
import shutil, pathlib


def get_psds_rundir(rundir):
    psds = {}
    dets = ['L1', 'H1', 'V1']
    for det in dets:
        asset = f"{rundir}/ROQdata/0/BayesWave_PSD_{det}/post/clean/glitch_median_PSD_forLI_{det}.dat"
        if os.path.exists(asset):
            psds[det] = asset
    return psds



# First, just check how many productions each event has, and build-up from there.

uber_repository = git.MetaRepository("/home/daniel.williams/events/O3/o3a_catalog_events")
server = gitlab.gitlab.Gitlab('https://git.ligo.org', private_token=config.get("gitlab", "token"))
repository = server.projects.get(3816)

events = gitlab.find_events(repository, milestone="PE: C01 Reruns")




for event in events:
    # if event.title in ["S190413ac", "S190503bf", "S190513bm",
    #                    "S190514n", "S190701ah", "S190720", "S190727h", 
    #                    "S190828l", "S190910s", "S190924h", "S190929d"]:
    #     continue

    if "Special" in event.labels:
        continue
    print(event.title)

    try:
        repo = uber_repository.get_repo(event.title)
    except:
        print(f"{event.title} missing from the uberrepo")
        continue

    default_branch = repo.get_default_branch()
    repo.repo.git.checkout(default_branch)
    repo.repo.git.pull()

    try:
        inis = repo.find_prods()
    except:
        continue

    #for ini in inis:
    #    if "nospin" in ini or "nonspin" in : continue

    nospin = None
    for prod in inis:
        configuration = RunConfiguration(prod)
        if configuration.check_fakecache():
            copy_prod = prod
        else:
            copy_prod = [ini for ini in inis if "Prod0" in ini][0]
        try:
            configuration.ini.get("engine", "disable-spin")
            nospin = True
        except:
            nospin = False
    if not nospin:
        print(event.title, copy_prod)
    else: 
        print(event.title, " This event already has a corrected production.")
        continue

    prods = {ini: int(re.search("Prod([\d]+)", str(ini.split("_"))).groups()[0]) for ini in inis}

    new_prod = (max(prods.values()))+1

    # I know this isn't always using Prod0 any more, cut me some slack, it's been a hectic month, future Daniel.
    prod0_ini = RunConfiguration(copy_prod)
    run_dir = event.data['Prod{}_rundir'.format(prods[copy_prod])]
    print(run_dir)
    psds = get_psds_rundir(run_dir)

    print(list(psds.keys()), prod0_ini.get_ifos())
    

    if set(psds.keys()) == set(prod0_ini.get_ifos()):
        #rint("This is ready to have an ini made")
        pass
    else:
        print("It looks liks some PSDs are still missing.")

    new_approximant = "IMRPhenomD"

    new_ini_loc = os.path.join(pathlib.Path(prod0_ini.ini_loc).parent.absolute(), f"Prod{new_prod}_IMRPhenomD_nospin.ini")
    new_ini = prod0_ini
    new_ini.ini_loc = new_ini_loc

    new_ini.update_webdir(event.title, rootdir = f"public_html/LVC/projects/O3/")
    new_ini.set_approximant("IMRPhenomD", amporder=prod0_ini.ini.get("engine", "amporder"),
                            fref=prod0_ini.ini.get("engine", "fref"))
    new_ini.update_psds(psds)
    new_ini.update_accounting()

    new_ini.ini.set("engine", "disable-spin", "")

    new_ini.save()

    repo.repo.git.add(new_ini_loc)
    repo.repo.git.commit(m=":robot: Added the new C01 Non-spinning config file.")
    repo.repo.git.push()
    

    #print(f"| C01 Prod{new_prod} | {new_approximant} | Offline C01 {
