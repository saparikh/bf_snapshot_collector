import os
import sys
from typing import List, Text, Dict
import logging
import yaml
from netmiko import ConnectHandler


class RetryingNetConnect(object):

    def __init__(self, device_session, logger_name):
        self._device_session = device_session
        self._logger = logging.getLogger(logger_name)
        try:
            self._net_connect = ConnectHandler(**device_session)
        except Exception as exc:
            self._logger.error(f"Skipped data collection, could not connect")
            self._logger.error(f"Exception: {exc}")
            raise Exception

    def run_command(self, cmd, cmd_timer):
        try:
            _output = self._net_connect.send_command(cmd, read_timeout=cmd_timer, strip_command=True)
        except socket.error as exc:
            self._logger.error(f"Socket error: {exc}\n")
            self._logger.error(f"Command {cmd} failed, skipping it")
            self._logger.error("Trying to reconnect to allow other commands to run")
            # re-establish a new SSH session
            try:
                self._net_connect = ConnectHandler(**self._device_session)
            except Exception as exc:
                self._logger.error(f"Cannot continue data collection for this device, could not reconnect")
                self._logger.error(f"Exception: {exc}")
                raise Exception
            else:
                try:
                    self._logger.error("Connection re-established, re-trying previous command")
                    _output = self._net_connect.send_command(cmd, read_timeout=cmd_timer, strip_command=True)
                except Exception as exc:
                    self._logger.error(f"Command {cmd} failed")
                    self._logger.error(f"Exception: {exc}")
                    sleep(60)
                    return None
                else:
                    return _output
        except Exception as exc:
            self._logger.error(f"Command {cmd} failed")
            self._logger.error(f"Exception: {exc}")
            sleep(60)
            pass
        else:
            self._logger.debug(f"Command output: {_output}")
            return _output

    def enable(self):
        try:
            self._net_connect.enable()
        except Exception as exc:
            self._logger.error(f"Failed to enter enable mode")
            self._logger.error(f"Exception: {exc}")
            pass


def custom_logger(logger_name, log_file, level=logging.INFO):
    """
    Method to return a custom logger with the given name and level
    """
    logger = logging.getLogger(logger_name)
    logger.setLevel(level)
    format_string = '%(asctime)s %(message)s'
    datefmt_string ='%m/%d/%Y %I:%M:%S %p'
    log_format = logging.Formatter(fmt=format_string, datefmt=datefmt_string)
    # Creating and adding the console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(log_format)
    logger.addHandler(console_handler)
    # Creating and adding the file handler
    file_handler = logging.FileHandler(log_file, mode='a')
    file_handler.setFormatter(log_format)
    logger.addHandler(file_handler)
    return logger


def get_inventory(inventory_file: Text) -> Dict:

    with open(inventory_file) as f:
        inventory = yaml.safe_load(f)

    if inventory.get("all") is None:
        raise Exception(f"{inventory_file} exists, but is not properly formatted")

    if inventory['all'].get('children') is None:
        raise Exception(f"{inventory_file} exists, but is not properly formatted")

    return inventory['all']['children']


def get_netmiko_os(device_os: Text) -> Text:
    """
    netmiko device os mapping
    """

    ansible_netmiko_map = {
        "arista.eos.eos": "arista_eos",
        "cisco.asa.asa": "cisco_asa",
        "cisco.iosxr.iosxr": "cisco_xr",
        "cisco.nxos.nxos": "cisco_nxos",
        "cisco.ios.ios": "cisco_ios",
        "juniper.junos.junos": "juniper_junos",
        "cumulus": "linux",
    }

    return ansible_netmiko_map.get(device_os, None)



def write_output_to_file(
        device_name: Text, output_path: Text, cmd: Text, cmd_output: Text,
):
    """
    Save show commands output to it's file
    """
    file_name = cmd.replace(" ", "_")
    file_path = output_path + "/" + device_name + "/" + file_name + ".txt"

    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "w") as f:
        f.write(cmd_output)