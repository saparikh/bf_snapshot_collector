import os
import socket
import sys
from time import sleep
from typing import Text, Dict, List
import logging
import yaml
from netmiko import ConnectHandler, NetmikoTimeoutException
from enum import Enum
from ttp import ttp
import re

from genie.conf.base import Device
from genie.libs.parser.utils import get_parser
from attrdict import AttrDict

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))

A10_PARTITION_TTP_TEMPLATE = f"{SCRIPT_DIR}/ttp_templates/acos_show_partition.ttp"
A10_VERSION_TTP_TEMPLATE = f"{SCRIPT_DIR}/ttp_templates/acos_show_version.ttp"


class CollectionStatus(Enum):
    PASS = 1
    FAIL = 2
    PARTIAL = 3


AnsibleOsToNetmikoOs = {
    "arista.eos.eos": "arista_eos",
    "acos": "a10",
    "check_point.gaia.checkpoint": "checkpoint_gaia",
    "cisco.asa.asa": "cisco_asa",
    "cisco.iosxr.iosxr": "cisco_xr",
    "cisco.nxos.nxos": "cisco_nxos",
    "cisco.ios.ios": "cisco_ios",
    "cumulus": "linux",
    "juniper.junos.junos": "juniper_junos",
}


class RetryingNetConnect(object):

    def __init__(self, device_name: str, device_session: Dict, logger_name: str):
        self._device_name = device_name
        self._device_session = device_session
        self._logger = logging.getLogger(logger_name)
        try:
            self._net_connect = ConnectHandler(**self._device_session, encoding='utf-8')
        except NetmikoTimeoutException as exc:
            if "Pattern not detected" in str(exc):
                self._logger.error(f"Device {self._device_name} didn't return prompt in 20 seconds, re-trying connection in 60 seconds")
                sleep(60)  # wait 60 seconds before retrying
                try:
                    self._net_connect = ConnectHandler(**self._device_session, encoding='utf-8')
                except Exception as exc:
                    self._logger.exception(f"2nd attempt at connecting failed, skipping device {self._device_name}.")
                    raise Exception
            else:
                self._logger.exception(f"Skipped data collection for {self._device_name}, could not connect")
                raise Exception
        except socket.error:
            self._logger.exception(f"Socket error for {cmd} to {self._device_name}")
            # wait 60 seconds and then try to re-establish a new SSH session
            sleep(60)
            try:
                self._net_connect = ConnectHandler(**self._device_session, encoding='utf-8')
            except Exception:
                self._logger.exception(f"Could not reconnect to {self._device_name}")
                raise Exception
        except Exception:
            self._logger.exception(f"Connection to {self._device_name} failed")
            raise Exception
        self._base_prompt = self._net_connect.base_prompt
        self._logger.info(f"Netmiko prompt: {self._net_connect.base_prompt}")

    def run_command(self, cmd: str, cmd_timer: int, pattern=None):
        try:
            self._logger.info(f"Using {pattern} as expect_string")
            _output = self._net_connect.send_command(cmd, read_timeout=cmd_timer, strip_command=True,
                                                     expect_string=pattern)
        except socket.error:
            self._logger.exception(f"Socket error for {cmd} to {self._device_name}")
            # wait 60 seconds and then try to re-establish a new SSH session
            sleep(60)
            try:
                self._net_connect = ConnectHandler(**self._device_session, encoding='utf-8')
            except Exception:
                self._logger.exception(f"Could not reconnect to {self._device_name}")
                raise Exception
            else:
                try:
                    self._logger.info("Connection re-established, re-trying previous command")
                    _output = self._net_connect.send_command(cmd, read_timeout=cmd_timer, strip_command=True,
                                                             expect_string=pattern)
                except Exception as exc:
                    self._logger.exception(f"Command {cmd} to {self._device_name} failed")
                    return None
                else:
                    return _output
        except Exception:
            self._logger.exception(f"Command {cmd} to {self._device_name} failed")
            pass
        else:
            self._logger.debug(f"Output of {cmd} to {self._device_name}: {_output}")
            return _output

    def enable(self):
        try:
            self._net_connect.enable()
        except Exception:
            self._logger.exception(f"Failed to enter enable mode at {self._device_name}")
            pass  # still want to try to run commands outside of enable mode

    def close(self):
        self._net_connect.disconnect()


def custom_logger(logger_name, log_file, console_log_level):
    """
    Method to return a custom logger with the given name and level
    """
    logger = logging.getLogger(logger_name)

    # to use different levels per handler the logger's level should be lower than either
    # we set it to DEBUG, the lowest value
    logger.setLevel(logging.DEBUG)

    format_string = '%(levelname)s:%(asctime)s %(message)s'
    datefmt_string = '%m/%d/%Y %I:%M:%S %p'
    log_format = logging.Formatter(fmt=format_string, datefmt=datefmt_string)

    # Creating and adding the console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(log_format)
    console_handler.setLevel(console_log_level)
    logger.addHandler(console_handler)

    # Creating and adding the file handler
    file_handler = logging.FileHandler(log_file, mode='a')
    file_handler.setFormatter(log_format)
    file_handler.setLevel(logging.INFO)  # always want detail in log files
    logger.addHandler(file_handler)

    return logger


def get_inventory(inventory_file: Text) -> Dict:
    with open(inventory_file) as f:
        inventory = yaml.safe_load(f)

    if inventory.get("all") is None or inventory['all'].get('children') is None:
        raise Exception(f"{inventory_file} is not properly formatted")

    return inventory['all']['children']


def get_show_commands(commands_file: Text) -> Dict:
    with open(commands_file) as f:
        commands = yaml.safe_load(f)

    if commands.get("all") is None:
        raise Exception(f"{commands} is not properly formatted")

    return commands['all']

def write_output_to_file(device_name: Text, output_path: Text, cmd: Text, cmd_output: Text, prepend_text=None):
    """
    Save show commands output to it's file
    """
    file_name = cmd.replace(" ", "_")
    file_path = f"{output_path}/{device_name}/{file_name}.txt"

    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "w") as f:
        if prepend_text is not None:
            f.write(prepend_text)
            f.write("\n")
        if cmd_output is None:
            f.write("Command output was None")
        else:
            f.write(cmd_output)


def a10_parse_version(input: Text) -> str:

    template = A10_VERSION_TTP_TEMPLATE

    parser = ttp()
    # Note:
    #   - must add macros first, then vars and then you can add the template
    #   - if you add templates individually, you will get multiple entries in
    #       parser.result(). That is why it is easier to concatenate the
    #       individual template files and then just add them as a single template
    #       this way you get a results object for the entire input
    #       as opposed to one object per template file
    #
    # to get additional debug information from ttp
    # import logging
    # logging.basicConfig(level=logging.DEBUG)
    #

    if template is None:
        return []

    parser.add_template(template)
    parser.add_input(input)
    parser.parse()
    res = parser.result()[0][0]

    if len(res) == 0:
        return "unknown"

    version = res[0].get('acos_version', None)
    if version is None:
        return "unknown"
    elif re.match("^2\..*$", version):
        return "v2"
    else:
        return "v4p"


def a10_parse_partition(input: Text) -> List:

    template = A10_PARTITION_TTP_TEMPLATE

    parser = ttp()
    # Note:
    #   - must add macros first, then vars and then you can add the template
    #   - if you add templates individually, you will get multiple entries in
    #       parser.result(). That is why it is easier to concatenate the
    #       individual template files and then just add them as a single template
    #       this way you get a results object for the entire input
    #       as opposed to one object per template file
    #
    # to get additional debug information from ttp
    # import logging
    # logging.basicConfig(level=logging.DEBUG)
    #

    if template is None:
        return []

    parser.add_template(template)
    parser.add_input(input)
    parser.parse()
    res = parser.result()[0][0]
    if len(res) == 0:
        return []
    else:
        return res[0].get('partitions', [])


def parse_genie_file(device_name, file, command=None, os=None, logger=None):
    """
    Wrapper function around Cisco pyATS/Genie library to parse cli output into structured data. Allows you to pass in a file
    that contains the cli output you want to parse
    :param file: (String) Path to file containing CLI output from Cisco device
    :param command: (String) CLI command that was used to generate the cli_output
    :param os: (String) Operating system of the device for which cli_output was obtained.
    :return: Dict object conforming to the defined genie parser schema.
             https://pubhub.devnetcloud.com/media/pyats-packages/docs/genie/genie_libs/#/parsers/show%20version
    """

    f = open(file, 'r')
    text = f.read()
    f.close()
    return parse_genie(device_name, text, command, os, logger)


def parse_genie(device_name, cli_output, command=None, os=None, logger=None):
    """
    Uses the Cisco pyATS/Genie library to parse cli output into structured data.
    :param cli_output: (String) CLI output from Cisco device
    :param command: (String) CLI command that was used to generate the cli_output
    :param os: (String) Operating system of the device for which cli_output was obtained.
    :return: Dict object conforming to the defined genie parser schema.
             https://pubhub.devnetcloud.com/media/pyats-packages/docs/genie/genie_libs/#/parsers/show%20version
    """

    # Input validation

    # Is the OS provided by the user a supported OS by Genie?
    # Supported Genie OSes: https://github.com/CiscoTestAutomation/genieparser/tree/master/src/genie/libs/parser
    #
    # SAMIR: Ignoring JUNOS for now, since there are not enough parsers for Junos commands in Genie
    genie_supported_oses = ["ios", "iosxe", "iosxr", "nxos"]
    if os.lower() not in genie_supported_oses:
        logger.error(
            "The network OS provided ({0}) to the genie_parse filter is not a supported OS in Genie.".format(
                os
            )
        )

    def _parse(device_name, raw_cli_output, cmd, nos, logger):
        # Boilerplate code to get the parser functional
        # tb = Testbed()
        device = Device(device_name, os=nos)

        device.custom.setdefault("abstraction", {})["order"] = ["os"]
        device.cli = AttrDict({"execute": None})

        # User input checking of the command provided. Does the command have a Genie parser?
        try:
            get_parser(cmd, device)
        except Exception as e:
            logger.error(
                "genie_parse: {0} - Available parsers: {1}".format(e,
                                                                   "https://pubhub.devnetcloud.com/media/pyats-packages/docs/genie/genie_libs/#/parsers")
            )

        try:
            parsed_output = device.parse(cmd, output=raw_cli_output)
            return parsed_output
        except Exception as e:
            logger.error(
                "genie_parse: {0} - Failed to parse command output.".format(e)
            )
        # what is returned if the try fails?
        # shouldn't there be a default value returned that you can check for?

    # Try to parse the output
    # If OS is IOS, ansible could have passed in IOS, but the Genie device-type is actually IOS-XE,
    # so we will try to parse both.
    if os == "ios":
        try:
            return _parse(device_name, cli_output, command, "ios", logger)
        except Exception:
            return _parse(device_name, cli_output, command, "iosxe", logger)
    else:
        return _parse(device_name, cli_output, command, os, logger)

