## Script (Python) "toggle_view"
##bind container=container
##bind context=context
##bind namespace=
##bind script=script
##bind subpath=traverse_subpath
##parameters=view_as_list, REQUEST
##
REQUEST=context.REQUEST

action_url = context.meta_type == 'Discussion Item' and context.absolute_url() \
             or context.absolute_url() + '/document_comments'

expires = view_as_list and 'Wed, 19 Feb 1980 14:28:00 GMT' or 'Wed, 19 Feb 2020 14:28:00 GMT'

REQUEST['RESPONSE'].setCookie('view_as_list', '1', path='/', expires=expires)
REQUEST['RESPONSE'].redirect(action_url)
