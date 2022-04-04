import os
import time
from typing import Dict
import re

import configargparse
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import netmiko.exceptions

from collection_helper import (get_inventory, write_output_to_file, custom_logger, RetryingNetConnect,
                               CollectionStatus, CollectionFailureReason, AnsibleOsToNetmikoOs, a10_parse_version)


def get_config(device_session: dict, device_name: str, device_command: str, output_path: str, logger) -> Dict:
    """
    Default config collector. Works for Cisco and Juniper devices.
    """
    cmd_timer = 240
    logger.info(f"Trying to connect to {device_name}")
    status = {
        "name": device_name,
        "status": CollectionStatus.FAIL,
        "reason": CollectionFailureReason.OTHER,
        "message": "",
    }
    # todo: figure out to get logger name from the logger object that is passed in.
    #  current setup just uses the device name for the logger name, so this works
    try:
        net_connect = RetryingNetConnect(device_name, device_session, device_name)
    except netmiko.exceptions.NetmikoTimeoutException as e:
        status['message'] = f"Connection failed. Exception {e}"
        status['reason'] = CollectionFailureReason.CONNECT_TIMEOUT
        return status
    except netmiko.exceptions.NetmikoAuthenticationException as e:
        status['message'] = f"Connection failed. Exception {e}"
        status['reason'] = CollectionFailureReason.AUTH
        return status
    except netmiko.exceptions.ReadTimeout as e:
        status['message'] = f"Connection failed. Exception {e}"
        status['reason'] = CollectionFailureReason.READ_TIMEOUT
        return status
    except Exception as e:
        status['message'] = f"Connection failed. Exception {e}"
        return status

    try:
        # Get the running config on the device
        logger.info(f"Running {device_command} on {device_name}")
        output = net_connect.run_command(device_command, cmd_timer)
        write_output_to_file(device_name, output_path, device_command, output)
    except Exception as e:
        status['message'] = f"Config retrieval failed. Exception {e}"
        return status

    logger.info(f"Completed configuration collection for {device_name}")
    status['status'] = CollectionStatus.PASS
    status['message'] = "Collection successful"
    return status


def get_config_eos(device_session: dict, device_name: str, device_command: str, output_path: str, logger) -> Dict:
    cmd_timer = 240
    logger.info(f"Trying to connect to {device_name}")
    status = {
        "name": device_name,
        "status": CollectionStatus.FAIL,
        "reason": CollectionFailureReason.OTHER,
        "message": "",
    }
    # todo: figure out to get logger name from the logger object that is passed in.
    #  current setup just uses the device name for the logger name, so this works
    try:
        net_connect = RetryingNetConnect(device_name, device_session, device_name)
        net_connect.enable()
    except netmiko.exceptions.NetmikoTimeoutException as e:
        status['message'] = f"Connection failed. Exception {e}"
        status['reason'] = CollectionFailureReason.CONNECT_TIMEOUT
        return status
    except netmiko.exceptions.NetmikoAuthenticationException as e:
        status['message'] = f"Connection failed. Exception {e}"
        status['reason'] = CollectionFailureReason.AUTH
        return status
    except netmiko.exceptions.ReadTimeout as e:
        status['message'] = f"Connection failed. Exception {e}"
        status['reason'] = CollectionFailureReason.READ_TIMEOUT
        return status
    except Exception as e:
        status['message'] = f"Connection failed. Exception {e}"
        return status

    try:
        # Get the running config on the device
        logger.info(f"Running {device_command} on {device_name}")
        output = net_connect.run_command(device_command, cmd_timer)
        write_output_to_file(device_name, output_path, device_command, output)
    except Exception as e:
        status['message'] = f"Config retrieval failed. Exception {e}"
        return status

    logger.info(f"Completed configuration collection for {device_name}")
    status['status'] = CollectionStatus.PASS
    status['message'] = "Collection successful"
    return status


def get_config_cumulus(device_session: dict, device_name: str, device_command: str, output_path: str, logger) -> Dict:
    cmd_timer = 240
    logger.info(f"Trying to connect to {device_name}")
    status = {
        "name": device_name,
        "status": CollectionStatus.FAIL,
        "reason": CollectionFailureReason.OTHER,
        "message": "",
    }
    # todo: figure out to get logger name from the logger object that is passed in.
    #  current setup just uses the device name for the logger name, so this works
    try:
        net_connect = RetryingNetConnect(device_name, device_session, device_name)
    except netmiko.exceptions.NetmikoTimeoutException as e:
        status['message'] = f"Connection failed. Exception {e}"
        status['reason'] = CollectionFailureReason.CONNECT_TIMEOUT
        return status
    except netmiko.exceptions.NetmikoAuthenticationException as e:
        status['message'] = f"Connection failed. Exception {e}"
        status['reason'] = CollectionFailureReason.AUTH
        return status
    except netmiko.exceptions.ReadTimeout as e:
        status['message'] = f"Connection failed. Exception {e}"
        status['reason'] = CollectionFailureReason.READ_TIMEOUT
        return status
    except Exception as e:
        status['message'] = f"Connection failed. Exception {e}"
        return status

    output = ""
    try:
        logger.info(f"Running 'cat /etc/hostname' on {device_name}")
        output += net_connect.run_command("cat /etc/hostname", cmd_timer)
        output += "\n"

        logger.info(f"Running 'cat /etc/network/interfaces' on {device_name}")
        output += "# This file describes the network interfaces\n"
        output += net_connect.run_command("cat /etc/network/interfaces", cmd_timer)
        output += "\n"

        logger.info(f"Running 'cat /etc/cumulus/ports.conf' on {device_name}")
        output += "# ports.conf --\n"
        output += net_connect.run_command("cat /etc/cumulus/ports.conf", cmd_timer)
        output += "\n"

        logger.info(f"Running 'cat /etc/frr/frr.conf' on {device_name}")
        output += "frr version\n"
        output += net_connect.run_command("cat /etc/frr/frr.conf", cmd_timer)
        output += "\n"
    except Exception as e:
        status['message'] = f"Config retrieval failed. Exception {e}"
        return status

    write_output_to_file(device_name, output_path, "cumulus_concatenated.txt", output)

    logger.info(f"Completed configuration collection for {device_name}")
    status['status'] = CollectionStatus.PASS
    status['message'] = "Collection successful"
    return status


def get_config_a10(
        device_session: dict, device_name: str, device_command: str, output_path: str, logger) -> Dict:
    """
    A10 Loadbalancer config collector.
    """
    cmd_timer = 240
    logger.info(f"Trying to connect to {device_name}")
    status = {
        "name": device_name,
        "status": CollectionStatus.FAIL,
        "reason": CollectionFailureReason.OTHER,
        "message": "",
    }
    # todo: figure out to get logger name from the logger object that is passed in.
    #  current setup just uses the device name for the logger name, so this works
    try:
        net_connect = RetryingNetConnect(device_name, device_session, device_name)
    except netmiko.exceptions.NetmikoTimeoutException as e:
        status['message'] = f"Connection failed. Exception {e}"
        status['reason'] = CollectionFailureReason.CONNECT_TIMEOUT
        return status
    except netmiko.exceptions.NetmikoAuthenticationException as e:
        status['message'] = f"Connection failed. Exception {e}"
        status['reason'] = CollectionFailureReason.AUTH
        return status
    except netmiko.exceptions.ReadTimeout as e:
        status['message'] = f"Connection failed. Exception {e}"
        status['reason'] = CollectionFailureReason.READ_TIMEOUT
        return status
    except Exception as e:
        status['message'] = f"Connection failed. Exception {e}"
        return status

    cmd_dict = {
        "v2_config": ["show running-config all-partitions"],
        "v4p_config": ["show running-config partition-config all"],
        "unknown_config": ["show running-config with-default"],
    }

    A10_PROMPT_REGEX_TRAILER = r"(-\w+)?(.*[#>])\s*$"

    # set default partition list to empty
    partitions = []

    # set the prompt pattern for Netmiko to use
    prompt_pattern = fr"({device_name}){A10_PROMPT_REGEX_TRAILER}"
    logger.info(f"Using {prompt_pattern} to find device prompt")

    # get the ACOS version to determine which command to run to get device configuration with partitions
    cmd = "show version"
    logger.info(f"Running {cmd} on {device_name}")
    try:
        output = net_connect.run_command(cmd, cmd_timer, pattern=prompt_pattern)
    except Exception as e:
        logger.exception(f"Failed to get output of {cmd}, going to sleep 10 minutes and retry")
        time.sleep(600)
        # reconnect to the device and run the command again
        try:
            net_connect = RetryingNetConnect(device_name, device_session, device_name)
            output = net_connect.run_command(cmd, cmd_timer, pattern=prompt_pattern)
        except Exception as e:
            logger.exception(f"Retry for show version failed")
            status['message'] = f"Connection failed. Exception {e}"
            return status
        else:
            logger.debug(f"Command output: {output}")
    else:
        logger.debug(f"Command output: {output}")

    if output is None:
        logger.error(f"Failed to get output for {cmd}")
        cfg_version = "unknown"
    else:
        cfg_version = a10_parse_version(output)

    # get the configuration commands
    logger.info(f"Getting configuration for {device_name}")
    cmd_list = cmd_dict.get(f"{cfg_version}_config", None)
    if cmd_list is None:
        logger.error(f"No configuration command mapped for version {cfg_version}")
        return status
    for cmd in cmd_list:
        logger.info(f"Running {cmd} on {device_name}")
        output = net_connect.run_command(cmd, cmd_timer, pattern=prompt_pattern)
        # trying to catch scenario in which netmiko doesn't return complete config
        if output is None:
            logger.error(f"Didn't retrieve any part of the config")
            return status
        if "end" not in output.strip().splitlines()[-1]:
            # certain versions have end as the 2nd to last line and the below line is the last line
            if "Current config commit point for partition 0 is 0 & config mode is classical-mode" not in output.strip().splitlines()[-1]:
                logger.error(f"Didn't retrieve full config file")
                status['message'] = "Collection failed, only got partial A10 configuration"
                return status

        logger.debug(f"Command output: {output}")
        write_output_to_file(device_name, output_path, cmd, output, "!BATFISH_FORMAT: a10_acos")

    logger.info(f"Completed configuration collection for {device_name}")
    status['status'] = CollectionStatus.PASS
    status['message'] = "Collection successful"
    return status

def get_config_checkpoint(device_session: dict, device_name: str, device_command: str, output_path: str, logger) -> Dict:
    """
    Checkpoint Gateway config collector.
    """
    cmd_timer = 240
    logger.info(f"Trying to connect to {device_name}")
    status = {
        "name": device_name,
        "status": CollectionStatus.FAIL,
        "reason": CollectionFailureReason.OTHER,
        "message": "",
    }
    # todo: figure out to get logger name from the logger object that is passed in.
    #  current setup just uses the device name for the logger name, so this works
    try:
        net_connect = RetryingNetConnect(device_name, device_session, device_name)
    except netmiko.exceptions.NetmikoTimeoutException as e:
        status['message'] = f"Connection failed. Exception {e}"
        status['reason'] = CollectionFailureReason.CONNECT_TIMEOUT
        return status
    except netmiko.exceptions.NetmikoAuthenticationException as e:
        status['message'] = f"Connection failed. Exception {e}"
        status['reason'] = CollectionFailureReason.AUTH
        return status
    except netmiko.exceptions.ReadTimeout as e:
        status['message'] = f"Connection failed. Exception {e}"
        status['reason'] = CollectionFailureReason.READ_TIMEOUT
        return status
    except Exception as e:
        status['message'] = f"Connection failed. Exception {e}"
        return status

    # set the correct prompt for netmiko to use
    # prompts can be of the following formats with optional trailing space at the end:
    #
    # name>
    # [Global] name-ch01-01>
    # [Global] name-ch02-01 >
    # name:TACP-0>
    # name#
    # [Global] name-ch01-01#
    # [Global] name-ch02-01 #
    # name:TACP-0#
    #
    CP_PROMPT_EXTRACT = f"(.*){device_name}" + r"(?P<trailer>.*)"
    pattern = re.compile(CP_PROMPT_EXTRACT, re.IGNORECASE)
    m = re.match(pattern, net_connect._base_prompt)

    prompt_pattern = None
    if m is not None:
        if m.group("trailer") is not None:
            prompt_pattern = f"{device_name}{m.group('trailer')}[>|#]\s*$"
        else:
            prompt_pattern = f"{device_name}[>|#]\s*$"

    logger.info(f"Using {prompt_pattern} to find device prompt")

    try:
        # Get the running config on the device
        logger.info(f"Running {device_command} on {device_name}")
        output = net_connect.run_command(device_command, cmd_timer, pattern=prompt_pattern)
        write_output_to_file(device_name, output_path, device_command, output, "#BATFISH_FORMAT: check_point_gateway")

    except Exception as e:
        status['message'] = f"Config retrieval failed. Exception {e}"
        return status

    logger.info(f"Completed configuration collection for {device_name}")
    status['status'] = CollectionStatus.PASS
    status['message'] = "Collection successful"
    return status


OS_COLLECTOR_FUNCTION = {
    "arista_eos": get_config_eos,
    "a10": get_config_a10,
    "checkpoint_gaia": get_config_checkpoint,
    "cisco_asa": get_config,
    "cisco_ios": get_config,
    "cisco_nxos": get_config,
    "cisco_xr": get_config,
    "juniper_junos": get_config,
    "linux": get_config_cumulus,
}

OS_CONFIG_COMMAND = {
    "arista_eos": "show running-config",
    "a10": "ignore",
    "checkpoint_gaia": "show configuration",
    "cisco_asa": "show running-config",
    "cisco_ios": "show running-config",
    "cisco_nxos": "show running-config all",
    "cisco_xr": "show running-config",
    "juniper_junos": "show configuration | display set",
    "linux": "ignore",
}


def main(inventory: Dict, max_threads: int, username: str, password: str, snapshot_name: str,
         collection_directory: str, log_level: int) -> None:
    pool = ThreadPoolExecutor(max_threads)
    future_list = []

    start_time = time.time()
    print(f"Starting snapshot collection {time.strftime('%Y-%m-%d %H:%M %Z', time.localtime(start_time))}")

    for grp, grp_data in inventory.items():
        device_os = AnsibleOsToNetmikoOs.get(grp_data['vars'].get('ansible_network_os'), None)
        if device_os is None:
            # todo: setup global logger to log this message to, for now print will get it into the bash script logs
            print(f"Unsupported Ansible OS {grp_data['vars'].get('ansible_network_os')}, skipping...")
            continue

        for device_name, device_vars in grp_data.get('hosts').items():
            log_file = f"{collection_directory}/logs/{snapshot_name}/{device_name}/collector.log"
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

            output_path = f"{collection_directory}/{snapshot_name}/configs/"
            cfg_func = OS_COLLECTOR_FUNCTION.get(device_os)
            cfg_cmd = OS_CONFIG_COMMAND.get(device_os)
            if cfg_func is None:
                logger.error(f"No collection function for {device_name} running {device_os}")
            elif cfg_cmd is None:
                logger.error(f"No command set for {device_name} running {device_os}")
            else:
                future = pool.submit(cfg_func, device_session=device_session, device_name=device_name,
                                     device_command=cfg_cmd, output_path=output_path, logger=logger)
                future_list.append(future)

    # TODO: revisit exception handling
    failed_devices = {
        CollectionFailureReason.NO_FAILURE: [],
        CollectionFailureReason.AUTH: [],
        CollectionFailureReason.READ_TIMEOUT: [],
        CollectionFailureReason.CONNECT_TIMEOUT: [],
        CollectionFailureReason.OTHER: []
    }
    any_failures = False

    for future in as_completed(future_list):
        if future.result()['status'] != CollectionStatus.PASS:
            any_failures = True
            reason = future.result()['reason']
            failed_devices[reason].append(future.result()['name'])

    # failed_devices = [future.result()['name'] for future in as_completed(future_list) if
    #                   future.result()['status'] != CollectionStatus.PASS]
    # if len(failed_devices) != 0:
    #     print(f"Collection failed for {len(failed_devices)} devices: {failed_devices}")


    end_time = time.time()

    if any_failures:
        print(f"Collection failed for devices: \n {failed_devices}")

    print(f"Completed snapshot collection {time.strftime('%Y-%m-%d %H:%M %Z', time.localtime(end_time))}")
    print(f"Total collection time {end_time - start_time} seconds")

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
