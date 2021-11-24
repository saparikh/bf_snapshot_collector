import os
import socket
import sys
from time import sleep
from typing import Text, Dict
import logging
import yaml
from netmiko import ConnectHandler
from enum import Enum


class CollectionStatus(Enum):
    PASS = 1
    FAIL = 2


AnsibleOsToNetmikoOs = {
    "arista.eos.eos": "arista_eos",
    "cisco.asa.asa": "cisco_asa",
    "cisco.iosxr.iosxr": "cisco_xr",
    "cisco.nxos.nxos": "cisco_nxos",
    "cisco.ios.ios": "cisco_ios",
    "juniper.junos.junos": "juniper_junos",
    "cumulus": "linux",
}


class RetryingNetConnect(object):

    def __init__(self, device_session, logger_name):
        self._device_session = device_session
        self._logger = logging.getLogger(logger_name)
        try:
            self._net_connect = ConnectHandler(**self._device_session, encoding='utf-8')
        except Exception as exc:
            self._logger.error(f"Exception: {exc}")
            raise Exception

    def run_command(self, cmd, cmd_timer, pattern=None):
        try:
            self._logger.info(f"Using {pattern} as expect_string")
            _output = self._net_connect.send_command(cmd, read_timeout=cmd_timer, strip_command=True,
                                                     expect_string=pattern)
        except socket.error as exc:
            self._logger.error(f"Command {cmd} failed: {exc}")
            # re-establish a new SSH session for other commands
            try:
                self._net_connect = ConnectHandler(**self._device_session, encoding='utf-8')
            except Exception as exc:
                self._logger.error(f"Could not reconnect to device: {exc}")
                raise Exception
            else:
                try:
                    self._logger.error("Connection re-established, re-trying previous command")
                    _output = self._net_connect.send_command(cmd, read_timeout=cmd_timer, strip_command=True)
                except Exception as exc:
                    self._logger.error(f"Command {cmd} failed: {exc}")
                    sleep(60)
                    return None
                else:
                    return _output
        except Exception as exc:
            self._logger.error(f"Command {cmd} failed: {exc}")
            sleep(60)
            pass
        else:
            self._logger.debug(f"Command output: {_output}")
            return _output

    def enable(self):
        try:
            self._net_connect.enable()
        except Exception as exc:
            self._logger.error(f"Failed to enter enable mode: {exc}")
            pass


def custom_logger(logger_name, log_file, level=logging.DEBUG):
    """
    Method to return a custom logger with the given name and level
    """
    logger = logging.getLogger(logger_name)
    logger.setLevel(level)
    format_string = '%(levelname)s:%(asctime)s %(message)s'
    datefmt_string = '%m/%d/%Y %I:%M:%S %p'
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

    if inventory.get("all") is None or inventory['all'].get('children') is None:
        raise Exception(f"{inventory_file} is not properly formatted")

    return inventory['all']['children']


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
