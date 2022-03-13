# Batfish Snapshot Collector

This repository contains a script that will collect the running configuration from network elements and package them in
the format required by Batfish.

## Assumptions / Restrictions:

### Supported devices
- Cisco ASA, IOS, IOS-XE, NXOS, IOS-XR
- Cumulus Linux
- Arista EOS
- Juniper JunOS
- Checkpoint Gateway
- A10 Loadbalancer (Ver 2.x and Ver 4.x)

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

You can collect network snapshots and upload to Batfish via this command:

```
BF_COLLECTOR_USER=<device-access-user> \
BF_COLLECTOR_PASSWORD=<device-access-passowrd> \ 
  bash snapshot_network.sh <inventory file> <batfish settings file> [<collection directory>]
```

In the first three lines of this command, we are passing in username and password to access the device as environment variables. They can be omitted if the environment variables are set via other means (e.g., the export command).

The third argument to the `snapshot_network.sh` script is optional and specifies where the output of the collector should be stored. The default value is the current working directory. 

The snapshots are given a name based on collection time, such as `20211123_19:58:34`. Collected snapshots are uploaded to Batfish Enterprise but also left on local drive in the collection directory under a folder with the snapshot name. The logs will be under the folder `logs/20211123_19:58:34` in the collection directory. 

## When using Batfish Enterprise

If you are using Batfish Enterprise:

1) Set the BFE_ENTERPRISE variable to True in the batfish settings file. 

2) Supply the BFE_ACCESS_TOKEN and BFE_SSL_CERT environment variables to snapshot_network script. Thus, the command becomes

```
BF_COLLECTOR_USER=<device-access-user> \
BF_COLLECTOR_PASSWORD=<device-access-passowrd> \ 
BFE_ACCESS_TOKEN=<bfe-access-token> \ 
BFE_SSL_CERT=<bfe-ssl-cert> \ 
  bash snapshot_network.sh <inventory file> <batfish settings file> [<collection directory>]
```

BFE_SSL_CERT variable is optional. It is only needed if you used a self-signed cert when installing Batfish Enterprise, instead of using a valid certificate. 