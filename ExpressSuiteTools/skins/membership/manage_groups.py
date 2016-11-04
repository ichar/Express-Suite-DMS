## Script (Python) "manage_groups"
##bind container=container
##bind context=context
##bind namespace=
##bind script=script
##bind subpath=traverse_subpath
##parameters=
##title=
##
REQUEST = context.REQUEST
if REQUEST.get('addGroup', None) and not REQUEST.get('group', None):
    REQUEST['RESPONSE'].redirect( context.absolute_url() + '/manage_groups_form')
else:
    context.portal_membership.manage_groups(REQUEST)
