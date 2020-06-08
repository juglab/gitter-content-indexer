#!/usr/bin/env python3
"""
Fetch gitter archives of all token bearer's public rooms
"""
import yaml
import json
import os
import time
import uuid
import requests
import requests_cache
from git import Repo
from elasticsearch import Elasticsearch
from elasticsearch.helpers import streaming_bulk
from datetime import datetime, timezone, timedelta
from dateutil.parser import parse

client = Elasticsearch('http://localhost:9200')

with open('token') as f:
    token = f.read().strip()

h = {'Authorization': 'Bearer %s' % token}

with open(r'config.yml') as file:
    config = yaml.load(file, Loader=yaml.FullLoader)
archive_dir = config['archivedir']
archive_name = os.path.join(archive_dir, 'archive')
requests_cache.install_cache(archive_dir + '/gitter_indexer') 
def utcnow():
    return datetime.now(timezone.utc)

def gitter_api_request(path):
    request_time = utcnow()
    if not path.startswith('/'):
        path = '/' + path
    r = requests.get('https://api.gitter.im/v1' + path, headers=h)
    r.raise_for_status()
    if parse(r.headers['date']) + timedelta(minutes=10) > request_time:
        # if not a cached response, slow down:
        remaining = int(r.headers['X-RateLimit-Remaining'])
        #print("Requests remaining: %s" % remaining)
        if remaining < 10:
            print("slowing down...")
            time.sleep(10)
        else:
            time.sleep(1)
    #else print("Request was cached")
        
    return r.json()

def create_index(client):
    """Creates an index in Elasticsearch if one isn't already there."""
    client.indices.create(
        index='gitter-index',
        body={
            "settings": {"number_of_shards": 1},
            "mappings": {
                "properties": {
                    "groupName": { "type": "keyword" },
                    "roomName": { "type": "keyword" },
                    "displayName": { "type": "text" },
                    "username": { "type": "keyword" },
                    "content": { "type": "text" },
                    "sent": { "type": "date", "format": "date_optional_time" },
                }
            },
        },
        ignore=400,
    )

def extract_es_messages(messages):
    for message in messages:
        es_message = { 
            'groupName' : group_name,
            'roomName' : room_name,
            'displayName' : message['fromUser']['displayName'],
            'username' : message['fromUser']['username'],
            'content' : message['text'],
            'sent' : message['sent']
        }
        #print(es_message)
        yield es_message

# Get list of indexes and check that the Gitter index exists.
# If it does not, create it
r = requests.get('http://localhost:9200/_aliases')
r.raise_for_status()
indexes = r.json().keys()
if ( 'gitter-index' not in indexes):
    print('Creating index "gitter-index"')
    create_index(client)

# Get the data from Gitter
rooms = gitter_api_request('/rooms?_=%s' % uuid.uuid4().hex)

for room in rooms:
    name = room['name']
    print('Processing: ' + name)
    group_name = 'None'
    room_name = ''
    if '/' in name:
        group_name = name.rsplit('/', 1)[0]
        room_name = name.rsplit('/', 1)[1]
        
    # We do not archive one to one or private conversations (the latter could be configurable)
    if room['oneToOne'] or room.get('security') == 'PRIVATE':
        continue
    
    uri = room.get('uri', room['url'].lstrip('/'))
    dest = os.path.join(archive_name, uri + '.json')
    if '/' in dest:
        d = dest.rsplit('/', 1)[0]
        if not os.path.exists(d):
            os.makedirs(d)

    if os.path.exists(dest):
        print("Checking for new messages: %s" % dest)
        with open(dest) as f:
            room_messages = json.load(f)
    else:
        print("New room: %s" % dest)
        room_messages = []
        
    if room_messages:
        key='afterId'
        last_id = room_messages[-1]['id']
        messages = gitter_api_request('/rooms/%s/chatMessages?limit=5000&afterId=%s&_=%s' % (
            room['id'], room_messages[-1]['id'], uuid.uuid4().hex))
    else:
        key='beforeId'
        try:
            messages = gitter_api_request('/rooms/%s/chatMessages?limit=5000&' % room['id'])
        except Exception as e:
            print("Failed to get messages for %s: %s" % (name, e))
            continue
        
    while messages:
        if key == 'beforeId':
            room_messages[:0] = messages
            edge_message = messages[0]
        else:
            room_messages.extend(messages)
            edge_message = messages[-1]
        messages = gitter_api_request('/rooms/%s/chatMessages?limit=5000&%s=%s' % (
            room['id'], key, edge_message['id']))
        
        if (len(messages) > 0):
            num_messages = len(messages) 
            successes = 0
            for ok, action in streaming_bulk( client=client, index='gitter-index', actions=extract_es_messages(messages)):
                successes += ok
            print('Indexed %d/%d messages' % (successes, num_messages))
            
        print('Total messages for this room ' + str(len(room_messages)))
        
    print('Archiving messages...')
    with open(dest, 'w') as f:
        json.dump(room_messages, f, sort_keys=True, indent=1)
        
now = datetime.now()
dt_string = now.strftime("%d/%m/%Y %H:%M:%S")
try:
    repo = Repo(archive_dir)
    repo.git.add(update=True)
    repo.index.commit('Message index update ' + dt_string)
    origin = repo.remote(name='origin')
    origin.push()
    print('\nSuccessfully pushed to backup archive')    
except Exception as e:
    print('Error while pushing to github: %s' % e)    
    