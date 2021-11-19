import os
import sys

import configargparse
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from collection_helper import get_inventory, get_netmiko_os, write_output_to_file, \
    custom_logger, RetryingNetConnect

def get_config(
        device_session: dict, device_name: str, device_command: str, output_path: str, logger,
) -> None:

    cmd_timer = 240
    logger.info(f"Trying to connect to {device_name}")
    # todo: figure out to get logger name from the logger object that is passed in.
    #  current setup just uses the device name for the logger name, so this works
    net_connect = RetryingNetConnect(device_session, device_name)

    # Get the running config on the device
    logger.info(f"Running {device_command} on {device_name}")
    output = net_connect.run_command(device_command, cmd_timer)
    write_output_to_file(device_name, output_path, device_command, output)

    logger.info(f"Completed configuration collection for {device_name}")

OS_COLLECTOR_FUNCTION = {
    "arista_eos": get_config,
    "cisco_asa": get_config,
    "cisco_ios": get_config,
    "cisco_nxos": get_config,
    "cisco_xr": get_config,
    "juniper_junos": get_config,
}

OS_CONFIG_COMMAND = {
    "arista_eos": "show running-config",
    "cisco_asa": "show running-config",
    "cisco_ios": "show running-config",
    "cisco_nxos": "show running-config all",
    "cisco_xr": "show running-config",
    "juniper_junos": "show configuration",
}


def main():

    parser = configargparse.ArgParser()
    parser.add_argument("--inventory", help="Absolute path to inventory file to use", required=True)
    parser.add_argument("--username", help="username to access devices", required=True)
    parser.add_argument("--password", help="password to access devices", required=True)
    parser.add_argument("--max-threads", help="Max threads for parallel collection. Default = 10, Maximum is 100",
                        type=int, default=10, choices=range(10,101))
    parser.add_argument("--collection_dir", help="Directory for data collection", required=True)
    parser.add_argument("--snapshot_name", help="Name for the snapshot directory",
                        default=datetime.now().strftime("%Y%m%d %H:%M:%S"))

    args = parser.parse_args()

    log_level = logging.INFO

    # check if inventory file exists
    inv_file = args.inventory
    if Path(inv_file).exists():
        inventory = get_inventory(inv_file)
    else:
        raise Exception(f"{inv_file} does not exist")

    username = args.username
    password = args.password
    snapshot_name = args.snapshot_name

    collection_directory = args.collection_dir
    if not Path(collection_directory).exists():
        raise Exception(f"{collection_directory} does not exist. Please create the directory and re-run the script")

    max_threads = args.max_threads
    pool = ThreadPoolExecutor(max_threads)
    future_list = []

    start_time = datetime.now()
    print(f"###Starting collection: {start_time}")

    for grp, grp_data in inventory.items():
        # map ansible_network_os to netmike_os
        device_os = get_netmiko_os(grp_data['vars'].get('ansible_network_os'))
        # allow the use of same inventory for config and route collection, but skip all OSes except nxos, iosxr
        if device_os is None:
            # todo: setup global logger to log this message to, for now print will get it into the bash script logs
            print(f"Unsupported operating system {device_os}, skipping...")
            continue

        for device_name, _ in grp_data.get('hosts').items():
            log_file = f"{collection_directory}/logs/{snapshot_name}/{device_name}/collector.log"
            try:
                os.makedirs(os.path.dirname(log_file), exist_ok=True)
            except:
                exc_str = f"Could not create directory for log_file {log_file}"
                raise Exception(exc_str)

            logger = custom_logger(device_name, log_file, log_level)
            logger.info(f"Starting collection for {device_name}")
            logger.debug(f"Group {grp}, Group_data {grp_data}")

            # create device_session for netmiko connection handler
            device_session = {
                "device_type": device_os,
                "host": device_name,
                "username": username,
                "password": password,
                "session_log": f"{collection_directory}/logs/{snapshot_name}/{device_name}/netmiko_session.log",
                "fast_cli": False
            }

            output_path = f"{collection_directory}/{snapshot_name}/configs/"
            cfg_func = OS_COLLECTOR_FUNCTION.get(device_os)
            cfg_cmd = OS_CONFIG_COMMAND.get(device_os)
            if cfg_func is None:
                logger.error(f"No collection function for {device_name} running {device_os}")
            elif cfg_cmd is None:
                logger.error(f"No command set for {device_name} running {device_os}")
            else:
                future = pool.submit(cfg_func, device_session=device_session,
                                     device_name=device_name, device_command=cfg_cmd,
                                     output_path=output_path, logger=logger)
                future_list.append(future)

    count = 0
    for future in as_completed(future_list):
        # todo: revisit exception handling
        try:
            # todo: return more information from function to help error detection
            data = future.result()
        except Exception as exc:
            print(f"Exception generated: \n {exc}")

        print(f"Finished device number {count}")
        count += 1

    end_time = datetime.now()
    print(f"###Completed collection: {end_time}")
    print(f"###Total time taken: {end_time - start_time}")
    return snapshot_name

if __name__ == "__main__":

    snapshot_name = main()
    sys.exit(snapshot_name)
