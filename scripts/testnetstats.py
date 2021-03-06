#! /usr/bin/env python3

""" pull local stats and post them to elastic """

from datetime import datetime
import logging
import json
import requests

from elasticsearch import Elasticsearch
from elasticsearch.exceptions import TransportError
import certifi
import hashlib
from os import environ
import sys
from socket import gethostname
import codalib

try:
    import geoip2.database
    reader = geoip2.database.Reader('/usr/share/GeoIP/GeoLite2-City.mmdb')
    GEOIP = True
except:
    GEOIP = False


def generate_id():
    """Generates a unique id based on hostname and timestamp"""
    hostname = gethostname()
    timestamp = datetime.utcnow().timestamp()
    hash_string = "%s-%s" % (hostname, timestamp)
    sha_signature = hashlib.sha256(hash_string.encode()).hexdigest()
    return sha_signature

def create_stats_index(client, index):
    """Builds an elastic index if it doesn't already exist"""
    request_body = {
        "settings": {
        },
        'mappings': {
            'stats': {
                'properties': {
                    'stattime':      {'type': 'date',    'format': "date_optional_time"},
                    "block_count":   {'type': 'integer', 'index': False},
                    "account_count": {'type': 'integer', 'index': False},
                    "peer_count":    {'type': 'integer', 'index': False},
                    'user_commands': {'type': 'integer', 'index': False},
                    'peers':         {'type': 'text',    'index': False,},
                    'geoip.location': {'type': 'geo_point',    'index': False,},
                }
            }
        }
    }

    try:
        client.indices.create(index=index, body=request_body)
    except TransportError as e:
        # ignore already existing index
        if e.error == "resource_already_exists_exception":
            pass
        else:
            raise


if __name__ == "__main__":
    # Load sensitive config
    try:
        with open('/etc/testnet_config.json') as config_file:
            config = json.load(config_file)
            elastic_url = config['elastic_url']
            testnet = config['testnet']
    except IOError as error:
        print('Error opening secrets config:', error)
        sys.exit(1)

    # Create index datestamp
    now = datetime.utcnow()
    index = 'testnetstats-%s.%s.%s' % (now.year, now.month, now.day)

    # quiet logger levels
    logging.getLogger('elasticsearch').setLevel(logging.ERROR)
    logging.getLogger('urllib3').setLevel(logging.INFO)

    # Connect to es
    es = Elasticsearch("https://%s" % elastic_url, ca_certs=certifi.where())

    # delete old index
    #es.indices.delete(index=index)

    # create/renew index
    create_stats_index(es, index=index)

    # get stats
    stats = codalib.coda_status()




    # Prep data
    body = {
        'block_count':   stats['blockchain_length'],
        'account_count': stats['num_accounts'],
        'peer_count':    len(stats['peers']),
        'peers':         stats['peers'],
        'user_commands': stats['user_commands_sent'],
        'hostname':      gethostname(),
        'testnet':       testnet,
        'stattime':      "%s" % datetime.utcnow().isoformat()
    }

    if GEOIP:
        ip = requests.get("http://169.254.169.254/latest/meta-data/public-ipv4").content
        response = reader.city(str(ip, 'utf-8'))
        body['geoip.location'] = "%s, %s" % (response.location.latitude,
                                             response.location.longitude)

    print('Posting:\n', json.dumps(body, indent=4, sort_keys=True))

    my_id = generate_id()
    result = es.create(index=index, doc_type="stats", id=my_id, body=body)
    print('Result:\n', json.dumps(result, indent=4, sort_keys=True))
