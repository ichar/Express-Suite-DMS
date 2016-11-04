## Script (Python) "manage_schedule"
##parameters=
##title=
##
REQUEST = context.REQUEST
context.portal_scheduler.manage_schedule( REQUEST )

REQUEST['RESPONSE'].redirect( context.absolute_url( action='manage_schedule_form' ))

