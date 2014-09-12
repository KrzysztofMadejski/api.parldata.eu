#!/usr/bin/env python3

"""The API implementation.
This file contains callbacks extending the basic REST functionality,
validations and authorization implementation.
"""

import re
from datetime import datetime, date, timedelta
import os
import os.path
import glob
import shutil
import json

import requests
from eve import Eve
from eve.io.mongo import Validator
from eve.auth import BasicAuth
from eve.utils import config
from flask import request, current_app

import settings


def post_all_methods_callback(resource, request, payload):
	"""This method is called before sending a response to any method.
	It renames all `_id` fields in the response payload to `id`.
	"""
	data = payload.get_data()
	if 'application/xml' in request.headers.get('Accept'):
		data = data.replace(b'<_id>', b'<id>')
		data = data.replace(b'<_id ', b'<id ')
		data = data.replace(b'</_id>', b'</id>')
	else:
		data = data.replace(b'"_id"', b'"id"')
	payload.set_data(data)


def on_fetched_item_callback(resource, response):
	"""Embeds related items requested in the `embed` URL query
	parameter into the fetched document. Allows multilevel embedding
	(limited to 3 levels). Nested embedded relations are separated by
	dot. Example:

	.../organizations/1234567890?embed=["parent", "memberships.person"]

	We cannot use Eve's built-in embedded resource serialization
	because	it handles only entities directly referenced by a field in
	the document and replaces that field. However, we need to embed
	reverse relations too, e.g. `memberships` in the organization
	entity lists all memberships referencing the organization.

	Furthermore, unlike the Eve built-in embedding Popolo requires that
	referenced items are embedded as a field with different name from
	the referencing one (e.g. `organization` vs. `organization_id`) and
	allows multilevel embedding.
	"""
	if 'embed' not in request.args: return
	embed = json.loads(request.args['embed'])
	for path in embed:
		_embed_relation(resource, path, response, [(resource, response['_id'])])


def on_fetched_resource_callback(resource, response):
	"""Embeds related items requested in the `embed` URL query
	parameter into all fetched documents.
	See `on_fetched_item_callback` for more. Example:

	.../organizations?where={...}&embed=["memberships.person"]
	"""
	if 'embed' not in request.args: return
	for item in response['_items']:
		on_fetched_item_callback(resource, item)


def _embed_relation(resource, path, document, ancestors):
	"""Embeds entities of a given (eventually multilevel) relation into
	the document.

	:param resource: resource of the document
	:param path: dot separated chain of relation names
	:param document: document to embed into
	:param ancestors: list of entities on the current 'path' of embedding

	List in the `ancestors` parameter containing tuples of resource
	name and entity id is used to prevent embedding of an entity into
	itself and to limit the depth of nested embedding.
	"""
	# Extract the topmost relation from the chain of relations and check
	# if there is a reference to a related entity in the actual document
	rel_name, _, tail = path.partition('.')
	relation = config.DOMAIN[resource]['relations'].get(rel_name)
	if not relation or relation['field'] not in document: return

	# Embed unless the entity is already embedded
	if rel_name not in document:
		# Retrieve the related entities
		related_resource = current_app.data.driver.db[relation['resource']]
		results = related_resource.find({relation['fkey']: document[relation['field']]})
		entities = []
		for result in results:
			# Prevent embedding of an entity into itself
			if (relation['resource'], result['_id']) in ancestors:
				continue
			# Omit xxx_id property in embedded entity - it is redundant with _id it references
			if relation['fkey'] != '_id':
				result.pop(relation['fkey'])
			entities.append(result)
		if entities:
			# Either entity or list of entities will be embedded depending on singular or plural of relation name
			if rel_name.endswith('s'):
				document[rel_name] = entities
			else:
				document[rel_name] = entities[0]
			# Omit xxx_id property in embedding entity - it is redundant with _id it references
			if relation['field'] != '_id':
				document.pop(relation['field'])

	# Recursively resolve deeper levels of embedding (limited to 3 levels)
	if tail and rel_name in document and len(ancestors) < 3:
		entities = document[rel_name]
		if not isinstance(entities, list):
			entities = [entities]
		for subdoc in entities:
			ancestors.append((relation['resource'], subdoc['_id']))
			_embed_relation(relation['resource'], tail, subdoc, ancestors)
			ancestors.pop()


def on_update_callback(resource, updates, original):
	"""Adds all changes in updated tracked properties to the list in
	`changed` property of the resource.
	"""
	for field in config.DOMAIN[resource].get('save_files', []):
		_relocate_url_field(resource, field, updates, original)

	effective_date = request.args.get('effective_date') or date.today().isoformat()
	if effective_date == 'fix': return

	changes = []
	for field in config.DOMAIN[resource].get('track_changes', []):
		if field in updates and updates[field] != original.get(field):
			change = _build_change(field, original, effective_date)
			changes.append(change)

	if changes or 'changes' in updates:
		updates['changes'] = changes + updates.get('changes', []) + original.get('changes', [])


def on_replace_callback(resource, document, original):
	"""Adds all changes in all tracked properties to the list in
	`changed` property of the resource.
	"""
	for field in config.DOMAIN[resource].get('save_files', []):
		_relocate_url_field(resource, field, document, original)

	effective_date = request.args.get('effective_date') or date.today().isoformat()
	if effective_date == 'fix': return

	changes = []
	for field in config.DOMAIN[resource].get('track_changes', []):
		if document.get(field) != original.get(field):
			change = _build_change(field, original, effective_date)
			changes.append(change)

	if changes or 'changes' in document or 'changes' in original:
		document['changes'] = changes + document.get('changes', []) + original.get('changes', [])


def _relocate_url_field(resource, field, document, original):
	"""Translates remote URL in the given field of the document to a
	corresponding locally hosted file. Also if the field is newly added
	or the remote file has changed, download it and store as a new
	file.

	Returns boolean whether the field value was actually changed.

	Implementation for `image` field in Slovak parliament (sk/nrsr) is
	specific.	Due to padded files it is impossible to detect changed
	file by its changed length so the files are compared by content.
	"""
	if field not in document: return False

	# Get info about the URL target file.
	remote_url = document[field]
	if config.URL_PREFIX == 'sk/nrsr' and field == 'image':
		resp = requests.get(remote_url)
	else:
		resp = requests.head(remote_url)
	resp.raise_for_status()
	content_type = resp.headers['content-type']
	ext = content_type[content_type.find('/')+1:]

	# If the field is newly added or the remote file has changed, it must be downloaded.
	pathfile = (config.FILES_DIR + '/' + config.URL_PREFIX + '/' +
		resource + '/' + str(original['_id']) + '/' + field)
	if not original.get(field):
		create_file = pathfile + '.' + ext
	else:
		create_file = None
		existing_file = original[field].replace(config.FILES_SERVER, config.FILES_DIR)
		if not os.path.isfile(existing_file) or \
				int(resp.headers['content-length']) != os.path.getsize(existing_file):
			n = len(glob.glob(pathfile + '.*'))
			create_file = pathfile + '.' + str(n+1) + '.' + ext

		if config.URL_PREFIX == 'sk/nrsr' and field == 'image':
			with open(existing_file, 'rb') as f:
				existing_content = f.read()
			if resp.content != existing_content:
				n = len(glob.glob(pathfile + '.*'))
				create_file = pathfile + '.' + str(n+1) + '.' + ext

	# Download and store the remote file.
	if create_file:
		if not (config.URL_PREFIX == 'sk/nrsr' and field == 'image'):
			resp = requests.get(remote_url)
			resp.raise_for_status()
		os.makedirs(os.path.dirname(create_file), exist_ok=True)
		with open(create_file, 'wb') as f:
			f.write(resp.content)

	# Modify the field in the document to the local file.
	if create_file:
		document[field] = create_file.replace(config.FILES_DIR, config.FILES_SERVER, 1)
		return True
	else:
		document[field] = original[field]
		return False


def _build_change(field, original, effective_date):
	"""Creates a change holding original value of the field to include
	into the list of changes.
	"""
	change = {
		'property': field,
		'value': original.get(field),
		'end_date': _datestring_add(effective_date, -1),
	}
	# If there are older values of this property already present in `changes`,
	# then validity of the current value will start immediately after the most
	# recent one.
	former_end_dates = [ch['end_date']
		for ch in original.get('changes', [])
		if ch['property'] == field]
	if former_end_dates:
		change['start_date'] = _datestring_add(max(former_end_dates), 1)

	return change


def _datestring_add(datestring, days):
	"""Returns the date specified as string in ISO format with given
	number of days added.
	"""
	return (datetime.strptime(datestring, '%Y-%m-%d') + timedelta(days=days)).date().isoformat()


def on_inserted_callback(resource, documents):
	"""Downloads and stores remote files referenced by document fields
	and modifies values of those fields to URL of the local copy.
	"""
	for document in documents:
		relocated = False
		for field in config.DOMAIN[resource].get('save_files', []):
			relocated |= _relocate_url_field(resource, field, document, {'_id': document['_id']})
		if relocated:
			current_app.data.replace(resource, document['_id'], document)


def on_delete_item_callback(resource, document):
	"""Deletes downloaded and stored files related to the entity
	about to be deleted.
	"""
	path = (config.FILES_DIR + '/' + config.URL_PREFIX + '/' +
		resource + '/' + str(document['_id']))
	shutil.rmtree(path, ignore_errors=True)


def on_delete_resource_callback(resource):
	"""Deletes all downloaded and stored files related to the resource.
	"""
	path = (config.FILES_DIR + '/' + config.URL_PREFIX + '/' + resource)
	shutil.rmtree(path, ignore_errors=True)


class VpapiValidator(Validator):
	"""Additional validations in the schema.
	"""
	def _validate_format(self, format, field, value):
		"""Validates custom rule `format`.

		No validation is performed for URLs because virtually
		everything is a valid URL according to RFC 3986.
		"""
		if format not in ['partialdate', 'email', 'url']:
			self._error(field, 'Unknown format "{0}"'.format(format))

		if format == 'partialdate' and not re.match(r'^[0-9]{4}(-[0-9]{2}){0,2}$', value) or \
				format == 'email' and not re.match(r'[^@]+@[^@]+\.[^@]+', value):
			self._error(field, "Value '{0}' does not satisfy format '{1}'".format(value, format))

	def _validate_disjoint(self, disjoint, field, value):
		"""Validates custom rule `disjoint` that is similar to the
		`unique` rule, but instead of comparing values as a whole it
		checks for no common element in the lists.

		Applicable only to fields with type `list`.
		"""
		if not isinstance(value, list):
			self._error(field, '`disjoint` rule allowed only for `list` fields')
		if disjoint:
			query = {}
			if self._id:
				try:
					query[config.ID_FIELD] = {'$ne': ObjectId(self._id)}
				except:
					query[config.ID_FIELD] = {'$ne': self._id}
			for element in value:
				if isinstance(element, dict):
					query[field] = {'$elemMatch': element}
				else:
					query[field] = element
				if current_app.data.find_one(self.resource, None, **query):
					self._error(field,
						'value `%s` for field `%s` contains a common element with an existing value' %
						(value, field))
					break

	def _validate_unique_elements(self, unique_elements, field, value):
		"""Validates custom rule `unique_elements` that checks all
		values are unique within the list.

		Applicable only to fields with type `list`.
		"""
		if not isinstance(value, list):
			self._error(field, '`unique_elements` rule allowed only for `list` fields')
		if unique_elements:
			if self._id:
				try:
					query = {config.ID_FIELD: ObjectId(self._id)}
				except:
					query = {config.ID_FIELD: self._id}
				value_in_db = current_app.data.find_one(self.resource, None, **query)
				if 'field' in value_in_db:
					value.extend(value_in_db['field'])
			if value:
				if isinstance(value[0], dict):
					uniqified = set(frozenset(element.items()) for element in value)
				else:
					uniqified = set(frozenset(element) for element in value)
				if len(uniqified) < len(value):
					self._error(field,
						'elements within the list `%s` are not unique' %
						(value))


class VpapiBasicAuth(BasicAuth):
	"""Authentication used for write access to the API."""
	def check_auth(self, username, password, allowed_roles, resource, method):
		return [username, password] in config.AUTHORIZED_USERS


def create_app(parliament, conf):
	# Merge parliament specific settings on top of common settings.
	instance_settings = settings.common
	instance_settings.update({
		'URL_PREFIX': parliament,
		'MONGO_DBNAME': parliament.replace('/', '-'),
		'AUTHORIZED_USERS': conf['authorized_users'],
	})

	app = Eve(
		settings=instance_settings,
		validator=VpapiValidator,
		auth=VpapiBasicAuth
	)

	# Responses of all methods will be adjusted (_id fields renamed to id).
	app.on_post_GET += post_all_methods_callback
	app.on_post_POST += post_all_methods_callback
	app.on_post_PUT += post_all_methods_callback
	app.on_post_PATCH += post_all_methods_callback
	app.on_post_DELETE += post_all_methods_callback

	# Embedding of related entities
	app.on_fetched_item += on_fetched_item_callback
	app.on_fetched_resource += on_fetched_resource_callback

	# Tracking of changed values on update and replace.
	app.on_update += on_update_callback
	app.on_replace += on_replace_callback

	# Mirroring of referenced files after entity creation.
	app.on_inserted += on_inserted_callback

	# Removing of mirrored files related to deleted entities.
	app.on_delete_item += on_delete_item_callback
	app.on_delete_resource += on_delete_resource_callback

	return app


# If executed directly by built-in application server, use example parliament xx/example.
if __name__ == '__main__':
	app = create_app('xx/example', {'authorized_users': [['scraper', 'secret']]})
	app.run()
