#!/usr/bin/env bash

set -eou pipefail

SCRIPT_DIR="$( dirname "${BASH_SOURCE[0]}" )"
BASE_DIR="$(dirname "${SCRIPT_DIR}")"

if [[ -z ${BF_COLLECTOR_USER+x} ]]; then
    echo "Environment variable BF_COLLECTOR_USER is not set"
    exit 1
fi

if [[ -z ${BF_COLLECTOR_PASSWORD+x} ]]; then
    echo "Environment variable BF_COLLECTOR_PASSWORD is not set"
    exit 1
fi

if [[ -z ${BF_ACCESS_TOKEN+x} ]]; then
    echo "Environment variable BF_ACCESS_TOKEN is not set"
    exit 1
fi

if [[ -z ${2+x} ]]; then
    echo "Usage: process_collection.sh <inventory file> <batfish settings file> <optional: collection directory>)"
    exit 1
fi

if ! [[ -z ${4+x} ]]; then
    echo "Usage: process_collection.sh <inventory file> <batfish settings file> <optional: collection directory>)"
    exit 1
fi

INVENTORY=$1
BF_SETTINGS=$2
COLLECTION_DIR="${3:-$( pwd )}"  # Collection directory is the 3rd, optional argument. Default is to use working directory.

if [[ ! -e ${COLLECTION_DIR} ]]; then
    echo ${COLLECTION_DIR} does not exist
    exit 1
fi

SNAPSHOT_NAME=`date +"%Y%m%d_%H:%M:%S"`
SNAPSHOT_DIR=${COLLECTION_DIR}/${SNAPSHOT_NAME}

echo "Collecting configuration from devices"
python ${SCRIPT_DIR}/config_collector.py \
    --inventory ${INVENTORY} \
    --collection-dir ${COLLECTION_DIR} \
    --snapshot-name ${SNAPSHOT_NAME} \
    --max-threads 60

#echo "Removing timestamps that lead to spurious config differences"
#grep -rle '^!Running configuration last done at: ' ${SNAPSHOT_DIR} | xargs sed -i -E 's/^(!Running configuration last done at: ).*$/\1REMOVED/g'
#grep -rle '^!Time: ' ${SNAPSHOT_DIR} | xargs sed -i 's/^!Time: .*$/!Time: REMOVED/g'
#grep -rle '^# Exported by' ${SNAPSHOT_DIR} | xargs sed -i -E 's/^(# Exported by [^ ]+ on ).*$/\1REMOVED/g'


BF_NETWORK=${BF_NETWORK:="MY_NETWORK"}
echo "Uploading snapshot ${SNAPSHOT_NAME} to network ${BF_NETWORK}"
python ${SCRIPT_DIR}/bfe_upload_snapshot.py \
    --snapshot ${SNAPSHOT_DIR} \
    --settings ${BF_SETTINGS}
