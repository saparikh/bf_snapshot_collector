# Batfish Snapshot Collector

This repository contains a script that will collect the running configuration from network elements and package them in
the format required by Batfish and Batfish Enterprise

## Assumptions / Restrictions:

### Supported devices
- Cisco ASA, IOS, IOS-XE, NXOS, IOS-XR
- Arista EOS
- Juniper JunOS

### Authentication
All devices in the inventory must be accessible with the same username and password. Also, that user should be put into
`enable` mode by default on platforms that require the user be in that mode in order to retrieve running configuration.

