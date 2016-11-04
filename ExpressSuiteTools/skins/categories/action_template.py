## Script (Python) "action_template"
##parameters=
##title=
##

REQUEST = context.REQUEST

category_id = context.getId()
action = REQUEST['action']

template_id = context.taskTemplateContainerAdapter.makeActionByRequest( category_id, action, REQUEST )

REQUEST['RESPONSE'].redirect( context.absolute_url( action='task_template_edit',
                                                    params={'template_id': template_id}
                                                  ))

