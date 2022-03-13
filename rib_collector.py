import os
import time
from typing import Dict

import configargparse
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from collection_helper import (get_inventory, write_output_to_file, custom_logger, RetryingNetConnect,
                               CollectionStatus, AnsibleOsToNetmikoOs, parse_genie)


def get_nxos_rib(device_session: dict, device_name: str, output_path: str, logger) -> Dict:
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
        status['message'] = f"Connection failed. Exception {e}"
        status['failed_commands'].append("All")
        return status

    cmd_dict = {
        "global_ctx": {
            "routes": ["show ip route vrf all"],
            "bgp_local_rib": ["show bgp ipv4 unicast"],
            "bgp_neighbor": ["show bgp vrf all all summary"],
            "bgp_neighbor_ribs": [
                "show ip bgp neighbors _neigh_ routes",
                "show ip bgp neighbors _neigh_ received-routes",
                "show ip bgp neighbors _neigh_ advertised-routes",
            ]
        },
        "vrf_ctx": {
            "bgp_local_rib": ["show bgp vrf all ipv4 unicast"],
            "bgp_neighbor_ribs": [
                "show ip bgp vrf _vrf_ neighbors _neigh_ routes",
                "show ip bgp vrf _vrf_ neighbors _neigh_ received-routes",
                "show ip bgp vrf _vrf_ neighbors _neigh_ advertised-routes",
             ]
        }
    }

    # Get the VRF list on the device
    cmd = "show vrf all detail"
    logger.info(f"Running {cmd} on {device_name}")
    try:
        output = net_connect.run_command(cmd, 120)
    except Exception as e:
        status['message'] = f"Failed to get VRF list. Exception {e}"
        status['failed_commands'].append(cmd)
        logger.error(f"Failed to get VRF list")
    else:
        write_output_to_file(device_name, output_path, cmd, output)
        partial_collection = True

    # Get routing and bgp data for default vrf (aka global context)
    _cmd_dict = cmd_dict['global_ctx']
    bgp_neighbors = {}

    logger.info(f"Running show commands for default vrf on {device_name} at {time.time()}")
    for cmd_group, cmd_list in _cmd_dict.items():
        if cmd_group == "bgp_neighbor_ribs":
            if len(bgp_neighbors) == 0:
                logger.info(f"No bgp neighbors found for {device_name}")
                continue
            for vrf, vrf_details in bgp_neighbors['vrf'].items():
                if vrf == 'default':
                    for bgp_neighbor in vrf_details['neighbor'].keys():
                        if ":" not in bgp_neighbor:
                            for cmd in cmd_list:
                                _cmd = cmd.replace("_neigh_", bgp_neighbor)
                                logger.info(f"Running {_cmd} on {device_name}")
                                try:
                                    output = net_connect.run_command(_cmd, cmd_timer)
                                    logger.debug(f"Command output: {output}")
                                except Exception as e:
                                    status['message'] = f"{_cmd} was last command to fail. Exception {e}"
                                    status['failed_commands'].append(_cmd)
                                    logger.error(f"{_cmd} failed")
                                else:
                                    write_output_to_file(device_name, output_path, _cmd, output)
                                    partial_collection = True

        else:
            for cmd in cmd_list:
                logger.info(f"Running {cmd} on {device_name}")
                try:
                    output = net_connect.run_command(cmd, cmd_timer)
                    logger.debug(f"Command output: {output}")
                except Exception as e:
                    status['message'] = f"{cmd} was last command to fail. Exception {e}"
                    status['failed_commands'].append(cmd)
                    logger.error(f"{cmd} failed")
                else:
                    write_output_to_file(device_name, output_path, cmd, output)
                    partial_collection = True
                    # parse results of bgp neighbors
                    if cmd_group == "bgp_neighbor":
                        logger.info(f"Attempting to parse output of {cmd} on {device_name}")
                        parsed_output = parse_genie(device_name, output, cmd, device_os, logger)
                        logger.debug(f"Parsed Command output: {parsed_output}")
                        if parsed_output is not None:
                            bgp_neighbors = parsed_output

    # Get routing and bgp data for non-default vrf
    _cmd_dict = cmd_dict['vrf_ctx']
    bgp_neighbors = {}

    logger.info(f"Running show commands for non-default vrfs on {device_name} at {time.time()}")
    for cmd_group, cmd_list in _cmd_dict.items():
        if cmd_group == "bgp_neighbor_ribs":
            if len(bgp_neighbors) == 0:
                logger.info(f"No bgp neighbors found for {device_name}")
                continue
            for vrf, vrf_details in bgp_neighbors['vrf'].items():
                if vrf.lower() not in ['default', 'mgmt', 'management']:
                    for bgp_neighbor in vrf_details['neighbor'].keys():
                        if ":" not in bgp_neighbor:  # skip ipv6 peers
                            for cmd in cmd_list:
                                _cmd = cmd.replace("_neigh_", bgp_neighbor)
                                _cmd = _cmd.replace("_vrf_", vrf)
                                logger.info(f"Running {_cmd} on {device_name}")
                                try:
                                    output = net_connect.run_command(_cmd, cmd_timer)
                                    logger.debug(f"Command output: {output}")
                                except Exception as e:
                                    status['message'] = f"{_cmd} was last command to fail. Exception {e}"
                                    status['failed_commands'].append(_cmd)
                                    logger.error(f"{_cmd} failed")
                                else:
                                    write_output_to_file(device_name, output_path, _cmd, output)
                                    partial_collection = True

        else:
            for cmd in cmd_list:
                logger.info(f"Running {cmd} on {device_name}")
                try:
                    output = net_connect.run_command(cmd, cmd_timer)
                    logger.debug(f"Command output: {output}")
                except Exception as e:
                    status['message'] = f"{cmd} was last command to fail. Exception {e}"
                    status['failed_commands'].append(cmd)
                    logger.error(f"{cmd} failed")
                else:
                    write_output_to_file(device_name, output_path, cmd, output)
                    partial_collection = True
                    # parse results of bgp neighbors
                    if cmd_group == "bgp_neighbor":
                        logger.info(f"Attempting to parse output of {cmd} on {device_name}")
                        parsed_output = parse_genie(device_name, output, cmd, device_os, logger)
                        logger.debug(f"Parsed Command output: {parsed_output}")
                        if parsed_output is not None:
                            bgp_neighbors = parsed_output

    end_time = time.time()
    logger.info(f"Completed RIB collection for {device_name} in {end_time-start_time:.2f} seconds")
    if len(status['failed_commands']) == 0:
        status['status'] = CollectionStatus.PASS
        status['message'] = "Collection successful"
    elif partial_collection:
        status['status'] = CollectionStatus.PARTIAL
        status['message'] = "Collection partially successful"

    return status


def get_xr_rib(device_session: dict, device_name: str, output_path: str, logger) -> Dict:
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
        status['message'] = f"Connection failed. Exception {e}"
        status['failed_commands'].append("All")
        logger.error(f"Connection failed")
        return status

    cmd_dict = {
        "global_ctx": {
            "bgp_neighbor": ["show bgp all all neighbors"],
            "routes": ["show route summary", "show route"],
            "bgp_local_rib": ["show bgp ipv4 unicast", "show bgp vpnv4 unicast"],
            "bgp_neighbor_ribs": [
                "show bgp ipv4 all neighbors _neigh_ advertised-routes",
                "show bgp ipv4 all neighbors _neigh_ routes",
                "show bgp ipv4 all neighbors _neigh_ received routes"
            ]
        },
        "vrf_ctx": {
            "bgp_neighbor": ["show bgp vrf all neighbors"],
            "routes": ["show route vrf all summary", "show route vrf all"],
            "bgp_local_rib": ["show bgp vrf all"],
            "bgp_neighbor_ribs": [
                "show bgp vrf _vrf_ ipv4 unicast neighbors _neigh_ advertised-routes",
                "show bgp vrf _vrf_ ipv4 unicast neighbors _neigh_ routes",
                "show bgp vrf _vrf_ ipv4 unicast neighbors _neigh_ received routes",
             ]
        }
    }

    # Get the VRF list on the device
    cmd = "show vrf all detail"
    logger.info(f"Running {cmd} on {device_name}")
    try:
        output = net_connect.run_command(cmd, 120)
    except Exception as e:
        status['message'] = f"Failed to get VRF list. Exception {e}"
        status['failed_commands'].append(cmd)
        logger.error(f"Failed to get VRF list")

    else:
        write_output_to_file(device_name, output_path, cmd, output)
        partial_collection = True

    # Get routing and bgp data for default vrf (aka global context)
    _cmd_dict = cmd_dict['global_ctx']
    bgp_neighbors = {}

    logger.info(f"Running show commands for default vrf on {device_name} at {time.time()}")
    for cmd_group, cmd_list in _cmd_dict.items():
        if cmd_group == "bgp_neighbor_ribs":
            if len(bgp_neighbors) == 0:
                logger.info(f"No bgp neighbors found for {device_name}")
                continue
            for vrf, vrf_details in bgp_neighbors['instance']['all']['vrf'].items():
                for bgp_neighbor in vrf_details['neighbor'].keys():
                    if ":" not in bgp_neighbor: # skip ipv6 peers
                        for cmd in cmd_list:
                            _cmd = cmd.replace("_neigh_", bgp_neighbor)
                            logger.info(f"Running {_cmd} on {device_name}")
                            try:
                                output = net_connect.run_command(_cmd, cmd_timer)
                                logger.debug(f"Command output: {output}")
                            except Exception as e:
                                status['message'] = f"{_cmd} was last command to fail. Exception {e}"
                                status['failed_commands'].append(_cmd)
                                logger.error(f"{_cmd} failed")
                            else:
                                write_output_to_file(device_name, output_path, _cmd, output)
                                partial_collection = True

        else:
            for cmd in cmd_list:
                logger.info(f"Running {cmd} on {device_name}")
                try:
                    output = net_connect.run_command(cmd, cmd_timer)
                    logger.debug(f"Command output: {output}")
                except Exception as e:
                    status['message'] = f"{cmd} was last command to fail. Exception {e}"
                    status['failed_commands'].append(cmd)
                    logger.error(f"{cmd} failed")
                else:
                    write_output_to_file(device_name, output_path, cmd, output)
                    partial_collection = True
                    # parse results of bgp neighbors
                    if cmd_group == "bgp_neighbor":
                        logger.info(f"Attempting to parse output of {cmd} on {device_name}")
                        parsed_output = parse_genie(device_name, output, cmd, device_os, logger)
                        logger.debug(f"Parsed Command output: {parsed_output}")
                        if parsed_output is not None:
                            bgp_neighbors = parsed_output

    # Get routing and bgp data for non-default vrf
    _cmd_dict = cmd_dict['vrf_ctx']
    bgp_neighbors = {}

    logger.info(f"Running show commands for non-default vrfs on {device_name} at {time.time()}")
    for cmd_group, cmd_list in _cmd_dict.items():
        if cmd_group == "bgp_neighbor_ribs":
            if len(bgp_neighbors) == 0:
                logger.info(f"No bgp neighbors found for {device_name}")
                continue
            for vrf, vrf_details in bgp_neighbors['instance']['all']['vrf'].items():
                if vrf.lower() in ["mgmt", "management", "default"]:
                    continue
                for bgp_neighbor in vrf_details['neighbor'].keys():
                    if ":" not in bgp_neighbor: # skip ipv6 peers
                        for cmd in cmd_list:
                            _cmd = cmd.replace("_neigh_", bgp_neighbor)
                            _cmd = _cmd.replace("_vrf_", vrf)
                            logger.info(f"Running {_cmd} on {device_name}")
                            try:
                                output = net_connect.run_command(_cmd, cmd_timer)
                                logger.debug(f"Command output: {output}")
                            except Exception as e:
                                status['message'] = f"{_cmd} was last command to fail. Exception {e}"
                                status['failed_commands'].append(_cmd)
                                logger.error(f"{_cmd} failed")
                            else:
                                write_output_to_file(device_name, output_path, _cmd, output)
                                partial_collection = True

        else:
            for cmd in cmd_list:
                logger.info(f"Running {cmd} on {device_name}")
                try:
                    output = net_connect.run_command(cmd, cmd_timer)
                    logger.debug(f"Command output: {output}")
                except Exception as e:
                    status['message'] = f"{cmd} was last command to fail. Exception {e}"
                    status['failed_commands'].append(cmd)
                    logger.error(f"{cmd} failed")
                else:
                    write_output_to_file(device_name, output_path, cmd, output)
                    partial_collection = True
                    # parse results of bgp neighbors
                    if cmd_group == "bgp_neighbor":
                        logger.info(f"Attempting to parse output of {cmd} on {device_name}")
                        parsed_output = parse_genie(device_name, output, cmd, device_os, logger)
                        logger.debug(f"Parsed Command output: {parsed_output}")
                        if parsed_output is not None:
                            bgp_neighbors = parsed_output

    end_time = time.time()
    logger.info(f"Completed RIB collection for {device_name} in {end_time-start_time:.2f} seconds")
    if len(status['failed_commands']) == 0:
        status['status'] = CollectionStatus.PASS
        status['message'] = "Collection successful"
    elif partial_collection:
        status['status'] = CollectionStatus.PARTIAL
        status['message'] = "Collection partially successful"

    return status


OS_COLLECTOR_FUNCTION = {
    "cisco_nxos": get_nxos_rib,
    "cisco_xr": get_xr_rib,
}


def main(inventory: Dict, max_threads: int, username: str, password: str, snapshot_name: str,
         collection_directory: str, log_level: int) -> None:
    pool = ThreadPoolExecutor(max_threads)
    future_list = []

    start_time = time.time()
    print(f"### Starting RIB collection: {time.strftime('%Y-%m-%d %H:%M %Z', time.localtime(start_time))}")

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
            cfg_func = OS_COLLECTOR_FUNCTION.get(device_os)
            if cfg_func is None:
                logger.error(f"No collection function for {device_name} running {device_os}")
            else:
                future = pool.submit(cfg_func, device_session=device_session, device_name=device_name,
                                     output_path=output_path, logger=logger)
                future_list.append(future)

    # TODO: revisit exception handling
    failed_devices = [future.result()['name'] for future in as_completed(future_list) if
                      future.result()['status'] != CollectionStatus.PASS]

    end_time = time.time()

    if len(failed_devices) != 0:
        print(f"### RIB Collection failed for {len(failed_devices)} devices: {failed_devices}")

    print(f"### Completed RIB collection: {time.strftime('%Y-%m-%d %H:%M %Z', time.localtime(end_time))}")
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
         log_level)
