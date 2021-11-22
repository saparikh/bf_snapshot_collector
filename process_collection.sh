#!/usr/bin/env bash

set -ou pipefail

SCRIPT_DIR="$( dirname "${BASH_SOURCE[0]}" )"
BASE_DIR="$(dirname "${SCRIPT_DIR}")"
# read the environment variables from the .env file. the python script also relies on the .env file
ENV_FILE=.env

if [[ -f "$ENV_FILE" ]]; then
    echo ".env file does not exist"
    exit 1
fi

if [[ -z ${1+x} ]]; then
    echo "Inventory file not supplied (usage: process_collection.sh <inventory file> <optional: collection directory>)"
    exit 1
fi

source $ENV_FILE
if [[ -z "${COLLECT_USER}" ]]; then
    echo "COLLECT_USER environment variable has not been defined"
    exit 1
fi

if [[ -z "${COLLECT_PASSWORD}" ]]; then
    echo "COLLECT_PASSWORD environment variable has not been defined"
    exit 1
fi

INVENTORY = $1  #inventory file MUST be the first argument
COLLECTION_DIR="${2:-SCRIPT_DIR}"  #collection directory is the 2nd optional argument. if not set, uses SCRIPT_DIR

if [[ ! -e ${COLLECTION_DIR} ]]; then
    echo ${COLLECTION_DIR} does not exist
    exit 1
fi

SNAPSHOT_NAME=`date +"%Y%m%d %H:%M:%S"`
SNAPSHOT_DIR=${COLLECTION_DIR}/${SNAPSHOT_NAME}

echo "Attempting to run python script to collect configuration from devices"
python3 $SCRIPT_DIR/config_collector.py --inventory $INVENTORY --username $COLLECT_USER --password $COLLECT_PASSWORD --collection_dir $COLLECTION_DIR --snapshot_name $SNAPSHOT_NAME --max-threads 60
echo "Configuration collection script run complete"
echo "Cleaning up timestamps that lead to spurious config differences"
grep -rle '^!Running configuration last done at: ' ${SNAPSHOT_DIR} | xargs sed -i -E 's/^(!Running configuration last done at: ).*$/\1REMOVED/g'
grep -rle '^!Time: ' ${SNAPSHOT_DIR} | xargs sed -i 's/^!Time: .*$/!Time: REMOVED/g'
grep -rle '^# Exported by' ${SNAPSHOT_DIR} | xargs sed -i -E 's/^(# Exported by [^ ]+ on ).*$/\1REMOVED/g'
# remote A10 configuration timestamps
#grep -rle '^!Configuration last updated at ' ${SNAPSHOT_DIR} | xargs sed -i -E 's/^(!Configuration last updated at ).*$/\1REMOVED/g'
#grep -rle '^!Configuration last saved at ' ${SNAPSHOT_DIR} | xargs sed -i -E 's/^(!Configuration last saved at ).*$/\1REMOVED/g'
#grep -rle '^!Current configuration: ' ${SNAPSHOT_DIR} | xargs sed -i -E 's/^(!Current configuration: ).*$/\1REMOVED/g'
echo "Completed collecting and processing snapshot"

echo "Uploading configuration to Batfish Enterprise"
#python3 $SCRIPT_DIR/bfe_snapshot_upload.py --snapshot_dir $SNAPSHOT_DIR
#echo "New snapshot uploaded to Batfish Enterprise"
python3 $SCRIPT_DIR/bfe_upload_snapshot.py --snapshot $SNAPSHOT_DIR --network "{BFE_NETWORK:-'MY_NETWORK'}"
echo "Snapshot uploaded to Batfish Enterprise"