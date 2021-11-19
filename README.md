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

The script does NOT support any variables defined per host, such as `ansible_host`. 
Therefore, the server on which you are running this script must be able to resolve the DNS names

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

