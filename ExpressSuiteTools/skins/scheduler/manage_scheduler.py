## Script (Python) "manage_scheduler"
##parameters=
##title=
##
REQUEST = context.REQUEST
context.portal_scheduler.manage_scheduler( REQUEST )

REQUEST['RESPONSE'].redirect( context.absolute_url( action='manage_scheduler_form' ))

