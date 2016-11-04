## Script (Python) "filter"
##bind container=container
##bind context=context
##bind namespace=
##bind script=script
##bind subpath=traverse_subpath
##parameters=filter_ver='', obj_id, REQUEST
##
from Products.ExpressSuiteTools.SecureImports import parseDate, parseTime

REQUEST=context.REQUEST

action_url = context.meta_type == 'Discussion Item' and context.absolute_url() \
             or context.absolute_url() + '/document_comments'

if REQUEST.has_key('filter_date'):
    REQUEST['RESPONSE'].setCookie('discussions_filter', parseDate('filter_date', REQUEST), path='/', expires='Wed, 19 Feb 2020 14:28:00 GMT')
    REQUEST['RESPONSE'].setCookie('discussions_filter_ver', '', path='/', expires='Wed, 19 Feb 1980 14:28:00 GMT')
elif filter_ver:
    REQUEST['RESPONSE'].setCookie('discussions_filter', '', path='/', expires='Wed, 19 Feb 1980 14:28:00 GMT')
    REQUEST['RESPONSE'].setCookie('discussions_filter_ver', filter_ver, path='/', expires='Wed, 19 Feb 2020 14:28:00 GMT')

REQUEST['RESPONSE'].redirect(action_url)
