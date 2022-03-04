# Batfish Snapshot Collector

This repository contains a script that will collect the running configuration from network elements and package them in
the format required by Batfish and Batfish Enterprise

## Assumptions / Restrictions:

### Supported devices
- Cisco ASA, IOS, IOS-XE, NXOS, IOS-XR
- Cumulus Linux
- Arista EOS
- Juniper JunOS

### Device inventory
The collection script expects a valid Ansible inventory file. There is an `example_inventory.yml` file to 
show you the expected format. 

The device name must either be resolvable via DNS or you must specify the `ansible_host` variable for the device.
Your inventory may have a mix of devices which are resolvable via DNS and devices that use the `ansible_host` variable.

### Device access
All devices in the inventory MUST be accessible with the SAME username and password. That user MUST either be put into 
`enable` mode or be granted correct privilege level to retrieve running configuration without being in `enable` mode.

For Cumulus, make sure the user can read all the necessary files, such as `/etc/frr/frr.conf`, without using `sudo`

## Collector setup

1) Create a python (3.7+) virtual environment and install dependencies
```
pip install -r requirements.txt
```

2) Create an inventory file for your devices

3) Create a file with settings to connect to Batfish. See `example_bf_settings.env` for an example.


## Taking network snapshots

You can collect network snapshots and upload to Batfish Enterprise via this command:

```
BF_COLLECTOR_USER=<device-access-user> \
BF_COLLECTOR_PASSWORD=<device-access-passowrd> \ 
BF_ACCESS_TOKEN=<bf-access-token> \ 
  bash snapshot_network.sh <inventory file> <batfish settings file> [<collection directory>]
```

In the first three lines of this command, we are passing in username and password to access the device as environment variables. They can be omitted if the environment variables are set via other means (e.g., the export command).

The third argument to the `snapshot_network.sh` script is optional and specifies where the output of the collector should be stored. The default value is the current working directory. 

The snapshots are given a name based on collection time, such as `20211123_19:58:34`. Collected snapshots are uploaded to Batfish Enterprise but also left on local drive in the collection directory under a folder with the snapshot name. The logs will be under the folder `logs/20211123_19:58:34` in the collection directory. 
