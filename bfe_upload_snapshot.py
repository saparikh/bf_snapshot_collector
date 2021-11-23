import configargparse
import os

from dotenv import dotenv_values
from pathlib import Path
from pybfe.client.session import Session

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
ENV_FILE = os.path.join(SCRIPT_DIR, "env")

if __name__ == "__main__":

    parser = configargparse.ArgParser()
    parser.add_argument("--snapshot",
                        help="Absolute path to snapshot directory or zip file", required=True)
    parser.add_argument("--network", help="name of the network to init snapshots in", default="MY_NETWORK")

    args = parser.parse_args()
    snapshot_path = args.snapshot
    if not Path(snapshot_path).exists():
        raise Exception(f"{snapshot_path} doesn't exist")
    elif not Path(snapshot_path).is_dir():
        raise Exception(f"{snapshot_path} is not a directory")
    elif not Path(f"{snapshot_path}/configs").exists():
        raise Exception(f"configs folder not found in {snapshot_path}")

    # Read BFE related ENV vars from the env file
    if not Path(ENV_FILE).exists():
        raise Exception(f"Env file {ENV_FILE} doesn't exist")
    config = dotenv_values(ENV_FILE)

    bfe_network = args.network
    bfe_host = config.get('BFE_HOST', None)
    bfe_port = config.get('BFE_PORT', 443)
    bfe_access_token = config.get('BFE_ACCESS_TOKEN', None)

    if bfe_host is None:
        raise Exception("BFE_HOST is not set in env file")
    if bfe_access_token is None:
        raise Exception("BFE_ACCESS_TOKEN is not set in env file")

    try:
        bf = Session(host=bfe_host, port=bfe_port, access_token=bfe_access_token)
    except Exception as e:
        raise Exception(f"Unable to connect to Batfish Enterprise server. Exception {e}")

    bf.set_network(bfe_network)
    print(f"Initializing snapshot in {snapshot_path}")

    snapshot_name = Path(snapshot_path).name
    snapshot = bf.init_snapshot(snapshot_path, name=snapshot_name)
