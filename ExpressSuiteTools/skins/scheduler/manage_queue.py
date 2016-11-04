## Script (Python) "manage_queue"
##parameters=
##title=
##
REQUEST = context.REQUEST
context.portal_scheduler.manage_queue( REQUEST )

REQUEST['RESPONSE'].redirect( context.absolute_url( action='manage_queue_form' ))

