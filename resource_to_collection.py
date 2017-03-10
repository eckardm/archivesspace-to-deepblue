import argparse
import configparser
import json
import logging
import requests
from selenium import webdriver
from slackclient import SlackClient

config = configparser.ConfigParser()
config.read('config.ini')

parser = argparse.ArgumentParser(description = 'Create or update a DSpace Collection from an ArchivesSpace Resource (also creates an Archivematica Storage Service Location for the DSpace Collection, creates and links an ArchivesSpace Digital Object for the DSpace Collection to the ArchivesSpace Resource, and notifies the processor via a message on Slack).')
parser.add_argument(
    'function', choices = ['create', 'update'],
    help = 'either create or update'
)
parser.add_argument(
    '-r', '--resource', required=True, 
    help = 'an archivesspace resource (source of collection metadata)'
)
parser.add_argument(
    '-c', '--collection', required=False,
    help = 'a dspace collection (to be created or updated)'
)
parser.add_argument(
    '-s', '--space', required=False,
    help = 'an archivematica storage service space (to which a location will be added)'
)
parser.add_argument(
    '-u', '--uniqname', required=False,
    help = 'the uniqname (of processor)'
)
args = parser.parse_args()

def archivesspace_authentication(archivesspace_base_url, archivesspace_user, archivesspace_password):
    logging.info('Logging into ArchivesSpace')
    url = archivesspace_base_url + '/users/' + archivesspace_user + '/login?password=' + archivesspace_password
    try:
        response = requests.post(url)
    except:
        logging.debug('Unable to authenticate... check the config file?')
        exit()
    
    token = response.json().get('session')
    
    return token
    
def dspace_authentication(dspace_base_url, dspace_email, dspace_password):
    logging.info('Logging into DSpace')
    url = dspace_base_url + "/RESTapi/login"
    body = {"email": dspace_email, "password": dspace_password}
    try:
        response = requests.post(url, json=body)
    except:
        logging.debug('Unable to authenticate... check the config file?')
        exit()

    token = response.text
    
    return token

archivesspace_token = archivesspace_authentication(config['archivesspace']['base_url'], config['archivesspace']['user'], config['archivesspace']['password'])
dspace_token = dspace_authentication(config['dspace']['base_url'], config['dspace']['email'], config['dspace']['password'])

# create and update functions
def parse_resource_id(resource):
    logging.info('Parsing ArchivesSpace Resource ID')
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
        logging.debug('Unable to parse resource ID from ' + resource)
        exit()
        
    logging.info('ArchivesSpace Resource ID: ' + resource_id)
        
    return resource_id
    
def get_resource(base_url, resource_id, token):
    logging.info('GETting ArchivesSpace Resource')
    url = base_url + '/repositories/2/resources/' + str(resource_id)
    headers = {'X-ArchivesSpace-Session': token}
    try:
        response = requests.get(url, headers=headers)
    except:
        logging.debug('Unable to GET ArchivesSpace Resource... does it exist?')
        exit()
    
    resource = response.json()
    
    return resource
    
def instance_check(resource):
    logging.info('Checking to see if ArchivesSpace Resource already has a Digital Object instance.')
    if len(resource.get('instances')) > 0:
        logging.debug('ArchivesSpace Resource has a Digital Object instance... should you update instead?')
        exit()
    
def create_introductory_text(resource):
    logging.info('Creating introductory text for DSpace Collection')
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
    logging.info('Creating DSpace Collection')
    collection = {}
    collection['name'] = resource.get('title').title() 
    introductory_text = create_introductory_text(resource)
    collection['introductoryText'] = introductory_text
    collection['copyrightText'] = '<h2>Please note:</h2><p>Copyright has been transferred to the Regents of the University of Michigan.</p><br /><br /><p>Access to digitized sound recordings may be limited to the reading room of the <a href="http://bentley.umich.edu/">Bentley Historical Library</a>, located on the Ann Arbor campus of the University of Michigan.</p>'
    collection['license'] = 'As the designated coordinator for this Deep Blue Collection, I am authorized by the Community members to serve as their representative in all dealings with the Repository. As the designee, I ensure that I have read the Deep Blue policies. Furthermore, I have conveyed to the community the terms and conditions outlined in those policies, including the language of the standard deposit license quoted below and that the community members have granted me the authority to deposit content on their behalf.'
    
    return collection
    
def post_collection(base_url, community_id, token, collection):
    logging.info('POSTing DSpace Collection')
    url = base_url + '/RESTapi/communities/' + str(community_id) + '/collections'
    headers = {
        "Accept": "application/json",
        "rest-dspace-token": token
    }
    try:
        response = requests.post(url, headers=headers, json=collection)
    except:
        logging.debug('Unable to POST DSpace Collection')
    
    collection = response.json()
    collection_handle = collection.get('handle')
    
    return collection_handle
    
def update_introductory_text(base_url, collection_handle, token):
    logging.info('Updating introductory text of DSpace Collection with DSpace Collection Handle')
    logging.info('GETting DSpace Collection')
    url = base_url + '/RESTapi/handle/' + collection_handle
    headers = {
        "Accept": "application/json",
        "rest-dspace-token": token
    }
    try:
        response = requests.get(url, headers=headers)
    except:
        logging.debug('Unable to GET DSpace Collection')
        exit()
    
    collection = response.json()
    
    logging.info('Updating introductory text')
    logging.info('PUTting DSpace Collection with updated introductory text')
    collection['introductoryText'] = collection['introductoryText'].replace('COLLECTION_HANDLE_PLACEHOLDER', collection_handle)
    url = base_url + '/RESTapi/collections/' + str(collection.get('id'))
    headers={
        'Accept': 'application/json',
        'rest-dspace-token': token
    }
    try:
        response = requests.put(url, headers=headers, json=collection)
    except:
        logging.debug('Unable to PUT DSpace Collection with updated introductory text')
        exit()
    
def create_digital_object(collection_handle, base_url, token):
    logging.info('Creating ArchivesSpace Digital Object')
    logging.info('POSTing ArchivesSpace Digital Object')
    digital_object = {
        'title': resource.get('title'),
        'digital_object_id': 'https://dev.deepblue.lib.umich.edu/handle/' + collection_handle,
        'publish': False,
        'file_versions': [
            {
                'file_uri': 'https://dev.deepblue.lib.umich.edu/handle/' + collection_handle,
                'xlink_show_attribute': 'new',
                'xlink_actuate_attribute': 'onRequest'
            }
        ]
    }
    url = base_url + '/repositories/2/digital_objects'
    headers = {'X-ArchivesSpace-Session': token}
    try:
        response = requests.post(url, headers=headers, json=digital_object)
    except:
        logging.debug('Unable to POST ArchivesSpace Digital Object')
        exit()
    
    digital_object = response.json()
    digital_object_ref = digital_object.get('uri')
    
    return digital_object_ref
    
def link_digital_object(base_url, resource_id, token, digital_object_ref):
    logging.info('Linking ArchivesSpace Digital Object to ArchivesSpace Resource')
    logging.info('GETting ArchivesSpace Resource')
    url = base_url + '/repositories/2/resources/' + str(resource_id)
    headers = {'X-ArchivesSpace-Session': token}
    try:
        response = requests.get(url, headers=headers)
    except:
        logging.debug('Unable to GET ArchivesSpace Resource')
        exit()
    
    logging.info('Updating ArchivesSpace Resource')
    logging.info('POSTing ArchivesSpace Resource with ArchivesSpace Digital Object')
    resource['instances'] = [
        {
            'instance_type': 'digital_object', 
            'digital_object': {
                'ref': digital_object_ref
            }
        }
    ]
    try:
        response = requests.post(url, headers=headers, json=resource)
    except:
        logging.debug('Unable to POST ArchivesSpace Resource with ArchivesSpace Digital Object')
        exit()
        
# update functions only
def get_collection(resource, base_url, token):
    logging.info('Getting DSpace Collection Handle')
    try:
        instance = resource.get('instances')[0]
    except:
        logging.debug('ArchivesSpace Resource does not have a Digital Object instance... should you create instead?.')
        exit()
    
    digital_object = instance.get('digital_object')
    digital_object_ref = digital_object.get('ref')
    
    logging.info('GETting ArchivesSpace Digital Object')
    url = base_url + digital_object_ref
    headers={'X-ArchivesSpace-Session': token}
    try:
        response = requests.get(url, headers=headers)
    except:
        logging.debug('Unable to GET ArchivesSpace Digital Object')
        exit()
 
    digital_object = response.json()
    
    file_version = digital_object.get('file_versions')[0]
    file_uri = file_version.get('file_uri')
    collection_handle = file_uri.replace('https://dev.deepblue.lib.umich.edu/handle/', '')
    logging.info('Collection Handle to be updated: ' + collection_handle)
    
    return collection_handle
    
def put_collection(base_url, collection_handle, token, updated_collection):
    logging.info('Updating DSpace Collection with updated ArchivesSpace Resource')
    logging.info('GETting DSpace Collection')
    url = base_url + '/RESTapi/handle/' + collection_handle
    headers = {
        'Accept': 'application/json',
        'rest-dspace-token': token
    }
    try:
        response = requests.get(url, headers=headers)
    except:
        logging.debug('Unable to GET DSpace Collection')
        exit()
    
    collection = response.json()
    collection_id = collection.get('id')
    
    # DSpace has "stale" data, so this needs to be updated here (rather than with the update_introductory_text function) 
    # https://github.com/DSpace/DSpace/pull/561
    logging.info('Updating DSpace Collection')
    updated_collection['introductoryText'] = updated_collection['introductoryText'].replace('COLLECTION_HANDLE_PLACEHOLDER', collection_handle)

    logging.info('PUTting updated DSpace Collection')
    url = base_url + '/RESTapi/collections/' + str(collection_id)
    headers = {
        'Accept': 'application/json',
        'rest-dspace-token': token
    }
    try:
        response = requests.put(url, headers=headers, json=updated_collection)
    except:
        logging.debug('Unable to PUT DSpace Collection')
        exit()
    
def update_digital_object(resource, base_url, token):
    logging.info('Updating ArchivesSpace Digital Object with updated title')
    instance = resource.get('instances')[0]
    digital_object = instance.get('digital_object')
    digital_object_ref = digital_object.get('ref')
    
    logging.info('GETting ArchivesSpace Digital Object')
    url = base_url + digital_object_ref
    headers={'X-ArchivesSpace-Session': token}
    try:
        response = requests.get(url, headers=headers)
    except:
        logging.debug('Unable to GET ArchivesSpace Digital Object')
        exit()
 
    digital_object = response.json()
    
    logging.info('Updating ArchivesSpace Digital Object')
    digital_object['title'] = resource.get('title')
    
    logging.info('POSTting ArchivesSpace Digital Object')
    try:
        response = requests.post(url, headers=headers, json=digital_object)
    except:
        logging.debug('Unable to POST ArchivesSpace Digital Object')
        exit()
        
def create_archivematica_storage_service_location(archivematica_storage_service_url, archivematica_storage_service_username, archivematica_storage_service_password, archivematica_storage_service_space, dspace_base_url,  dspace_collection_handle, archivesspace_resource_title):
    logging.info('Adding Archivematica Storage Service Location')
    driver = webdriver.Firefox()
    
    # archivematica storage service authentication
    driver.get(archivematica_storage_service_url)
    assert 'Archivematica Storage Service' in driver.title
    username = driver.find_element_by_id('id_username')
    username.clear()
    username.send_keys(archivematica_storage_service_username)
    password = driver.find_element_by_id('id_password')
    password.clear()
    password.send_keys(archivematica_storage_service_password)
    form = driver.find_element_by_xpath('//form')
    form.submit()
    
    # create archivematica storage service location
    driver.get(archivematica_storage_service_url + '/spaces/' + archivematica_storage_service_space + '/location_create/')
    assert 'Archivematica Storage Service' in driver.title
    purpose = driver.find_element_by_id('id_purpose')
    for option in purpose.find_elements_by_tag_name('option'):
        if option.text == 'AIP Storage':
            option.click()
    relative_path = driver.find_element_by_id('id_relative_path')
    relative_path.clear()
    relative_path.send_keys(dspace_base_url + '/swordv2/collection/' + dspace_collection_handle)
    description = driver.find_element_by_id('id_description')
    description.clear()
    description.send_keys(archivesspace_resource_title)
    form = driver.find_element_by_xpath('//form')
    form.submit()
    
    driver.close()
        
def notify_processor(uniqname, resource, collection_handle):
    logging.info('Notifying Processor')
    slack_client = SlackClient(config['slack']['token'])
    channels_call = slack_client.api_call("channels.list")
    users_call = slack_client.api_call("users.list")
    if users_call.get("ok"):
        members = users_call["members"]
    member_id = [member["id"] for member in members if member["name"] == uniqname][0]
    slack_client.api_call(
        "chat.postMessage",
        channel = "C2B25BKTM",
        text = "Hey <@" + member_id + ">, the *" + resource.get("title") + "* Collection has been added to DeepBlue: https://dev.deepblue.lib.umich.edu/handle/" + collection_handle + "\nDeposit away! :partyparrot:",
        username = "ArchivesSpace-Archivematica-DSpace bot",
        icon_emoji = ':robot_face:',
    )

if args.function == 'create':
    resource_id = parse_resource_id(args.resource)
    resource = get_resource(config['archivesspace']['base_url'], resource_id, archivesspace_token)
    instance_check(resource)
    collection = create_collection(resource)
    collection_handle = post_collection(config['dspace']['base_url'], config['dspace']['community_id'], dspace_token, collection)
    update_introductory_text(config['dspace']['base_url'], collection_handle, dspace_token)
    digital_object_ref = create_digital_object(collection_handle, config['archivesspace']['base_url'], archivesspace_token)
    link_digital_object(config['archivesspace']['base_url'], resource_id, archivesspace_token, digital_object_ref)
    if args.space:
        create_archivematica_storage_service_location(config['archivematica_storage_service']['url'], config['archivematica_storage_service']['username'], config['archivematica_storage_service']['password'], args.space, config['dspace']['base_url'], collection_handle, resource['title'])
    if args.uniqname:
        notify_processor(args.uniqname, resource, collection_handle)
    logging.info(collection_handle + ' created.')
    
elif args.function == 'update':
    resource_id = parse_resource_id(args.resource)
    resource = get_resource(config['archivesspace']['base_url'], resource_id, archivesspace_token)
    updated_collection = create_collection(resource)
    collection_handle = get_collection(resource, config['archivesspace']['base_url'], archivesspace_token)
    put_collection(config['dspace']['base_url'], collection_handle, dspace_token, updated_collection)
    update_digital_object(resource, config['archivesspace']['base_url'], archivesspace_token)
    logging.info(collection_handle + ' updated.')
