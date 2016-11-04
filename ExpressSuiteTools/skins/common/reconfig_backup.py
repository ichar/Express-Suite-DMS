## Script (Python) "reconfig_backup"
##title=Configure pack and backup options
##parameters=
##
# $Id: reconfig_backup.py,v 1.2 2003/04/14 07:08:20 Exp $
REQUEST = context.REQUEST
result = context.portal_properties.editProperties(REQUEST) or 'CMF+Settings+changed.'
return REQUEST.RESPONSE.redirect(context.portal_url() + '/backup_config_form?portal_status_message='+result)