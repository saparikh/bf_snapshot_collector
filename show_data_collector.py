import os
import time
from typing import Dict

import configargparse
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from collection_helper import (get_inventory, write_output_to_file, custom_logger, RetryingNetConnect,
                               CollectionStatus, AnsibleOsToNetmikoOs, get_show_commands, parse_genie)


def get_show_data(device_session: dict, device_name: str, output_path: str, cmd_dict: dict, logger) -> Dict:
    """
    Show command collector for all operating systems
    """
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

    logger.info(f"Running show commands for {device_name} at {time.time()}")

    for cmd_group in cmd_dict.keys():
        cmd_timer = 240     # set the general command timeout to 4 minutes

        if cmd_group == "bgp_v4":
            # todo: if you need per-neighbor RIB collection, write an OS specific function modeled after get_nxos_data
            # todo: if VRF specific BGP data collection requires vrf name in command, write an OS specific function
            # the generic show_data function will just grab BGP neighbors, summary, and RIBs for default and
            # named VRF
            cmd_timer = 1200  # set BGP command timer to 20 minutes
            cmd_list = []

            for scope, scope_cmds in cmd_dict['bgp_v4'].items():
                if scope not in ["global", "vrf"]:
                    logger.error(f"Unknown {scope} with commands {scope_cmds} under bgp_v4 command dict")
                    continue
                for subscope, cmds in scope_cmds.items():
                    if subscope == "neighbor_ribs":
                        logger.error(f"BGP neighbor RIB collection not supported on {device_name}")
                        continue
                    else:
                        cmd_list.extend(cmds)
        # handle global and vrf specific IPv4 route commands
        elif cmd_group == "routes_v4":
            cmd_timer = 1200  # set the RIB command timeout to 20 minutes
            cmd_list = []
            for scope, cmds in cmd_dict['routes_v4'].items():
                cmd_list.extend(cmds)
        else:
            cmd_list = cmd_dict.get(cmd_group)

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

    end_time = time.time()
    logger.info(f"Completed operational data collection for {device_name} in {end_time-start_time:.2f} seconds")
    if len(status['failed_commands']) == 0:
        status['status'] = CollectionStatus.PASS
        status['message'] = "Collection successful"
    elif partial_collection:
        status['status'] = CollectionStatus.PARTIAL
        status['message'] = "Collection partially successful"

    try:
        net_connect.close()
    except Exception as e:
        logger.exception(f"Exception when closing netmiko connection: {str(e)}")
        pass
    return status


def get_nxos_data(device_session: dict, device_name: str, output_path: str, cmd_dict: dict, logger) -> Dict:
    """
    Show data collection for Cisco NXOS devices.
    """
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

    logger.info(f"Running show commands for {device_name} at {time.time()}")

    for cmd_group in cmd_dict.keys():
        cmd_timer = 240     # set the general command timeout to 4 minutes

        if cmd_group == "bgp_v4":
            # need to get the list of BGP neighbors per VRF in order to collect per neighbor RIBs
            # The  mechanism for this is to run the command "show bgp vrf all all summary" and
            # use Cisco Genie parser to extract the list of { vrf, bgp_neighbor } maps
            #
            # rather than rely on this command being in the command list, if there are any commands
            # under "bgp_v4", we will run this command.
            #
            cmd = "show bgp vrf all all summary"
            cmd_timer = 300     # set BGP neighbor command timeout to 5 minutes
            bgp_neighbors = {}
            cmd_list = []
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
                logger.info(f"Attempting to parse output of {cmd} on {device_name}")
                parsed_output = parse_genie(device_name, output, cmd, device_os, logger)
                logger.debug(f"Parsed Command output: {parsed_output}")
                if parsed_output is not None:
                    bgp_neighbors = parsed_output
                partial_collection = True

            cmd_timer = 1200  # set the BGP RIB command timeout to 20 minutes

            for scope, scope_cmds in cmd_dict['bgp_v4'].items():
                if scope == "global":
                    for subscope, cmds in scope_cmds.items():
                        if subscope == "neighbor_ribs":
                            if len(bgp_neighbors) == 0:
                                logger.info(f"No bgp neighbors found for {device_name}")
                                continue
                            for vrf, vrf_details in bgp_neighbors['vrf'].items():
                                if vrf == 'default':
                                    for bgp_neighbor in vrf_details['neighbor'].keys():
                                        if ":" not in bgp_neighbor:
                                            for cmd in cmds:
                                                _cmd = cmd.replace("_neigh_", bgp_neighbor)
                                                cmd_list.append(_cmd)
                        else:
                            cmd_list.extend(cmds)
                elif scope == "vrf":
                    for subscope, cmds in scope_cmds.items():
                        if subscope == "neighbor_ribs":
                            if len(bgp_neighbors) == 0:
                                logger.info(f"No bgp neighbors found for {device_name}")
                                continue
                            for vrf, vrf_details in bgp_neighbors['vrf'].items():
                                # ignore default VRF since it is already taken care of
                                # ignore management VRF - mgmt and management are common names for it
                                if vrf.lower() not in ['default', 'mgmt', 'management']:
                                    for bgp_neighbor in vrf_details['neighbor'].keys():
                                        if ":" not in bgp_neighbor:
                                            for cmd in cmds:
                                                _cmd = cmd.replace("_neigh_", bgp_neighbor)
                                                _cmd = _cmd.replace("_vrf_", vrf)
                                                cmd_list.append(_cmd)
                        else:
                            cmd_list.extend(cmds)
                else:
                    logger.error(f"Unknown {scope} with commands {scope_cmds} under bgp_v4 command dict")
        # handle global and vrf specific IPv4 route commands
        elif cmd_group == "routes_v4":
            cmd_timer = 1200  # set the RIB command timeout to 20 minutes
            cmd_list = []
            for scope, cmds in cmd_dict['routes_v4'].items():
                cmd_list.extend(cmds)
        else:
            cmd_list = cmd_dict.get(cmd_group)

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

    end_time = time.time()
    logger.info(f"Completed operational data collection for {device_name} in {end_time-start_time:.2f} seconds")
    if len(status['failed_commands']) == 0:
        status['status'] = CollectionStatus.PASS
        status['message'] = "Collection successful"
    elif partial_collection:
        status['status'] = CollectionStatus.PARTIAL
        status['message'] = "Collection partially successful"

    try:
        net_connect.close()
    except Exception as e:
        logger.exception(f"Exception when closing netmiko connection: {str(e)}")
        pass
    return status


def get_xr_data(device_session: dict, device_name: str, output_path: str, cmd_dict: dict, logger) -> Dict:
    """
    Show data collector for Cisco IOS-XR devices.
    """
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

    logger.info(f"Running show commands for {device_name} at {time.time()}")

    for cmd_group in cmd_dict.keys():
        cmd_timer = 240     # set the general command timeout to 4 minutes

        if cmd_group == "bgp_v4":
            # need to get the list of BGP neighbors per VRF in order to collect per neighbor RIBs
            # need to run a command for default VRF "show bgp all all neighbors" and one for non-default
            # VRFs "show bgp vrf all neighbors" and then parse the output using Cisco genie parser
            #
            # rather than rely on these commands being in the command list, if there are any commands
            # under "bgp_v4", we will run this command.
            #
            # get BGP neighbors for default VRF
            cmd_timer = 300     # set BGP neighbor command timeout to 5 minutes
            global_bgp_neighbors = {}
            vrf_bgp_neighbors = {}
            cmd_list = []

            # get BGP neighbors for default VRF
            cmd = "show bgp all all neighbors"
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
                logger.info(f"Attempting to parse output of {cmd} on {device_name}")
                parsed_output = parse_genie(device_name, output, cmd, device_os, logger)
                logger.debug(f"Parsed Command output: {parsed_output}")
                if parsed_output is not None:
                    global_bgp_neighbors = parsed_output
                partial_collection = True

            # get BGP neighbors for non-default VRFs
            cmd = "show bgp vrf all neighbors"
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
                logger.info(f"Attempting to parse output of {cmd} on {device_name}")
                parsed_output = parse_genie(device_name, output, cmd, device_os, logger)
                logger.debug(f"Parsed Command output: {parsed_output}")
                if parsed_output is not None:
                    vrf_bgp_neighbors = parsed_output
                partial_collection = True

            cmd_timer = 1200  # set the BGP RIB command timeout to 20 minutes

            for scope, scope_cmds in cmd_dict['bgp_v4'].items():
                if scope == "global":
                    for subscope, cmds in scope_cmds.items():
                        if subscope == "neighbor_ribs":
                            if len(global_bgp_neighbors) == 0:
                                logger.info(f"No bgp neighbors found for default VRF on {device_name}")
                                continue
                            for vrf, vrf_details in global_bgp_neighbors['instance']['all']['vrf'].items():
                                for bgp_neighbor in vrf_details['neighbor'].keys():
                                    if ":" not in bgp_neighbor:  # skip ipv6 peers
                                        for cmd in cmds:
                                            _cmd = cmd.replace("_neigh_", bgp_neighbor)
                                            cmd_list.append(_cmd)
                        else:
                            cmd_list.extend(cmds)
                elif scope == "vrf":
                    for subscope, cmds in scope_cmds.items():
                        if subscope == "neighbor_ribs":
                            if len(vrf_bgp_neighbors) == 0:
                                logger.info(f"No bgp neighbors found for non default VRFs on {device_name}")
                                continue
                            for vrf, vrf_details in vrf_bgp_neighbors['instance']['all']['vrf'].items():
                                # ignore default VRF since it is already taken care of
                                # ignore management VRF - mgmt and management are common names for it
                                if vrf.lower() in ["mgmt", "management", "default"]:
                                    continue
                                for bgp_neighbor in vrf_details['neighbor'].keys():
                                    if ":" not in bgp_neighbor:  # skip ipv6 peers
                                        for cmd in cmds:
                                            _cmd = cmd.replace("_neigh_", bgp_neighbor)
                                            _cmd = _cmd.replace("_vrf_", vrf)
                                            cmd_list.append(_cmd)
                        else:
                            cmd_list.extend(cmds)
                else:
                    logger.error(f"Unknown {scope} with commands {scope_cmds} under bgp_v4 command dict")
        # handle global and vrf specific IPv4 route commands
        elif cmd_group == "routes_v4":
            cmd_timer = 1200  # set the RIB command timeout to 20 minutes
            cmd_list = []
            for scope, cmds in cmd_dict['routes_v4'].items():
                cmd_list.extend(cmds)
        else:
            cmd_list = cmd_dict.get(cmd_group)

        for cmd in cmd_list:
            logger.info(f"Running {cmd} from {cmd_group} on {device_name}")
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

    try:
        net_connect.close()
    except Exception as e:
        logger.exception(f"Exception when closing netmiko connection: {str(e)}")
        pass
    return status


OS_SHOW_COLLECTOR_FUNCTION = {
    "a10": get_show_data,
    "arista_eos": get_show_data,
    "checkpoint_gaia": get_show_data,
    "cisco_asa": get_show_data,
    "cisco_ios": get_show_data,
    "cisco_nxos": get_nxos_data,
    "cisco_xr": get_xr_data,
    "juniper_junos": get_show_data
}


def main(inventory: Dict, max_threads: int, username: str, password: str, snapshot_name: str,
         collection_directory: str, commands_file: str, log_level: int) -> None:
    pool = ThreadPoolExecutor(max_threads)
    future_list = []

    start_time = time.time()
    print(f"### Starting operational data collection: {time.strftime('%Y-%m-%d %H:%M %Z', time.localtime(start_time))}")

    commands = None
    if commands_file is not None:
        commands = get_show_commands(commands_file)

    for grp, grp_data in inventory.items():
        device_os = AnsibleOsToNetmikoOs.get(grp_data['vars'].get('ansible_network_os'), None)

        if device_os is None:
            # todo: setup global logger to log this message to, for now print will get it into the bash script logs
            print(f"Unsupported Ansible OS {grp_data['vars'].get('ansible_network_os')}, skipping...")
            continue

        op_func = OS_SHOW_COLLECTOR_FUNCTION.get(device_os)
        if op_func is None:
            print(f"No collection function for {device_os}, skipping...")
            continue

        cmd_dict = commands.get(grp, None)
        if cmd_dict is None:
            print(f"No command dictionary for devices in {grp}, skipping...")
            continue

        for device_name, device_vars in grp_data.get('hosts').items():
            log_file = f"{collection_directory}/logs/{snapshot_name}/{device_name}/show_data_collector.log"
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
            future = pool.submit(op_func, device_session=device_session, device_name=device_name,
                                 output_path=output_path, cmd_dict=cmd_dict, logger=logger)
            future_list.append(future)

    # TODO: revisit exception handling
    failed_devices = [future.result()['name'] for future in as_completed(future_list) if
                      future.result()['status'] != CollectionStatus.PASS]

    end_time = time.time()

    if len(failed_devices) != 0:
        print(f"### Operational data collection failed for {len(failed_devices)} devices: {failed_devices}")

    print(f"### Completed operational data collection: {time.strftime('%Y-%m-%d %H:%M %Z', time.localtime(end_time))}")
    print(f"### Total operational data collection time: {end_time - start_time} seconds")


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
    parser.add_argument("--command-file", help="YAML file with list of commands per OS", default=None)
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
         args.command_file, log_level)
