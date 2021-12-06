import configargparse

from dotenv import dotenv_values
from pathlib import Path
from pybfe.client.session import Session


def main(bf: Session, bf_network: str, snapshot_dir: str) -> None:
    bf.set_network(bf_network)
    bf.init_snapshot(snapshot_dir, name=Path(snapshot_dir).name)


if __name__ == "__main__":

    parser = configargparse.ArgParser()
    parser.add_argument("--snapshot",
                        help="Absolute path to snapshot directory or zip file", required=True)
    parser.add_argument("--settings", help="Batfish settings file", required=True)
    parser.add_argument("--access-token", help="Batfish Enterprise access token", required=True,
                        env_var="BF_ACCESS_TOKEN")

    args = parser.parse_args()
    snapshot_path = Path(args.snapshot)
    if not snapshot_path.exists():
        raise Exception(f"{snapshot_path} doesn't exist")
    elif not snapshot_path.is_dir():
        raise Exception(f"{snapshot_path} is not a directory")
    elif not Path.joinpath(snapshot_path, "configs").exists():
        raise Exception(f"configs folder not found in {snapshot_path}")

    # Read BF related ENV vars from the env file
    if not Path(args.settings).exists():
        raise Exception(f"Env file {args.settings} doesn't exist")
    settings = dotenv_values(args.settings)

    bf_host = settings.get('BF_HOST', None)
    bf_port = settings.get('BF_PORT', 443)
    bf_network = settings.get('BF_NETWORK', None)

    if bf_host is None:
        raise Exception(f"BF_HOST is not set in {args.settings}")
    if bf_network is None:
        raise Exception(f"BF_NETWORK is not set in {args.settings}")

    bf = Session(host=bf_host, port=bf_port, access_token=args.access_token)

    main(bf, bf_network, args.snapshot)
