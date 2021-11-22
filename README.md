# Batfish Snapshot Collector

This repository contains a script that will collect the running configuration from network elements and package them in
the format required by Batfish and Batfish Enterprise

## Assumptions / Restrictions:

### Supported devices
- Cisco ASA, IOS, IOS-XE, NXOS, IOS-XR
- Cumulus Linux
- Arista EOS
- Juniper JunOS

### Inventory
The collection script expects a valid Ansible inventory file. There is an `example_inventory.yml` file to 
show you the expected format. 

The device name must either be resolvable via DNS or you must specify the `ansible_host` variable for the device.
Your inventory may have a mix of devices which are resolvable via DNS and devices that use the `ansible_host` variable.

### Authentication
All devices in the inventory MUST be accessible with the SAME username and password. That user MUST either be put into 
`enable` mode or be granted correct privilege level to retrieve running configuration without being in `enable` mode.

For Cumulus, make sure the user has password-less sudo access

### Setup

1) Create a python virtual environment and install dependencies
```bash
pip install -r requirements.txt
```

2) Copy `sample.env` to `.env` and edit with correct user credentials and Batfish Enterprise installation

3) Run collection bash script
```bash
bash process_collection.sh <inventory file>
```

