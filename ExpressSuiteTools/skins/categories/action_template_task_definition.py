## Script (Python) "action_template_task_definition"
##parameters=
##title=
##

from Products.ExpressSuiteTools.SecureImports import DuplicateIdError

REQUEST=context.REQUEST

category_id = context.getId()
template_id = REQUEST['template_id']
action = REQUEST['action']

if REQUEST.get('task_definition_type', '').startswith('routing') and template_id[:5] != 'move_':
    template_id = 'move_' + template_id
    REQUEST.set('template_id', template_id)

id_task_definition = ''

try:
    id_task_definition = context.taskTemplateContainerAdapter.makeTaskDefinitionActionByRequest( category_id, action, REQUEST )
except DuplicateIdError, error:
    return apply( context.task_template_list, (context, REQUEST),
                  script.values( use_default_values=1, portal_status_message=str(error) ) )


if id_task_definition != '':
    REQUEST.RESPONSE.redirect( context.absolute_url( action='task_template_task_definition_info',
                                               params={ 'template_id': template_id,
                                                        'id_task_definition': id_task_definition
                                                      }
                                             ))
else:
    REQUEST.RESPONSE.redirect( context.absolute_url(action='task_template_list')  )


