import os
import time
from typing import Dict

import configargparse
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from collection_helper import (get_inventory, write_output_to_file, custom_logger, RetryingNetConnect,
                               CollectionStatus, AnsibleOsToNetmikoOs)


def get_nxos_data(device_session: dict, device_name: str, output_path: str, commands: list, logger) -> Dict:
    """
    Default config collector. Works for Cisco and Juniper devices.
    """
    cmd_timer = 1200
    device_os = "nxos"  # used for cisco genie parsers
    start_time = time.time()
    logger.info(f"Trying to connect to {device_name} at {start_time}")
    status = {
        "name": device_name,
        "status": CollectionStatus.FAIL,
        "failed_commands": [],
        "message": "",
    }

    partial_collection = False

    # todo: figure out to get logger name from the logger object that is passed in.
    #  current setup just uses the device name for the logger name, so this works
    try:
        net_connect = RetryingNetConnect(device_name, device_session, device_name)
    except Exception as e:
        status['message'] = f"Connection failed. Exception {str(e)}"
        status['failed_commands'].append("All")
        return status

    cmd_dict = {
        "topology": ["show lldp neighbors detail, show cdp neighbors detail"],
        "version": ["show version"],
        "interface": ["show interface", "show interface snmp-ifindex", "show ip interface vrf all brief"],
        "ospf": ["show ip ospf neighbor"]
    }

    logger.info(f"Running show commands for {device_name} at {time.time()}")

    # if user doesn't pass in command tags, then grab all the data
    if commands is None:
        for cmd_group, cmd_list in cmd_dict.items():
            for cmd in cmd_list:
                logger.info(f"Running {cmd} on {device_name}")
                try:
                    output = net_connect.run_command(cmd, cmd_timer)
                    logger.debug(f"Command output: {output}")
                except Exception as e:
                    status['message'] = f"{cmd} was last command to fail. Exception {str(e)}"
                    status['failed_commands'].append(cmd)
                    logger.error(f"{cmd} failed")
                else:
                    write_output_to_file(device_name, output_path, cmd, output)
                    partial_collection = True
    else:
        # just grab the data for the command groups the user requested
        for cmd in commands:
            logger.info(f"Running {cmd} on {device_name}")
            try:
                output = net_connect.run_command(cmd, cmd_timer)
                logger.debug(f"Command output: {output}")
            except Exception as e:
                status['message'] = f"{cmd} was last command to fail. Exception {str(e)}"
                status['failed_commands'].append(cmd)
                logger.error(f"{cmd} failed")
            else:
                write_output_to_file(device_name, output_path, cmd, output)
                partial_collection = True

    end_time = time.time()
    logger.info(f"Completed operational data collection for {device_name} in {end_time-start_time:.2f} seconds")
    if len(status['failed_commands']) == 0:
        status['status'] = CollectionStatus.PASS
        status['message'] = "Collection successful"
    elif partial_collection:
        status['status'] = CollectionStatus.PARTIAL
        status['message'] = "Collection partially successful"

    net_connect.close()
    return status


def get_xr_data(device_session: dict, device_name: str, output_path: str, commands: list, logger) -> Dict:
    """
    Default config collector. Works for Cisco and Juniper devices.
    """
    cmd_timer = 1200
    device_os = "iosxr"  # used for cisco genie parsers
    start_time = time.time()
    logger.info(f"Trying to connect to {device_name} at {start_time}")
    status = {
        "name": device_name,
        "status": CollectionStatus.FAIL,
        "failed_commands": [],
        "message": "",
    }

    partial_collection = False

    # todo: figure out to get logger name from the logger object that is passed in.
    #  current setup just uses the device name for the logger name, so this works
    try:
        net_connect = RetryingNetConnect(device_name, device_session, device_name)
    except Exception as e:
        status['message'] = f"Connection failed. Exception {str(e)}"
        status['failed_commands'].append("All")
        logger.error(f"Connection failed")
        return status

    cmd_dict = {
        "topology": ["show lldp neighbors detail, show cdp neighbors detail"],
        "version": ["show version"],
        "interface": ["show interfaces", "show snmp interface"],
        "ospf": ["show ospf", "show ospf vrf all", "show ospf neighbor"]
    }

    logger.info(f"Running show commands for {device_name} at {time.time()}")

    # if user doesn't pass in command tags, then grab all the data
    if commands is None:
        for cmd_group, cmd_list in cmd_dict.items():
            for cmd in cmd_list:
                logger.info(f"Running {cmd} on {device_name}")
                try:
                    output = net_connect.run_command(cmd, cmd_timer)
                    logger.debug(f"Command output: {output}")
                except Exception as e:
                    status['message'] = f"{cmd} was last command to fail. Exception {str(e)}"
                    status['failed_commands'].append(cmd)
                    logger.error(f"{cmd} failed")
                else:
                    write_output_to_file(device_name, output_path, cmd, output)
                    partial_collection = True
    else:
        # just grab the data for the command groups the user requested
        for cmd in commands:
            logger.info(f"Running {cmd} on {device_name}")
            try:
                output = net_connect.run_command(cmd, cmd_timer)
                logger.debug(f"Command output: {output}")
            except Exception as e:
                status['message'] = f"{cmd} was last command to fail. Exception {str(e)}"
                status['failed_commands'].append(cmd)
                logger.error(f"{cmd} failed")
            else:
                write_output_to_file(device_name, output_path, cmd, output)
                partial_collection = True

    end_time = time.time()
    logger.info(f"Completed operational data collection for {device_name} in {end_time - start_time:.2f} seconds")
    if len(status['failed_commands']) == 0:
        status['status'] = CollectionStatus.PASS
        status['message'] = "Collection successful"
    elif partial_collection:
        status['status'] = CollectionStatus.PARTIAL
        status['message'] = "Collection partially successful"

    net_connect.close()
    return status


OS_SHOW_COLLECTOR_FUNCTION = {
    "cisco_nxos": get_nxos_data,
    "cisco_xr": get_xr_data
}


def main(inventory: Dict, max_threads: int, username: str, password: str, snapshot_name: str,
         collection_directory: str, commands_file: str, log_level: int) -> None:
    pool = ThreadPoolExecutor(max_threads)
    future_list = []

    start_time = time.time()
    print(f"### Starting operational data collection: {time.strftime('%Y-%m-%d %H:%M %Z', time.localtime(start_time))}")

    if commands_file is not None:
        print("Passing in list of commands per OS not supported yet")

    for grp, grp_data in inventory.items():
        device_os = AnsibleOsToNetmikoOs.get(grp_data['vars'].get('ansible_network_os'), None)
        if device_os is None:
            # todo: setup global logger to log this message to, for now print will get it into the bash script logs
            print(f"Unsupported operating system {device_os}, skipping...")
            continue

        for device_name, device_vars in grp_data.get('hosts').items():
            log_file = f"{collection_directory}/logs/{snapshot_name}/{device_name}/rib_collector.log"
            os.makedirs(os.path.dirname(log_file), exist_ok=True)

            logger = custom_logger(device_name, log_file, log_level)
            logger.info(f"Starting collection for {device_name}")
            logger.info(f"Device vars are {device_vars}")

            # by default use the device name specified in inventory
            _host = device_name
            # override it with the IP address if specified in the inventory
            if device_vars is not None and device_vars.get("ansible_host", None) is not None:
                _host = device_vars.get("ansible_host")
                logger.info(f"Using IP {_host} to connect to {device_name}")

            # create device_session for netmiko connection handler
            device_session = {
                "device_type": device_os,
                "host": _host,
                "username": username,
                "password": password,
                "session_log": f"{collection_directory}/logs/{snapshot_name}/{device_name}/netmiko_session.log",
                "fast_cli": False
            }

            output_path = f"{collection_directory}/{snapshot_name}/show/"
            op_func = OS_SHOW_COLLECTOR_FUNCTION.get(device_os)
            if op_func is None:
                logger.error(f"No collection function for {device_name} running {device_os}")
            else:
                future = pool.submit(op_func, device_session=device_session, device_name=device_name,
                                     output_path=output_path, commands=None, logger=logger)
                future_list.append(future)

    # TODO: revisit exception handling
    failed_devices = [future.result()['name'] for future in as_completed(future_list) if
                      future.result()['status'] != CollectionStatus.PASS]

    end_time = time.time()

    if len(failed_devices) != 0:
        print(f"### Operational data collection failed for {len(failed_devices)} devices: {failed_devices}")

    print(f"### Completed operational data collection: {time.strftime('%Y-%m-%d %H:%M %Z', time.localtime(end_time))}")
    print(f"### Total RIB collection time: {end_time - start_time} seconds")


if __name__ == "__main__":
    parser = configargparse.ArgParser()
    parser.add_argument("--inventory", help="Absolute path to inventory file to use", required=True)
    parser.add_argument("--username", help="Username to access devices", required=True, env_var="BF_COLLECTOR_USER")
    parser.add_argument("--password", help="Password to access devices", required=True, env_var="BF_COLLECTOR_PASSWORD")
    parser.add_argument("--max-threads", help="Max threads for parallel collection. Default = 10, Maximum is 100",
                        type=int, default=10)
    parser.add_argument("--collection-dir", help="Directory for data collection", required=True)
    parser.add_argument("--snapshot-name", help="Name for the snapshot directory",
                        default=datetime.now().strftime("%Y%m%d_%H:%M:%S"))
    parser.add_argument("--command-list", help="JSON file with list of commands per OS", default=None)
    parser.add_argument("--log-level", help="Log level", default="warn")

    args = parser.parse_args()

    log_level = logging._nameToLevel.get(args.log_level.upper())
    if not log_level:
        raise Exception("Invalid log level: {}".format(args.log_level))

    # check if inventory file exists
    if not Path(args.inventory).exists():
        raise Exception(f"{args.inventory} does not exist")
    inventory = get_inventory(args.inventory)

    if not Path(args.collection_dir).exists():
        raise Exception(f"{args.collection_dir} does not exist. Please create the directory and re-run the script")

    main(inventory, args.max_threads, args.username, args.password, args.snapshot_name, args.collection_dir,
         args.command_list, log_level)
