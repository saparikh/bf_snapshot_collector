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

For Cumulus, make sure the user has can read all of the necessary files, such as `/etc/frr/frr.conf`, without using `sudo`

## Collector setup

1) Create a python (3.7+) virtual environment and install dependencies
```
pip install -r requirements.txt
```

2) Copy `example_env` to `env` and edit with correct user credentials and Batfish Enterprise installation

3) Create an inventory file for your devices

## Taking network snapshots

You can collect network snapshots and upload to Batfish Enterprise via this command:

```
bash snapshot_network.sh <inventory file> [<collection directory>]
```

The second argument to the script is optional and specifies where the output of the collector should be stored. The default value is the current working directory. 

The snapshots are given a name based on collection time, such as `20211123_19:58:34`. Collected snapshots are uploaded to Batfish Enterprise but also left on local drive in the collection directory under a folder with the snapshot name. The logs will be under the folder `logs/20211123_19:58:34` in the collection directory. 
