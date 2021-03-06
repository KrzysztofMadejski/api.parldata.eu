""" Person
	A real person, alive or dead
	JSON schema: http://www.popoloproject.com/schemas/person.json#
"""

from . import identifier
from . import link
from . import other_name
from . import contact_detail
from . import change

resource = {
	'schema': {
		'id': {
			# The person's unique identifier
			'type': 'string',
			'empty': False,
			'unique': True,
		},
		'name': {
			# A person's preferred full name
			'type': 'string',
			'nullable': True,
		},
		'other_names': {
			# Alternate or former names
			'type': 'list',
			'schema': {
				'type': 'dict',
				'schema': other_name.schema,
			},
			'unique_elements': True,
		},
		'identifiers': {
			# Issued identifiers
			'type': 'list',
			'schema': {
				'type': 'dict',
				'schema': identifier.schema,
			},
			'disjoint': True,
			'unique_elements': True,
		},
		'family_name': {
			# One or more family names
			'type': 'string',
			'nullable': True,
		},
		'given_name': {
			# One or more primary given names
			'type': 'string',
			'nullable': True,
		},
		'additional_name': {
			# One or more secondary given names
			'type': 'string',
			'nullable': True,
		},
		'honorific_prefix': {
			# One or more honorifics preceding a person's name
			'type': 'string',
			'nullable': True,
		},
		'honorific_suffix': {
			# One or more honorifics following a person's name
			'type': 'string',
			'nullable': True,
		},
		'patronymic_name': {
			# One or more patronymic names
			'type': 'string',
			'nullable': True,
		},
		'sort_name': {
			# A name to use in an lexicographically ordered list
			'type': 'string',
			'nullable': True,
		},
		'email': {
			# A preferred email address
			'type': 'string',
			'format': 'email',
			'nullable': True,
		},
		'gender': {
			# A gender
			'type': 'string',
			'nullable': True,
			'allowed': ['male', 'female', 'other']
		},
		'birth_date': {
			# A date of birth
			'type': 'string',
			'format': 'partialdate',
			'nullable': True,
		},
		'death_date': {
			# A date of death
			'type': 'string',
			'format': 'partialdate',
			'nullable': True,
		},
		'image': {
			# A URL of a head shot
			'type': 'string',
			'format': 'url',
			'nullable': True,
		},
		'summary': {
			# A one-line account of a person's life
			'type': 'string',
			'nullable': True,
		},
		'national_identity': {
			# A national identity
			'type': 'string',
			'nullable': True,
		},
		'biography': {
			# An extended account of a person's life
			'type': 'string',
			'nullable': True,
		},
		'contact_details': {
			# Means of contacting the person
			'type': 'list',
			'schema': {
				'type': 'dict',
				'schema': contact_detail.schema,
			},
			'unique_elements': True,
		},
		'links': {
			# URLs to documents about the person
			'type': 'list',
			'schema': {
				'type': 'dict',
				'schema': link.schema,
			},
			'unique_elements': True,
		},
		# 'created_at' is added automatically by Eve framework
		# 'updated_at' is added automatically by Eve framework
		'sources': {
			# URLs to documents from which the person is derived
			'type': 'list',
			'schema': {
				'type': 'dict',
				'schema': link.schema,
			},
			'unique_elements': True,
		},
		'changes': {
			# List of property value changes
			# Managed automatically by callbacks when any of tracked properties change_schema value
			'type': 'list',
			'schema': {
				'type': 'dict',
				'schema': change.schema,
			},
		},
	},
	'track_changes': ('name', 'family_name', 'given_name', 'additional_name',
		'honorific_prefix', 'honorific_suffix', 'patronymic_name', 'email',
		'gender', 'image', 'national_identity', 'contact_details'),
	'save_files': ('image', ),
	'relations': {
		'memberships': {
			# The relationships to which the person is a party
			'field': 'id',
			'resource': 'memberships',
			'fkey': 'person_id'
		},
		'motions': {
			# The person's motions
			'field': 'id',
			'resource': 'motions',
			'fkey': 'creator_id'
		},
		'speeches': {
			# The person's speeches
			'field': 'id',
			'resource': 'speeches',
			'fkey': 'creator_id'
		},
		'votes': {
			# Votes cast by the person
			'field': 'id',
			'resource': 'votes',
			'fkey': 'voter_id'
		},
	},
}
