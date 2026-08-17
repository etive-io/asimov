import ast

from supervisor import gitlab, mattermost
from supervisor import config
from supervisor import condor, git
from supervisor.ini import RunConfiguration

import os, glob, datetime

import otter

server = gitlab.gitlab.Gitlab('https://git.ligo.org', private_token=config.get("gitlab", "token"))
repository = server.projects.get(3816)

def get_psds_rundir(rundir):
    psds = {}
    dets = ['L1', 'H1', 'V1']
    for det in dets:
        asset = f"{rundir}/ROQdata/0/BayesWave_PSD_{det}/post/clean/glitch_median_PSD_forLI_{det}.dat"
        if os.path.exists(asset):
            psds[det] = asset
    return psds

def upload_results(repo, event, prod, preferred=False, rename=None):
    try:
        repo.upload_prod(prod, event.data[f"{prod}_rundir"], preferred, rename)
    except ValueError as e:
        if "already in table" in str(e):
            print("Already uploaded.")
        else:
            status = "Upload error"
            return False
    if preferred:
        event.data[f'{prod}'] = "Finalised"
    else:
        event.data[f"{prod}"] = "Uploaded"
        
    event.update_data()
    mattermost.send_message(f":mega: {event.title} {prod} has been uploaded. :robot:", "o3a-catalog-paper")
    mattermost.send_message(f":mega: {event.title} {prod} has been uploaded. :robot:")
    return True

def start_dag(event, repo, prod, psd_prod="Prod0"):
    psds_dict = get_psds_rundir(event.data[f'{psd_prod}_rundir'])

    try:
        repo.build_dag("analyses", prod, psds_dict)
        status = "DAG ready"
    except ValueError as e:
        status = "ini error"
        print(e)

    try: 
        cluster = repo.submit_dag("analyses", prod)
        job = condor.CondorJob(cluster)
        event.data[prod] = cluster
        event.data[f"{prod}_rundir"] = f"/home/daniel.williams/events/O3/o3a_catalog/{event.title}/analyses/"+job.run_directory
        event.update_data()
        event.state = "Productions running"
    except ValueError as e:
        status = "Submission error"
        print(e)
        cluster = None
        job = None
    return cluster, status, job

uber_repository = git.MetaRepository("/home/daniel.williams/events/O3/o3a_catalog_events")

events = gitlab.find_events(repository, milestone="PE: C01 Reruns")

mattermost = mattermost.Mattermost()

mattermost.send_message(":mega: The run supervising robot is running. :robot:", "@daniel-williams")

report = otter.Otter(filename="/home/daniel.williams/public_html/LVC/projects/O3/C01/summary.html", 
                     author="R. Daniel Williams",
                     title="Asimov/Olivaw : Event supervision report"
)

with report:
    report + "This report contains the latest updates on the run status of the various PE runs ongoing at CIT."
    report + "Supervisor last checked these events at " + str(datetime.datetime.now())

message = """# Run updates\n"""
message += """| Event | Gitlab State | Run state | Production | Approx | Sampler | Status |\n"""
message += """|---|---|---|---|---|---|\n"""


for event in events:
    print(event.title)
    status = None
    table = []
    table_header = ["Event", "Production", "Status", "Approximant", "F_low", "IFOs", "dtype", "fake"]

    
    if event.state == None:
        continue
    #if "Special" in event.labels:
    #    continue

    if "DAQ::Needs BW" in event.labels and not (event.state in ["Ready to start", "Productions running"]):
        continue

    try:
        repo = uber_repository.get_repo(event.title)
    except:
        print(f"{event.title} missing from the uberrepo")
        continue

    repo.update(stash=True)

    with report:
        report + f"#{event.title}"
    

    try:
        event_prods = repo.find_prods("analyses")
    except:
        print(f"No C01 runs in this repository")
        continue
    
    event_psds = set(["L1", "H1", "V1"])

    if event.state == "Ready to start":
        print(f"I'm going to try to start {event.title}")
        cluster, status, job = start_dag(event, repo, prod)

    elif event.state in ["Generating PSDs", "Productions running", "Stuck"]:
        psds_dict = {}
        prod_keys = [key for key in event.data.keys() if "Prod" in key[0:5]]
        n_productions = len(event_prods)
        event_psds_l = []
        for prod in event_prods:

            prod = prod.split("_")[0]
            event_config = RunConfiguration(prod)

            
            if prod in event.data:
                cluster = event.data[prod]
                print(f"{prod}")

                if "start" in cluster.lower(): 
                    # This production is not running at the moment
                    # But it has been marked ready to start
                    if "Prod0" in event.data:
                        prod0_ini = RunConfiguration([ini for ini in event_prods if "Prod0" in ini][0])
                        ifos = prod0_ini.get_ifos()
                        prod0_run_dir = event.data[f"Prod0_rundir"]
                        psds = get_psds_rundir(prod0_run_dir)
                    else:
                        prod0_status = None
                        ifos = ["None"]
                        psds = []
                    if (set(ifos) == set(psds)) or (set(event_config.get_psds.keys()) == set(ifos)):
                        cluster, status, job = start_dag(event, repo, prod)
                    else:
                        status = "Not ready"
                        cluster = None
                        ifos = "Unknown"
                        psds = ""


                elif "blocked" not in cluster.lower():
                    run_ini = os.path.join(event.data[f"{prod}_rundir"], "config.ini")
                    actual_config = RunConfiguration(run_ini)
                    engine_data = actual_config.get_engine()
                    sampler = actual_config.ini.get("analysis", "engine")
                    flow = actual_config.ini.get("lalinference", "flow")
                    datatypes = actual_config.ini.get("datafind", "types")
                    psds = actual_config.get_psds()
                    try:
                        if actual_config.ini.get("lalinference", "fake-cache"): datasource = "✔️"
                    except: 
                        datasource = "❌"
                    ifos = actual_config.get_ifos()
                    event_psds_l.append([prod,psds])
                    table.append([event.title, prod, cluster, engine_data['approx'], flow, ifos, datatypes, datasource])

                if "preferred" in cluster.lower():
                    if upload_results(repo, event, prod, preferred=True, rename = f"C01:{engine_data['approx']}"):
                        n_productions -= 1
                    else:
                        continue
                    

                if "stopped" in cluster.lower():
                    n_productions -= 1
                    status = "Manually cancelled"
                    continue

                elif "stuck" in cluster.lower():
                    status = "Stuck"
                    continue

                elif cluster.lower() == "blocked":
                    status = "Blocked"
                    continue

                elif cluster.lower() == "uploaded":
                    status = "Uploaded"
                    n_productions -= 1

                elif cluster.lower() == "restart":
                    status = "Restarting"
                    cluster, status, job = start_dag(event, repo, prod)

                elif cluster.lower() == "manualupload":
                    continue
                
                elif cluster.lower() == "finished":
                    # Upload the event data
                    if upload_results(repo, event, prod):
                        n_productions -= 1
                    else:
                        print(f"Error uploading production {prod}")
                        continue


                else:
                    # This event is meant to be running normally, 
                    # let's check up on it

                    try:
                        job = condor.CondorJob(event.data[prod])
                        status = job.status
                    except ValueError:
                        # There seems to be a problem finding this job, let's 
                        # work out if it's finished or stuck

                        rundir = event.data[f"{prod}_rundir"]
                        if (cluster.lower() != "uploaded") and (cluster.lower() != "manualupload") and (len(glob.glob(f"{rundir}/posterior_samples/*.hdf5"))>0):
                            event.add_label(f"{prod} finished")

                            event.data[f"{prod}"] = "Finished"
                            event.update_data()
                            continue

                        elif not "stuck" in cluster.lower():
                            print(f"Problem with {event.title} production {prod}")
                            event.state = "Stuck"
                            event.add_note(f"An unknown error has been encountered with {prod}")
                            mattermost.send_message(f":mega: I've run into a problem with {event.title} {prod}. :robot:")
                            event.data[f"{prod}"] = event.data[f"{prod}"] + "# Stuck"
                            event.update_data()
                            status = "Not running"
                            ifos = "Unknown"
                            continue
                    except RuntimeError:
                        pass

                    if status in ['Removed', 'Held', 'Submission error', 'Unexplained']:
                        event.state = "Stuck"
                        event.data[f"{prod}"] = event.data[f"{prod}"] + "# Stuck"
                        event.update_data()

                    run_dir = event.data[f"{prod}_rundir"]
                    prod0_run_dir = event.data[f"Prod0_rundir"]
                    prod0_ini = RunConfiguration([ini for ini in event_prods if "Prod0" in ini][0])
                    ifos = prod0_ini.get_ifos()
                    psds = get_psds_rundir(prod0_run_dir)
                    event_psds = set(ifos) - set(psds)
                    #else:
                    if (set(ifos)==set(psds)) and event.state != "Stuck":
                        event.state = "Productions running"
                    else:
                        status = status + " waiting on PSDs {}".format(event_psds)
            
            message += f"""| {event.title} | {event.state} | {cluster} | {prod} | {engine_data['approx']} | {sampler} | {status} | \n"""

        with report:
            report + f"{n_productions} still running"

            report + "## Productions summary"
            report + otter.html.tabulate.tabulate(table, tablefmt=otter.html.MyHTMLFormat, headers=table_header)
            report + "## PSD summary"
            report + otter.html.tabulate.tabulate(event_psds_l, tablefmt=otter.html.MyHTMLFormat)
            report + "##Samples summary"

        if n_productions == 0:
            event.state = "Runs complete"
        else:
            print(f"\t{n_productions} still running.")


mattermost.submit_payload(message)
