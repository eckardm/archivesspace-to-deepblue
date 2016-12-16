import argparse
import requests
import json
from lxml import etree

from config import archivesspace, dspace

parser = argparse.ArgumentParser(description='Create or update a DSpace collection from an ArchivesSpace resource.')
parser.add_argument(
    'function', choices=['create', 'update'],
    help='either create or update'
)
parser.add_argument(
    '-r', '--resource', required=True, 
    help='an archivesspace resource'
)
args = parser.parse_args()

def archivesspace_authentication(base_url, user, password):
    url = base_url + '/users/' + user + '/login?password=' + password
    response = requests.post(url)
    
    token = response.json().get('session')
    
    return token
    
def dspace_authentication(base_url, email, password):
    url = base_url + "/RESTapi/login"
    body = {"email": email, "password": password}
    response = requests.post(url, json=body)

    token = response.text
    
    return token

archivesspace_token = archivesspace_authentication(archivesspace.get('base_url'), archivesspace.get('user'), archivesspace.get('password'))
dspace_token = dspace_authentication(dspace.get('base_url'), dspace.get('email'), dspace.get('password'))

# create and update functions
def parse_resource_id(resource):
    # matches:
    #  * 'http://141.211.39.87:8080/resources/:id/edit#tree::resource_:id'
    #  * 'http://141.211.39.87:8080/resources/:id'
    #  * 'http://141.211.39.87:8089/repositories/2/resources/:id'
    if '/resources/' in resource:
        resource_id = resource.split('/resources/')[1].split('#')[0]
    # matches ':id'
    elif resource.isdigit():
        resource_id = resource
    else:
        print 'Unable to parse resource ID from ' + resource + '.'
        exit()
        
    return resource_id
    
def get_resource(base_url, resource_id, token):
    url = base_url + '/repositories/2/resources/' + str(resource_id)
    headers = {'X-ArchivesSpace-Session': token}
    response = requests.get(url, headers=headers)
    
    resource = response.json()
    
    return resource
    
def instance_check(resource):
    if len(resource.get('instances')) > 0:
        print 'Resource already has an instance.'
        exit()
    
def create_introductory_text(resource):
    with open('introductory_text.txt', mode='r') as f:
        introductory_text = f.read()
    introductory_text = introductory_text.replace('TITLE_PLACEHOLDER', resource.get('title'))
    if resource.get('level') == 'recordgrp':
        introductory_text = introductory_text.replace('RECORD_GROUP_OR_MANUSCRIPT_COLLECTION', 'record group')
    elif resource.get('level') == 'collection':
        introductory_text = introductory_text.replace('RECORD_GROUP_OR_MANUSCRIPT_COLLECTION', 'manuscript collection')
    introductory_text = introductory_text.replace('COLLECTION_NUMBER_PLACEHOLDER', resource.get('ead_id').split('-', 2)[-1])
    introductory_text = introductory_text.replace('ABSTRACT_PLACEHOLDER', [note.get('content')[0] for note in resource.get('notes') if note.get('type') == 'abstract'][0])
    introductory_text = introductory_text.replace('HISTORY_OR_BIOGRAPHY_PLACEHOLDER', [note.get('subnotes')[0].get('content') for note in resource.get('notes') if note.get('type') == 'bioghist'][0].replace('\n\n', '</p><p>'))
        
    return introductory_text
    
def create_collection(resource):
    collection = {}
    collection['name'] = resource.get('title').title() 
    introductory_text = create_introductory_text(resource)
    collection['introductoryText'] = introductory_text
    collection['copyrightText'] = '<h2>Please note:</h2><p>Copyright has been transferred to the Regents of the University of Michigan.</p><br /><br /><p>Access to digitized sound recordings may be limited to the reading room of the <a href="http://bentley.umich.edu/">Bentley Historical Library</a>, located on the Ann Arbor campus of the University of Michigan.</p>'
    collection['license'] = 'As the designated coordinator for this Deep Blue Collection, I am authorized by the Community members to serve as their representative in all dealings with the Repository. As the designee, I ensure that I have read the Deep Blue policies. Furthermore, I have conveyed to the community the terms and conditions outlined in those policies, including the language of the standard deposit license quoted below and that the community members have granted me the authority to deposit content on their behalf.'
    
    return collection
    
def post_collection(base_url, community_id, token, collection):
    url = base_url + '/RESTapi/communities/' + str(community_id) + '/collections'
    headers = {
        "Accept": "application/json",
        "rest-dspace-token": token
    }
    response = requests.post(url, headers=headers, json=collection)
    
    collection = response.json()
    collection_handle = collection.get('handle')
    
    return collection_handle
    
def update_introductory_text(base_url, collection_handle, token):
    url = base_url + '/RESTapi/handle/' + collection_handle
    headers = {
        "Accept": "application/json",
        "rest-dspace-token": token
    }
    response = requests.get(url, headers=headers)
    
    collection = response.json()
    collection['introductoryText'] = collection['introductoryText'].replace('COLLECTION_HANDLE_PLACEHOLDER', collection_handle)
    url = base_url + '/RESTapi/collections/' + str(collection.get('id'))
    headers={
        'Accept': 'application/json',
        'rest-dspace-token': token
    }
    response = requests.put(url, headers=headers, json=collection)
    
def create_digital_object(collection_handle, base_url, token):
    digital_object = {
        "title": resource.get('title'),
        "digital_object_id": 'https://dev.deepblue.lib.umich.edu/handle/' + collection_handle,
        "publish": False,
        "file_versions": [
            {
                "file_uri": 'https://dev.deepblue.lib.umich.edu/handle/' + collection_handle,
                "xlink_show_attribute": "new",
                "xlink_actuate_attribute":"onRequest"
            }
        ]
    }
    url = base_url + '/repositories/2/digital_objects'
    headers = {'X-ArchivesSpace-Session': token}
    response = requests.post(url, headers=headers, json=digital_object)
    
    digital_object = response.json()
    digital_object_ref = digital_object.get('uri')
    
    return digital_object_ref
    
def link_digital_object(base_url, resource_id, token, digital_object_ref):
    url = base_url + '/repositories/2/resources/' + str(resource_id)
    headers = {'X-ArchivesSpace-Session': token}
    response = requests.get(url, headers=headers)
    
    resource['instances'] = [
        {
            'instance_type': 'digital_object', 
            'digital_object': {
                'ref': digital_object_ref
            }
        }
    ]
    response = requests.post(url, headers=headers, json=resource)

# update functions only
def get_collection(resource, base_url, token):
    try:
        instance = resource.get('instances')[0]
    except:
        print 'Resource does not have an instance.'
        exit()
    digital_object = instance.get('digital_object')
    digital_object_ref = digital_object.get('ref')
    
    url = base_url + digital_object_ref
    headers={'X-ArchivesSpace-Session': token}
    response = requests.get(url, headers=headers)
 
    digital_object = response.json()
    file_version = digital_object.get('file_versions')[0]
    file_uri = file_version.get('file_uri')
    collection_handle = file_uri.replace('https://dev.deepblue.lib.umich.edu/handle/', '')
    
    return collection_handle
    
def put_collection(base_url, collection_handle, token, updated_collection):
    url = base_url + '/RESTapi/handle/' + collection_handle
    headers = {
        'Accept': 'application/json',
        'rest-dspace-token': token
    }
    response = requests.get(url, headers=headers)
    
    collection = response.json()
    collection_id = collection.get('id')
    
    updated_collection['introductoryText'] = updated_collection['introductoryText'].replace('COLLECTION_HANDLE_PLACEHOLDER', collection_handle)

    url = base_url + '/RESTapi/collections/' + str(collection_id)
    headers = {
        'Accept': 'application/json',
        'rest-dspace-token': token
    }
    response = requests.put(url, headers=headers, json=updated_collection)
    
def update_digital_object(resource, base_url, token):
    instance = resource.get('instances')[0]
    digital_object = instance.get('digital_object')
    digital_object_ref = digital_object.get('ref')
    
    url = base_url + digital_object_ref
    headers={'X-ArchivesSpace-Session': token}
    response = requests.get(url, headers=headers)
 
    digital_object = response.json()
    digital_object['title'] = resource.get('title')
    
    response = requests.post(url, headers=headers, json=digital_object)

if args.function == 'create':
    resource_id = parse_resource_id(args.resource)
    resource = get_resource(archivesspace.get('base_url'), resource_id, archivesspace_token)
    instance_check(resource)
    collection = create_collection(resource)
    collection_handle = post_collection(dspace.get('base_url'), 35, dspace_token, collection)
    update_introductory_text(dspace.get('base_url'), collection_handle, dspace_token)
    digital_object_ref = create_digital_object(collection_handle, archivesspace.get('base_url'), archivesspace_token)
    link_digital_object(archivesspace.get('base_url'), resource_id, archivesspace_token, digital_object_ref)
    print collection_handle + ' created.'
    
elif args.function == 'update':
    resource_id = parse_resource_id(args.resource)
    resource = get_resource(archivesspace.get('base_url'), resource_id, archivesspace_token)
    updated_collection = create_collection(resource)
    collection_handle = get_collection(resource, archivesspace.get('base_url'), archivesspace_token)
    put_collection(dspace.get('base_url'), collection_handle, dspace_token, updated_collection)
    update_digital_object(resource, archivesspace.get('base_url'), archivesspace_token)
    print collection_handle + ' updated.'
