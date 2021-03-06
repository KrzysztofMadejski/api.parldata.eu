""" Count
	The number of votes for an option in a vote event
	JSON schema: http://www.popoloproject.com/schemas/count.json#
"""

schema = {
	'option': {
		# An option in a vote event
		'type': 'string',
		'required': True,
		'allowed': ['yes', 'no', 'abstain', 'absent', 'not voting', 'paired']
	},
	'value': {
		# The number of votes for an option
		'type': 'integer',
		'required': True,
	},
	'group_id': {
		# The ID of a group of voters
		'type': 'string',
		'nullable': True,
	},
	'group': {
		# A group of voters
		'nullable': True,
	},
}
